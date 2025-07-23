# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Tuple

import pytest
import yaml
from github import Github
from github.Repository import Repository
from jsonpath_ng.ext import parse as jsonpath_parse

from charmed_analytics_ci.rock_ci_metadata_models import RockCIMetadata

DEFAULT_IMAGE_BASE = "ghcr.io/example/my-rock"


@pytest.fixture
def repo_info() -> dict:
    """Fixture for shared GitHub test repository configuration."""
    return {
        "repo_full_name": os.environ["CHACI_TEST_REPO"],
        "token": os.environ["CHACI_TEST_TOKEN"],
        "base_branch": os.environ["CHACI_TEST_BASE_BRANCH"],
        "email": os.environ["CHACI_TEST_EMAIL"],
    }


@pytest.fixture
def github_client(repo_info: dict) -> Repository:
    """Provides an authenticated GitHub repository object using PyGithub."""
    gh = Github(repo_info["token"])
    return gh.get_repo(repo_info["repo_full_name"])


def run_chaci(
    metadata_path: Path,
    base_branch: str,
    token: str,
    username: str = "test-user",
    email: Optional[str] = None,
    tmpdir: Optional[Path] = None,
    triggering_pr: Optional[str] = None,
) -> Tuple[subprocess.CompletedProcess[str], str, str, str]:
    """
    Run the CHACI CLI tool to integrate a rock image into a given base branch.

    This function generates a unique tag for the rock image, constructs the `chaci integrate-rock`
    command, and runs it in a temporary or specified clone directory. It also supports passing
    an optional triggering PR link and GitHub email.

    Args:
        metadata_path: Path to the rock metadata YAML file.
        base_branch: Target branch into which the rock should be integrated.
        token: GitHub personal access token for authentication.
        username: GitHub username used for commit attribution (default: "test-user").
        email: Optional GitHub email address for signed commits.
        tmpdir: Optional directory to use for cloning; a temporary one is created if not provided.
        triggering_pr: Optional URL of the triggering pull request to link in the integration.

    Returns:
        A tuple containing:
            - The completed subprocess result of running the `chaci` command.
            - The short name of the rock image.
            - The randomly generated image tag.
            - The full rock image reference (e.g., "ghcr.io/org/image:tag").
    """
    rock_short_name = DEFAULT_IMAGE_BASE.split("/")[-1]
    rock_tag = str(uuid.uuid4())[:8]
    rock_image = f"{DEFAULT_IMAGE_BASE}:{rock_tag}"

    with tempfile.TemporaryDirectory() if tmpdir is None else tmpdir as clone_dir:
        command = [
            "chaci",
            "integrate-rock",
            str(metadata_path),
            base_branch,
            rock_image,
            "--github-token",
            token,
            "--github-username",
            username,
            "--clone-dir",
            str(clone_dir),
        ]

        if triggering_pr:
            command += ["--triggering-pr", triggering_pr]

        if email:
            command += ["--github-email", email]

        result = subprocess.run(
            command,
            env={**os.environ, "GH_TOKEN": token},
            capture_output=True,
            text=True,
        )

    return result, rock_short_name, rock_tag, rock_image


# ---------------------- PARAMETRIZED SUCCESS CASES ----------------------


@pytest.mark.parametrize(
    "metadata_filename, expected_body_filename, expect_service_files_modified",
    [
        ("rock-ci-metadata.yaml", "expected_pr_body.md", True),
        ("rock-ci-metadata-service.yaml", "expected_pr_body_service.md", True),
        ("rock-ci-metadata-service-missing.yaml", "expected_pr_body_service_missing.md", False),
    ],
)
def test_chaci_success_opens_pr_and_cleans_up(
    repo_info: dict,
    github_client: Repository,
    metadata_filename: str,
    expected_body_filename: str,
    expect_service_files_modified: bool,
) -> None:
    """Test that chaci opens a pull request, modifies expected files, and cleans it up."""
    metadata_file = Path(__file__).parent / metadata_filename
    raw = yaml.safe_load(metadata_file.read_text())
    metadata = RockCIMetadata.model_validate(raw)

    expected_body = (Path(__file__).parent / expected_body_filename).read_text().strip()
    result, rock_short_name, rock_tag, rock_image = run_chaci(
        metadata_path=metadata_file,
        base_branch=repo_info["base_branch"],
        token=repo_info["token"],
        username=github_client.owner.login,
        email=repo_info["email"],
    )

    pr_branch = f"integrate-{rock_short_name}-{rock_tag}"
    pr_title = f"chore: integrate rock image {rock_short_name}:{rock_tag}"

    assert result.returncode == 0, f"CLI failed unexpectedly:\n{result.stdout}\n{result.stderr}"

    pr = None
    try:
        pr = _get_open_pr(github_client, pr_branch, pr_title)
        assert pr.body.strip() == expected_body

        # Validate that the HEAD commit is GPG signed
        commit = github_client.get_commit(pr.head.sha)
        assert (
            commit.commit.verification.verified
        ), f"Expected signed commit, but verification failed: {commit.commit.verification.reason}"

        changed_files = {f.filename: f for f in pr.get_files()}
        _assert_image_replacements(changed_files, github_client, pr_branch, metadata, rock_image)
        _assert_service_spec_changes(changed_files, metadata, expect_service_files_modified)
    finally:
        _cleanup_pr(pr, github_client, pr_branch)


