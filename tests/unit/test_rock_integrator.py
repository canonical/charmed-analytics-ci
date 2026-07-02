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
    _load_yaml_or_json,
    _set_jsonpath_value,
    apply_integration,
    load_metadata_file,
)

ROCK_IMAGE = "ghcr.io/canonical/my-rock:1.2.3"

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


def test_load_metadata_file(valid_metadata_file: Path) -> None:
    """Ensure valid metadata passes schema validation."""
    metadata = load_metadata_file(valid_metadata_file)
    assert isinstance(metadata, RockCIMetadata)
    assert metadata.integrations


def test_apply_integration_success(
    valid_metadata_file: Path, test_files: tuple[Path, Path]
) -> None:
    """Test full integration update flow."""
    base_dir = valid_metadata_file.parent

    result: IntegrationResult = apply_integration(
        metadata_path=valid_metadata_file,
        rock_images=[ROCK_IMAGE],
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
        rock_images=[ROCK_IMAGE],
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
            rock_images=[ROCK_IMAGE],
            base_dir=valid_metadata_file.parent,
            integration_index=99,
        )


# ─────────────────────────────────────────────
# Multiple rock image handling
# ─────────────────────────────────────────────


MULTI_IMAGE_METADATA = {
    "integrations": [
        {
            "consumer-repository": "https://github.com/canonical/example",
            "replace-image": [
                {"file": "a.yaml", "path": "spec.image", "name": "rock-a"},
                {"file": "b.yaml", "path": "spec.image", "name": "rock-b"},
            ],
        }
    ]
}


@pytest.fixture
def multi_image_metadata_file(temp_dir: Path) -> Path:
    """Write metadata with two named replace-image entries."""
    metadata_path = temp_dir / "rock-ci-metadata.yaml"
    metadata_path.write_text(yaml.dump(MULTI_IMAGE_METADATA))
    return metadata_path


@pytest.fixture
def multi_image_files(temp_dir: Path) -> tuple[Path, Path]:
    """Create the two target files referenced by the multi-image metadata."""
    a_yaml = temp_dir / "a.yaml"
    a_yaml.write_text(yaml.dump({"spec": {"image": "old-a"}}))
    b_yaml = temp_dir / "b.yaml"
    b_yaml.write_text(yaml.dump({"spec": {"image": "old-b"}}))
    return a_yaml, b_yaml


def test_multiple_images_matched_by_name(
    multi_image_metadata_file: Path, multi_image_files: tuple[Path, Path]
) -> None:
    """Each named entry is updated with its matching rock image."""
    base_dir = multi_image_metadata_file.parent
    image_a = "ghcr.io/canonical/rock-a:1.0.0"
    image_b = "ghcr.io/canonical/rock-b:2.0.0"

    result = apply_integration(
        metadata_path=multi_image_metadata_file,
        rock_images=[image_a, image_b],
        base_dir=base_dir,
        integration_index=0,
    )

    assert len(result.updated_files) == 2
    assert result.path_errors == []
    assert {u.image for u in result.image_updates} == {image_a, image_b}

    assert yaml.safe_load((base_dir / "a.yaml").read_text())["spec"]["image"] == image_a
    assert yaml.safe_load((base_dir / "b.yaml").read_text())["spec"]["image"] == image_b


def test_unmatched_named_entries_are_skipped(
    multi_image_metadata_file: Path, multi_image_files: tuple[Path, Path]
) -> None:
    """Only entries whose name matches a provided image are updated; others are left untouched."""
    base_dir = multi_image_metadata_file.parent
    image_a = "ghcr.io/canonical/rock-a:1.0.0"

    result = apply_integration(
        metadata_path=multi_image_metadata_file,
        rock_images=[image_a],
        base_dir=base_dir,
        integration_index=0,
    )

    assert [u.name for u in result.image_updates] == ["rock-a"]
    assert result.path_errors == []
    assert yaml.safe_load((base_dir / "a.yaml").read_text())["spec"]["image"] == image_a
    assert yaml.safe_load((base_dir / "b.yaml").read_text())["spec"]["image"] == "old-b"


def test_nameless_entry_with_multiple_images_reports_error(
    valid_metadata_file: Path, test_files: tuple[Path, Path]
) -> None:
    """A nameless entry is ambiguous when several images are provided and yields a path error."""
    base_dir = valid_metadata_file.parent

    result = apply_integration(
        metadata_path=valid_metadata_file,
        rock_images=["ghcr.io/canonical/rock-a:1.0.0", "ghcr.io/canonical/rock-b:2.0.0"],
        base_dir=base_dir,
        integration_index=0,
    )

    assert any("no 'name'" in err for err in result.path_errors)


# ─────────────────────────────────────────────
# Internal utility function tests
# ─────────────────────────────────────────────


def test_set_jsonpath_value_success() -> None:
    """Successfully set a nested value using a valid JSONPath."""
    data = {"resources": {"foo": {"bar": "OLD"}}}
    _set_jsonpath_value(data, "resources.foo.bar", "NEW")
    assert data["resources"]["foo"]["bar"] == "NEW"


def test_set_jsonpath_value_array_index() -> None:
    """Set a value using an array index via JSONPath."""
    data = {"containers": [{"image": "old"}]}
    _set_jsonpath_value(data, "containers[0].image", "new")
    assert data["containers"][0]["image"] == "new"


def test_set_jsonpath_value_invalid_path_raises() -> None:
    """Raise error when the JSONPath does not match anything."""
    data = {"foo": "bar"}
    with pytest.raises(KeyError, match="No matches found for path"):
        _set_jsonpath_value(data, "nonexistent.key", "value")


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
