from pathlib import Path
from unittest import mock

import pytest

from charmed_analytics_ci.rock_integrator import IntegrationResult
from charmed_analytics_ci.rock_metadata_handler import integrate_rock_into_consumers


@pytest.fixture
def metadata_file(tmp_path: Path) -> Path:
    """Creates a temporary fake rock-ci-metadata.yaml file for testing."""
    content = """
integrations:
  - consumer-repository: https://github.com/example/repo.git
    replace-image:
      - file: file.yaml
        path: spec.image
    service-spec:
      - file: svc.yaml
        user:
          path: spec.user
          value: root
        command:
          path: spec.cmd
          value: run
"""
    path = tmp_path / "rock-ci-metadata.yaml"
    path.write_text(content)
    return path


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
    """Fails when missing files are not listed in service-spec."""
    mock_validate_metadata.return_value = {
        "integrations": [
            {
                "consumer-repository": "https://github.com/example/repo.git",
                "replace-image": [{"file": "missing.yaml", "path": "spec.image"}],
                "service-spec": [],
            }
        ]
    }

    missing_file = tmp_path / "missing.yaml"
    mock_apply_integration.return_value = IntegrationResult(
        updated_files=[],
        missing_files=[missing_file],
        path_errors=[],
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
    """Missing service-spec files are not treated as errors."""
    mock_validate_metadata.return_value = {
        "integrations": [
            {
                "consumer-repository": "https://github.com/example/repo.git",
                "replace-image": [{"file": "file.yaml", "path": "spec.image"}],
                "service-spec": [
                    {
                        "file": "svc.yaml",
                        "user": {"path": "spec.user", "value": "root"},
                        "command": {"path": "spec.cmd", "value": "run"},
                    }
                ],
            }
        ]
    }

    missing_file = tmp_path / "svc.yaml"
    updated_file = tmp_path / "file.yaml"

    mock_apply_integration.return_value = IntegrationResult(
        updated_files=[updated_file],
        missing_files=[missing_file],
        path_errors=[],
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
    """Fails if any path errors are returned."""
    mock_validate_metadata.return_value = {
        "integrations": [
            {
                "consumer-repository": "https://github.com/example/repo.git",
                "replace-image": [{"file": "file.yaml", "path": "spec.image"}],
            }
        ]
    }

    mock_apply_integration.return_value = IntegrationResult(
        updated_files=[],
        missing_files=[],
        path_errors=["bad path"],
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
    """Fails if no updated files were detected."""
    mock_validate_metadata.return_value = {
        "integrations": [
            {
                "consumer-repository": "https://github.com/example/repo.git",
                "replace-image": [{"file": "file.yaml", "path": "spec.image"}],
            }
        ]
    }

    mock_apply_integration.return_value = IntegrationResult(
        updated_files=[],
        missing_files=[],
        path_errors=[],
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
    """PR is created only when integration is clean and valid."""
    mock_validate_metadata.return_value = {
        "integrations": [
            {
                "consumer-repository": "https://github.com/example/repo.git",
                "replace-image": [{"file": "file.yaml", "path": "spec.image"}],
            }
        ]
    }

    updated_file = tmp_path / "file.yaml"

    mock_apply_integration.return_value = IntegrationResult(
        updated_files=[updated_file],
        missing_files=[],
        path_errors=[],
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
