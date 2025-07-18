# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import shutil
import tempfile
from pathlib import Path
from typing import Generator
from unittest import mock

import pytest
from git import GitCommandError, Repo

from charmed_analytics_ci.git_client import (
    GitClient,
    GitClientError,
    GitCredentials,
    PullRequestAlreadyExistsError,
    _build_authenticated_url,
    _configure_git,
    _extract_repo_name,
    create_git_client_from_url,
)

TEST_USERNAME = "testuser"
TEST_TOKEN = "ghp_exampletoken"
TEST_URL = "https://github.com/testorg/testrepo.git"
ALT_URL = "https://github.com/otherorg/wrongrepo.git"
TEST_REPO_NAME = "testrepo"
TEST_BRANCH = "main"
FEATURE_BRANCH = "feature-branch"
COMMIT_MESSAGE = "test commit"
PR_TITLE = "Add feature"
PR_BODY = "Implements feature XYZ"


@pytest.fixture
def temp_repo_dir() -> Generator[Path, None, None]:
    """Creates and cleans up a temporary directory for repo cloning."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_repo(monkeypatch) -> mock.MagicMock:
    """Provides a mocked GitPython Repo and patches clone_from."""
    repo = mock.MagicMock(spec=Repo)
    monkeypatch.setattr("charmed_analytics_ci.git_client.Repo", mock.MagicMock(return_value=repo))
    monkeypatch.setattr(
        "charmed_analytics_ci.git_client.Repo.clone_from", mock.MagicMock(return_value=repo)
    )
    return repo


@pytest.fixture
def mock_github(monkeypatch) -> mock.MagicMock:
    """Mocks GitHub API and repo retrieval."""
    mock_gh_repo = mock.MagicMock()
    mock_github = mock.MagicMock()
    mock_github.get_repo.return_value = mock_gh_repo
    monkeypatch.setattr(
        "charmed_analytics_ci.git_client.Github", mock.MagicMock(return_value=mock_github)
    )
    return mock_gh_repo


def test_create_git_client_from_url_clones_when_missing(temp_repo_dir, mock_repo, mock_github):
    """It clones a repository if not found locally."""
    creds = GitCredentials(TEST_USERNAME, TEST_TOKEN)
    client = create_git_client_from_url(TEST_URL, creds, clone_path=temp_repo_dir)
    assert isinstance(client, GitClient)


def test_create_git_client_from_url_uses_existing_repo_if_valid(
    temp_repo_dir, mock_repo, mock_github
):
    """It reuses a valid existing repository with matching remote."""
    repo_path = temp_repo_dir / TEST_REPO_NAME
    repo_path.mkdir()
    mock_repo.remote.return_value.url = TEST_URL

    creds = GitCredentials(TEST_USERNAME, TEST_TOKEN)
    client = create_git_client_from_url(TEST_URL, creds, clone_path=temp_repo_dir)
    assert isinstance(client, GitClient)


def test_create_git_client_from_url_fails_on_wrong_remote(temp_repo_dir, mock_repo, mock_github):
    """It raises error if an existing repo points to a different remote."""
    repo_path = temp_repo_dir / TEST_REPO_NAME
    repo_path.mkdir()
    mock_repo.remote.return_value.url = ALT_URL

    creds = GitCredentials(TEST_USERNAME, TEST_TOKEN)
    with pytest.raises(GitClientError, match="points to a different remote"):
        create_git_client_from_url(TEST_URL, creds, clone_path=temp_repo_dir)


def test_create_git_client_from_url_fails_to_clone(monkeypatch, temp_repo_dir):
    """It raises GitClientError if cloning fails."""
    monkeypatch.setattr(
        "charmed_analytics_ci.git_client.Repo.clone_from",
        mock.Mock(side_effect=GitCommandError("clone", 128, stderr="fatal: repo not found")),
    )
    monkeypatch.setattr("charmed_analytics_ci.git_client.Github", mock.Mock())

    creds = GitCredentials(TEST_USERNAME, TEST_TOKEN)
    with pytest.raises(GitClientError, match="Failed to clone repository"):
        create_git_client_from_url(TEST_URL, creds, clone_path=temp_repo_dir)


def test_checkout_branch_switches_if_exists(mock_repo):
    """It switches to an existing branch without error."""
    client = GitClient(mock_repo, mock.Mock(), GitCredentials(TEST_USERNAME, TEST_TOKEN))
    client.checkout_branch(TEST_BRANCH)
    mock_repo.git.checkout.assert_called_once_with(TEST_BRANCH)


def test_checkout_branch_creates_if_missing(mock_repo, caplog):
    """It creates a new branch if it does not exist and logs the fallback."""
    stderr_message = "error: pathspec 'feature-branch' did not match any file(s) known to git"
    err = GitCommandError("checkout", 1, stderr=stderr_message)

    mock_repo.git.checkout.side_effect = [err, None]

    client = GitClient(mock_repo, mock.Mock(), GitCredentials(TEST_USERNAME, TEST_TOKEN))

    with caplog.at_level("INFO"):
        client.checkout_branch(FEATURE_BRANCH)

    assert mock_repo.git.checkout.call_count == 2
    mock_repo.git.checkout.assert_called_with("-b", FEATURE_BRANCH)
    assert f"Branch '{FEATURE_BRANCH}' not found; creating new local branch." in caplog.text


def test_commit_and_push_executes_all_git_commands(mock_repo):
    """It stages, commits, and pushes with correct arguments."""
    mock_repo.active_branch.name = TEST_BRANCH
    client = GitClient(mock_repo, mock.Mock(), GitCredentials(TEST_USERNAME, TEST_TOKEN))
    client.commit_and_push(COMMIT_MESSAGE)
    mock_repo.git.add.assert_called_once_with(A=True)
    mock_repo.index.commit.assert_called_once_with(COMMIT_MESSAGE)
    mock_repo.git.push.assert_called_once()


def test_commit_and_push_force_push(mock_repo):
    """It supports force pushing changes."""
    mock_repo.active_branch.name = TEST_BRANCH
    client = GitClient(mock_repo, mock.Mock(), GitCredentials(TEST_USERNAME, TEST_TOKEN))
    client.commit_and_push(COMMIT_MESSAGE, force=True)
    push_args = mock_repo.git.push.call_args[0]
    assert "-f" in push_args


def test_open_pull_request_success(mock_repo):
    """It creates a PR when no open PR from branch exists."""
    mock_gh_repo = mock.MagicMock()
    mock_gh_repo.owner.login = TEST_USERNAME
    mock_gh_repo.get_pulls.return_value.totalCount = 0
    mock_repo.active_branch.name = FEATURE_BRANCH

    client = GitClient(mock_repo, mock_gh_repo, GitCredentials(TEST_USERNAME, TEST_TOKEN))
    pr = client.open_pull_request(TEST_BRANCH, PR_TITLE, PR_BODY)

    mock_gh_repo.create_pull.assert_called_once_with(
        base=TEST_BRANCH,
        head=f"{TEST_USERNAME}:{FEATURE_BRANCH}",
        title=PR_TITLE,
        body=PR_BODY,
    )
    assert pr == mock_gh_repo.create_pull.return_value


def test_open_pull_request_duplicate(mock_repo):
    """It raises PullRequestAlreadyExistsError if a duplicate PR exists."""
    mock_gh_repo = mock.MagicMock()
    mock_gh_repo.owner.login = TEST_USERNAME
    mock_gh_repo.get_pulls.return_value.totalCount = 1
    mock_gh_repo.get_pulls.return_value.__getitem__.return_value.html_url = (
        "https://github.com/testorg/testrepo/pull/123"
    )
    mock_repo.active_branch.name = FEATURE_BRANCH

    client = GitClient(mock_repo, mock_gh_repo, GitCredentials(TEST_USERNAME, TEST_TOKEN))
    with pytest.raises(PullRequestAlreadyExistsError) as exc_info:
        client.open_pull_request(TEST_BRANCH, PR_TITLE, PR_BODY)
    assert "pull/123" in str(exc_info.value)


def test_extract_repo_name_https():
    """It correctly extracts 'owner/repo' from HTTPS URLs."""
    url = "https://github.com/testorg/testrepo.git"
    assert _extract_repo_name(url) == "testorg/testrepo"


def test_extract_repo_name_https_without_dotgit():
    """It works even if .git suffix is omitted."""
    url = "https://github.com/testorg/testrepo"
    assert _extract_repo_name(url) == "testorg/testrepo"


def test_extract_repo_name_ssh():
    """It correctly extracts from SSH format URLs."""
    url = "git@github.com:testorg/testrepo.git"
    assert _extract_repo_name(url) == "testorg/testrepo"


def test_extract_repo_name_invalid():
    """It raises GitClientError on invalid URL."""
    with pytest.raises(GitClientError, match="Invalid GitHub URL"):
        _extract_repo_name("ftp://example.com/repo.git")


def test_configure_git_sets_user_and_remote(monkeypatch):
    """It sets git user config and updates remote URL."""
    repo = mock.MagicMock()
    config_writer = mock.MagicMock()
    repo.config_writer.return_value.__enter__.return_value = config_writer

    creds = GitCredentials(username="robot", token="s3cr3t")
    _configure_git(repo, creds, "acme/myrepo")

    config_writer.set_value.assert_any_call("user", "name", "robot")
    config_writer.set_value.assert_any_call("user", "email", "robot@users.noreply.github.com")

    repo.remote().set_url.assert_called_once_with(
        "https://s3cr3t:x-oauth-basic@github.com/acme/myrepo.git"
    )


def test_build_authenticated_url():
    """It returns the correct authenticated GitHub URL."""
    token = "ghp_exampletoken123"
    repo_name = "acme/rocket"

    expected_url = "https://ghp_exampletoken123:x-oauth-basic@github.com/acme/rocket.git"
    assert _build_authenticated_url(token, repo_name) == expected_url