def _get_open_pr(github_client: Repository, branch: str, title: str):
    prs = [
        p
        for p in github_client.get_pulls(state="open")
        if p.head.ref == branch and p.title == title
    ]
    assert len(prs) == 1, f"Expected one PR to be opened, found {len(prs)}"
    return prs[0]


def _assert_image_replacements(changed_files, github_client, pr_branch, metadata, expected_image):
    for integration in metadata.integrations:
        for entry in integration.replace_image:
            file_path = str(entry.file)
            assert file_path in changed_files, f"Expected file '{file_path}' to be modified"

            raw = github_client.get_contents(file_path, ref=pr_branch).decoded_content
            try:
                data = yaml.safe_load(raw)
            except Exception:
                data = json.loads(raw)

            matches = list(jsonpath_parse(entry.path).find(data))
            assert matches, f"No match for path '{entry.path}' in file {file_path}"

            for match in matches:
                assert match.value == expected_image, (
                    f"Expected path '{entry.path}' in '{file_path}' to be set to "
                    f"'{expected_image}', but found '{match.value}'"
                )


def _assert_service_spec_changes(changed_files, metadata, expect_modified: bool):
    service_files = {str(e.file) for i in metadata.integrations for e in i.service_spec or []}
    for service_file in service_files:
        if expect_modified:
            assert (
                service_file in changed_files
            ), f"Expected service file '{service_file}' to be updated"
        else:
            assert (
                service_file not in changed_files
            ), f"Did NOT expect service file '{service_file}' to be changed"


def _cleanup_pr(pr, github_client, pr_branch: str):
    if pr:
        pr.edit(state="closed")
    try:
        github_client.get_git_ref(f"heads/{pr_branch}").delete()
    except Exception:
        pass


def test_chaci_adds_triggering_pr_link_if_provided(
    repo_info: dict,
    github_client: Repository,
) -> None:
    """Test that chaci includes a link to the triggering PR when provided."""
    metadata_file = Path(__file__).parent / "rock-ci-metadata.yaml"
    triggering_pr_url = "https://github.com/example/repo/pull/123"

    result, rock_short_name, rock_tag, _ = run_chaci(
        metadata_path=metadata_file,
        base_branch=repo_info["base_branch"],
        token=repo_info["token"],
        username=github_client.owner.login,
        triggering_pr=triggering_pr_url,
        email=repo_info["email"],
    )

    pr_branch = f"integrate-{rock_short_name}-{rock_tag}"
    pr_title = f"chore: integrate rock image {rock_short_name}:{rock_tag}"

    assert result.returncode == 0, f"CLI failed:\n{result.stdout}\n{result.stderr}"

    pr = None
    try:
        pr = _get_open_pr(github_client, pr_branch, pr_title)
        assert triggering_pr_url in pr.body, "Expected triggering PR URL to be in the PR body"
    finally:
        _cleanup_pr(pr, github_client, pr_branch)


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
            email=repo_info["email"],
        )

    assert result.returncode != 0, (
        f"Expected CLI to fail for {metadata_filename}, but it succeeded.\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    combined_output = result.stdout + result.stderr
    assert (
        expected_error.lower() in combined_output.lower()
    ), f"Expected error '{expected_error}' not found in output:\n{combined_output}"
