import importlib
import sys
import tomllib
from collections.abc import Callable, Iterator
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest
from typer.testing import CliRunner

from quant_ranger._impl.cli import make_app
from quant_ranger._impl.testing import RecordingLogger
from quant_ranger._impl.updaters import ZizmorUpdater

EXAMPLE_PLUGIN_PATH = Path(__file__).parent.parent / "examples" / "plugin"

PLUGIN_MODULE_NAME = "quant_ranger_test_plugins"

EXITING_MODULE_NAME = f"{PLUGIN_MODULE_NAME}_exiting"

# A plugin module calling sys.exit() at import time. SystemExit is not an
# Exception, so it needs its own skip coverage.
EXITING_MODULE_SOURCE = "raise SystemExit(3)\n"

PLUGIN_MODULE_SOURCE = dedent(
    '''
    """Plugin classes served through a generated test distribution."""

    from collections.abc import Sequence
    from typing import override

    from quant_ranger import (
        Logger,
        UpdateItem,
        UpdateOptions,
        UpdateOutcome,
        UpdateOutput,
        UpdateResult,
        UpdateResultsArtifact,
    )
    from quant_ranger.aggregators import Aggregator, AggregatorOptions
    from quant_ranger.updaters import Updater, UpdateTask


    class PluginTask(UpdateTask[UpdateItem, UpdateOutput, UpdateOptions]):
        @override
        def run(self) -> UpdateOutcome:
            raise NotImplementedError


    class PluginUpdater(Updater[UpdateItem, UpdateOutput, UpdateOptions]):
        name = "plugin-updater"
        description = "Run plugin updates."
        task_type = PluginTask


    class DuplicateNameUpdater(PluginUpdater):
        name = "zizmor"


    class NamelessUpdater(Updater[UpdateItem, UpdateOutput, UpdateOptions]):
        description = "Missing a name."
        task_type = PluginTask


    class NotAPlugin:
        pass


    class PluginAggregator(Aggregator[UpdateItem, UpdateOutput, AggregatorOptions]):
        name = "plugin-aggregator"
        description = "Summarize plugin updates."

        @override
        def aggregate(
            self,
            results: Sequence[UpdateResult[UpdateOutput, UpdateItem]],
            logger: Logger,
            artifact: UpdateResultsArtifact,
        ) -> None:
            del results, logger, artifact


    from quant_ranger.site_config import (
        CopierMigration,
        PullRequestTemplate,
        SiteConfig,
    )

    site_config = SiteConfig(
        default_owner="quantco",
        default_github_api_url="https://github.example/api/v3",
        pixi_version_setup_pixi_marker="quantco-fork/setup-pixi",
        copier_migrations={
            "custom-migration": CopierMigration(
                answer_key="custom_feature",
                templates=frozenset(
                    {"github.example/quantco/copier-template-python-open-source"}
                ),
                resolve_desired_value=lambda _current_value: True,
                pull_request_template=PullRequestTemplate(
                    title="chore: Enable custom feature",
                    body="Enable the custom feature.",
                    branch_prefix="copier-migration",
                ),
            )
        },
        copier_trusted_templates={"github.example/quantco/copier-template-python-open-source"},
    )

    site_config_without_owner = SiteConfig(default_owner=None)

    not_a_site_config = object()
    '''
)

runner = CliRunner()


@pytest.fixture
def install_plugin_dist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[[str], None]]:
    """Provide an installer for a real plugin distribution on `sys.path`.

    The installer writes the plugin module plus `.dist-info` metadata with
    the given `entry_points.txt` content, so `importlib.metadata` discovers
    the plugin through the same path as an installed package.
    """
    monkeypatch.syspath_prepend(str(tmp_path))

    def install(entry_points_txt: str) -> None:
        (tmp_path / f"{PLUGIN_MODULE_NAME}.py").write_text(PLUGIN_MODULE_SOURCE)
        (tmp_path / f"{EXITING_MODULE_NAME}.py").write_text(EXITING_MODULE_SOURCE)
        _write_dist_info(
            tmp_path,
            distribution_name="quant_ranger_test_plugin",
            entry_points_txt=entry_points_txt,
        )
        importlib.invalidate_caches()

    yield install
    sys.modules.pop(PLUGIN_MODULE_NAME, None)


