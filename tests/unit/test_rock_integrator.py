# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import shutil
import tempfile
from pathlib import Path
from typing import Generator

import pytest
import yaml

from charmed_analytics_ci.rock_ci_metadata_models import RockCIMetadata
from charmed_analytics_ci.rock_integrator import (
    IntegrationResult,
    _dump_yaml_or_json,
    _get_from_path,
    _load_yaml_or_json,
    _set_in_path,
    apply_integration,
    validate_metadata_file,
)

ROCK_IMAGE = "ghcr.io/canonical/my-rock:1.2.3"

# Sample metadata content for valid test case
VALID_METADATA = {
    "integrations": [
        {
            "consumer-repository": "https://github.com/canonical/example",
            "replace-image": [{"file": "test.yaml", "path": "containers[0].image"}],
            "service-spec": [
                {
                    "file": "service.yaml",
                    "user": {"path": "user", "value": "_daemon_"},
                    "command": {"path": "command", "value": "bash -c 'run'"},
                }
            ],
        }
    ]
}


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary working directory for file-based tests."""
    tmpdir = Path(tempfile.mkdtemp())
    yield tmpdir
    shutil.rmtree(tmpdir)


@pytest.fixture
def valid_metadata_file(temp_dir: Path) -> Path:
    """Write a valid rock-ci-metadata.yaml file and return its path."""
    metadata_path = temp_dir / "rock-ci-metadata.yaml"
    metadata_path.write_text(yaml.dump(VALID_METADATA))
    return metadata_path


@pytest.fixture
def test_files(temp_dir: Path) -> tuple[Path, Path]:
    """Create minimal YAML files to be updated."""
    test_yaml = temp_dir / "test.yaml"
    test_yaml.write_text(yaml.dump({"containers": [{"image": "old"}]}))

    service_yaml = temp_dir / "service.yaml"
    service_yaml.write_text(yaml.dump({"user": "", "command": ""}))

    return test_yaml, service_yaml


def test_validate_metadata_file(valid_metadata_file: Path) -> None:
    """Ensure valid metadata passes schema validation."""
    metadata = validate_metadata_file(valid_metadata_file)
    assert isinstance(metadata, RockCIMetadata)
    assert metadata.integrations  # Optional: validate structure


def test_apply_integration_success(
    valid_metadata_file: Path, test_files: tuple[Path, Path]
) -> None:
    """Test full integration update flow."""
    base_dir = valid_metadata_file.parent

    result: IntegrationResult = apply_integration(
        metadata_path=valid_metadata_file,
        rock_image=ROCK_IMAGE,
        base_dir=base_dir,
        integration_index=0,
    )

    assert len(result.updated_files) == 2
    assert result.missing_files == []
    assert result.path_errors == []

    yaml_data = yaml.safe_load((base_dir / "test.yaml").read_text())
    assert yaml_data["containers"][0]["image"] == ROCK_IMAGE

    service_data = yaml.safe_load((base_dir / "service.yaml").read_text())
    assert service_data["user"] == "_daemon_"
    assert service_data["command"] == "bash -c 'run'"


def test_missing_file_error(valid_metadata_file: Path, temp_dir: Path) -> None:
    """Ensure missing files are detected and reported properly."""
    result = apply_integration(
        metadata_path=valid_metadata_file,
        rock_image=ROCK_IMAGE,
        base_dir=temp_dir,
        integration_index=0,
    )
    assert result.updated_files == []
    assert len(result.missing_files) == 2
    assert result.path_errors == []


def test_invalid_integration_index(valid_metadata_file: Path) -> None:
    """Ensure an IndexError is raised for invalid integration index."""
    with pytest.raises(IndexError):
        apply_integration(
            metadata_path=valid_metadata_file,
            rock_image=ROCK_IMAGE,
            base_dir=valid_metadata_file.parent,
            integration_index=99,
        )


# ─────────────────────────────────────────────
# Internal utility function tests
# ─────────────────────────────────────────────


def test_set_in_path_nested_dict_raises_if_missing() -> None:
    """Should raise if the top-level key does not exist."""
    data = {}
    with pytest.raises(KeyError, match="Key 'a' not found in path 'a.b.c'"):
        _set_in_path(data, "a.b.c", 42)


def test_set_in_path_with_list_raises_if_path_invalid() -> None:
    """Should raise if trying to set inside a nonexistent nested structure."""
    data = {"containers": [{}]}
    with pytest.raises(
        KeyError, match="Key 'image' not found in path 'containers\\[0\\]\\.image'"
    ):
        _set_in_path(data, "containers[0].image", "nginx:latest")


def test_get_from_path_nested_dict() -> None:
    """Retrieve a value from nested dict using path."""
    data = {"a": {"b": {"c": "value"}}}
    assert _get_from_path(data, "a.b.c") == "value"


def test_get_from_path_with_list() -> None:
    """Retrieve a value from list using bracket syntax."""
    data = {"containers": [{"image": "nginx"}]}
    assert _get_from_path(data, "containers[0].image") == "nginx"


def test_dump_and_load_json(tmp_path: Path) -> None:
    """Test round-trip JSON dump/load."""
    json_file = tmp_path / "file.json"
    sample = {"foo": "bar", "nested": {"x": 1}}
    _dump_yaml_or_json(json_file, sample)

    loaded = _load_yaml_or_json(json_file)
    assert loaded == sample


def test_dump_and_load_yaml(tmp_path: Path) -> None:
    """Test round-trip YAML dump/load."""
    yaml_file = tmp_path / "file.yaml"
    sample = {"foo": "bar", "list": [1, 2, 3]}
    _dump_yaml_or_json(yaml_file, sample)

    loaded = _load_yaml_or_json(yaml_file)
    assert loaded == sample
