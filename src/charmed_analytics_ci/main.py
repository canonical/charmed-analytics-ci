import os
from pathlib import Path

import click

from charmed_analytics_ci.logger import setup_logger
from charmed_analytics_ci.rock_metadata_handler import integrate_rock_into_consumers

logger = setup_logger(__name__)


@click.group()
def main():
    """CLI tool for managing CI tasks for charmed analytics."""


@main.command(name="integrate-rock")
@click.argument("metadata_file", type=click.Path(exists=True, dir_okay=False))
@click.argument("base_branch", type=str)
@click.argument("rock_image", type=str)
@click.option(
    "--github-token",
    type=str,
    default=None,
    help="GitHub token (falls back to GH_TOKEN environment variable if not provided).",
)
@click.option(
    "--github-username",
    type=str,
    default="__token__",
    show_default=True,
    help="GitHub username to use for authentication.",
)
@click.option(
    "--github-email",
    type=str,
    default=None,
    help="GitHub email to use for git commits (overrides default noreply format).",
)
@click.option(
    "--clone-dir",
    default="/tmp",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Directory where consumer repositories will be cloned.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Simulate integration without committing or opening PRs.",
)
@click.option(
    "--triggering-pr",
    type=str,
    default=None,
    help="URL of the GitHub PR that triggered this integration (for traceability).",
)
def integrate_rock_command(
    metadata_file: str,
    base_branch: str,
    rock_image: str,
    github_token: str | None,
    github_username: str,
    github_email: str | None,
    clone_dir: str,
    dry_run: bool,
    triggering_pr: str | None,
) -> None:
    """
    Integrate a rock image into all consumers listed in the metadata file.

    METADATA_FILE: Path to rock-ci-metadata.yaml

    BASE_BRANCH: Branch to merge the PR into (e.g. main)

    ROCK_IMAGE: Image reference (e.g. ghcr.io/canonical/foo:1.0.0)
    """
    logger.info("Executing integrate-rock command")

    try:
        token = github_token or os.environ.get("GH_TOKEN")
        if not token:
            raise click.ClickException("GitHub token not provided and GH_TOKEN not set.")

        email = (
            github_email
            or os.environ.get("GH_USER_EMAIL")
            or f"{github_username}@users.noreply.github.com"
        )

        integrate_rock_into_consumers(
            metadata_path=Path(metadata_file),
            rock_image=rock_image,
            clone_base_dir=Path(clone_dir),
            github_token=token,
            github_username=github_username,
            github_email=email,
            base_branch=base_branch,
            dry_run=dry_run,
            triggering_pr=triggering_pr,
        )
    except Exception as e:
        logger.exception(f"Failed to integrate rock image: {e}")
        click.get_current_context().exit(1)


if __name__ == "__main__":
    main()