def test_registers_plugin_commands_from_entry_points(
    install_plugin_dist: Callable[[str], None],
) -> None:
    install_plugin_dist(
        dedent(
            f"""
            [quant_ranger.updaters]
            plugin-updater = {PLUGIN_MODULE_NAME}:PluginUpdater

            [quant_ranger.aggregators]
            plugin-aggregator = {PLUGIN_MODULE_NAME}:PluginAggregator
            """
        )
    )
    logger = RecordingLogger()
    app = make_app(startup_logger=logger)

    update_help = runner.invoke(app, ["update", "--help"])
    aggregate_help = runner.invoke(app, ["aggregate", "--help"])

    assert update_help.exit_code == 0
    assert "plugin-updater" in update_help.output
    assert "Run plugin updates." in update_help.output
    assert f"Plugin commands ({PLUGIN_MODULE_NAME})" in update_help.output
    assert update_help.output.index("zizmor") < update_help.output.index(
        "plugin-updater"
    )
    assert aggregate_help.exit_code == 0
    assert "plugin-aggregator" in aggregate_help.output
    assert f"Plugin commands ({PLUGIN_MODULE_NAME})" in aggregate_help.output
    assert "Loading updater plugins:" in logger.debug_messages
    assert f"  plugin-updater ({PLUGIN_MODULE_NAME})" in logger.debug_messages
    assert "Loading aggregator plugins:" in logger.debug_messages
    assert f"  plugin-aggregator ({PLUGIN_MODULE_NAME})" in logger.debug_messages


def test_skips_plugin_discovery_when_load_plugins_is_disabled(
    install_plugin_dist: Callable[[str], None],
) -> None:
    install_plugin_dist(
        dedent(
            f"""
            [quant_ranger.updaters]
            plugin-updater = {PLUGIN_MODULE_NAME}:PluginUpdater
            """
        )
    )
    logger = RecordingLogger()
    app = make_app(startup_logger=logger, load_plugins=False)

    result = runner.invoke(app, ["update", "--help"])

    assert result.exit_code == 0
    assert "zizmor" in result.output
    assert "plugin-updater" not in result.output
    assert logger.debug_messages == []
    assert logger.warnings == []


def test_rejects_duplicate_builtin_command_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "quant_ranger._impl.cli._app.BUILTIN_UPDATERS",
        (ZizmorUpdater, ZizmorUpdater),
    )

    with pytest.raises(
        ValueError,
        match=(
            "Duplicate builtin command name 'zizmor': ZizmorUpdater and ZizmorUpdater."
        ),
    ):
        make_app(load_plugins=False)


def test_skips_invalid_plugin_entry_points_without_blocking_valid_ones(
    install_plugin_dist: Callable[[str], None],
) -> None:
    # Entry points are processed sorted by name, so `valid` loads only after
    # every broken entry point has already failed and been skipped.
    install_plugin_dist(
        dedent(
            f"""
            [quant_ranger.updaters]
            duplicate = {PLUGIN_MODULE_NAME}:DuplicateNameUpdater
            exits = {EXITING_MODULE_NAME}:X
            missing = {PLUGIN_MODULE_NAME}_missing:PluginUpdater
            nameless = {PLUGIN_MODULE_NAME}:NamelessUpdater
            not-a-plugin = {PLUGIN_MODULE_NAME}:NotAPlugin
            valid = {PLUGIN_MODULE_NAME}:PluginUpdater
            """
        )
    )
    logger = RecordingLogger()
    app = make_app(startup_logger=logger)

    result = runner.invoke(app, ["update", "--help"])

    assert result.exit_code == 0
    assert "zizmor" in result.output
    assert "plugin-updater" in result.output
    assert f"Plugin commands ({PLUGIN_MODULE_NAME})" in result.output
    assert f"  plugin-updater ({PLUGIN_MODULE_NAME})" in logger.debug_messages
    assert len(logger.warnings) == 5
    assert any(
        "Skipping plugin entry point 'duplicate'" in warning
        and "command name 'zizmor' duplicates an existing command" in warning
        for warning in logger.warnings
    )
    assert any(
        "Skipping plugin entry point 'exits'" in warning
        and "failed to load: 3" in warning
        for warning in logger.warnings
    )
    assert any(
        "Skipping plugin entry point 'missing'" in warning
        and f"failed to load: No module named '{PLUGIN_MODULE_NAME}_missing'" in warning
        for warning in logger.warnings
    )
    assert any(
        "Skipping plugin entry point 'nameless'" in warning
        and "must define a `name` string class attribute" in warning
        for warning in logger.warnings
    )
    assert any(
        "Skipping plugin entry point 'not-a-plugin'" in warning
        and "must load a subclass of Updater" in warning
        for warning in logger.warnings
    )


