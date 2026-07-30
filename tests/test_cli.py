import json
import runpy
import sys
from collections.abc import Mapping, Sequence
from importlib import import_module
from pathlib import Path
from textwrap import dedent
from typing import Annotated, Any, ClassVar, cast, get_args, override

import pytest
import typer
from pydantic import Field
from rich.text import Text
from typer.models import ArgumentInfo, OptionInfo
from typer.testing import CliRunner
from typer.utils import DefaultFactoryAndDefaultValueError

from quant_ranger._impl.aggregators import AnyAggregator
from quant_ranger._impl.artifacts import write_results_file
from quant_ranger._impl.cli._aggregate import (
    AggregateRunOptions,
    make_aggregate_command,
)
from quant_ranger._impl.cli._app import (
    DEBUG_WARNING,
    ROOT_USER_WARNING,
    main,
    make_app,
)
from quant_ranger._impl.cli._helpers import command_signature
from quant_ranger._impl.cli._update import make_update_command
from quant_ranger._impl.github import GitHubClient, GitHubError
from quant_ranger._impl.helpers import CliError, CommandError, ExecOutput
from quant_ranger._impl.logger import ConsoleLogger, Logger
from quant_ranger._impl.models import (
    PathUpdateItem,
    RepositoryRef,
    ScanFailure,
    Schedule,
    Status,
    UpdateItem,
    UpdateOptions,
    UpdateOutcome,
    UpdateOutput,
    UpdateResult,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.testing import FakeGitHubClient
from quant_ranger._impl.updaters import AnyUpdater, ZizmorUpdater
from quant_ranger._impl.updaters._copier._migration import CopierMigrationOptions
from quant_ranger._impl.updaters._custom import CustomUpdaterOptions
from quant_ranger.aggregators import (
    Aggregator,
    AggregatorOptions,
)
from quant_ranger.scanners import ScanResult
from quant_ranger.site_config import SiteConfig, SiteConfigParameter
from quant_ranger.updaters import Updater, UpdateTask

runner = CliRunner()
cli_aggregate_module = import_module("quant_ranger._impl.cli._aggregate")
cli_app_module = import_module("quant_ranger._impl.cli._app")
cli_update_module = import_module("quant_ranger._impl.cli._update")


@pytest.fixture(scope="module")
def app() -> typer.Typer:
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            cli_app_module,
            "load_site_config",
            lambda **_kwargs: SiteConfig(default_owner="quantco"),
        )
        return make_app(load_plugins=False)


@pytest.fixture(autouse=True)
def non_root_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_app_module.os, "geteuid", lambda: 1, raising=False)


def _normalized_root_warning() -> str:
    return " ".join(ROOT_USER_WARNING.split())


def _normalized_output(output: str) -> str:
    return " ".join(output.split())


def _plain_output(output: str) -> str:
    return Text.from_ansi(output).plain


def _use_fake_github_clients(
    monkeypatch: pytest.MonkeyPatch,
    *github_clients: FakeGitHubClient,
) -> None:
    def fake_make_run_contexts(**kwargs: Any) -> list[RunContext]:
        for github_client in github_clients:
            github_client.publish_changes = kwargs["publish_changes"]
        return [
            RunContext(
                site_config=kwargs["site_config"],
                github_client=cast(GitHubClient, github_client),
                logger=kwargs["logger"],
            )
            for github_client in github_clients
        ]

    monkeypatch.setattr(cli_update_module, "_make_run_contexts", fake_make_run_contexts)


def _record_run_update_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        cli_update_module,
        "_run_update",
        lambda **kwargs: calls.append(kwargs),
    )
    return calls


def _record_zizmor_update_items(
    monkeypatch: pytest.MonkeyPatch,
) -> list[UpdateItem]:
    captured_items: list[UpdateItem] = []

    def fake_update_all(
        self: Updater[UpdateItem],
        update_items: Sequence[UpdateItem],
        context: RunContext,
        *,
        concurrency: int = 1,
    ) -> list[UpdateResult]:
        del self, context, concurrency
        captured_items.extend(update_items)
        return []

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._zizmor.ZizmorUpdater.update_all",
        fake_update_all,
    )
    return captured_items


def _run_zizmor_update(
    app: typer.Typer,
    *,
    raw_repositories: Sequence[str] = (),
    owner: str | None = None,
    all_installed_repositories: bool = False,
) -> Any:
    arguments = ["update"]
    for repository in raw_repositories:
        arguments.extend(["--repository", repository])
    if owner is not None:
        arguments.extend(["--owner", owner])
    if all_installed_repositories:
        arguments.append("--all-installed-repositories")
    arguments.append("zizmor")
    return runner.invoke(app, arguments)


def test_root_command_prints_help_when_no_subcommand_is_given(
    app: typer.Typer,
) -> None:
    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "Run repository maintenance and process results." in result.output


def test_version_option_prints_program_version(app: typer.Typer) -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.startswith("quant-ranger ")


