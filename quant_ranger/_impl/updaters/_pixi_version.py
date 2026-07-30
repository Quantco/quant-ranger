import re
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal, override

import tomlkit
import typer
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from tomlkit.exceptions import ParseError

from quant_ranger._impl.cli_options import ScheduleOption, SiteConfigParameter
from quant_ranger._impl.git import RepositoryCheckout
from quant_ranger._impl.github import PullRequestOptions
from quant_ranger._impl.models import (
    RepositoryRef,
    Schedule,
    Status,
    UpdateItem,
    UpdateOptions,
    UpdateOutcome,
    UpdateOutput,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.scanners import Scanner

from ._base import Updater, UpdateTask

PIXI_VERSION_PR_BODY = (
    "Update to [pixi {version}]"
    "(https://github.com/prefix-dev/pixi/releases/tag/{version})"
)
# A pixi version as written by setup-pixi workflows; must stay in sync with
# the version group of PIXI_VERSION_PATTERN.
PIXI_VERSION_FORMAT = re.compile(r"v\d+\.\d+\.\d+")
PIXI_VERSION_PATTERN = re.compile(
    rf"(pixi-version:\s*)['\"]?({PIXI_VERSION_FORMAT.pattern})['\"]?"
)
PIXI_LOCKFILE = "pixi.lock"


def _validate_pixi_version(value: str | None) -> str | None:
    if value is not None and PIXI_VERSION_FORMAT.fullmatch(value) is None:
        raise typer.BadParameter(f"{value!r} does not have the form v0.70.0.")
    return value


class PixiVersionUpdaterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    autoupdate_branch: str = Field(
        default="pixi-version-autoupdate",
        alias="autoupdate-branch",
    )
    autoupdate_commit_message: str = Field(
        default="chore: Update pixi version",
        alias="autoupdate-commit-message",
    )
    autoupdate_schedule: Schedule | Literal["never"] = Field(
        default=Schedule.MONTHLY,
        alias="autoupdate-schedule",
    )
    autoupdate_pull_request_labels: list[str] = Field(
        default=["dependencies"],
        alias="autoupdate-pull-request-labels",
    )


class ToolConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    pixi_version_updater: PixiVersionUpdaterConfig = Field(
        default=PixiVersionUpdaterConfig(),
        alias="pixi-version-updater",
    )


class PixiTomlConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tool: ToolConfig = ToolConfig()


class PixiVersionItem(UpdateItem):
    """Update item for one repository and its parsed pixi-version config."""

    config: PixiVersionUpdaterConfig


class PixiVersionScanner(Scanner[PixiVersionItem]):
    """Scanner for repositories with pixi lockfiles matching scheduled runs."""

    def __init__(self, schedule: Schedule | None = None) -> None:
        self.schedule = schedule

    @override
    def scan_repository(
        self,
        repository_ref: RepositoryRef,
        context: RunContext,
    ) -> Sequence[PixiVersionItem]:
        lockfiles = context.github_client.find_files_by_name(
            repository_ref,
            PIXI_LOCKFILE,
        )
        if not lockfiles:
            context.logger.debug("No pixi.lock file found.")
            return []

        config = self._read_config(repository_ref, context)
        if self.schedule is not None and config.autoupdate_schedule != self.schedule:
            context.logger.debug(
                f"Skipping repository: configured schedule is "
                f"{config.autoupdate_schedule}; current scheduled run is {self.schedule}."
            )
            return []

        return [PixiVersionItem(repository_ref=repository_ref, config=config)]

    def _read_config(
        self,
        repository_ref: RepositoryRef,
        context: RunContext,
    ) -> PixiVersionUpdaterConfig:
        contents = context.github_client.get_file_content(repository_ref, "pixi.toml")
        if contents is None:
            return PixiVersionUpdaterConfig()

        try:
            parsed = tomlkit.parse(contents).unwrap()
            return PixiTomlConfig.model_validate(parsed).tool.pixi_version_updater
        except (ParseError, ValidationError) as error:
            context.logger.warning(
                "Could not parse pixi.toml; using default pixi-version updater "
                f"config: {error}"
            )
            return PixiVersionUpdaterConfig()


class PixiVersionOptions(UpdateOptions):
    schedule: ScheduleOption = None
    pixi_version: Annotated[
        str | None,
        typer.Option(
            "--pixi-version",
            callback=_validate_pixi_version,
            help=(
                "Update to this pixi version (e.g. v0.70.0) instead of resolving "
                "the latest release from GitHub."
            ),
        ),
    ] = None
    setup_pixi_marker: Annotated[
        str,
        SiteConfigParameter(
            lambda site_config: typer.Option(
                "--setup-pixi-marker",
                default_factory=lambda: site_config.pixi_version_setup_pixi_marker,
                show_default=site_config.pixi_version_setup_pixi_marker,
                help=(
                    "Only update workflow files containing this marker, e.g. when "
                    "using a fork of setup-pixi."
                ),
            ),
        ),
    ]


class PixiVersionUpdateTask(
    UpdateTask[PixiVersionItem, UpdateOutput, PixiVersionOptions]
):
    def __init__(
        self,
        checkout: RepositoryCheckout,
        context: RunContext,
        *,
        item: PixiVersionItem,
        options: PixiVersionOptions,
        latest_pixi_version: str,
    ) -> None:
        super().__init__(checkout, context, item=item, options=options)
        self.latest_pixi_version = latest_pixi_version

    @override
    def run(self) -> UpdateOutcome:
        config = self.item.config

        latest_pixi_version = self.latest_pixi_version
        self.context.logger.debug(f"Latest pixi version: {latest_pixi_version}")
        updated_files = self._update_workflow_files(latest_pixi_version)
        if not updated_files:
            self.context.logger.debug("All workflow files are up-to-date")
            return UpdateOutcome(result=Status.UP_TO_DATE)
        self.checkout.add_all()

        pr_opened = self.context.github_client.create_pull_request(
            self.checkout,
            PullRequestOptions(
                title=config.autoupdate_commit_message,
                body=PIXI_VERSION_PR_BODY.format(version=latest_pixi_version),
                source_branch=config.autoupdate_branch,
                target_branch=self.checkout.repository_ref.branch,
                labels=config.autoupdate_pull_request_labels,
                quant_ranger_id=PixiVersionUpdater.name,
            ),
            self.context.logger,
        )

        if not pr_opened:
            return UpdateOutcome(result=Status.SKIPPED)

        return UpdateOutcome(result=Status.UPDATED)

    def _update_workflow_files(self, latest_pixi_version: str) -> list[Path]:
        updated_files: list[Path] = []
        workflow_dir = self.checkout.absolute_path / ".github" / "workflows"

        try:
            workflow_files = sorted(
                entry
                for entry in workflow_dir.iterdir()
                if entry.is_file() and entry.suffix in {".yml", ".yaml"}
            )
        except OSError:
            self.context.logger.debug("No .github/workflows directory found")
            return updated_files

        for workflow_file in workflow_files:
            content = workflow_file.read_text()
            if self.options.setup_pixi_marker not in content:
                continue

            file_updated = False

            def replace_version(match: re.Match[str]) -> str:
                nonlocal file_updated
                if match.group(2) == latest_pixi_version:
                    return match.group(0)
                file_updated = True
                return f"{match.group(1)}{latest_pixi_version}"

            updated_content = PIXI_VERSION_PATTERN.sub(replace_version, content)
            if file_updated:
                workflow_file.write_text(updated_content)
                updated_files.append(workflow_file)

        return updated_files


class PixiVersionUpdater(Updater[PixiVersionItem, UpdateOutput, PixiVersionOptions]):
    name = "pixi-version"
    description = (
        "Update pinned Pixi versions. Rewrites marked setup-pixi workflow "
        "entries to a selected or latest release."
    )
    task_type = PixiVersionUpdateTask

    @override
    def __init__(self, options: PixiVersionOptions) -> None:
        super().__init__(options)
        self.scanner = PixiVersionScanner(schedule=self.options.schedule)
        self._latest_pixi_version = options.pixi_version
        self._latest_pixi_version_lock = threading.Lock()

    @override
    def make_task(
        self,
        item: PixiVersionItem,
        checkout: RepositoryCheckout,
        context: RunContext,
    ) -> PixiVersionUpdateTask:
        return PixiVersionUpdateTask(
            checkout=checkout,
            context=context,
            item=item,
            options=self.options,
            latest_pixi_version=self._get_latest_pixi_version(context),
        )

    def _get_latest_pixi_version(self, context: RunContext) -> str:
        # Tasks may run concurrently; resolve the latest release only once.
        with self._latest_pixi_version_lock:
            if self._latest_pixi_version is None:
                self._latest_pixi_version = context.github_client.get_latest_release(
                    "prefix-dev",
                    "pixi",
                )
            return self._latest_pixi_version
