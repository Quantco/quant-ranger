import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import override

from packaging.version import Version

from quant_ranger._impl.github import PullRequestOptions
from quant_ranger._impl.helpers import CommandError
from quant_ranger._impl.models import (
    RepositoryRef,
    Status,
    UpdateItem,
    UpdateOutcome,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.scanners import Scanner

from .._base import Updater, UpdateTask
from ._common import (
    COPIER_ANSWERS_FILE,
    attempt_mergiraf_solve,
    github_server_host_from_repository_url,
    is_trusted_template,
    is_valid_version_tag,
    parse_copier_answers,
    parse_template_repository_for_host,
    run_copier_command,
    run_pixi_lock_if_manifest_changed,
    untrusted_template_message,
)

COPIER_PR_BODY_TEMPLATE = """This PR was automatically generated. Please check for leftover merge conflicts before merging.

Changelog:
{changelog}"""

_MENTION_PATTERN = re.compile(r"@(\S*)")


@dataclass(frozen=True, slots=True)
class CopierTemplateUpdate:
    template_repository: RepositoryRef
    sorted_newer_tags: list[str]
    """Tags newer than the recorded template ref, sorted by PEP 440 version."""

    src_path: str
    github_server_host: str
    copier_answers_content: str


def get_sorted_newer_tags(tags: Iterable[str], current_ref: str) -> list[str]:
    """Return template tags newer than the Copier ref recorded in answers.

    Copier can record branches, commit hashes, or Git describe refs in `_commit`.
    We only accept PEP 440 template tags because tags are the trusted release
    boundary for automatic template updates.
    https://copier.readthedocs.io/en/stable/generating/#templates-versions

    Args:
        tags: Template tags, in any order. Non-version tags are ignored.
        current_ref: The Copier `_commit` value recorded in `.copier-answers.yml`.

    Returns:
        Tags newer than `current_ref`, sorted by PEP 440 version.

    Raises:
        ValueError: If `current_ref` is not a version tag.
    """
    if not is_valid_version_tag(current_ref):
        msg = f"Incompatible _commit format {current_ref!r}; only tags are allowed."
        raise ValueError(msg)
    current_version = Version(current_ref)

    tags_by_version: dict[Version, str] = dict(
        sorted((Version(tag), tag) for tag in tags if is_valid_version_tag(tag))
    )

    return [
        tag for version, tag in tags_by_version.items() if version > current_version
    ]


class CopierUpdateItem(UpdateItem):
    """Update item for one repository and its newer template tags."""

    template_update: CopierTemplateUpdate


class CopierScanner(Scanner[CopierUpdateItem]):
    @override
    def scan_repository(
        self,
        repository_ref: RepositoryRef,
        context: RunContext,
    ) -> Sequence[CopierUpdateItem]:
        content = context.github_client.get_file_content(
            repository_ref,
            COPIER_ANSWERS_FILE,
        )
        if content is None:
            context.logger.debug(f"No {COPIER_ANSWERS_FILE} file found.")
            return []

        answers = parse_copier_answers(content)

        github_server_host = github_server_host_from_repository_url(
            context.github_client.get_repository_url(repository_ref)
        )

        template_repository = parse_template_repository_for_host(
            answers.src_path,
            github_server_host=github_server_host,
        )
        tags = context.github_client.get_repo_tags(
            template_repository.owner,
            template_repository.name,
        )
        sorted_newer_tags = get_sorted_newer_tags(tags, answers.commit)

        if not sorted_newer_tags:
            context.logger.debug("No newer copier template tags found.")
            return []

        return [
            CopierUpdateItem(
                repository_ref=repository_ref,
                template_update=CopierTemplateUpdate(
                    template_repository=template_repository,
                    sorted_newer_tags=sorted_newer_tags,
                    src_path=answers.src_path,
                    github_server_host=github_server_host,
                    copier_answers_content=content,
                ),
            )
        ]


class CopierUpdateTask(UpdateTask[CopierUpdateItem]):
    @override
    def run(self) -> UpdateOutcome:
        template_update = self.item.template_update
        template_repository = template_update.template_repository
        latest_tag = template_update.sorted_newer_tags[-1]
        try:
            checkout_copier_answers_content = (
                self.checkout.absolute_path / COPIER_ANSWERS_FILE
            ).read_text()
        except OSError as error:
            return UpdateOutcome(
                result=Status.FAILURE,
                message=f"Could not read {COPIER_ANSWERS_FILE}: {error}",
            )

        if checkout_copier_answers_content != template_update.copier_answers_content:
            return UpdateOutcome(
                result=Status.SKIPPED,
                message=f"{COPIER_ANSWERS_FILE} changed between scanning and checkout.",
            )

        trusted_template = is_trusted_template(
            template_update.src_path,
            self.context.site_config.copier_trusted_templates,
        )
        if not trusted_template:
            self.context.logger.info(
                untrusted_template_message(
                    self.item.repository_ref,
                    template_update.src_path,
                )
            )

        self.context.logger.debug(f"Running copier to update to {latest_tag}.")
        copier_args = [
            "copier",
            "update",
            f"--vcs-ref={latest_tag}",
            "--defaults",
        ]
        if trusted_template:
            copier_args.append("--trust")

        try:
            run_copier_command(
                copier_args,
                self.checkout,
                self.context.logger,
                token=self.context.github_client.token,
                github_server_host=template_update.github_server_host,
            )
        except CommandError as error:
            return UpdateOutcome(
                result=Status.FAILURE,
                message=str(error),
                details=error.details,
            )

        attempt_mergiraf_solve(self.checkout, self.context.logger)
        run_pixi_lock_if_manifest_changed(self.checkout, self.context.logger)

        self.checkout.add_all()
        if self.checkout.is_clean():
            self.context.logger.debug("No changes detected after copier update.")
            return UpdateOutcome(result=Status.UP_TO_DATE)

        changelog = "\n\n".join(
            "## {tag}\n{message}".format(
                tag=tag,
                message=self.context.github_client.get_repo_tag_message(
                    template_repository.owner,
                    template_repository.name,
                    tag,
                )
                or "Missing Changelog",
            )
            for tag in template_update.sorted_newer_tags
        )
        # Avoid notifying people mentioned in template changelogs when
        # quant-ranger opens the update PR.
        changelog = _MENTION_PATTERN.sub(r"\1", changelog)

        pull_request = self.context.github_client.create_pull_request(
            self.checkout,
            PullRequestOptions(
                title=f"chore: Update copier template to {latest_tag}",
                body=COPIER_PR_BODY_TEMPLATE.format(changelog=changelog),
                source_branch=f"copier-autoupdate-{latest_tag}",
                target_branch=self.checkout.repository_ref.branch,
                quant_ranger_id=CopierUpdater.name,
            ),
            self.context.logger,
        )
        return UpdateOutcome(
            result=Status.UPDATED if pull_request.updated else Status.SKIPPED,
            pull_request_number=pull_request.number,
        )


class CopierUpdater(Updater[CopierUpdateItem]):
    name = "copier"
    description = (
        "Update a Copier template. Advances root `.copier-answers.yml` projects "
        "to the newest PEP 440 tag."
    )
    scanner = CopierScanner()
    task_type = CopierUpdateTask
