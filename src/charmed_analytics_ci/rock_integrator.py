# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

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


def parse_rock_image(rock_image: str) -> tuple[str, str, str]:
    """
    Parse a rock image string into name, tag, and short name.

    Args:
        rock_image: A string like 'ghcr.io/canonical/my-rock:1.2.3'

    Returns:
        Tuple of (full_name, tag, short_name)

    Raises:
        ValueError: If the image string is not in the expected format.
    """
    if ":" not in rock_image:
        raise ValueError(f"Invalid rock image format (missing tag): '{rock_image}'")

    full_name, tag = rock_image.rsplit(":", 1)
    short_name = full_name.split("/")[-1]

    if not full_name or not tag:
        raise ValueError(f"Invalid rock image format: '{rock_image}'")

    return full_name, tag, short_name


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
class AppliedReplacement:
    """Describes a single image reference that was written to a file."""

    file: Path
    path: str
    image: str
    name: Optional[str] = None


@dataclass
class IntegrationResult:
    """Describes the result of applying one integration."""

    updated_files: List[Path]
    missing_files: List[Path]
    path_errors: List[str]
    image_updates: List[AppliedReplacement] = field(default_factory=list)


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
    rock_images: List[str],
    base_dir: Path,
    integration_index: int = 0,
) -> IntegrationResult:
    """
    Apply image and service-spec updates from rock metadata into a cloned charm repo.

    Args:
        metadata_path: Path to the validated rock-ci-metadata.yaml file.
        rock_images: One or more rock image strings (e.g., ['my-rock:1.2.3']).
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

    # Map each provided rock image to its short name (e.g. 'my-rock' -> 'ghcr.io/.../my-rock:1.0').
    images_by_name: Dict[str, str] = {}
    for image in rock_images:
        _, _, short_name = parse_rock_image(image)
        images_by_name[short_name] = image

    updated_files: List[Path] = []
    missing_files: List[Path] = []
    path_errors: List[str] = []
    image_updates: List[AppliedReplacement] = []

    # === Handle replace-image updates
    for entry in integration.replace_image:
        # Resolve which rock image should be written to this entry.
        if entry.name is not None:
            image = images_by_name.get(entry.name)
            if image is None:
                logger.info(
                    "Skipping replace-image entry '%s' in %s: no matching rock image provided",
                    entry.name,
                    entry.file,
                )
                continue
        elif len(images_by_name) == 1:
            image = next(iter(images_by_name.values()))
        else:
            path_errors.append(
                f"{base_dir / entry.file}: replace-image entry for path '{entry.path}' has no "
                f"'name' but {len(images_by_name)} rock images were provided; add a 'name' to "
                f"disambiguate which image to apply"
            )
            continue

        file_path = base_dir / entry.file
        if not file_path.exists():
            missing_files.append(file_path)
            continue

        try:
            data = _load_yaml_or_json(file_path)
            _set_jsonpath_value(data, entry.path, image)
            _dump_yaml_or_json(file_path, data)
            updated_files.append(file_path)
            image_updates.append(
                AppliedReplacement(file=entry.file, path=entry.path, image=image, name=entry.name)
            )
            logger.info(f"✅ Updated image path '{entry.path}' in {file_path} → {image}")
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
        image_updates=image_updates,
    )
