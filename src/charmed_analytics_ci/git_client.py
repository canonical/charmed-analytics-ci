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

# Supported GitHub URL patterns
HTTPS_URL_PATTERN = re.compile(r"^https://(?:[^@]+@)?github\.com/([^/]+/[^/]+)(?:\.git)?$")
SSH_URL_PATTERN = re.compile(r"^git@github\.com:([^/]+/[^/]+)\.git$")


@dataclass
class GitCredentials:
    """
    Holds GitHub credentials.

    Attributes:
        username: GitHub username.
        email: GitHub email address.
        token: Personal access token used for authentication.
    """

    username: str
    email: str
    token: str


class GitClientError(Exception):
    """
    Exception raised for generic Git client-related issues.

    Raised when an operation with git or GitHub API fails due to configuration or connectivity.
    """


class PullRequestAlreadyExistsError(GitClientError):
    """
    Raised when a pull request from the current branch already exists on GitHub.

    Attributes:
        url: URL of the existing pull request.
    """

    def __init__(self, url: str):
        super().__init__(f"A pull request already exists: {url}")
        self.url = url


class GitClient:
    """
    A client that wraps local Git operations and GitHub pull request creation.

    Attributes:
        repo: A GitPython Repo object representing the local repository.
        gh_repo: A PyGithub Repository object connected to the GitHub repo.
        credentials: GitHub credentials used for Git and API operations.
    """

    def __init__(self, repo: Repo, gh_repo: Repository, credentials: GitCredentials) -> None:
        """
        Initialize a GitClient instance.

        Args:
            repo: The local GitPython repository instance.
            gh_repo: The corresponding GitHub Repository object.
            credentials: GitHub credentials for authentication.
        """
        self.repo = repo
        self.gh_repo = gh_repo
        self.credentials = credentials

    @property
    def current_branch(self) -> str:
        """
        Return the name of the currently checked out Git branch.
        """
        return self.repo.active_branch.name

    def checkout_branch(self, branch: str) -> None:
        """
        Switch to a specified branch, creating it locally if it doesn't exist.

        Args:
            branch: Name of the branch to check out.

        Raises:
            GitClientError: If checkout fails for unexpected reasons.
        """
        try:
            self.repo.git.checkout(branch)
        except GitCommandError as e:
            # Check if the error was due to a missing branch
            error_msg = str(e).lower()
            if "did not match any file(s) known to git" in error_msg or "pathspec" in error_msg:
                logger.info(f"Branch '{branch}' not found; creating new local branch.")
                try:
                    self.repo.git.checkout("-b", branch)
                except GitCommandError as create_err:
                    raise GitClientError(
                        f"Failed to create new branch '{branch}': {create_err}"
                    ) from create_err
            else:
                raise GitClientError(f"Failed to checkout branch '{branch}': {e}") from e

    def commit_and_push(
        self,
        commit_message: str,
        branch: Optional[str] = None,
        force: bool = False,
        sign: bool = True,
    ) -> None:
        """
        Stage all changes, commit them, and push to remote.

        Args:
            commit_message: The message to use for the commit.
            branch: Optional branch to switch to before committing.
            force: Whether to force-push changes.
            sign: Whether to GPG-sign the commit.
        """
        if branch:
            self.checkout_branch(branch)

        self.repo.git.add(A=True)

        commit_args = ["-m", commit_message]
        if sign:
            commit_args.insert(0, "-S")  # prepend -S to enable GPG signing

        try:
            self.repo.git.commit(*commit_args)
        except GitCommandError as e:
            raise GitClientError(f"Git commit failed: {e}") from e

        push_args = ["-u", "origin", self.current_branch]
        if force:
            push_args.insert(0, "-f")

        self.repo.git.push(*push_args)

    def open_pull_request(self, base: str, title: str, body: str) -> PullRequest:
        """
        Open a pull request from the current branch to a base branch.

        Args:
            base: The target branch to merge into (e.g., "main").
            title: Title of the pull request.
            body: Detailed body text for the pull request.

        Returns:
            The created GitHub PullRequest object.

        Raises:
            PullRequestAlreadyExistsError: If a PR from the same branch already exists.
            GitClientError: If pull request creation fails.
        """
        head = f"{self.gh_repo.owner.login}:{self.current_branch}"
        try:
            prs = self.gh_repo.get_pulls(state="open", head=head, base=base)
            if prs.totalCount > 0:
                raise PullRequestAlreadyExistsError(prs[0].html_url)

            logger.info("Creating PR: %s → %s", self.current_branch, base)
            pr = self.gh_repo.create_pull(base=base, head=head, title=title, body=body)
            logger.info("PR created: %s", pr.html_url)
            return pr
        except GithubException as e:
            raise GitClientError(f"Failed to create pull request: {e}") from e