def test_loads_site_config_from_entry_point(
    install_plugin_dist: Callable[[str], None],
) -> None:
    install_plugin_dist(
        dedent(
            f"""
            [quant_ranger.site_config]
            corp = {PLUGIN_MODULE_NAME}:site_config
            """
        )
    )
    logger = RecordingLogger()
    app = make_app(startup_logger=logger)

    result = runner.invoke(
        app,
        ["update", "copier-migration", "--help"],
        env={"COLUMNS": "300"},
    )

    assert result.exit_code == 0
    assert "[custom-migration]" in result.output
    assert "[example]" not in result.output
    assert f"Loaded site config 'corp' ({PLUGIN_MODULE_NAME})." in (
        logger.debug_messages
    )


def test_site_config_provides_setup_pixi_marker_default(
    install_plugin_dist: Callable[[str], None],
) -> None:
    install_plugin_dist(
        dedent(
            f"""
            [quant_ranger.site_config]
            corp = {PLUGIN_MODULE_NAME}:site_config
            """
        )
    )
    app = make_app(startup_logger=RecordingLogger())

    # A wide terminal keeps rich from truncating the option's default value.
    result = runner.invoke(
        app,
        ["update", "pixi-version", "--help"],
        env={"COLUMNS": "300"},
    )

    assert result.exit_code == 0
    assert "quantco-fork/setup-pixi" in result.output


