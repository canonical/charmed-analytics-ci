from pathlib import Path
from unittest import mock

import pytest

from charmed_analytics_ci.rock_metadata_handler import integrate_rock_into_consumers


@pytest.fixture
def metadata_file(tmp_path: Path) -> Path:
    """
    Create a temporary fake rock-ci-metadata.yaml file for testing.
    """
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
def test_skips_pr_if_missing_files(
    mock_validate_metadata,
    mock_apply_integration,
    mock_create_git_client,
    mock_load_template,
    metadata_file: Path,
    tmp_path: Path,
) -> None:
    """
    Test that PR is skipped if integration has only missing files (no changes).
    """
    # Setup integration metadata
    mock_validate_metadata.return_value = {
        "integrations": [
            {
                "consumer-repository": "https://github.com/example/repo.git",
                "replace-image": [{"file": "a.yaml", "path": "spec.image"}],
                "service-spec": [{"file": "b.yaml", "user": {"path": "u", "value": "v"}}],
            }
        ]
    }

    # Simulate no updates, but some files missing
    mock_apply_integration.return_value = mock.Mock(
        updated_files=[],
        missing_files=[Path("a.yaml")],
        path_errors=[],
    )

    mock_client = mock.Mock(repo=mock.Mock(working_dir=str(tmp_path)))
    mock_create_git_client.return_value = mock_client
    mock_load_template.return_value = mock.Mock(render=mock.Mock(return_value="fake-body"))

    # Execute handler
    integrate_rock_into_consumers(
        metadata_path=metadata_file,
        rock_image="rock/image:1.0.0",
        clone_base_dir=tmp_path,
        github_token="ghp_secret",
        github_username="ci-bot",
        base_branch="main",
    )

    # Ensure no PR was opened
    mock_client.commit_and_push.assert_not_called()
    mock_client.open_pull_request.assert_not_called()


@mock.patch("charmed_analytics_ci.rock_metadata_handler._load_pr_template")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.create_git_client_from_url")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.apply_integration")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.validate_metadata_file")
def test_creates_pr_when_files_updated(
    mock_validate_metadata,
    mock_apply_integration,
    mock_create_git_client,
    mock_load_template,
    metadata_file: Path,
    tmp_path: Path,
) -> None:
    """
    Test that PR is created when some files are successfully updated.
    """
    mock_validate_metadata.return_value = {
        "integrations": [
            {
                "consumer-repository": "https://github.com/example/repo.git",
                "replace-image": [{"file": "file.yaml", "path": "spec.image"}],
                "service-spec": [],
            }
        ]
    }

    mock_apply_integration.return_value = mock.Mock(
        updated_files=[Path("file.yaml")],
        missing_files=[],
        path_errors=[],
    )

    mock_client = mock.Mock(repo=mock.Mock(working_dir=str(tmp_path)))
    mock_create_git_client.return_value = mock_client
    mock_load_template.return_value = mock.Mock(render=mock.Mock(return_value="fake-body"))

    integrate_rock_into_consumers(
        metadata_path=metadata_file,
        rock_image="rock/image:1.0.0",
        clone_base_dir=tmp_path,
        github_token="ghp_secret",
        github_username="ci-bot",
        base_branch="main",
    )

    # Ensure PR creation was triggered
    mock_client.commit_and_push.assert_called_once()
    mock_client.open_pull_request.assert_called_once()
