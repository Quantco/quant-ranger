from collections.abc import Sequence
from typing import Annotated, override

import typer
from pydantic import BaseModel, ConfigDict
from typer.models import OptionInfo

from quant_ranger._impl.cli_options import SiteConfigParameter
from quant_ranger._impl.github import PullRequestOptions
from quant_ranger._impl.helpers import CommandError
from quant_ranger._impl.logger import Logger
from quant_ranger._impl.models import (
    RepositoryRef,
    Status,
    UpdateItem,
    UpdateOptions,
    UpdateOutcome,
    UpdateOutput,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.scanners import Scanner
from quant_ranger._impl.site_config import (
    CopierMigration,
    CopierMigrationValue,
    SiteConfig,
)

from .._base import Updater, UpdateTask
from ._common import (
    COPIER_ANSWERS_FILE,
    CopierAnswers,
    attempt_mergiraf_solve,
    github_server_host_from_repository_url,
    is_trusted_template,
    parse_copier_answers,
    parse_template_repository_for_host,
    run_copier_command,
    run_pixi_lock_if_manifest_changed,
    untrusted_template_message,
)


class CopierMigrationTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    migration_key: str
    desired_value: CopierMigrationValue

    @property
    def copier_argument(self) -> str:
        return f"{self.migration_key}={_format_copier_data_value(self.desired_value)}"


class CopierMigrationUpdateItem(UpdateItem):
    migration: str
    migration_target: CopierMigrationTarget
    src_path: str
    github_server_host: str
    copier_answers_content: str


def _make_migration_target(
    answers: CopierAnswers,
    migration: CopierMigration,
    logger: Logger,
) -> CopierMigrationTarget | None:
    answer_key = migration.answer_key
    extra_answers = answers.model_extra or {}
    if answer_key not in extra_answers:
        logger.debug(
            f"Copier answers do not define {answer_key}; migration is not needed."
        )
        return None

    current_value = extra_answers[answer_key]
    if not isinstance(current_value, CopierMigrationValue):
        raise ValueError(
            f"Copier answer {answer_key} has unsupported value {current_value!r}."
        )

    desired_value = migration.resolve_desired_value(current_value)
    if desired_value == current_value:
        logger.debug(
            f"Copier answer {answer_key} "
            "already satisfies the desired state; migration is not needed."
        )
        return None

    return CopierMigrationTarget(
        migration_key=answer_key,
        desired_value=desired_value,
    )


class CopierMigrationScanner(Scanner[CopierMigrationUpdateItem]):
    def __init__(
        self,
        *,
        migration: str,
    ) -> None:
        self.migration = migration

    @override
    def scan_repository(
        self,
        repository_ref: RepositoryRef,
        context: RunContext,
    ) -> Sequence[CopierMigrationUpdateItem]:
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

        migration = context.site_config.copier_migrations[self.migration]
        template = f"{github_server_host}/{template_repository.full_name}".lower()
        if template not in migration.templates:
            context.logger.debug(
                f"Copier migration {self.migration} does not apply to template "
                f"{template}."
            )
            return []

        migration_target = _make_migration_target(
            answers,
            migration,
            context.logger,
        )
        if migration_target is None:
            return []

        return [
            CopierMigrationUpdateItem(
                repository_ref=repository_ref,
                migration=self.migration,
                migration_target=migration_target,
                src_path=answers.src_path,
                github_server_host=github_server_host,
                copier_answers_content=content,
            )
        ]


def _copier_migration_option(site_config: SiteConfig) -> OptionInfo:
    migration_names = tuple(site_config.copier_migrations)

    def validate_migration(value: str) -> str:
        if value not in migration_names:
            choices = ", ".join(repr(migration) for migration in migration_names)
            qualifier = "" if len(migration_names) == 1 else "one of "
            raise typer.BadParameter(f"{value!r} is not {qualifier}{choices}.")
        return value

    def complete_migration(incomplete: str) -> list[str]:
        return [
            migration
            for migration in migration_names
            if migration.startswith(incomplete)
        ]

    return typer.Option(
        "--migration",
        callback=validate_migration,
        autocompletion=complete_migration,
        metavar=f"[{'|'.join(migration_names)}]",
        help="Copier migration to run.",
    )


class CopierMigrationOptions(UpdateOptions):
    migration: Annotated[
        str,
        SiteConfigParameter(_copier_migration_option),
    ]


class CopierMigrationUpdateTask(
    UpdateTask[CopierMigrationUpdateItem, UpdateOutput, CopierMigrationOptions]
):
    @override
    def run(self) -> UpdateOutcome:
        try:
            checkout_copier_answers_content = (
                self.checkout.absolute_path / COPIER_ANSWERS_FILE
            ).read_text()
        except OSError as error:
            return UpdateOutcome(
                result=Status.FAILURE,
                message=f"Could not read {COPIER_ANSWERS_FILE}: {error}",
            )

        if checkout_copier_answers_content != self.item.copier_answers_content:
            return UpdateOutcome(
                result=Status.SKIPPED,
                message=f"{COPIER_ANSWERS_FILE} changed between scanning and checkout.",
            )

        trusted_template = is_trusted_template(
            self.item.src_path,
            self.context.site_config.copier_trusted_templates,
        )
        if not trusted_template:
            self.context.logger.info(
                untrusted_template_message(
                    self.item.repository_ref,
                    self.item.src_path,
                )
            )

        self.context.logger.debug(
            f"Running copier to update to set {self.item.migration_target.copier_argument}."
        )
        copier_args = [
            "copier",
            "update",
            "--defaults",
            "--vcs-ref=:current:",
            "--data",
            self.item.migration_target.copier_argument,
        ]
        if trusted_template:
            copier_args.append("--trust")

        try:
            run_copier_command(
                copier_args,
                self.checkout,
                self.context.logger,
                token=self.context.github_client.token,
                github_server_host=self.item.github_server_host,
            )
        except CommandError as error:
            return UpdateOutcome(
                result=Status.FAILURE,
                message=str(error),
                details=error.details,
            )

        attempt_mergiraf_solve(self.checkout, self.context.logger)
        migration = self.context.site_config.copier_migrations[self.item.migration]
        if migration.post_migration is not None:
            migration.post_migration(self.checkout, self.context)
        run_pixi_lock_if_manifest_changed(self.checkout, self.context.logger)

        self.checkout.add_all()
        if self.checkout.is_clean():
            self.context.logger.debug("No changes detected after copier migration.")
            return UpdateOutcome(result=Status.UP_TO_DATE)

        pull_request = self.context.github_client.create_pull_request(
            self.checkout,
            PullRequestOptions(
                title=migration.pull_request_template.title,
                body=migration.pull_request_template.body,
                source_branch=(
                    f"{migration.pull_request_template.branch_prefix}-"
                    f"{self.item.migration}"
                ),
                target_branch=self.checkout.repository_ref.branch,
                quant_ranger_id=CopierMigrationUpdater.name,
            ),
            self.context.logger,
        )
        return UpdateOutcome(
            result=Status.UPDATED if pull_request.updated else Status.SKIPPED,
            pull_request_number=pull_request.number,
        )


class CopierMigrationUpdater(
    Updater[CopierMigrationUpdateItem, UpdateOutput, CopierMigrationOptions]
):
    name = "copier-migration"
    description = (
        "Apply a Copier-answer migration. Changes a supported template answer "
        "without advancing the template revision."
    )
    task_type = CopierMigrationUpdateTask

    @override
    def __init__(self, options: CopierMigrationOptions) -> None:
        super().__init__(options)
        self.scanner = CopierMigrationScanner(
            migration=self.options.migration,
        )


def _format_copier_data_value(value: CopierMigrationValue) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)
