# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

import yaml
from jsonpath_ng.ext import parse as parse_jsonpath
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


def _load_yaml_or_json(path: Path) -> Union[dict, list]:
    """
    Load YAML or JSON content into a Python object.

    Args:
        path: File path to a .yaml or .json file.

    Returns:
        The parsed Python object (usually a dict or list).
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
    """
    if path.suffix == ".json":
        path.write_text(json.dumps(data, indent=4) + "\n")
    else:
        with path.open("w") as f:
            _yaml.dump(data, f)


def _set_jsonpath_value(data: Union[dict, list], path_expr: str, value: str) -> None:
    """
    Set a value at the specified JSONPath within the data.

    Args:
        data: Parsed dict or list object.
        path_expr: JSONPath expression string.
        value: The value to assign.

    Raises:
        KeyError: If the path does not exist in the data.
    """
    jsonpath_expr = parse_jsonpath(path_expr)
    matches = jsonpath_expr.find(data)

    if not matches:
        raise KeyError(f"No matches found for path: {path_expr}")

    for match in matches:
        match.full_path.update(data, value)


def load_metadata_file(metadata_path: Path) -> RockCIMetadata:
    """
    Validate and parse rock-ci-metadata.yaml using Pydantic.

    Args:
        metadata_path: Path to the YAML metadata file.

    Returns:
        Parsed metadata as a RockCIMetadata object.
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
    """
    metadata = load_metadata_file(metadata_path)

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
        if not file_path.exists():
            missing_files.append(file_path)
            continue

        try:
            data = _load_yaml_or_json(file_path)
            _set_jsonpath_value(data, entry.path, rock_image)
            _dump_yaml_or_json(file_path, data)
            updated_files.append(file_path)
            logger.info(f"✅ Updated image path '{entry.path}' in {file_path}")
        except Exception as e:
            path_errors.append(f"{file_path}: {entry.path} -> {e}")

    # === Handle service-spec updates
    for entry in integration.service_spec or []:
        file_path = base_dir / entry.file
        if not file_path.exists():
            logger.warning(f"⚠️ Missing file for service-spec: {file_path}")
            missing_files.append(file_path)
            continue

        try:
            data = _load_yaml_or_json(file_path)

            if entry.user:
                _set_jsonpath_value(data, entry.user.path, entry.user.value)

            if entry.command:
                _set_jsonpath_value(data, entry.command.path, entry.command.value)

            _dump_yaml_or_json(file_path, data)
            updated_files.append(file_path)
        except Exception as e:
            path_errors.append(f"{file_path}: service-spec -> {e}")

    return IntegrationResult(
        updated_files=updated_files,
        missing_files=missing_files,
        path_errors=path_errors,
    )
