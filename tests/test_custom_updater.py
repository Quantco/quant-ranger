import sys
from pathlib import Path
from textwrap import dedent
from typing import cast, override

import pytest

from quant_ranger._impl.git import RepositoryCheckout
from quant_ranger._impl.github import GitHubClient
from quant_ranger._impl.helpers import CliError
from quant_ranger._impl.logger import LogLevel
from quant_ranger._impl.models import (
    RepositoryRef,
    Status,
    UpdateItem,
    UpdateOptions,
    UpdateOutcome,
    UpdateOutput,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.testing import FakeGitHubClient, RecordingLogger
from quant_ranger._impl.updaters._custom import (
    CUSTOM_UPDATER_MODULE_PREFIX,
    CustomFileUpdater,
    CustomUpdater,
    CustomUpdaterOptions,
)
from quant_ranger.scanners import RepositoriesScanner
from quant_ranger.site_config import SiteConfig
from quant_ranger.updaters import UpdateTask

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class NoopTask(UpdateTask[UpdateItem]):
    @override
    def run(self) -> UpdateOutcome:
        return UpdateOutcome(result=Status.UP_TO_DATE)


def test_custom_updater_loads_exported_updater_instance(tmp_path: Path) -> None:
    module_path = _write_custom_updater(
        tmp_path,
        """
        from quant_ranger import Status, UpdateItem, UpdateOutcome
        from quant_ranger.scanners import RepositoriesScanner
        from quant_ranger.updaters import CustomFileUpdater, UpdateTask


        class NoopTask(UpdateTask[UpdateItem]):
            def run(self):
                self.context.logger.info("custom task ran")
                return UpdateOutcome(
                    result=Status.UP_TO_DATE,
                    message=self.item.repository_ref.display_name,
                )


        class NoopUpdater(CustomFileUpdater[UpdateItem]):
            name = "noop"
            description = "Reports each repository as up to date."
            scanner = RepositoriesScanner()
            task_type = NoopTask


        updater = NoopUpdater()
        """,
    )
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")
    checkout_path = tmp_path / "checkout"
    checkout_path.mkdir()
    logger = RecordingLogger()
    updater = CustomUpdater(CustomUpdaterOptions(path=module_path))

    items = updater.scanner.scan_all(
        [repository_ref],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, FakeGitHubClient()),
            logger=logger,
        ),
    )
    results = updater.update_all(
        items.update_items,
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(
                GitHubClient,
                FakeGitHubClient(
                    checkout=RepositoryCheckout(checkout_path, repository_ref)
                ),
            ),
            logger=logger,
        ),
    )

    assert updater.name == "custom"
    assert updater.description == (
        "Run a trusted Python updater. Imports a file that exports a "
        "`CustomFileUpdater` instance named `updater`."
    )
    assert len(results) == 1
    assert results[0].result == Status.UP_TO_DATE
    assert results[0].message == "quantco/example@main"
    assert logger.logged(LogLevel.INFO, "[quantco/example@main] custom task ran")


def test_custom_updater_rejects_exported_updater_class(tmp_path: Path) -> None:
    module_path = _write_custom_updater(
        tmp_path,
        """
        from quant_ranger import Status, UpdateItem, UpdateOutcome
        from quant_ranger.scanners import RepositoriesScanner
        from quant_ranger.updaters import CustomFileUpdater, UpdateTask


        class NoopTask(UpdateTask[UpdateItem]):
            def run(self):
                return UpdateOutcome(result=Status.UP_TO_DATE)


        class NoopUpdater(CustomFileUpdater[UpdateItem]):
            name = "exported-class-updater"
            scanner = RepositoriesScanner()
            task_type = NoopTask


        updater = NoopUpdater
        """,
    )

    with pytest.raises(CliError, match="must be a CustomFileUpdater instance"):
        CustomUpdater(CustomUpdaterOptions(path=module_path))


def test_custom_updater_can_use_pre_made_scanners(tmp_path: Path) -> None:
    module_path = _write_custom_updater(
        tmp_path,
        """
        from quant_ranger import Status, UpdateItem, UpdateOutcome
        from quant_ranger.scanners import RepositoryFileScanner
        from quant_ranger.updaters import CustomFileUpdater, UpdateTask


        class NoopTask(UpdateTask[UpdateItem]):
            def run(self):
                return UpdateOutcome(result=Status.UP_TO_DATE)


        class NoopUpdater(CustomFileUpdater[UpdateItem]):
            name = "pixi-lock-scanner"
            scanner = RepositoryFileScanner(filename_pattern="pixi.lock")
            task_type = NoopTask


        updater = NoopUpdater()
        """,
    )
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")
    github_client = FakeGitHubClient(
        files={repository_ref.full_name: ["pixi.lock"]},
    )
    updater = CustomUpdater(CustomUpdaterOptions(path=module_path))

    items = updater.scanner.scan_all(
        [repository_ref],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=RecordingLogger(),
        ),
    )

    assert items.update_items == (UpdateItem(repository_ref=repository_ref),)
    assert github_client.find_files_calls == [(repository_ref, "pixi.lock")]


def test_custom_updater_loads_checked_in_example() -> None:
    example_path = PROJECT_ROOT / "examples" / "simple_custom_updater.py"

    updater = CustomUpdater(CustomUpdaterOptions(path=example_path))

    assert isinstance(updater.scanner, RepositoriesScanner)
    assert updater.options == CustomUpdaterOptions(path=example_path)


