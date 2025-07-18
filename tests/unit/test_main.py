from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner, Result

from charmed_analytics_ci.main import main


@pytest.fixture
def runner() -> CliRunner:
    """Provides a Click CLI runner for invoking CLI commands."""
    return CliRunner()


@mock.patch("charmed_analytics_ci.main.integrate_rock_into_consumers")
def test_cli_success_basic(
    mock_integrate: mock.MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    """
    Test CLI succeeds when all arguments are provided and the GitHub token is passed explicitly.
    """
    metadata_file = tmp_path / "metadata.yaml"
    metadata_file.write_text("fake: content")

    result: Result = runner.invoke(
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
    assert args["triggering_pr"] is None


@mock.patch("charmed_analytics_ci.main.integrate_rock_into_consumers")
def test_cli_passes_triggering_pr(
    mock_integrate: mock.MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    """
    Test CLI correctly passes the triggering PR URL when provided.
    """
    metadata_file = tmp_path / "metadata.yaml"
    metadata_file.write_text("fake: content")
    pr_url = "https://github.com/canonical/foo/pull/123"

    result: Result = runner.invoke(
        main,
        [
            "integrate-rock",
            str(metadata_file),
            "main",
            "ghcr.io/example/my-rock:2.3.4",
            "--github-token",
            "test-token",
            "--triggering-pr",
            pr_url,
        ],
    )

    assert result.exit_code == 0
    args = mock_integrate.call_args.kwargs
    assert args["triggering_pr"] == pr_url


@mock.patch("charmed_analytics_ci.main.integrate_rock_into_consumers")
def test_cli_uses_env_token_if_not_provided(
    mock_integrate: mock.MagicMock,
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Test CLI falls back to GH_TOKEN environment variable when no token is provided via CLI.
    """
    monkeypatch.setenv("GH_TOKEN", "env-token-456")
    metadata_file = tmp_path / "metadata.yaml"
    metadata_file.write_text("fake: content")

    result: Result = runner.invoke(
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
    assert args["triggering_pr"] is None


def test_cli_fails_without_token(
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Test CLI exits with error if no GitHub token is provided or available in environment.
    """
    monkeypatch.delenv("GH_TOKEN", raising=False)
    metadata_file = tmp_path / "metadata.yaml"
    metadata_file.write_text("fake: content")

    with caplog.at_level("ERROR"):
        result: Result = runner.invoke(
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
