# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from git import GitCommandError, Repo
from github import Github
from github.Auth import Token
from github.GithubException import GithubException
from github.PullRequest import PullRequest
from github.Repository import Repository

from charmed_analytics_ci.logger import setup_logger

logger = setup_logger(__name__)

# Supported GitHub URL patterns (HTTPS or SSH)
HTTPS_URL_PATTERN = re.compile(r"^https://(?:[^@]+@)?github\.com/([^/]+/[^/]+)(?:\.git)?$")
SSH_URL_PATTERN = re.compile(r"git@github\.com:([^/]+/[^/]+)\.git")


@dataclass
class GitCredentials:
    """Holds GitHub credentials."""

    username: str
    token: str


class GitClientError(Exception):
    """Generic error raised by GitClient operations."""


class PullRequestAlreadyExistsError(GitClientError):
    """Raised when a pull request from the same branch already exists."""

    def __init__(self, url: str):
        self.url = url
        super().__init__(f"A pull request already exists: {url}")


class GitClient:
    """Manages local Git operations and GitHub pull request interactions."""

    def __init__(self, repo: Repo, gh_repo: Repository, credentials: GitCredentials) -> None:
        """
        Initialize GitClient.

        Args:
            repo: Local Git repository instance.
            gh_repo: GitHub repository object.
            credentials: GitHub username and token.
        """
        self.repo = repo
        self.gh_repo = gh_repo
        self.credentials = credentials

    @property
    def current_branch(self) -> str:
        """Returns the name of the currently checked out branch."""
        return self.repo.active_branch.name

    def checkout_branch(self, branch: str) -> None:
        """
        Switch to a given branch. Creates it locally if it doesn't exist.

        Args:
            branch: The name of the branch to switch to.
        """
        try:
            self.repo.git.checkout(branch)
        except GitCommandError:
            self.repo.git.checkout("-b", branch)

    def commit_and_push(
        self,
        commit_message: str,
        branch: Optional[str] = None,
        force: bool = False,
    ) -> None:
        """
        Commit all staged changes and push to the specified branch.

        Args:
            commit_message: The Git commit message.
            branch: If specified, switch/create this branch before committing.
            force: Whether to force push the changes.
        """
        if branch:
            self.checkout_branch(branch)

        self.repo.git.add(A=True)
        self.repo.index.commit(commit_message)

        push_args = ["-u", "origin", self.current_branch]
        if force:
            push_args.insert(0, "-f")

        self.repo.git.push(*push_args)

    def open_pull_request(
        self,
        base: str,
        title: str,
        body: str,
    ) -> PullRequest:
        """
        Create a pull request from the current branch to the target base branch.

        Args:
            base: The branch to merge into (e.g., 'main').
            title: Title of the pull request.
            body: Body/description of the pull request.

        Returns:
            A GitHub PullRequest object.

        Raises:
            PullRequestAlreadyExistsError: If a PR from this branch already exists.
            GitClientError: If PR creation fails.
        """
        full_head = f"{self.gh_repo.owner.login}:{self.current_branch}"
        try:
            existing_prs = self.gh_repo.get_pulls(state="open", head=full_head, base=base)
            if existing_prs.totalCount > 0:
                raise PullRequestAlreadyExistsError(existing_prs[0].html_url)

            logger.info("Creating PR: %s → %s", self.current_branch, base)
            pr = self.gh_repo.create_pull(
                base=base,
                head=f"{self.gh_repo.owner.login}:{self.current_branch}",
                title=title,
                body=body,
            )
            logger.info("PR created: %s", pr.html_url)
            return pr

        except GithubException as e:
            raise GitClientError(f"Failed to create pull request: {e}") from e


def create_git_client_from_url(
    url: str,
    credentials: GitCredentials,
    clone_path: Path = Path("/tmp"),
) -> GitClient:
    """
    Clone a GitHub repository or reuse existing one, then return a GitClient.

    Args:
        url: The GitHub repository URL (HTTPS or SSH).
        credentials: GitHub username and access token.
        clone_path: Local directory to clone into.

    Returns:
        A ready-to-use GitClient instance.

    Raises:
        GitClientError: If repo exists and remote URL doesn't match.
    """
    repo_name = _extract_repo_name(url)
    local_path = clone_path / repo_name.split("/")[-1]

    if not local_path.exists():
        logger.info("Cloning repository %s to %s", url, local_path)
        repo = Repo.clone_from(url, local_path)
    else:
        logger.info("Using existing repo at %s", local_path)
        repo = Repo(local_path)

        existing_remote = repo.remote().url
        expected = _extract_repo_name(url)
        actual = _extract_repo_name(existing_remote)

        if expected != actual:
            raise GitClientError(
                f"Repo at {local_path} points to a different remote " f"({actual} != {expected})"
            )

    _configure_git(repo, credentials, repo_name)

    github_client = Github(auth=Token(credentials.token))
    gh_repo = github_client.get_repo(repo_name)

    return GitClient(repo, gh_repo, credentials)


def _extract_repo_name(url: str) -> str:
    """
    Extract 'org/repo' from a GitHub HTTPS or SSH URL.

    Args:
        url: The GitHub repository URL.

    Returns:
        Repository name in 'owner/repo' format.

    Raises:
        GitClientError: If the URL format is invalid.
    """
    match = HTTPS_URL_PATTERN.match(url) or SSH_URL_PATTERN.match(url)
    if not match:
        raise GitClientError(f"Invalid GitHub URL: {url}")
    return match.group(1).removesuffix(".git")


def _configure_git(repo: Repo, creds: GitCredentials, repo_name: str) -> None:
    """
    Set Git username/email and configure remote with token auth.

    Args:
        repo: The local Git repository.
        creds: GitHub credentials.
        repo_name: GitHub repository in 'owner/repo' format.
    """
    with repo.config_writer(config_level="repository") as config:
        config.set_value("user", "name", creds.username)
        config.set_value("user", "email", f"{creds.username}@users.noreply.github.com")

    # Configure HTTPS remote with embedded token for auth
    authenticated_url = f"https://{creds.token}:x-oauth-basic@github.com/{repo_name}.git"
    repo.remote().set_url(authenticated_url)
