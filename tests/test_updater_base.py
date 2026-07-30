from pathlib import Path
from threading import Barrier
from typing import Any, ClassVar, cast, override

import pytest

from quant_ranger._impl.git import RepositoryCheckout
from quant_ranger._impl.github import GitHubClient, GitHubError
from quant_ranger._impl.logger import LogLevel
from quant_ranger._impl.models import (
    PathUpdateItem,
    RepositoryRef,
    Schedule,
    Status,
    UpdateOptions,
    UpdateOutcome,
    UpdateOutput,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.testing import FakeGitHubClient, RecordingLogger
from quant_ranger.site_config import SiteConfig
from quant_ranger.updaters import Updater, UpdateTask


def test_update_all_materializes_each_update_item(tmp_path: Path) -> None:
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")
    checkout = RepositoryCheckout(tmp_path, repository_ref)
    github_client = FakeGitHubClient(checkout=checkout)
    updater = RecordingUpdater(RecordingOptions())

    assert updater.item_type is PathUpdateItem
    assert updater.output_type is RecordingOutput

    results = updater.update_all(
        [
            PathUpdateItem(repository_ref=repository_ref, path="first"),
            PathUpdateItem(repository_ref=repository_ref, path="second"),
        ],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=RecordingLogger(),
        ),
    )

    assert [result.result for result in results] == [Status.UPDATED, Status.UPDATED]
    assert [result.item for result in results] == [
        PathUpdateItem(repository_ref=repository_ref, path="first"),
        PathUpdateItem(repository_ref=repository_ref, path="second"),
    ]
    assert [result.output for result in results] == [
        RecordingOutput(path="first", schedule=None),
        RecordingOutput(path="second", schedule=None),
    ]
    assert github_client.clone_calls == [repository_ref, repository_ref]


def test_update_all_converts_clone_errors_to_failure_results() -> None:
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()

    results = RecordingUpdater(RecordingOptions()).update_all(
        [PathUpdateItem(repository_ref=repository_ref)],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(
                GitHubClient,
                FakeGitHubClient(error=GitHubError("clone failed")),
            ),
            logger=logger,
        ),
    )

    assert len(results) == 1
    assert results[0].result == Status.FAILURE
    assert results[0].message == "clone failed"
    assert logger.logged(LogLevel.ERROR, "[quantco/example@main] failure: clone failed")
    assert logger.logged(LogLevel.ERROR, "GitHubError: clone failed")


def test_update_all_converts_unexpected_updater_errors_to_failure_results(
    tmp_path: Path,
) -> None:
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()
    updater = ExplodingUpdater(UpdateOptions())

    assert updater.output_type is UpdateOutput

    results = updater.update_all(
        [PathUpdateItem(repository_ref=repository_ref)],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(
                GitHubClient,
                FakeGitHubClient(
                    checkout=RepositoryCheckout(tmp_path, repository_ref),
                ),
            ),
            logger=logger,
        ),
    )

    assert len(results) == 1
    assert results[0].result == Status.FAILURE
    assert results[0].item == PathUpdateItem(repository_ref=repository_ref)
    assert results[0].message == "boom"
    assert logger.logged(LogLevel.ERROR, "[quantco/example@main] failure: boom")
    assert logger.logged(LogLevel.ERROR, "RuntimeError: boom")


def test_update_all_logs_unexpected_error_tracebacks_in_full(
    tmp_path: Path,
) -> None:
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()

    DeeplyExplodingUpdater(UpdateOptions()).update_all(
        [PathUpdateItem(repository_ref=repository_ref)],
        RunContext(
            github_client=cast(
                GitHubClient,
                FakeGitHubClient(
                    checkout=RepositoryCheckout(tmp_path, repository_ref),
                ),
            ),
            logger=logger,
            site_config=SiteConfig(),
        ),
    )

    assert not logger.logged(LogLevel.ERROR, "truncated")
    assert logger.logged(LogLevel.ERROR, "RuntimeError: deep boom")
    assert len(logger.errors) == 1
    assert len(logger.errors[0].splitlines()) > 10


def test_update_all_truncates_long_details_of_returned_failures(
    tmp_path: Path,
) -> None:
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()

    LongDetailsFailureUpdater(UpdateOptions()).update_all(
        [PathUpdateItem(repository_ref=repository_ref)],
        RunContext(
            github_client=cast(
                GitHubClient,
                FakeGitHubClient(
                    checkout=RepositoryCheckout(tmp_path, repository_ref),
                ),
            ),
            logger=logger,
            site_config=SiteConfig(),
        ),
    )

    assert logger.logged(LogLevel.ERROR, "[... 10 lines truncated ...]")
    assert logger.logged(LogLevel.ERROR, "line 0")
    assert logger.logged(LogLevel.ERROR, "line 19")
    assert not logger.logged(LogLevel.ERROR, "line 10")


def test_update_all_propagates_keyboard_interrupt(tmp_path: Path) -> None:
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()

    class InterruptingTask(UpdateTask[PathUpdateItem]):
        @override
        def run(self) -> UpdateOutcome:
            raise KeyboardInterrupt

    class InterruptingUpdater(Updater[PathUpdateItem]):
        name: ClassVar[str] = "interrupting"
        task_type: type[UpdateTask[PathUpdateItem]] = InterruptingTask

    with pytest.raises(KeyboardInterrupt):
        InterruptingUpdater(UpdateOptions()).update_all(
            [PathUpdateItem(repository_ref=repository_ref)],
            RunContext(
                site_config=SiteConfig(),
                github_client=cast(
                    GitHubClient,
                    FakeGitHubClient(
                        checkout=RepositoryCheckout(tmp_path, repository_ref),
                    ),
                ),
                logger=logger,
            ),
        )

    assert logger.errors == []