def test_update_command_passes_options_to_run_update(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _record_run_update_calls(monkeypatch)

    result = runner.invoke(
        app,
        [
            "update",
            "--repository",
            "example",
            "--owner",
            "Other",
            "--gh",
            "--github-api-url",
            "https://github.example/api/v3",
            "--publish-changes",
            "--force-push",
            "--jobs",
            "3",
            "zizmor",
        ],
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["updater"].name == "zizmor"
    assert call["updater"].options == UpdateOptions()
    assert call["raw_repositories"] == ["example"]
    assert call["owner"] == "Other"
    assert call["all_installed_repositories"] is False
    assert call["use_gh"] is True
    assert call["github_api_url"] == "https://github.example/api/v3"
    assert call["concurrency"] == 3
    assert call["publish_changes"] is True
    assert call["force_push"] is True
    assert call["show_pr_details"] is False
    assert call["pr_details_diff_lines"] is None


@pytest.mark.parametrize(
    ("arguments", "expected_diff_lines"),
    [
        pytest.param(["--pr-details"], None, id="full"),
        pytest.param(
            ["--pr-details-diff-lines", "20"],
            20,
            id="limited",
        ),
    ],
)
def test_update_command_passes_pull_request_details(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    expected_diff_lines: int | None,
) -> None:
    calls = _record_run_update_calls(monkeypatch)

    result = runner.invoke(
        app,
        ["update", *arguments, "zizmor"],
    )

    assert result.exit_code == 0
    assert calls[0]["show_pr_details"] is True
    assert calls[0]["pr_details_diff_lines"] == expected_diff_lines


def test_update_command_uses_site_default_owner(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _record_run_update_calls(monkeypatch)

    result = runner.invoke(app, ["update", "zizmor"])

    assert result.exit_code == 0
    assert calls[0]["owner"] == "quantco"
    assert calls[0]["all_installed_repositories"] is False


@pytest.mark.parametrize(
    ("selection_arguments", "selection_option"),
    [
        pytest.param(["--owner", "quantco"], "--owner", id="owner"),
        pytest.param(
            ["--repository", "quantco/example"],
            "--repository",
            id="repositories",
        ),
    ],
)
def test_update_command_rejects_selection_with_all_installed_repositories(
    app: typer.Typer,
    selection_arguments: list[str],
    selection_option: str,
) -> None:
    result = runner.invoke(
        app,
        [
            "update",
            *selection_arguments,
            "--all-installed-repositories",
            "zizmor",
        ],
        env={"COLUMNS": "300"},
    )

    assert result.exit_code == 2
    output = _normalized_output(result.output)
    assert selection_option in output
    assert "--all-installed-repositories" in output
    assert "cannot be used" in output
    assert "together" in output


def test_update_command_passes_all_installed_repositories_option(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _record_run_update_calls(monkeypatch)

    result = runner.invoke(
        app,
        ["update", "--all-installed-repositories", "zizmor"],
    )

    assert result.exit_code == 0
    assert calls[0]["owner"] == "quantco"
    assert calls[0]["all_installed_repositories"] is True


@pytest.mark.parametrize(
    "arguments",
    [
        ["update", "--force-push", "zizmor"],
        # Blank repository specs do not select anything and must not bypass
        # the force-push safeguard.
        ["update", "--force-push", "--repository", ", ", "zizmor"],
    ],
)
def test_update_command_rejects_force_push_without_explicit_repositories(
    app: typer.Typer,
    arguments: list[str],
) -> None:
    result = runner.invoke(app, arguments)

    assert result.exit_code == 2
    assert "`--force-push` requires explicit repositories" in _normalized_output(
        result.output
    )


def test_update_command_passes_declared_updater_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CustomOptions(UpdateOptions):
        schedule: Annotated[
            Schedule | None,
            typer.Option("--schedule"),
        ] = None

    class CustomOptionsTask(UpdateTask[UpdateItem, UpdateOutput, CustomOptions]):
        @override
        def run(self) -> UpdateOutcome:
            raise NotImplementedError

    class CustomOptionsUpdater(Updater[UpdateItem, UpdateOutput, CustomOptions]):
        name: ClassVar[str] = "custom"
        task_type: type[UpdateTask[UpdateItem, UpdateOutput, CustomOptions]] = (
            CustomOptionsTask
        )

    calls: list[CustomOptionsUpdater] = []

    def fake_run_update_with_error_handling(
        updater_type: type[CustomOptionsUpdater],
        option_values: Mapping[str, object],
        run_options: object,
    ) -> None:
        del run_options
        updater = updater_type(CustomOptions.model_validate(option_values))
        assert isinstance(updater, CustomOptionsUpdater)
        calls.append(updater)

    custom_app = typer.Typer()

    @custom_app.callback()
    def update_callback(context: typer.Context) -> None:
        context.obj = object()

    custom_app.command("custom")(
        make_update_command(CustomOptionsUpdater, SiteConfig())
    )
    monkeypatch.setattr(
        cli_update_module,
        "_run_update_with_error_handling",
        fake_run_update_with_error_handling,
    )

    result = runner.invoke(custom_app, ["custom", "--schedule", "quarterly"])

    assert result.exit_code == 0
    assert len(calls) == 1
    assert calls[0].options == CustomOptions(schedule=Schedule.QUARTERLY)


def test_update_command_uses_default_factory_of_updater_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FactoryOptions(UpdateOptions):
        labels: Annotated[
            list[str],
            typer.Option("--label"),
        ] = Field(default_factory=lambda: ["automated"])

    class FactoryOptionsTask(UpdateTask[UpdateItem, UpdateOutput, FactoryOptions]):
        @override
        def run(self) -> UpdateOutcome:
            raise NotImplementedError

    class FactoryOptionsUpdater(Updater[UpdateItem, UpdateOutput, FactoryOptions]):
        name: ClassVar[str] = "factory"
        task_type: type[UpdateTask[UpdateItem, UpdateOutput, FactoryOptions]] = (
            FactoryOptionsTask
        )

    option_values_calls: list[Mapping[str, object]] = []

    def fake_run_update_with_error_handling(
        updater_type: type[FactoryOptionsUpdater],
        option_values: Mapping[str, object],
        run_options: object,
    ) -> None:
        del updater_type, run_options
        option_values_calls.append(option_values)

    custom_app = typer.Typer()

    @custom_app.callback()
    def update_callback(context: typer.Context) -> None:
        context.obj = object()

    custom_app.command("factory")(
        make_update_command(FactoryOptionsUpdater, SiteConfig())
    )
    monkeypatch.setattr(
        cli_update_module,
        "_run_update_with_error_handling",
        fake_run_update_with_error_handling,
    )

    result = runner.invoke(custom_app, ["factory"])

    assert result.exit_code == 0
    assert option_values_calls == [{"labels": ["automated"]}]


def test_command_signature_resolves_site_config_option() -> None:
    other_metadata = object()

    class ExtendedSiteConfig(SiteConfig):
        choices: tuple[str, ...]

    def migration_option(site_config: SiteConfig) -> Any:
        assert isinstance(site_config, ExtendedSiteConfig)
        return typer.Option(
            "--migration",
            metavar=f"[{'|'.join(site_config.choices)}]",
            default_factory=lambda: site_config.pixi_version_setup_pixi_marker,
        )

    class ConfigOptions(UpdateOptions):
        migration: Annotated[
            str,
            other_metadata,
            SiteConfigParameter(migration_option),
        ]
        label: str = "static"

    site_config = ExtendedSiteConfig(
        choices=("preview", "stable"),
        pixi_version_setup_pixi_marker="preview",
    )
    signature = command_signature(ConfigOptions, site_config=site_config)
    parameter = signature.parameters["migration"]
    _, *metadata = get_args(parameter.annotation)
    calls: list[Mapping[str, object]] = []

    def command(context: typer.Context, **option_values: object) -> None:
        del context
        calls.append(option_values)

    setattr(command, "__signature__", signature)
    app = typer.Typer()
    app.command()(command)
    defaulted = runner.invoke(app)

    assert defaulted.exit_code == 0
    assert calls == [{"migration": "preview", "label": "static"}]
    assert metadata[0] is other_metadata
    option = metadata[1]
    assert isinstance(option, OptionInfo)
    assert option.metavar == "[preview|stable]"


def test_site_config_parameter_rejects_double_default() -> None:
    class DoubleDefaultOptions(UpdateOptions):
        my_value: Annotated[
            str,
            SiteConfigParameter(
                lambda _site_config: typer.Option(
                    "--my-value",
                    default_factory=lambda: "site-value",
                ),
            ),
        ] = "updater-value"

    signature = command_signature(DoubleDefaultOptions, site_config=SiteConfig())

    def command(context: typer.Context, **option_values: object) -> None:
        del context, option_values

    setattr(command, "__signature__", signature)
    app = typer.Typer()
    app.command()(command)

    with pytest.raises(
        DefaultFactoryAndDefaultValueError,
        match="Cannot specify `default_factory` and a default value together",
    ):
        runner.invoke(app)


def test_site_config_parameter_validates_factory_result() -> None:
    site_config = SiteConfig()
    argument = SiteConfigParameter(lambda _: typer.Argument()).resolve(site_config)

    assert isinstance(argument, ArgumentInfo)

    invalid = SiteConfigParameter(cast(Any, lambda _: object()))
    with pytest.raises(
        TypeError,
        match=r"must return typer.Option\(\) or typer.Argument\(\)",
    ):
        invalid.resolve(site_config)


def test_update_command_passes_results_file_to_run_update(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _record_run_update_calls(monkeypatch)
    results_file = tmp_path / "results.json"

    result = runner.invoke(
        app,
        [
            "update",
            "--repository",
            "example",
            "--results-file",
            str(results_file),
            "zizmor",
        ],
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    assert calls[0]["results_file"] == results_file


def test_aggregate_command_runs_log_failures_from_results_file(
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    results_file = tmp_path / "results.json"
    write_results_file(
        results_file,
        updater=ZizmorUpdater(UpdateOptions()),
        results=[
            UpdateResult(
                result=Status.FAILURE,
                item=UpdateItem(
                    repository_ref=RepositoryRef(owner="quantco", name="example")
                ),
                message="boom\nmore details",
            )
        ],
        scan_failures=(
            ScanFailure(
                repository_ref=RepositoryRef(owner="quantco", name="scan-broken"),
                message="scan boom",
            ),
        ),
    )

    result = runner.invoke(
        app,
        [
            "aggregate",
            "log-failures",
            str(results_file),
        ],
    )

    assert result.exit_code == 0
    assert 'Running aggregator "log-failures"...' in result.output
    assert "quantco/example" in result.output
    assert "boom" in result.output
    assert "more details" in result.output
    assert "quantco/scan-broken (scan)" in result.output
    assert "scan boom" in result.output


def test_aggregate_command_logs_unexpected_exceptions(
    tmp_path: Path,
) -> None:
    class FailingAggregator(Aggregator[UpdateItem, UpdateOutput, AggregatorOptions]):
        name: ClassVar[str] = "failing"

        @override
        def aggregate(
            self,
            results: Sequence[UpdateResult[UpdateOutput, UpdateItem]],
            logger: Logger,
            scan_failures: Sequence[ScanFailure],
            updater_name: str,
        ) -> None:
            del results, logger, scan_failures
            raise RuntimeError("boom")

    results_file = _write_sample_results_file(tmp_path / "results.json")

    result = runner.invoke(
        _custom_aggregate_app(FailingAggregator),
        ["failing", str(results_file)],
    )

    assert result.exit_code == 1


def test_aggregate_command_passes_deliberate_exits_through(
    tmp_path: Path,
) -> None:
    class ExitingAggregator(Aggregator[UpdateItem, UpdateOutput, AggregatorOptions]):
        name: ClassVar[str] = "exiting"

        @override
        def aggregate(
            self,
            results: Sequence[UpdateResult[UpdateOutput, UpdateItem]],
            logger: Logger,
            scan_failures: Sequence[ScanFailure],
            updater_name: str,
        ) -> None:
            del results, logger, scan_failures
            raise typer.Exit(3)

    results_file = _write_sample_results_file(tmp_path / "results.json")

    result = runner.invoke(
        _custom_aggregate_app(ExitingAggregator),
        ["exiting", str(results_file)],
    )

    assert result.exit_code == 3


def test_aggregate_command_exits_via_sigint_on_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class InterruptingAggregator(
        Aggregator[UpdateItem, UpdateOutput, AggregatorOptions]
    ):
        name: ClassVar[str] = "interrupting"

        @override
        def aggregate(
            self,
            results: Sequence[UpdateResult[UpdateOutput, UpdateItem]],
            logger: Logger,
            scan_failures: Sequence[ScanFailure],
            updater_name: str,
        ) -> None:
            del results, logger, scan_failures
            raise KeyboardInterrupt

    exit_calls = 0

    def fake_exit_via_sigint() -> None:
        nonlocal exit_calls
        exit_calls += 1
        raise typer.Exit(1)

    monkeypatch.setattr(cli_aggregate_module, "exit_via_sigint", fake_exit_via_sigint)
    results_file = _write_sample_results_file(tmp_path / "results.json")

    result = runner.invoke(
        _custom_aggregate_app(InterruptingAggregator),
        ["interrupting", str(results_file)],
    )

    assert exit_calls == 1
    assert result.exit_code == 1


def test_aggregate_command_rejects_item_type_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class PathItemAggregator(
        Aggregator[PathUpdateItem, UpdateOutput, AggregatorOptions]
    ):
        name: ClassVar[str] = "path-item"

        @override
        def aggregate(
            self,
            results: Sequence[UpdateResult[UpdateOutput, PathUpdateItem]],
            logger: Logger,
            scan_failures: Sequence[ScanFailure],
            updater_name: str,
        ) -> None:
            raise NotImplementedError

    def fake_aggregate(
        self: PathItemAggregator,
        results: Sequence[UpdateResult[UpdateOutput, PathUpdateItem]],
        logger: Logger,
        scan_failures: Sequence[ScanFailure],
    ) -> None:
        del self, results, logger, scan_failures
        raise AssertionError("aggregate should not be called")

    custom_app = _custom_aggregate_app(PathItemAggregator)
    monkeypatch.setattr(PathItemAggregator, "aggregate", fake_aggregate)
    results_file = _write_sample_results_file(tmp_path / "results.json")

    result = runner.invoke(custom_app, ["path-item", str(results_file)])

    assert result.exit_code == 2
    assert "expects item type PathUpdateItem or a subclass" in _normalized_output(
        result.output
    )


def test_aggregate_command_rejects_output_type_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class SpecificOutput(UpdateOutput):
        pass

    class SpecificOutputAggregator(
        Aggregator[UpdateItem, SpecificOutput, AggregatorOptions]
    ):
        name: ClassVar[str] = "specific-output"

        @override
        def aggregate(
            self,
            results: Sequence[UpdateResult[SpecificOutput, UpdateItem]],
            logger: Logger,
            scan_failures: Sequence[ScanFailure],
            updater_name: str,
        ) -> None:
            raise NotImplementedError

    def fake_aggregate(
        self: SpecificOutputAggregator,
        results: Sequence[UpdateResult[SpecificOutput, UpdateItem]],
        logger: Logger,
        scan_failures: Sequence[ScanFailure],
    ) -> None:
        del self, results, logger, scan_failures
        raise AssertionError("aggregate should not be called")

    custom_app = _custom_aggregate_app(SpecificOutputAggregator)
    monkeypatch.setattr(SpecificOutputAggregator, "aggregate", fake_aggregate)
    results_file = _write_sample_results_file(tmp_path / "results.json")

    result = runner.invoke(custom_app, ["specific-output", str(results_file)])

    assert result.exit_code == 2
    assert "expects output type SpecificOutput or a subclass" in _normalized_output(
        result.output
    )


def test_update_command_passes_copier_migration_option(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []

    def fake_run_update(**kwargs: Any) -> None:
        calls.append(kwargs["updater"])

    monkeypatch.setattr(cli_update_module, "_run_update", fake_run_update)

    result = runner.invoke(
        app,
        [
            "update",
            "--repository",
            "example",
            "copier-migration",
            "--migration",
            "example",
        ],
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    assert calls[0].name == "copier-migration"
    assert calls[0].options == CopierMigrationOptions(migration="example")


def test_update_command_rejects_unknown_copier_migration(
    app: typer.Typer,
) -> None:
    result = runner.invoke(
        app,
        [
            "update",
            "--repository",
            "example",
            "copier-migration",
            "--migration",
            "unknown",
        ],
    )

    assert result.exit_code == 2
    output = _plain_output(result.output)
    assert "Invalid value" in output
    assert "--migration" in output
    assert "'unknown' is not 'example'" in output


def test_update_command_passes_custom_updater_path(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    custom_updater_path = tmp_path / "custom_updater.py"
    custom_updater_path.write_text(
        dedent(
            """
            from quant_ranger import Status, UpdateItem, UpdateOutcome
            from quant_ranger.scanners import RepositoriesScanner
            from quant_ranger.updaters import CustomFileUpdater, UpdateTask


            class NoopTask(UpdateTask[UpdateItem]):
                def run(self):
                    return UpdateOutcome(result=Status.UP_TO_DATE)


            class NoopUpdater(CustomFileUpdater[UpdateItem]):
                name = "noop"
                scanner = RepositoriesScanner()
                task_type = NoopTask


            updater = NoopUpdater()
            """
        )
    )
    calls: list[Any] = []

    def fake_run_update(**kwargs: Any) -> None:
        calls.append(kwargs["updater"])

    monkeypatch.setattr(cli_update_module, "_run_update", fake_run_update)

    result = runner.invoke(
        app,
        [
            "update",
            "--repository",
            "example",
            "custom",
            "--path",
            str(custom_updater_path),
        ],
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    assert calls[0].name == "custom"
    assert calls[0].options == CustomUpdaterOptions(path=custom_updater_path.resolve())


def test_update_command_rejects_results_file_for_custom_updater(
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    custom_updater_path = tmp_path / "custom_updater.py"
    imported_marker = tmp_path / "imported.txt"
    custom_updater_path.write_text(
        dedent(
            f"""
            from pathlib import Path

            from quant_ranger import Status, UpdateItem, UpdateOutcome
            from quant_ranger.scanners import RepositoriesScanner
            from quant_ranger.updaters import CustomFileUpdater, UpdateTask


            Path({str(imported_marker)!r}).write_text("imported")


            class NoopTask(UpdateTask[UpdateItem]):
                def run(self):
                    return UpdateOutcome(result=Status.UP_TO_DATE)


            class NoopUpdater(CustomFileUpdater[UpdateItem]):
                name = "noop"
                scanner = RepositoriesScanner()
                task_type = NoopTask


            updater = NoopUpdater()
            """
        )
    )
    results_file = tmp_path / "results.json"

    result = runner.invoke(
        app,
        [
            "update",
            "--repository",
            "example",
            "--results-file",
            str(results_file),
            "custom",
            "--path",
            str(custom_updater_path),
        ],
    )

    assert result.exit_code == 2
    assert "`--results-file` is not supported for custom updaters." in result.output
    assert not imported_marker.exists()
    assert not results_file.exists()


def test_update_command_reports_invalid_custom_updater_file(
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    custom_updater_path = tmp_path / "custom_updater.py"
    custom_updater_path.write_text("VALUE = 42\n")

    result = runner.invoke(
        app,
        [
            "update",
            "--repository",
            "example",
            "custom",
            "--path",
            str(custom_updater_path),
        ],
    )

    assert result.exit_code == 2
    assert "must define `updater = ...`" in result.output


def test_update_pixi_version_rejects_malformed_version_option(
    app: typer.Typer,
) -> None:
    result = runner.invoke(
        app,
        ["update", "--repository", "example", "pixi-version", "--pixi-version", "0.70"],
    )

    assert result.exit_code == 2
    assert "'0.70' does not have the form v0.70.0." in _plain_output(result.output)


def test_update_pixi_version_accepts_well_formed_version_option(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _record_run_update_calls(monkeypatch)

    result = runner.invoke(
        app,
        [
            "update",
            "--repository",
            "example",
            "pixi-version",
            "--pixi-version",
            "v0.70.0",
        ],
    )

    assert result.exit_code == 0
    assert calls[0]["updater"].options.pixi_version == "v0.70.0"


def test_update_node_dependency_cooldown_accepts_repeatable_exclusions(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _record_run_update_calls(monkeypatch)
    base_args = ["update", "--repository", "example", "node-dependency-cooldown"]

    default_result = runner.invoke(app, base_args)
    configured_result = runner.invoke(
        app,
        [
            *base_args,
            "--minimum-release-age-days",
            "3",
            "--bun-minimum-release-age-exclude",
            "@example/config",
            "--bun-minimum-release-age-exclude",
            "@example/ui",
            "--bun-minimum-release-age-exclude",
            "@example/config",
            "--minimum-release-age-exclude",
            "@example/*",
            "--minimum-release-age-exclude",
            "example-package",
        ],
    )

    assert default_result.exit_code == 0
    assert configured_result.exit_code == 0
    default_options = calls[0]["updater"].options
    assert default_options.minimum_release_age_days == 7
    assert default_options.bun_minimum_release_age_excludes == []
    assert default_options.minimum_release_age_excludes == []
    configured_options = calls[1]["updater"].options
    assert configured_options.minimum_release_age_days == 3
    assert configured_options.bun_minimum_release_age_excludes == [
        "@example/config",
        "@example/ui",
    ]
    assert configured_options.minimum_release_age_excludes == [
        "@example/*",
        "example-package",
    ]


def test_update_node_dependency_cooldown_rejects_invalid_exclusion(
    app: typer.Typer,
) -> None:
    result = runner.invoke(
        app,
        [
            "update",
            "--repository",
            "example",
            "node-dependency-cooldown",
            "--minimum-release-age-exclude",
            "",
        ],
    )

    assert result.exit_code == 2
    assert "must be non-empty single-line values" in _plain_output(result.output)


def test_update_node_dependency_cooldown_rejects_non_positive_release_age(
    app: typer.Typer,
) -> None:
    result = runner.invoke(
        app,
        [
            "update",
            "--repository",
            "example",
            "node-dependency-cooldown",
            "--minimum-release-age-days",
            "0",
        ],
    )

    assert result.exit_code == 2
    assert "Invalid value" in _plain_output(result.output)


def test_argument_help_lists_registered_tools(app: typer.Typer) -> None:
    result = runner.invoke(app, ["update", "--help"], env={"COLUMNS": "300"})

    assert result.exit_code == 0
    assert "zizmor" in result.output
    assert "Fix configured zizmor findings." in result.output
    assert "copier" in result.output
    assert "Update a Copier template." in result.output
    assert "copier-migration" in result.output
    assert "Apply a Copier-answer migration." in result.output
    assert "pixi-version" in result.output
    assert "Update pinned Pixi versions." in result.output
    assert "pixi-update" in result.output
    assert "Regenerate Pixi lockfiles." in result.output
    assert "node-dependency-cooldown" in result.output
    assert "Configure Node dependency cooldowns." in result.output
    assert "github-app-token" in result.output
    assert "Migrate GitHub App token inputs." in result.output
    assert "custom" in result.output
    assert "Run a trusted Python updater." in result.output
    assert "Plugin commands" not in result.output


def test_update_help_describes_all_installed_repositories_option(
    app: typer.Typer,
) -> None:
    result = runner.invoke(app, ["update", "--help"], env={"COLUMNS": "300"})

    assert result.exit_code == 0
    help_output = _normalized_output(_plain_output(result.output))
    assert "--all-installed-repositories" in help_output
    assert (
        "Process all repositories this GitHub App has access to, across all "
        "installations."
    ) in help_output


def test_update_command_debug_option_enables_debug_logging(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_update(**kwargs: Any) -> None:
        kwargs["logger"].debug("details")

    monkeypatch.setattr(cli_update_module, "_run_update", fake_run_update)

    result = runner.invoke(app, ["update", "--debug", "zizmor"])

    assert result.exit_code == 0
    output = _normalized_output(result.output)
    assert " ".join(DEBUG_WARNING.split()) in output
    assert "details" in output


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ([], False),
        (["update", "zizmor"], False),
        (["update", "--debug", "zizmor"], True),
        (["update", "-d", "zizmor"], True),
        (["update", "--", "--debug"], False),
        (["--", "-d"], False),
    ],
)
def test_main_scans_argv_for_debug_startup_logging(
    arguments: list[str],
    expected: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured_kwargs: dict[str, Any] = {}

    def fake_make_app(**kwargs: Any) -> Any:
        captured_kwargs.update(kwargs)
        return lambda: None

    monkeypatch.setattr(cli_app_module, "make_app", fake_make_app)
    monkeypatch.setattr(sys, "argv", ["quant-ranger", *arguments])

    main()

    captured_kwargs["startup_logger"].debug("plugin details")
    captured = capsys.readouterr().err
    assert ("plugin details" in captured) is expected


def test_update_command_converts_cli_errors_to_exit(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_update(**kwargs: Any) -> None:
        raise CliError("bad input")

    monkeypatch.setattr(cli_update_module, "_run_update", fake_run_update)

    result = runner.invoke(app, ["update", "zizmor"])

    assert result.exit_code == 2
    assert "bad input" in result.output


def test_update_command_logs_unexpected_exceptions(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_update(**kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_update_module, "_run_update", fake_run_update)

    result = runner.invoke(app, ["update", "zizmor"])

    assert result.exit_code == 1


def test_update_command_passes_deliberate_exits_through(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_update(**kwargs: Any) -> None:
        del kwargs
        raise typer.Exit(3)

    monkeypatch.setattr(cli_update_module, "_run_update", fake_run_update)

    result = runner.invoke(app, ["update", "zizmor"])

    assert result.exit_code == 3
    assert "error" not in result.output
    assert "Traceback" not in result.output


def test_update_command_exits_via_sigint_on_keyboard_interrupt(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_calls = 0

    def fake_run_update(**kwargs: Any) -> None:
        del kwargs
        raise KeyboardInterrupt

    def fake_exit_via_sigint() -> None:
        nonlocal exit_calls
        exit_calls += 1
        raise typer.Exit(130)

    monkeypatch.setattr(cli_update_module, "_run_update", fake_run_update)
    monkeypatch.setattr(cli_update_module, "exit_via_sigint", fake_exit_via_sigint)

    result = runner.invoke(app, ["update", "zizmor"])

    assert exit_calls == 1
    assert result.exit_code == 130
    assert "error" not in result.output
    assert "Traceback" not in result.output


def test_main_invokes_typer_app(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_app() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(cli_app_module, "make_app", lambda **kwargs: fake_app)

    main()

    assert called


def test_main_renders_unexpected_exceptions_with_rich_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_app() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_app_module, "make_app", lambda **kwargs: fake_app)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr().err
    assert "Unexpected error" in captured
    assert "Traceback (most recent call last)" in captured
    assert "RuntimeError: boom" in captured


def test_main_warns_when_running_as_root(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_app() -> None:
        pass

    monkeypatch.setattr(cli_app_module, "make_app", lambda **kwargs: fake_app)
    monkeypatch.setattr(cli_app_module.os, "geteuid", lambda: 0, raising=False)

    main()

    captured = capsys.readouterr().err
    assert _normalized_root_warning() in _normalized_output(captured)


def test_cli_app_module_main_guard_invokes_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_app_call(self: typer.Typer) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(typer.Typer, "__call__", fake_app_call)
    monkeypatch.delitem(sys.modules, "quant_ranger._impl.cli._app", raising=False)

    runpy.run_module("quant_ranger._impl.cli._app", run_name="__main__")

    assert called


def test_package_main_invokes_cli_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_main() -> None:
        nonlocal called
        called = True

    cli_package = import_module("quant_ranger.cli")
    monkeypatch.setattr(cli_package, "main", fake_main)

    runpy.run_module("quant_ranger.__main__", run_name="__main__")

    assert called


def test_run_update_discovers_active_repositories_for_owner(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_repository = RepositoryRef(owner="quantco", name="active", branch="main")
    github_client = FakeGitHubClient(active_by_owner={"quantco": [active_repository]})
    captured_items = _record_zizmor_update_items(monkeypatch)
    _use_fake_github_clients(monkeypatch, github_client)

    result = _run_zizmor_update(app, owner="quantco")

    assert result.exit_code == 0
    assert github_client.active_repository_calls == ["quantco"]
    assert captured_items == [UpdateItem(repository_ref=active_repository)]


def test_run_update_uses_installed_repositories_directly(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_repositories = [
        RepositoryRef(owner="quantco", name="first", branch="main"),
        RepositoryRef(owner="Other", name="second", branch="develop"),
    ]
    github_client = FakeGitHubClient(
        installed=active_repositories,
    )
    captured_items = _record_zizmor_update_items(monkeypatch)
    _use_fake_github_clients(monkeypatch, github_client)

    result = _run_zizmor_update(app, all_installed_repositories=True)

    assert result.exit_code == 0
    assert github_client.installed_repository_calls == 1
    assert github_client.active_repository_calls == []
    assert captured_items == [
        UpdateItem(repository_ref=repository) for repository in active_repositories
    ]


def test_run_update_filters_installations_by_owner(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quantco_repo = RepositoryRef(owner="quantco", name="first", branch="main")
    quantco_client = FakeGitHubClient(
        installation_owner="quantco",
        installed=[quantco_repo],
    )
    other_client = FakeGitHubClient(
        installation_owner="Other",
        installed=[RepositoryRef(owner="Other", name="second", branch="main")],
    )
    captured_items = _record_zizmor_update_items(monkeypatch)
    _use_fake_github_clients(monkeypatch, quantco_client, other_client)

    result = _run_zizmor_update(app, owner="quantco")

    assert result.exit_code == 0
    assert quantco_client.installed_repository_calls == 1
    assert other_client.installed_repository_calls == 0
    assert quantco_client.active_repository_calls == []
    assert captured_items == [UpdateItem(repository_ref=quantco_repo)]


def test_run_update_filters_explicit_repositories_by_installation(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quantco_client = FakeGitHubClient(installation_owner="quantco")
    other_client = FakeGitHubClient(installation_owner="Other")
    captured_items = _record_zizmor_update_items(monkeypatch)
    _use_fake_github_clients(monkeypatch, quantco_client, other_client)

    result = _run_zizmor_update(
        app,
        raw_repositories=["quantco/first", "Other/second"],
        owner="quantco",
    )

    assert result.exit_code == 0
    # Each explicit repository is routed to the matching installation only.
    assert captured_items == [
        UpdateItem(
            repository_ref=RepositoryRef(owner="quantco", name="first"),
        ),
        UpdateItem(
            repository_ref=RepositoryRef(owner="Other", name="second"),
        ),
    ]


def test_run_update_rejects_if_any_repository_is_unavailable(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_items = _record_zizmor_update_items(monkeypatch)
    _use_fake_github_clients(
        monkeypatch,
        FakeGitHubClient(installation_owner="quantco"),
        FakeGitHubClient(installation_owner="Other"),
    )

    result = _run_zizmor_update(
        app,
        raw_repositories=["quantco/first", "Unknown/missing"],
        owner="quantco",
    )

    assert result.exit_code == 2
    assert (
        "Repository or branch was not found or inaccessible: Unknown/missing."
        in _normalized_output(result.output)
    )
    # Validate every explicit repository before running any updates.
    assert captured_items == []


def test_run_update_rejects_repository_unavailable_to_installation_token(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fake_github_clients(
        monkeypatch,
        FakeGitHubClient(
            token="ghs_installation-token",
            missing_refs={"quantco/missing"},
        ),
    )

    result = _run_zizmor_update(
        app,
        raw_repositories=["quantco/missing"],
        owner="quantco",
    )

    assert result.exit_code == 2
    assert "quantco/missing" in _normalized_output(result.output)


def test_run_update_rejects_owner_without_matching_installation(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fake_github_clients(
        monkeypatch, FakeGitHubClient(installation_owner="quantco")
    )

    result = _run_zizmor_update(app, owner="missing")

    assert result.exit_code == 2
    assert "missing" in result.output


@pytest.mark.parametrize(
    ("owner", "all_installed_repositories"),
    [("quantco", False), (None, True)],
)
def test_run_update_wraps_repository_discovery_errors(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
    owner: str | None,
    all_installed_repositories: bool,
) -> None:
    github_client = FakeGitHubClient(error=GitHubError("boom"))
    _use_fake_github_clients(monkeypatch, github_client)

    result = _run_zizmor_update(
        app,
        owner=owner,
        all_installed_repositories=all_installed_repositories,
    )

    assert result.exit_code == 2
    assert "boom" in result.output


def _clear_app_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_APP_CLIENT_ID", raising=False)
    monkeypatch.delenv("GH_APP_PRIVATE_KEY", raising=False)


def test_update_command_rejects_missing_github_token(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_app_credentials(monkeypatch)
    monkeypatch.setattr(
        cli_update_module, "resolve_github_token", lambda **kwargs: None
    )

    result = runner.invoke(app, ["update", "zizmor"])

    assert result.exit_code == 2
    assert "GitHub authentication is required" in _normalized_output(result.output)


def test_update_command_wraps_token_resolution_errors(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_update_module,
        "resolve_github_app_credentials",
        lambda: pytest.fail("GitHub App credentials should not be resolved with --gh"),
    )

    def fake_resolve_github_token(**kwargs: Any) -> str | None:
        raise CommandError(
            "gh auth failed", ExecOutput(exit_code=1, stdout="", stderr="")
        )

    monkeypatch.setattr(
        cli_update_module, "resolve_github_token", fake_resolve_github_token
    )

    result = runner.invoke(app, ["update", "--gh", "zizmor"])

    assert result.exit_code == 2
    assert "Failed to resolve GitHub token" in _normalized_output(result.output)


def test_update_command_creates_one_context_per_installation(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_APP_CLIENT_ID", "123456")
    monkeypatch.setenv("GH_APP_PRIVATE_KEY", "pem-contents")
    monkeypatch.setenv("GH_TOKEN", "gh-token")
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    quantco_client = FakeGitHubClient(
        installation_owner="quantco",
        installed=[RepositoryRef(owner="quantco", name="first", branch="main")],
    )
    other_client = FakeGitHubClient(
        installation_owner="Other",
        installed=[RepositoryRef(owner="Other", name="second", branch="main")],
    )
    calls: list[dict[str, Any]] = []

    def fake_app_installation_clients(
        credentials: Any, **kwargs: Any
    ) -> list[GitHubClient]:
        calls.append({"credentials": credentials, **kwargs})
        return [
            cast(GitHubClient, quantco_client),
            cast(GitHubClient, other_client),
        ]

    monkeypatch.setattr(
        cli_update_module,
        "app_installation_clients",
        fake_app_installation_clients,
    )
    captured_items = _record_zizmor_update_items(monkeypatch)

    result = runner.invoke(
        app,
        [
            "update",
            "--github-api-url",
            "https://github.example/api/v3",
            "--pr-details-diff-lines",
            "20",
            "--all-installed-repositories",
            "zizmor",
        ],
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    assert calls[0]["credentials"].client_id == "123456"
    assert calls[0]["api_url"] == "https://github.example/api/v3"
    assert calls[0]["publish_changes"] is False
    assert calls[0]["show_pr_details"] is True
    assert calls[0]["pr_details_diff_lines"] == 20
    # Both installations are processed within one run.
    assert captured_items == [
        UpdateItem(
            repository_ref=RepositoryRef(owner="quantco", name="first", branch="main")
        ),
        UpdateItem(
            repository_ref=RepositoryRef(owner="Other", name="second", branch="main")
        ),
    ]


def test_update_command_rejects_partial_app_credentials(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_APP_CLIENT_ID", "123456")
    monkeypatch.delenv("GH_APP_PRIVATE_KEY", raising=False)

    result = runner.invoke(app, ["update", "zizmor"])

    assert result.exit_code == 2
    assert "both GH_APP_CLIENT_ID and GH_APP_PRIVATE_KEY" in _normalized_output(
        result.output
    )


def test_update_command_wraps_installation_discovery_errors(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_APP_CLIENT_ID", "123456")
    monkeypatch.setenv("GH_APP_PRIVATE_KEY", "pem-contents")

    def fake_app_installation_clients(*args: Any, **kwargs: Any) -> Any:
        raise GitHubError("Failed to list installations for the GitHub App.")

    monkeypatch.setattr(
        cli_update_module,
        "app_installation_clients",
        fake_app_installation_clients,
    )

    result = runner.invoke(app, ["update", "zizmor"])

    assert result.exit_code == 2
    assert "Failed to list installations" in _normalized_output(result.output)


def test_repositories_from_cli_accept_commas_and_blank_entries(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_items = _record_zizmor_update_items(monkeypatch)
    _use_fake_github_clients(monkeypatch, FakeGitHubClient())

    result = _run_zizmor_update(
        app,
        raw_repositories=["first, ,Other/second@release"],
        owner="quantco",
    )

    assert result.exit_code == 0
    assert captured_items == [
        UpdateItem(repository_ref=RepositoryRef(owner="quantco", name="first")),
        UpdateItem(
            repository_ref=RepositoryRef(owner="Other", name="second", branch="release")
        ),
    ]


def test_repositories_from_cli_wrap_invalid_specs(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fake_github_clients(monkeypatch, FakeGitHubClient())

    result = _run_zizmor_update(
        app,
        raw_repositories=["too/many/parts"],
        owner="quantco",
    )

    assert result.exit_code == 2
    assert "Invalid repository spec" in _normalized_output(result.output)


def test_run_update_uses_updater_scanner(
    app: typer.Typer,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_app_credentials(monkeypatch)
    monkeypatch.setenv("GH_TOKEN", "secret-token")
    monkeypatch.setattr(
        cli_update_module.GitHubClient,
        "check_ref_exists",
        lambda self, repository_ref: True,
    )
    captured_items: list[UpdateItem] = []
    captured_concurrency: dict[str, int] = {}

    def fake_scan_all(
        self: object,
        repository_refs: Sequence[RepositoryRef],
        context: RunContext,
        *,
        concurrency: int = 1,
    ) -> ScanResult[UpdateItem]:
        del self
        captured_concurrency["scan"] = concurrency
        return ScanResult(
            update_items=tuple(
                UpdateItem(repository_ref=repository_ref)
                for repository_ref in repository_refs
            ),
            scan_failures=(
                ScanFailure(
                    repository_ref=repository_refs[0],
                    message="Could not parse config.",
                ),
            ),
        )

    def fake_update_all(
        self: Updater[UpdateItem],
        update_items: Sequence[UpdateItem],
        context: RunContext,
        *,
        concurrency: int = 1,
    ) -> list[UpdateResult]:
        del context
        captured_concurrency["update"] = concurrency
        update_items = list(update_items)
        captured_items.extend(update_items)
        return [
            UpdateResult(
                result=Status.UP_TO_DATE,
                item=update_items[0],
            )
        ]

    monkeypatch.setattr(
        "quant_ranger._impl.scanners._repositories.RepositoriesScanner.scan_all",
        fake_scan_all,
    )
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._zizmor.ZizmorUpdater.update_all",
        fake_update_all,
    )
    results_file = tmp_path / "results.json"

    result = runner.invoke(
        app,
        [
            "update",
            "--owner",
            "quantco",
            "--repository",
            "example",
            "--jobs",
            "3",
            "--results-file",
            str(results_file),
            "zizmor",
        ],
    )

    assert result.exit_code == 0
    assert captured_concurrency == {"scan": 3, "update": 3}
    assert captured_items == [
        UpdateItem(
            repository_ref=RepositoryRef(
                owner="quantco",
                name="example",
            )
        )
    ]
    assert (
        "Update finished: 0 skipped, 0 updated, 1 up-to-date, 0 failed, "
        "1 failed during scanning." in _normalized_output(result.output)
    )
    payload = json.loads(results_file.read_text())
    assert payload["results"][0]["result"] == "up-to-date"
    assert payload["scan_failures"] == [
        {
            "repository_ref": {
                "owner": "quantco",
                "name": "example",
                "branch": None,
            },
            "message": "Could not parse config.",
            "details": None,
        }
    ]


def _custom_aggregate_app(
    aggregator_type: type[AnyAggregator],
    updater_types: Sequence[type[AnyUpdater]] = (ZizmorUpdater,),
) -> typer.Typer:
    custom_app = typer.Typer()

    @custom_app.callback()
    def aggregate_callback(context: typer.Context) -> None:
        context.obj = AggregateRunOptions(
            logger=ConsoleLogger(),
        )

    custom_app.command(aggregator_type.name)(
        make_aggregate_command(aggregator_type, updater_types, SiteConfig())
    )
    return custom_app


def _write_sample_results_file(results_file: Path) -> Path:
    write_results_file(
        results_file,
        updater=ZizmorUpdater(UpdateOptions()),
        results=[_sample_result()],
        scan_failures=(),
    )
    return results_file


def _sample_result() -> UpdateResult:
    return UpdateResult(
        result=Status.UPDATED,
        item=UpdateItem(repository_ref=RepositoryRef(owner="quantco", name="example")),
    )