def create_git_client_from_url(
    url: str, credentials: GitCredentials, clone_path: Path = Path("/tmp")
) -> GitClient:
    """
    Clone or reuse a GitHub repository and return a GitClient instance.

    This function:
    - Validates and extracts the repo name.
    - Clones the repo if not already present.
    - Configures the repo with Git credentials.
    - Connects to GitHub API.

    Args:
        url: GitHub HTTPS or SSH URL.
        credentials: GitHub credentials for clone and API.
        clone_path: Where to store the local clone.

    Returns:
        A fully initialized GitClient.

    Raises:
        GitClientError: If cloning or configuration fails.
    """
    repo_name = _extract_repo_name(url)
    repo_dir = clone_path / repo_name.split("/")[-1]
    authenticated_url = _build_authenticated_url(credentials.token, repo_name)

    repo = _get_or_clone_repo(authenticated_url, url, repo_dir)
    _configure_git(repo, credentials, repo_name)

    try:
        gh_repo = Github(auth=Token(credentials.token)).get_repo(repo_name)
    except Exception as e:
        raise GitClientError(f"Failed to connect to GitHub repository '{repo_name}': {e}") from e

    return GitClient(repo=repo, gh_repo=gh_repo, credentials=credentials)


def _get_or_clone_repo(authenticated_url: str, original_url: str, local_path: Path) -> Repo:
    """
    Clone the repo if not already cloned, otherwise validate and reuse.

    Args:
        authenticated_url: Authenticated URL with token.
        original_url: Original user-provided GitHub URL.
        local_path: Where the repo is or will be located.

    Returns:
        GitPython Repo object.

    Raises:
        GitClientError: If cloning fails or remotes mismatch.
    """
    try:
        if not local_path.exists():
            logger.info("Cloning repository %s to %s", authenticated_url, local_path)
            return Repo.clone_from(authenticated_url, local_path)

        logger.info("Using existing repo at %s", local_path)
        repo = Repo(local_path)

        expected = _extract_repo_name(original_url)
        actual = _extract_repo_name(repo.remote().url)

        if expected != actual:
            raise GitClientError(
                f"Repo at {local_path} points to a different remote ({actual} != {expected})"
            )

        return repo
    except GitCommandError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        raise GitClientError(f"Failed to clone repository '{original_url}': {error_msg}") from e


def _extract_repo_name(url: str) -> str:
    """
    Extract 'org/repo' from a GitHub SSH or HTTPS URL.

    Args:
        url: GitHub repository URL.

    Returns:
        A string like 'org/repo'.

    Raises:
        GitClientError: If URL is not a valid GitHub format.
    """
    match = HTTPS_URL_PATTERN.match(url) or SSH_URL_PATTERN.match(url)
    if not match:
        raise GitClientError(f"Invalid GitHub URL: {url}")
    return match.group(1).removesuffix(".git")


def _configure_git(repo: Repo, creds: GitCredentials, repo_name: str) -> None:
    """
    Set Git user info and configure the remote to use HTTPS with token.

    Args:
        repo: Local repository.
        creds: GitHub credentials.
        repo_name: GitHub repository name in 'org/repo' format.
    """
    with repo.config_writer(config_level="repository") as config:
        config.set_value("user", "name", creds.username)
        config.set_value("user", "email", creds.email)

    remote_url = _build_authenticated_url(creds.token, repo_name)
    repo.remote().set_url(remote_url)


def _build_authenticated_url(token: str, repo_name: str) -> str:
    """
    Construct a GitHub HTTPS URL with authentication token.

    Args:
        token: GitHub personal access token.
        repo_name: GitHub repository in the form 'org/repo'.

    Returns:
        Authenticated GitHub HTTPS URL.
    """
    return f"https://{token}:x-oauth-basic@github.com/{repo_name}.git"