def test_site_config_without_owner_requires_owner_or_all_installed_repositories(
    install_plugin_dist: Callable[[str], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_plugin_dist(
        dedent(
            f"""
            [quant_ranger.site_config]
            corp = {PLUGIN_MODULE_NAME}:site_config_without_owner
            """
        )
    )
    app = make_app(startup_logger=RecordingLogger())

    help_result = runner.invoke(app, ["update", "zizmor", "--help"])
    assert help_result.exit_code == 0

    # A wide terminal keeps rich from wrapping the error message.
    result = runner.invoke(app, ["update", "zizmor"], env={"COLUMNS": "300"})

    assert result.exit_code == 2
    assert "`--repository owner/repo`" in result.output

    result = runner.invoke(
        app,
        ["update", "--repository", "repository", "zizmor"],
    )

    assert result.exit_code == 2
    assert "requires a default owner" in result.output

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "quant_ranger._impl.cli._update._run_update",
        lambda **kwargs: calls.append(kwargs),
    )
    result = runner.invoke(
        app,
        ["update", "--all-installed-repositories", "zizmor"],
    )

    assert result.exit_code == 0
    assert calls[0]["owner"] is None
    assert calls[0]["all_installed_repositories"] is True

    result = runner.invoke(
        app,
        ["update", "--repository", "quantco/repository", "zizmor"],
    )

    assert result.exit_code == 0
    assert calls[1]["raw_repositories"] == ["quantco/repository"]
    assert calls[1]["owner"] is None


def test_rejects_multiple_site_config_plugins(
    install_plugin_dist: Callable[[str], None],
) -> None:
    install_plugin_dist(
        dedent(
            f"""
            [quant_ranger.site_config]
            corp-a = {PLUGIN_MODULE_NAME}:site_config
            corp-b = {PLUGIN_MODULE_NAME}:site_config
            """
        )
    )

    logger = RecordingLogger()
    with pytest.raises(SystemExit) as exc_info:
        make_app(startup_logger=logger)

    assert exc_info.value.code == 2
    assert any(
        "Multiple site config plugins are installed: 'corp-a'" in error
        for error in logger.errors
    )


def test_rejects_site_config_plugin_that_fails_to_load(
    install_plugin_dist: Callable[[str], None],
) -> None:
    install_plugin_dist(
        dedent(
            f"""
            [quant_ranger.site_config]
            corp = {EXITING_MODULE_NAME}:X
            """
        )
    )

    logger = RecordingLogger()
    with pytest.raises(SystemExit) as exc_info:
        make_app(startup_logger=logger)

    assert exc_info.value.code == 2
    assert any(
        "Site config plugin 'corp'" in error and "failed to load: 3." in error
        for error in logger.errors
    )


def test_rejects_site_config_plugin_with_wrong_type(
    install_plugin_dist: Callable[[str], None],
) -> None:
    install_plugin_dist(
        dedent(
            f"""
            [quant_ranger.site_config]
            corp = {PLUGIN_MODULE_NAME}:not_a_site_config
            """
        )
    )

    logger = RecordingLogger()
    with pytest.raises(SystemExit) as exc_info:
        make_app(startup_logger=logger)

    assert exc_info.value.code == 2
    assert any(
        "Site config plugin 'corp'" in error
        and "must load a SiteConfig instance" in error
        for error in logger.errors
    )


def test_checked_in_example_plugin_is_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Guards examples/plugin against API drift: its entry points must point
    # at importable classes that pass plugin validation, and the command
    # names must match what its README documents.
    monkeypatch.syspath_prepend(str(EXAMPLE_PLUGIN_PATH))
    monkeypatch.syspath_prepend(str(tmp_path))
    pyproject = tomllib.loads((EXAMPLE_PLUGIN_PATH / "pyproject.toml").read_text())
    _write_dist_info(
        tmp_path,
        distribution_name="quant_ranger_example_plugin",
        entry_points_txt=_entry_points_txt_from_pyproject(pyproject),
    )
    importlib.invalidate_caches()

    app = make_app(startup_logger=RecordingLogger())

    update_help = runner.invoke(app, ["update", "--help"], env={"COLUMNS": "300"})
    aggregate_help = runner.invoke(app, ["aggregate", "--help"])

    assert update_help.exit_code == 0
    assert "ensure-config" in update_help.output
    assert "octo-org" in update_help.output
    ensure_config_help = runner.invoke(
        app,
        ["update", "ensure-config", "--help"],
        env={"COLUMNS": "300"},
    )
    assert ensure_config_help.exit_code == 0
    assert "--enabled" in ensure_config_help.output
    assert "--disabled" in ensure_config_help.output
    assert "Enable or disable the example tool." in ensure_config_help.output
    assert aggregate_help.exit_code == 0
    assert "status-summary" in aggregate_help.output
    status_summary_help = runner.invoke(
        app,
        ["aggregate", "status-summary", "--help"],
        env={"COLUMNS": "300"},
    )
    assert status_summary_help.exit_code == 0
    assert "--summary-label" in status_summary_help.output
    assert "Label shown before the status counts." in status_summary_help.output


def _write_dist_info(
    path: Path,
    *,
    distribution_name: str,
    entry_points_txt: str,
) -> None:
    dist_info = path / f"{distribution_name}-0.1.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\n"
        f"Name: {distribution_name.replace('_', '-')}\n"
        "Version: 0.1.0\n"
    )
    (dist_info / "entry_points.txt").write_text(entry_points_txt)


def _entry_points_txt_from_pyproject(pyproject: dict[str, Any]) -> str:
    lines: list[str] = []
    for group, entries in pyproject["project"]["entry-points"].items():
        lines.append(f"[{group}]")
        lines.extend(f"{name} = {value}" for name, value in entries.items())
        lines.append("")
    return "\n".join(lines)
