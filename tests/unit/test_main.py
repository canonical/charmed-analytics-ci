from unittest import mock

import pytest
from click.testing import CliRunner

from charmed_analytics_ci.main import main


@pytest.fixture
def runner():
    return CliRunner()


@mock.patch("charmed_analytics_ci.main.integrate_rock_into_consumers")
def test_cli_success_basic(mock_integrate, runner, tmp_path):
    metadata_file = tmp_path / "metadata.yaml"
    metadata_file.write_text("fake: content")

    result = runner.invoke(
        main,
        [
            "integrate-rock",
            str(metadata_file),
            "main",
            "ghcr.io/example/my-rock:1.2.3",
            "--github-token",
            "gh-token-123",
            "--github-username",
            "cli-tester",
            "--clone-dir",
            str(tmp_path),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    mock_integrate.assert_called_once()
    args = mock_integrate.call_args.kwargs
    assert args["github_token"] == "gh-token-123"
    assert args["github_username"] == "cli-tester"
    assert args["rock_image"] == "ghcr.io/example/my-rock:1.2.3"
    assert args["dry_run"] is True


@mock.patch("charmed_analytics_ci.main.integrate_rock_into_consumers")
def test_cli_uses_env_token_if_not_provided(mock_integrate, runner, tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "env-token-456")
    metadata_file = tmp_path / "metadata.yaml"
    metadata_file.write_text("fake: content")

    result = runner.invoke(
        main,
        [
            "integrate-rock",
            str(metadata_file),
            "main",
            "ghcr.io/example/my-rock:2.0.0",
        ],
    )

    assert result.exit_code == 0
    args = mock_integrate.call_args.kwargs
    assert args["github_token"] == "env-token-456"
    assert args["github_username"] == "__token__"


def test_cli_fails_without_token(runner, tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    metadata_file = tmp_path / "metadata.yaml"
    metadata_file.write_text("fake: content")

    with caplog.at_level("ERROR"):
        result = runner.invoke(
            main,
            [
                "integrate-rock",
                str(metadata_file),
                "main",
                "ghcr.io/example/my-rock:failtest",
            ],
        )

    assert result.exit_code == 1
    assert any(
        "GitHub token not provided and GH_TOKEN not set." in message for message in caplog.messages
    ), f"Expected error message not found in logs: {caplog.messages}"
