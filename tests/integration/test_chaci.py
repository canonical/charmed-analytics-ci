import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Tuple

import pytest
from github import Github
from github.Repository import Repository

DEFAULT_IMAGE_BASE = "ghcr.io/example/my-rock"


@pytest.fixture
def repo_info() -> dict:
    """
    Fixture for shared GitHub test repository configuration.

    Returns:
        Dictionary with repository details including full name, token, and base branch.
    """
    return {
        "repo_full_name": os.environ["CHACI_TEST_REPO"],
        "token": os.environ["CHACI_TEST_TOKEN"],
        "base_branch": os.environ["CHACI_TEST_BASE_BRANCH"],
    }


@pytest.fixture
def github_client(repo_info: dict) -> Repository:
    """
    Provides an authenticated GitHub repository object using PyGithub.

    Args:
        repo_info: Dictionary containing GitHub authentication details.

    Returns:
        A PyGithub Repository object.
    """
    gh = Github(repo_info["token"])
    return gh.get_repo(repo_info["repo_full_name"])


def run_chaci(
    metadata_path: Path,
    base_branch: str,
    token: str,
    username: str = "test-user",
    tmpdir: Optional[Path] = None,
) -> Tuple[subprocess.CompletedProcess[str], str, str, str]:
    """
    Run the chaci CLI with a randomly generated tag for a fixed image base.

    Args:
        metadata_path: Path to the rock-ci-metadata.yaml file.
        base_branch: The GitHub branch to target for PRs.
        token: GitHub authentication token.
        username: GitHub username.
        tmpdir: Optional custom temporary directory.

    Returns:
        A tuple containing the subprocess result, rock short name, tag, and image.
    """
    rock_short_name = DEFAULT_IMAGE_BASE.split("/")[-1]
    rock_tag = str(uuid.uuid4())[:8]
    rock_image = f"{DEFAULT_IMAGE_BASE}:{rock_tag}"

    with tempfile.TemporaryDirectory() if tmpdir is None else tmpdir as clone_dir:
        result = subprocess.run(
            [
                "chaci",
                "integrate-rock",
                str(metadata_path),
                base_branch,
                rock_image,
                token,
                username,
                "--clone-dir",
                str(clone_dir),
            ],
            env={**os.environ, "GH_TOKEN": token},
            capture_output=True,
            text=True,
        )

    return result, rock_short_name, rock_tag, rock_image


# ---------------------- PARAMETRIZED SUCCESS CASES ----------------------


@pytest.mark.parametrize(
    "metadata_filename, expected_body_filename",
    [
        ("rock-ci-metadata.yaml", "expected_pr_body.md"),
        ("rock-ci-metadata-service.yaml", "expected_pr_body_service.md"),
        ("rock-ci-metadata-service-missing.yaml", "expected_pr_body_service_missing.md"),
    ],
)
def test_chaci_success_opens_pr_and_cleans_up(
    repo_info: dict,
    github_client: Repository,
    metadata_filename: str,
    expected_body_filename: str,
) -> None:
    """Test that chaci opens a pull request and cleans it up after validation."""
    expected_body = (Path(__file__).parent / expected_body_filename).read_text().strip()
    metadata_file = Path(__file__).parent / metadata_filename

    result, rock_short_name, rock_tag, _ = run_chaci(
        metadata_path=metadata_file,
        base_branch=repo_info["base_branch"],
        token=repo_info["token"],
        username=github_client.owner.login,
    )

    pr_branch = f"integrate-{rock_short_name}-{rock_tag}"
    pr_title = f"chore: integrate rock image {rock_short_name}:{rock_tag}"

    assert result.returncode == 0, f"CLI failed unexpectedly:\n{result.stdout}\n{result.stderr}"

    pr = None
    try:
        prs = [
            p
            for p in github_client.get_pulls(state="open")
            if p.head.ref == pr_branch and p.title == pr_title
        ]
        assert len(prs) == 1, f"Expected one PR to be opened, found {len(prs)}"
        pr = prs[0]
        assert pr.body.strip() == expected_body
    finally:
        if pr:
            pr.edit(state="closed")
        try:
            github_client.get_git_ref(f"heads/{pr_branch}").delete()
        except Exception:
            pass


# ---------------------- PARAMETRIZED FAILURE CASES ----------------------


@pytest.mark.parametrize(
    "metadata_filename, expected_error",
    [
        ("rock-ci-metadata-nonexistent-repo.yaml", "failed to clone repository"),
        ("rock-ci-metadata-missing-file.yaml", "missing expected files"),
        ("rock-ci-metadata-invalid-path.yaml", "no matches found for path"),
    ],
)
def test_chaci_integration_failures(
    repo_info: dict, metadata_filename: str, expected_error: str
) -> None:
    """Test that the chaci CLI fails with expected error messages for invalid metadata."""
    metadata_file = Path(__file__).parent / metadata_filename

    with tempfile.TemporaryDirectory() as tmpdir:
        result, *_ = run_chaci(
            metadata_path=metadata_file,
            base_branch=repo_info["base_branch"],
            token=repo_info["token"],
            username="test-user",
            tmpdir=Path(tmpdir),
        )

    assert result.returncode != 0, (
        f"Expected CLI to fail for {metadata_filename}, but it succeeded.\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    combined_output = result.stdout + result.stderr
    assert (
        expected_error.lower() in combined_output.lower()
    ), f"Expected error '{expected_error}' not found in output:\n{combined_output}"
