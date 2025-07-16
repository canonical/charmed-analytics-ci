# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path
from unittest import mock

import pytest

from charmed_analytics_ci.rock_ci_metadata_models import (
    IntegrationEntry,
    PathValue,
    ReplaceImageEntry,
    RockCIMetadata,
    ServiceSpecEntry,
)
from charmed_analytics_ci.rock_integrator import IntegrationResult
from charmed_analytics_ci.rock_metadata_handler import integrate_rock_into_consumers


@pytest.fixture
def metadata_file(tmp_path: Path) -> Path:
    """Creates an empty rock-ci-metadata.yaml file in a temporary path."""
    path = tmp_path / "rock-ci-metadata.yaml"
    path.write_text("integrations: []")
    return path


def build_metadata(with_service_spec: bool = True) -> RockCIMetadata:
    """Helper to build RockCIMetadata with or without service-spec entries."""
    return RockCIMetadata(
        integrations=[
            IntegrationEntry(
                consumer_repository="https://github.com/example/repo.git",
                replace_image=[ReplaceImageEntry(file="file.yaml", path="spec.image")],
                service_spec=(
                    [
                        ServiceSpecEntry(
                            file="svc.yaml",
                            user=PathValue(path="spec.user", value="root"),
                            command=PathValue(path="spec.cmd", value="run"),
                        )
                    ]
                    if with_service_spec
                    else []
                ),
            )
        ]
    )


@mock.patch("charmed_analytics_ci.rock_metadata_handler._load_pr_template")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.create_git_client_from_url")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.apply_integration")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.validate_metadata_file")
def test_errors_if_missing_non_service_files(
    mock_validate_metadata,
    mock_apply_integration,
    mock_create_git_client,
    mock_load_template,
    metadata_file: Path,
    tmp_path: Path,
) -> None:
    """Fails if non-service-spec files are missing in the integration result."""
    mock_validate_metadata.return_value = build_metadata(with_service_spec=False)
    missing_file = tmp_path / "file.yaml"
    mock_apply_integration.return_value = IntegrationResult(
        updated_files=[], missing_files=[missing_file], path_errors=[]
    )
    mock_client = mock.Mock(repo=mock.Mock(working_dir=str(tmp_path)))
    mock_create_git_client.return_value = mock_client
    mock_load_template.return_value = mock.Mock(render=mock.Mock(return_value="body"))

    with pytest.raises(RuntimeError, match="missing expected files"):
        integrate_rock_into_consumers(
            metadata_path=metadata_file,
            rock_image="rock/image:1.0.0",
            clone_base_dir=tmp_path,
            github_token="token",
            github_username="bot",
            base_branch="main",
        )


@mock.patch("charmed_analytics_ci.rock_metadata_handler._load_pr_template")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.create_git_client_from_url")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.apply_integration")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.validate_metadata_file")
def test_allows_missing_service_spec_files(
    mock_validate_metadata,
    mock_apply_integration,
    mock_create_git_client,
    mock_load_template,
    metadata_file: Path,
    tmp_path: Path,
) -> None:
    """Allows service-spec files to be missing without raising an error."""
    mock_validate_metadata.return_value = build_metadata()
    missing_file = tmp_path / "svc.yaml"
    updated_file = tmp_path / "file.yaml"
    mock_apply_integration.return_value = IntegrationResult(
        updated_files=[updated_file], missing_files=[missing_file], path_errors=[]
    )
    mock_client = mock.Mock(repo=mock.Mock(working_dir=str(tmp_path)))
    mock_create_git_client.return_value = mock_client
    mock_load_template.return_value = mock.Mock(render=mock.Mock(return_value="body"))

    integrate_rock_into_consumers(
        metadata_path=metadata_file,
        rock_image="rock/image:1.0.0",
        clone_base_dir=tmp_path,
        github_token="token",
        github_username="bot",
        base_branch="main",
    )
    mock_client.commit_and_push.assert_called_once()
    mock_client.open_pull_request.assert_called_once()


@mock.patch("charmed_analytics_ci.rock_metadata_handler._load_pr_template")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.create_git_client_from_url")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.apply_integration")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.validate_metadata_file")
def test_errors_if_path_errors_present(
    mock_validate_metadata,
    mock_apply_integration,
    mock_create_git_client,
    mock_load_template,
    metadata_file: Path,
    tmp_path: Path,
) -> None:
    """Raises error when invalid path expressions are found."""
    mock_validate_metadata.return_value = build_metadata(with_service_spec=False)
    mock_apply_integration.return_value = IntegrationResult(
        updated_files=[], missing_files=[], path_errors=["bad path"]
    )
    mock_client = mock.Mock(repo=mock.Mock(working_dir=str(tmp_path)))
    mock_create_git_client.return_value = mock_client
    mock_load_template.return_value = mock.Mock(render=mock.Mock(return_value="body"))

    with pytest.raises(RuntimeError, match="invalid path expressions"):
        integrate_rock_into_consumers(
            metadata_path=metadata_file,
            rock_image="rock/image:1.0.0",
            clone_base_dir=tmp_path,
            github_token="token",
            github_username="bot",
            base_branch="main",
        )


@mock.patch("charmed_analytics_ci.rock_metadata_handler._load_pr_template")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.create_git_client_from_url")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.apply_integration")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.validate_metadata_file")
def test_errors_if_no_changes_detected(
    mock_validate_metadata,
    mock_apply_integration,
    mock_create_git_client,
    mock_load_template,
    metadata_file: Path,
    tmp_path: Path,
) -> None:
    """Raises error if integration produced no updated files."""
    mock_validate_metadata.return_value = build_metadata(with_service_spec=False)
    mock_apply_integration.return_value = IntegrationResult(
        updated_files=[], missing_files=[], path_errors=[]
    )
    mock_client = mock.Mock(repo=mock.Mock(working_dir=str(tmp_path)))
    mock_create_git_client.return_value = mock_client
    mock_load_template.return_value = mock.Mock(render=mock.Mock(return_value="body"))

    with pytest.raises(RuntimeError, match="no changes detected"):
        integrate_rock_into_consumers(
            metadata_path=metadata_file,
            rock_image="rock/image:1.0.0",
            clone_base_dir=tmp_path,
            github_token="token",
            github_username="bot",
            base_branch="main",
        )


@mock.patch("charmed_analytics_ci.rock_metadata_handler._load_pr_template")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.create_git_client_from_url")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.apply_integration")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.validate_metadata_file")
def test_creates_pr_after_successful_validation(
    mock_validate_metadata,
    mock_apply_integration,
    mock_create_git_client,
    mock_load_template,
    metadata_file: Path,
    tmp_path: Path,
) -> None:
    """Commits changes and opens a PR when integration is successful."""
    mock_validate_metadata.return_value = build_metadata(with_service_spec=False)
    updated_file = tmp_path / "file.yaml"
    mock_apply_integration.return_value = IntegrationResult(
        updated_files=[updated_file], missing_files=[], path_errors=[]
    )
    mock_client = mock.Mock(repo=mock.Mock(working_dir=str(tmp_path)))
    mock_create_git_client.return_value = mock_client
    mock_load_template.return_value = mock.Mock(render=mock.Mock(return_value="body"))

    integrate_rock_into_consumers(
        metadata_path=metadata_file,
        rock_image="rock/image:1.0.0",
        clone_base_dir=tmp_path,
        github_token="token",
        github_username="bot",
        base_branch="main",
    )
    mock_client.commit_and_push.assert_called_once()
    mock_client.open_pull_request.assert_called_once()
