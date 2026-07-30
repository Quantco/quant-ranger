from typing import Annotated, override

import typer

from quant_ranger import (
    PullRequestOptions,
    Status,
    UpdateOptions,
    UpdateOutcome,
    UpdateOutput,
)
from quant_ranger.updaters import Updater, UpdateTask

from .scanner import PythonProjectItem, PythonProjectScanner


class EnsureConfigOptions(UpdateOptions):
    enabled: Annotated[
        bool,
        typer.Option(
            "--enabled/--disabled",
            help="Enable or disable the example tool.",
        ),
    ] = True


class EnsureConfigTask(
    UpdateTask[PythonProjectItem, UpdateOutput, EnsureConfigOptions]
):
    @override
    def run(self) -> UpdateOutcome:
        config_path = self.checkout.absolute_path / ".example-config"
        desired = f"enabled = {str(self.options.enabled).lower()}\n"
        if config_path.exists() and config_path.read_text() == desired:
            return UpdateOutcome(result=Status.UP_TO_DATE)

        config_path.write_text(desired)
        self.checkout.add(".example-config")
        pull_request_opened = self.context.github_client.create_pull_request(
            self.checkout,
            PullRequestOptions(
                title="chore: configure example tool",
                body=f"Sets the shared tool configuration for {self.item.project_name}.",
                source_branch="quant-ranger-example-config",
                target_branch=self.item.repository_ref.branch,
                quant_ranger_id="ensure-config",
            ),
            self.context.logger,
        )
        return UpdateOutcome(
            result=Status.UPDATED if pull_request_opened else Status.SKIPPED,
        )


class EnsureConfigUpdater(
    Updater[PythonProjectItem, UpdateOutput, EnsureConfigOptions]
):
    name = "ensure-config"
    description = "Add the shared tool configuration."
    scanner = PythonProjectScanner()
    task_type = EnsureConfigTask
