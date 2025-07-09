from pathlib import Path
from unittest import mock

import pytest

from charmed_analytics_ci.rock_metadata_handler import integrate_rock_into_consumers


@pytest.fixture
def fake_metadata(tmp_path: Path) -> Path:
    """Creates a fake metadata file for testing."""
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
def test_skips_pr_if_files_missing(
    mock_validate,
    mock_apply,
    mock_create_client,
    mock_template_loader,
    fake_metadata,
    tmp_path,
):
    mock_validate.return_value = {
        "integrations": [
            {
                "consumer-repository": "https://github.com/example/repo.git",
                "replace-image": [{"file": "a.yaml", "path": "spec.image"}],
                "service-spec": [{"file": "b.yaml", "user": {"path": "u", "value": "v"}}],
            }
        ]
    }
    mock_apply.return_value = mock.Mock(updated_files=[], missing_files=[Path("a.yaml")])
    mock_create_client.return_value = mock.Mock(repo=mock.Mock(working_dir=str(tmp_path)))
    mock_template_loader.return_value = mock.Mock(render=mock.Mock(return_value="body"))

    integrate_rock_into_consumers(
        metadata_path=fake_metadata,
        rock_image="rock/image:1.0.0",
        clone_base_dir=tmp_path,
        github_token="secret",
        github_username="ci-bot",
    )

    client = mock_create_client.return_value
    client.commit_and_push.assert_not_called()
    client.open_pull_request.assert_not_called()


@mock.patch("charmed_analytics_ci.rock_metadata_handler._load_pr_template")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.create_git_client_from_url")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.apply_integration")
@mock.patch("charmed_analytics_ci.rock_metadata_handler.validate_metadata_file")
def test_creates_pr_when_changes_exist(
    mock_validate,
    mock_apply,
    mock_create_client,
    mock_template_loader,
    fake_metadata,
    tmp_path,
):
    mock_validate.return_value = {
        "integrations": [
            {
                "consumer-repository": "https://github.com/example/repo.git",
                "replace-image": [{"file": "file.yaml", "path": "spec.image"}],
                "service-spec": [],
            }
        ]
    }
    mock_apply.return_value = mock.Mock(updated_files=[Path("file.yaml")], missing_files=[])
    mock_create_client.return_value = mock.Mock(repo=mock.Mock(working_dir=str(tmp_path)))
    mock_template_loader.return_value = mock.Mock(render=mock.Mock(return_value="body"))

    integrate_rock_into_consumers(
        metadata_path=fake_metadata,
        rock_image="rock/image:1.0.0",
        clone_base_dir=tmp_path,
        github_token="secret",
        github_username="ci-bot",
    )

    client = mock_create_client.return_value
    client.commit_and_push.assert_called_once()
    client.open_pull_request.assert_called_once()
