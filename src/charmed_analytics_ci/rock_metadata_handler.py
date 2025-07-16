# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from importlib.resources import files
from pathlib import Path

from jinja2 import Template

from charmed_analytics_ci.git_client import GitCredentials, create_git_client_from_url
from charmed_analytics_ci.logger import setup_logger
from charmed_analytics_ci.rock_ci_metadata_models import IntegrationEntry, RockCIMetadata
from charmed_analytics_ci.rock_integrator import (
    IntegrationResult,
    apply_integration,
    validate_metadata_file,
)

logger = setup_logger(__name__)


def _load_pr_template() -> Template:
    """Load and return the Jinja2 template for PR description from the package resources."""
    template_path = files("charmed_analytics_ci.templates").joinpath("pr_body.md.j2")
    return Template(template_path.read_text())


def validate_integration_result(
    result: IntegrationResult,
    index: int,
    repo_url: str,
    integration: IntegrationEntry,
    base_dir: Path,
) -> None:
    """
    Raise an error if the integration result indicates failure.

    Args:
        result: Result of the integration operation.
        index: Index of the integration in the metadata list.
        repo_url: Git URL of the integration target.
        integration: The integration metadata entry.
        base_dir: Base path of the cloned repository.

    Raises:
        RuntimeError: If the integration is invalid or incomplete.
    """
    allowed_missing = {base_dir / entry.file for entry in integration.service_spec or []}

    non_service_spec_missing = [
        path for path in result.missing_files if path not in allowed_missing
    ]

    if non_service_spec_missing:
        formatted = ", ".join(str(p) for p in non_service_spec_missing)
        raise RuntimeError(
            f"Integration {index} failed for {repo_url}: missing expected files: {formatted}"
        )

    if result.path_errors:
        formatted = "\n".join(f" - {e}" for e in result.path_errors)
        raise RuntimeError(
            f"Integration {index} failed: {repo_url} due to invalid path expressions:\n{formatted}"
        )

    if not result.updated_files:
        raise RuntimeError(
            f"Integration {index} failed for {repo_url}: no changes detected in updated files"
        )


def integrate_rock_into_consumers(
    metadata_path: Path,
    rock_image: str,
    clone_base_dir: Path,
    github_token: str,
    github_username: str,
    base_branch: str,
) -> None:
    """
    Integrate a rock image into multiple consumer repositories defined in a metadata file.
    """
    metadata: RockCIMetadata = validate_metadata_file(metadata_path)
    integrations = metadata.integrations
    rock_name, rock_tag = rock_image.split(":")
    rock_short_name = rock_name.split("/")[-1]
    pr_branch_name = f"integrate-{rock_short_name}-{rock_tag}"

    pr_template = _load_pr_template()
    prepared_prs = []

    for i, integration in enumerate(integrations):
        repo_url = integration.consumer_repository
        logger.info(f"Preparing integration {i} → {repo_url} into base branch {base_branch}")

        creds = GitCredentials(username=github_username, token=github_token)
        client = create_git_client_from_url(repo_url, credentials=creds, clone_path=clone_base_dir)
        base_dir = Path(client.repo.working_dir)

        client.checkout_branch(base_branch)

        result = apply_integration(
            metadata_path=metadata_path,
            rock_image=rock_image,
            base_dir=base_dir,
            integration_index=i,
        )

        validate_integration_result(result, i, repo_url, integration, base_dir)

        # Construct PR title and message
        pr_title = f"chore: integrate rock image {rock_short_name}:{rock_tag}"
        commit_message = pr_title

        replace_image = [entry.model_dump() for entry in integration.replace_image]
        service_spec_all = [entry.model_dump() for entry in integration.service_spec or []]
        missing_files = set(result.missing_files)

        service_spec_found = [
            entry for entry in service_spec_all if (base_dir / entry["file"]) not in missing_files
        ]
        service_spec_missing = [
            entry for entry in service_spec_all if (base_dir / entry["file"]) in missing_files
        ]

        pr_body = pr_template.render(
            replace_image=replace_image,
            service_spec=service_spec_found,
            service_spec_missing=service_spec_missing,
        )

        prepared_prs.append((client, commit_message, pr_title, pr_body))

    # Push and open PRs after all validations pass
    for client, commit_message, pr_title, pr_body in prepared_prs:
        client.commit_and_push(commit_message=commit_message, branch=pr_branch_name)
        client.open_pull_request(base=base_branch, title=pr_title, body=pr_body)