def test_update_all_passes_options_to_task(tmp_path: Path) -> None:
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")
    checkout = RepositoryCheckout(tmp_path, repository_ref)

    results = RecordingUpdater(
        RecordingOptions(schedule=Schedule.QUARTERLY)
    ).update_all(
        [PathUpdateItem(repository_ref=repository_ref)],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, FakeGitHubClient(checkout=checkout)),
            logger=RecordingLogger(),
        ),
    )

    assert len(results) == 1
    assert results[0].result == Status.UPDATED
    assert results[0].output == RecordingOutput(path=".", schedule="quarterly")


def test_update_all_can_run_update_items_concurrently(
    tmp_path: Path,
) -> None:
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")
    checkout = RepositoryCheckout(tmp_path, repository_ref)
    barrier = Barrier(2, timeout=5)

    class BlockingTask(UpdateTask[PathUpdateItem, RecordingOutput, RecordingOptions]):
        @override
        def run(self) -> UpdateOutcome[RecordingOutput]:
            barrier.wait()

            return UpdateOutcome[RecordingOutput](
                result=Status.UPDATED,
                output=RecordingOutput(path=self.item.path.as_posix(), schedule=None),
            )

    class BlockingUpdater(Updater[PathUpdateItem, RecordingOutput, RecordingOptions]):
        name: ClassVar[str] = "blocking"
        task_type: type[
            UpdateTask[PathUpdateItem, RecordingOutput, RecordingOptions]
        ] = BlockingTask

    results = BlockingUpdater(RecordingOptions()).update_all(
        [
            PathUpdateItem(repository_ref=repository_ref, path="first"),
            PathUpdateItem(repository_ref=repository_ref, path="second"),
        ],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, FakeGitHubClient(checkout=checkout)),
            logger=RecordingLogger(),
        ),
        concurrency=2,
    )

    assert [result.result for result in results] == [Status.UPDATED, Status.UPDATED]
    assert sorted(result.item.path.as_posix() for result in results) == [
        "first",
        "second",
    ]


def test_updater_rejects_invalid_item_type() -> None:
    invalid_base = cast(Any, Updater)[str, UpdateOutput, UpdateOptions]

    with pytest.raises(
        TypeError,
        match="BadItemUpdater item type must be a subclass of UpdateItem.",
    ):

        class BadItemUpdater(invalid_base):
            pass


def test_updater_rejects_invalid_output_type() -> None:
    invalid_base = cast(Any, Updater)[PathUpdateItem, str, UpdateOptions]

    with pytest.raises(
        TypeError,
        match="BadOutputUpdater output type must be a subclass of UpdateOutput.",
    ):

        class BadOutputUpdater(invalid_base):
            pass


def test_updater_requires_generic_base_when_inferring_options_type() -> None:
    bare_base = cast(Any, Updater)

    with pytest.raises(
        TypeError,
        match=r"BareUpdater must inherit from Updater\[\.\.\.\] or set options_type.",
    ):

        class BareUpdater(bare_base):
            pass


def test_updater_rejects_invalid_options_type() -> None:
    invalid_base = cast(Any, Updater)[PathUpdateItem, UpdateOutput, str]

    with pytest.raises(
        TypeError,
        match="BadOptionsUpdater options type must be a subclass of UpdateOptions.",
    ):

        class BadOptionsUpdater(invalid_base):
            pass


class RecordingOutput(UpdateOutput):
    path: str
    schedule: str | None


class RecordingOptions(UpdateOptions):
    schedule: Schedule | None = None


class RecordingTask(UpdateTask[PathUpdateItem, RecordingOutput, RecordingOptions]):
    @override
    def run(self) -> UpdateOutcome[RecordingOutput]:
        return UpdateOutcome[RecordingOutput](
            result=Status.UPDATED,
            output=RecordingOutput(
                path=self.item.path.as_posix(),
                schedule=self.options.schedule.value if self.options.schedule else None,
            ),
        )


class ExplodingTask(UpdateTask[PathUpdateItem]):
    @override
    def run(self) -> UpdateOutcome:
        raise RuntimeError("boom")


_RECURSION_DEPTH = 10


class DeeplyExplodingTask(UpdateTask[PathUpdateItem]):
    @override
    def run(self) -> UpdateOutcome:
        self._recurse_and_raise(_RECURSION_DEPTH)
        raise AssertionError("unreachable")

    def _recurse_and_raise(self, depth: int) -> None:
        if depth == 0:
            raise RuntimeError("deep boom")
        self._recurse_and_raise(depth - 1)


class LongDetailsFailureTask(UpdateTask[PathUpdateItem]):
    @override
    def run(self) -> UpdateOutcome:
        return UpdateOutcome(
            result=Status.FAILURE,
            message="long output",
            details="\n".join(f"line {index}" for index in range(20)),
        )


class RecordingUpdater(Updater[PathUpdateItem, RecordingOutput, RecordingOptions]):
    name: ClassVar[str] = "recording"
    task_type: type[UpdateTask[PathUpdateItem, RecordingOutput, RecordingOptions]] = (
        RecordingTask
    )


class ExplodingUpdater(Updater[PathUpdateItem]):
    name: ClassVar[str] = "exploding"
    task_type: type[UpdateTask[PathUpdateItem]] = ExplodingTask


class DeeplyExplodingUpdater(Updater[PathUpdateItem]):
    name: ClassVar[str] = "deeply-exploding"
    task_type: type[UpdateTask[PathUpdateItem]] = DeeplyExplodingTask


class LongDetailsFailureUpdater(Updater[PathUpdateItem]):
    name: ClassVar[str] = "long-details"
    task_type: type[UpdateTask[PathUpdateItem]] = LongDetailsFailureTask
