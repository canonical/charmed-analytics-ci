from importlib.resources import files
from pathlib import Path

from jinja2 import Template

from charmed_analytics_ci.git_client import GitCredentials, create_git_client_from_url
from charmed_analytics_ci.logger import setup_logger
from charmed_analytics_ci.rock_integrator import apply_integration, validate_metadata_file

logger = setup_logger(__name__)


def _load_pr_template() -> Template:
    """Load and return the Jinja2 template for PR description from the package resources."""
    template_path = files("charmed_analytics_ci.templates").joinpath("pr_body.md.j2")
    return Template(template_path.read_text())


def integrate_rock_into_consumers(
    metadata_path: Path,
    rock_image: str,
    clone_base_dir: Path,
    github_token: str,
    github_username: str,
    base_branch: str,
) -> None:
    """
    For each integration in the metadata file:
    - Clone the target repository
    - Check out the base branch
    - Apply the rock image update
    - Open a pull request with changes targeting the base branch

    Args:
        metadata_path: Path to the validated rock-ci-metadata.yaml file.
        rock_image: Fully qualified rock image (e.g. ghcr.io/canonical/my-rock:1.2.3).
        clone_base_dir: Directory into which to clone consumer repositories.
        github_token: GitHub personal access token for authentication.
        github_username: Username of the GitHub bot/user.
        base_branch: The branch into which the PR should be merged.
    """
    metadata = validate_metadata_file(metadata_path)
    integrations = metadata.get("integrations", [])
    rock_name, rock_tag = rock_image.split(":")
    pr_branch_name = f"integrate-{rock_name.split('/')[-1]}-{rock_tag}"

    pr_template = _load_pr_template()

    for i, integration in enumerate(integrations):
        repo_url = integration["consumer-repository"]

        logger.info(f"Processing integration {i} → {repo_url} into base branch {base_branch}")

        creds = GitCredentials(username=github_username, token=github_token)
        client = create_git_client_from_url(repo_url, credentials=creds, clone_path=clone_base_dir)

        # Check out the base branch so we branch off it
        client.checkout_branch(base_branch)

        result = apply_integration(
            metadata_path=metadata_path,
            rock_image=rock_image,
            base_dir=Path(client.repo.working_dir),
            integration_index=i,
        )

        if result.missing_files:
            logger.warning(
                f"Skipped PR: some expected files were missing: "
                f"{', '.join(str(f) for f in result.missing_files)}"
            )
            continue

        if not result.updated_files:
            logger.info("No changes detected for this integration. Skipping PR.")
            continue

        pr_title = f"chore: integrate rock image {rock_name}:{rock_tag}"
        commit_message = pr_title

        replace_image = integration["replace-image"]
        service_spec_all = integration.get("service-spec", [])
        missing_files_set = set(str(p) for p in result.missing_files)

        service_spec_found = [
            entry for entry in service_spec_all if entry["file"] not in missing_files_set
        ]
        service_spec_missing = [
            entry for entry in service_spec_all if entry["file"] in missing_files_set
        ]

        pr_body = pr_template.render(
            replace_image=replace_image,
            service_spec=service_spec_found,
            service_spec_missing=service_spec_missing,
        )

        client.commit_and_push(commit_message=commit_message, branch=pr_branch_name)
        client.open_pull_request(base=base_branch, title=pr_title, body=pr_body)
