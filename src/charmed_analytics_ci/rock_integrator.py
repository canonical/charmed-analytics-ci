# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Union

import yaml
from ruamel.yaml import YAML

from charmed_analytics_ci.logger import setup_logger
from charmed_analytics_ci.rock_ci_metadata_models import RockCIMetadata

logger = setup_logger(__name__)

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.indent(mapping=2, sequence=2, offset=0)
_yaml.width = 1000000  # prevent wrapping of long lines


@dataclass
class Replacement:
    """Describes a file and path where the image should be replaced."""

    file: Path
    path: str


@dataclass
class ServiceSpecEntry:
    """Describes a service-spec file modification."""

    file: Path
    user: Optional[dict] = None
    command: Optional[dict] = None


@dataclass
class IntegrationResult:
    """Describes the result of applying one integration."""

    updated_files: List[Path]
    missing_files: List[Path]
    path_errors: List[str]


def _get_from_path(data: Any, path: str) -> Any:
    """
    Retrieve a value from a nested dict/list using dot/bracket notation.

    Args:
        data: The nested data structure (dicts/lists).
        path: Path like 'spec.containers[0].image'.

    Returns:
        The value at the specified path.

    Raises:
        KeyError: If a required dict key is missing.
        IndexError: If a list index is out of bounds.
    """
    elements = re.split(r"\.(?![^\[]*\])", path)

    for el in elements:
        if "[" in el:
            key, idx = el.split("[")
            idx = int(idx.rstrip("]"))

            if key not in data or not isinstance(data[key], list):
                raise KeyError(f"Expected a list at key '{key}' in path '{path}'")
            if idx >= len(data[key]):
                raise IndexError(f"Index [{idx}] out of bounds for '{key}' in path '{path}'")
            data = data[key][idx]
        else:
            if el not in data:
                raise KeyError(f"Missing key '{el}' in path '{path}'")
            data = data[el]

    return data


def _set_in_path(data: Any, path: str, value: Any) -> None:
    """
    Set a value in a nested dict/list using dot/bracket path notation,
    but only if the full path already exists.

    Args:
        data: The dict or list to mutate.
        path: Path expression like 'spec.containers[0].image'.
        value: Value to assign at the specified path.

    Raises:
        KeyError or IndexError: If the path does not exist.
    """
    elements = re.split(r"\.(?![^\[]*\])", path)
    for i, el in enumerate(elements):
        is_last = i == len(elements) - 1
        if "[" in el:
            key, idx = el.split("[")
            idx = int(idx.rstrip("]"))
            if key not in data or not isinstance(data[key], list):
                raise KeyError(f"Key '{key}' not found or not a list in path '{path}'")
            if idx >= len(data[key]):
                raise IndexError(f"Index [{idx}] out of range for '{key}' in path '{path}'")
            if is_last:
                data[key][idx] = value
            else:
                data = data[key][idx]
        else:
            if el not in data:
                raise KeyError(f"Key '{el}' not found in path '{path}'")
            if is_last:
                data[el] = value
            else:
                data = data[el]


def _load_yaml_or_json(path: Path) -> Union[dict, list]:
    """
    Load YAML or JSON content into a Python object.

    Args:
        path: File path to a .yaml or .json file.

    Returns:
        The parsed Python object (usually a dict or list).

    Raises:
        ValueError: If the file extension is unsupported.
        FileNotFoundError: If the file doesn't exist.
    """
    if path.suffix == ".json":
        return json.loads(path.read_text())
    return _yaml.load(path)


def _dump_yaml_or_json(path: Path, data: Union[dict, list]) -> None:
    """
    Write a Python object back to a YAML or JSON file.

    Args:
        path: File path to write to (.json or .yaml).
        data: Data to write (typically dict or list).

    Raises:
        ValueError: If the file extension is unsupported.
    """
    if path.suffix == ".json":
        path.write_text(json.dumps(data, indent=4) + "\n")
    else:
        with path.open("w") as f:
            _yaml.dump(data, f)


def validate_metadata_file(metadata_path: Path) -> RockCIMetadata:
    """
    Validate and parse rock-ci-metadata.yaml using Pydantic.

    Args:
        metadata_path: Path to the YAML metadata file.

    Returns:
        Parsed metadata as a RockCIMetadata object.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        pydantic.ValidationError: If the file fails validation.
    """
    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata file not found: {metadata_path}")

    raw = yaml.safe_load(metadata_path.read_text())
    return RockCIMetadata.model_validate(raw)


def apply_integration(
    metadata_path: Path,
    rock_image: str,
    base_dir: Path,
    integration_index: int = 0,
) -> IntegrationResult:
    """
    Apply image and service-spec updates from rock metadata into a cloned charm repo.

    Args:
        metadata_path: Path to the validated rock-ci-metadata.yaml file.
        rock_image: Rock image string (e.g., my-rock:1.2.3).
        base_dir: Filesystem path to the charm repository root.
        integration_index: Index of the integration entry to apply.

    Returns:
        IntegrationResult describing updates, warnings, and errors.

    Raises:
        IndexError: If the specified integration_index is invalid.
        pydantic.ValidationError: If the metadata file is invalid.
        FileNotFoundError: If the metadata file doesn't exist.
    """
    metadata = validate_metadata_file(metadata_path)

    try:
        integration = metadata.integrations[integration_index]
    except IndexError:
        raise IndexError(f"Integration index {integration_index} not found in metadata")

    updated_files: List[Path] = []
    missing_files: List[Path] = []
    path_errors: List[str] = []

    # === Handle replace-image updates
    for entry in integration.replace_image:
        file_path = base_dir / entry.file
        path_expr = entry.path

        if not file_path.exists():
            missing_files.append(file_path)
            continue

        try:
            data = _load_yaml_or_json(file_path)
            _set_in_path(data, path_expr, rock_image)
            _dump_yaml_or_json(file_path, data)
            updated_files.append(file_path)
            logger.info(f"✅ Updated image path '{path_expr}' in {file_path}")
        except Exception as e:
            path_errors.append(f"{file_path}: {path_expr} -> {e}")

    # === Handle service-spec updates
    for entry in integration.service_spec:
        file_path = base_dir / entry.file

        if not file_path.exists():
            logger.warning(f"⚠️ Missing file for service-spec: {file_path}")
            missing_files.append(file_path)
            continue

        try:
            data = _load_yaml_or_json(file_path)

            if entry.user:
                _set_in_path(data, entry.user.path, entry.user.value)

            if entry.command:
                _set_in_path(data, entry.command.path, entry.command.value)

            _dump_yaml_or_json(file_path, data)
            updated_files.append(file_path)
        except Exception as e:
            path_errors.append(f"{file_path}: service-spec -> {e}")

    return IntegrationResult(
        updated_files=updated_files,
        missing_files=missing_files,
        path_errors=path_errors,
    )