def test_custom_file_updater_initializes_empty_options() -> None:
    class NoopUpdater(CustomFileUpdater[UpdateItem]):
        name = "noop"
        scanner = RepositoriesScanner()
        task_type = NoopTask

    updater = NoopUpdater()

    assert updater.options == UpdateOptions()
    assert NoopUpdater.item_type is UpdateItem
    assert NoopUpdater.output_type is UpdateOutput
    assert NoopUpdater.options_type is UpdateOptions


def test_custom_file_updater_rejects_custom_options_type() -> None:
    with pytest.raises(TypeError, match="cannot define custom options"):

        class NoopUpdater(CustomFileUpdater[UpdateItem]):
            name = "noop"
            scanner = RepositoriesScanner()
            task_type = NoopTask
            options_type = CustomUpdaterOptions


def test_custom_updater_requires_explicit_updater_export(tmp_path: Path) -> None:
    module_path = _write_custom_updater(
        tmp_path,
        """
        VALUE = 42
        """,
    )

    with pytest.raises(CliError, match="must define `updater = ...`"):
        CustomUpdater(CustomUpdaterOptions(path=module_path))


def test_custom_updater_rejects_uppercase_updater_export(tmp_path: Path) -> None:
    module_path = _write_custom_updater(
        tmp_path,
        """
        from quant_ranger import Status, UpdateItem, UpdateOutcome
        from quant_ranger.scanners import RepositoriesScanner
        from quant_ranger.updaters import CustomFileUpdater, UpdateTask


        class NoopTask(UpdateTask[UpdateItem]):
            def run(self):
                return UpdateOutcome(result=Status.UP_TO_DATE)


        class NoopUpdater(CustomFileUpdater[UpdateItem]):
            name = "uppercase-export"
            scanner = RepositoriesScanner()
            task_type = NoopTask


        UPDATER = NoopUpdater
        """,
    )

    with pytest.raises(CliError, match="must define `updater = ...`"):
        CustomUpdater(CustomUpdaterOptions(path=module_path))


def test_custom_updater_rejects_invalid_updater_export(tmp_path: Path) -> None:
    module_path = _write_custom_updater(
        tmp_path,
        """
        updater = object()
        """,
    )

    with pytest.raises(CliError, match="must be a CustomFileUpdater instance"):
        CustomUpdater(CustomUpdaterOptions(path=module_path))


def test_custom_updater_rejects_plain_updater_instances(tmp_path: Path) -> None:
    module_path = _write_custom_updater(
        tmp_path,
        """
        from quant_ranger import Status, UpdateItem, UpdateOptions, UpdateOutcome
        from quant_ranger.scanners import RepositoriesScanner
        from quant_ranger.updaters import Updater, UpdateTask


        class NoopTask(UpdateTask[UpdateItem]):
            def run(self):
                return UpdateOutcome(result=Status.UP_TO_DATE)


        class NoopUpdater(Updater[UpdateItem]):
            name = "noop"
            scanner = RepositoriesScanner()
            task_type = NoopTask


        updater = NoopUpdater(UpdateOptions())
        """,
    )

    with pytest.raises(CliError, match="must be a CustomFileUpdater instance"):
        CustomUpdater(CustomUpdaterOptions(path=module_path))


@pytest.mark.parametrize("path_name", ["missing.py", "."])
def test_custom_updater_rejects_paths_that_are_not_files(
    tmp_path: Path,
    path_name: str,
) -> None:
    with pytest.raises(CliError, match="is not a file"):
        CustomUpdater(CustomUpdaterOptions(path=tmp_path / path_name))


def test_custom_updater_wraps_unimportable_module_specs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module_path = _write_custom_updater(tmp_path, "VALUE = 42\n")
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._custom.importlib.util.spec_from_file_location",
        lambda name, path: None,
    )

    with pytest.raises(CliError, match="Could not import custom updater file"):
        CustomUpdater(CustomUpdaterOptions(path=module_path))


def test_custom_updater_uses_unique_module_names_for_reloads(tmp_path: Path) -> None:
    module_path = _write_custom_updater(
        tmp_path,
        """
        from pathlib import Path

        from quant_ranger import Status, UpdateItem, UpdateOutcome
        from quant_ranger.scanners import RepositoriesScanner
        from quant_ranger.updaters import CustomFileUpdater, UpdateTask

        names_file = Path(__file__).parent / "module_names.txt"
        with names_file.open("a") as file:
            file.write(__name__ + chr(10))


        class NoopTask(UpdateTask[UpdateItem]):
            def run(self):
                return UpdateOutcome(result=Status.UP_TO_DATE)


        class NoopUpdater(CustomFileUpdater[UpdateItem]):
            name = "noop"
            scanner = RepositoriesScanner()
            task_type = NoopTask


        updater = NoopUpdater()
        """,
    )

    CustomUpdater(CustomUpdaterOptions(path=module_path))
    CustomUpdater(CustomUpdaterOptions(path=module_path))

    first_name, second_name = (tmp_path / "module_names.txt").read_text().splitlines()
    assert first_name != second_name
    assert first_name.startswith(CUSTOM_UPDATER_MODULE_PREFIX)
    assert second_name.startswith(CUSTOM_UPDATER_MODULE_PREFIX)
    assert first_name not in sys.modules
    assert second_name not in sys.modules


def _write_custom_updater(
    tmp_path: Path,
    content: str,
    *,
    filename: str = "custom_updater.py",
) -> Path:
    module_path = tmp_path / filename
    module_path.write_text(dedent(content))
    return module_path
