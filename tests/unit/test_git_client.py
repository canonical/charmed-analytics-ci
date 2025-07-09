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
    create_git_client_from_url,
)

# Constants for test configuration
TEST_USERNAME = "testuser"
TEST_TOKEN = "ghp_exampletoken"
TEST_URL = "https://github.com/testorg/testrepo.git"
TEST_REPO_NAME = "testrepo"
TEST_BRANCH = "main"
FEATURE_BRANCH = "feature-branch"
COMMIT_MESSAGE = "test commit"
PR_TITLE = "Add feature"
PR_BODY = "Implements feature XYZ"


@pytest.fixture
def temp_repo_dir() -> Generator[Path, None, None]:
    """Create a temporary directory and clean it up after the test."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_repo(monkeypatch) -> mock.MagicMock:
    """Mock the GitPython Repo object and patch clone_from."""
    repo = mock.MagicMock(spec=Repo)
    monkeypatch.setattr("charmed_analytics_ci.git_client.Repo", mock.MagicMock(return_value=repo))
    monkeypatch.setattr(
        "charmed_analytics_ci.git_client.Repo.clone_from", mock.MagicMock(return_value=repo)
    )
    return repo


@pytest.fixture
def mock_github(monkeypatch) -> mock.MagicMock:
    """Mock the GitHub API client and its get_repo method."""
    mock_gh_repo = mock.MagicMock()
    mock_github_client = mock.MagicMock()
    mock_github_client.get_repo.return_value = mock_gh_repo
    monkeypatch.setattr(
        "charmed_analytics_ci.git_client.Github", mock.MagicMock(return_value=mock_github_client)
    )
    return mock_gh_repo


def test_create_git_client_from_url_clones_new_repo(
    temp_repo_dir: Path, mock_repo: mock.MagicMock, mock_github: mock.MagicMock
) -> None:
    """Test that a new repo is cloned when it doesn't exist locally."""
    creds = GitCredentials(username=TEST_USERNAME, token=TEST_TOKEN)
    client = create_git_client_from_url(TEST_URL, creds, clone_path=temp_repo_dir)
    assert isinstance(client, GitClient)


def test_create_git_client_from_url_existing_repo_matching_remote(
    temp_repo_dir: Path, mock_repo: mock.MagicMock, mock_github: mock.MagicMock
) -> None:
    """Test using an existing repo when the remote URL matches."""
    creds = GitCredentials(username=TEST_USERNAME, token=TEST_TOKEN)
    repo_path = temp_repo_dir / TEST_REPO_NAME
    repo_path.mkdir()
    mock_repo.remote.return_value.url = TEST_URL

    client = create_git_client_from_url(TEST_URL, creds, clone_path=temp_repo_dir)
    assert isinstance(client, GitClient)


def test_create_git_client_from_url_existing_repo_wrong_remote(
    temp_repo_dir: Path, mock_repo: mock.MagicMock, mock_github: mock.MagicMock
) -> None:
    """Test error is raised when the existing repo has a different remote."""
    creds = GitCredentials(username=TEST_USERNAME, token=TEST_TOKEN)
    repo_path = temp_repo_dir / TEST_REPO_NAME
    repo_path.mkdir()
    mock_repo.remote.return_value.url = "https://github.com/other/wrong.git"

    with pytest.raises(GitClientError):
        create_git_client_from_url(TEST_URL, creds, clone_path=temp_repo_dir)


def test_checkout_branch_existing_branch(mock_repo: mock.MagicMock) -> None:
    """Test that checkout to an existing branch does not fail."""
    client = GitClient(mock_repo, mock.MagicMock(), GitCredentials(TEST_USERNAME, TEST_TOKEN))
    client.checkout_branch(TEST_BRANCH)
    mock_repo.git.checkout.assert_called_with(TEST_BRANCH)


def test_checkout_branch_creates_new_branch(mock_repo: mock.MagicMock) -> None:
    """Test that a new branch is created if it does not exist."""
    mock_repo.git.checkout.side_effect = [GitCommandError("checkout", 1), None]
    client = GitClient(mock_repo, mock.MagicMock(), GitCredentials(TEST_USERNAME, TEST_TOKEN))
    client.checkout_branch(FEATURE_BRANCH)
    assert mock_repo.git.checkout.call_count == 2


def test_commit_and_push_calls_git_methods(mock_repo: mock.MagicMock) -> None:
    """Test that commit and push logic is executed correctly."""
    mock_repo.active_branch.name = TEST_BRANCH
    client = GitClient(mock_repo, mock.MagicMock(), GitCredentials(TEST_USERNAME, TEST_TOKEN))
    client.commit_and_push(COMMIT_MESSAGE)
    mock_repo.git.add.assert_called_once_with(A=True)
    mock_repo.index.commit.assert_called_once_with(COMMIT_MESSAGE)
    mock_repo.git.push.assert_called_once()


def test_open_pull_request_success(mock_repo: mock.MagicMock) -> None:
    """Test that a pull request is created when none exists."""
    mock_gh_repo = mock.MagicMock()
    mock_gh_repo.owner.login = TEST_USERNAME
    mock_gh_repo.get_pulls.return_value.totalCount = 0
    mock_repo.active_branch.name = FEATURE_BRANCH

    client = GitClient(mock_repo, mock_gh_repo, GitCredentials(TEST_USERNAME, TEST_TOKEN))
    pr = client.open_pull_request(base=TEST_BRANCH, title=PR_TITLE, body=PR_BODY)

    mock_gh_repo.create_pull.assert_called_once_with(
        base=TEST_BRANCH,
        head=f"{TEST_USERNAME}:{FEATURE_BRANCH}",
        title=PR_TITLE,
        body=PR_BODY,
    )
    assert pr == mock_gh_repo.create_pull.return_value


def test_open_pull_request_already_exists(mock_repo: mock.MagicMock) -> None:
    """Test that an error is raised when a duplicate PR already exists."""
    mock_gh_repo = mock.MagicMock()
    mock_gh_repo.owner.login = TEST_USERNAME
    mock_gh_repo.get_pulls.return_value.totalCount = 1
    mock_gh_repo.get_pulls.return_value.__getitem__.return_value.html_url = (
        "https://github.com/testorg/testrepo/pull/1"
    )
    mock_repo.active_branch.name = FEATURE_BRANCH

    client = GitClient(mock_repo, mock_gh_repo, GitCredentials(TEST_USERNAME, TEST_TOKEN))

    with pytest.raises(PullRequestAlreadyExistsError) as exc_info:
        client.open_pull_request(base=TEST_BRANCH, title=PR_TITLE, body=PR_BODY)

    assert "https://github.com/testorg/testrepo/pull/1" in str(exc_info.value)
