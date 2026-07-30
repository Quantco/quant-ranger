from collections.abc import Sequence
from threading import Barrier, BrokenBarrierError, Lock, get_ident
from typing import cast, override

import pytest

from quant_ranger._impl.github import GitHubClient
from quant_ranger._impl.logger import LogLevel
from quant_ranger._impl.models import RepositoryRef, UpdateItem
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.testing import RecordingLogger
from quant_ranger.scanners import Scanner
from quant_ranger.site_config import SiteConfig


def test_scanner_can_scan_repositories_concurrently() -> None:
    barrier = Barrier(2)
    lock = Lock()
    thread_ids: set[int] = set()

    class BlockingScanner(Scanner[UpdateItem]):
        @override
        def scan_repository(
            self,
            repository_ref: RepositoryRef,
            context: RunContext,
        ) -> Sequence[UpdateItem]:
            del context
            with lock:
                thread_ids.add(get_ident())
            try:
                barrier.wait(timeout=2)
            except BrokenBarrierError as error:
                raise AssertionError(
                    "scanner tasks did not run concurrently"
                ) from error
            return [UpdateItem(repository_ref=repository_ref)]

    scanner = BlockingScanner()
    repositories = [
        RepositoryRef(owner="quantco", name="first", branch="main"),
        RepositoryRef(owner="quantco", name="second", branch="main"),
    ]

    scan_output = scanner.scan_all(
        repositories,
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, object()),
            logger=RecordingLogger(),
        ),
        concurrency=2,
    )

    assert sorted(item.repository_ref.name for item in scan_output.update_items) == [
        "first",
        "second",
    ]
    assert len(thread_ids) == 2


@pytest.mark.parametrize("concurrency", [1, 2])
def test_scanner_captures_scan_failure_errors(concurrency: int) -> None:
    class FailingScanner(Scanner[UpdateItem]):
        @override
        def scan_repository(
            self,
            repository_ref: RepositoryRef,
            context: RunContext,
        ) -> Sequence[UpdateItem]:
            del context
            if repository_ref.name == "broken":
                raise ValueError("could not parse config")
            return [UpdateItem(repository_ref=repository_ref)]

    logger = RecordingLogger()
    repositories = [
        RepositoryRef(owner="quantco", name="ok", branch="main"),
        RepositoryRef(owner="quantco", name="broken", branch="main"),
    ]

    scan_output = FailingScanner().scan_all(
        repositories,
        RunContext(
            github_client=cast(GitHubClient, object()),
            logger=logger,
            site_config=SiteConfig(),
        ),
        concurrency=concurrency,
    )

    assert [item.repository_ref.name for item in scan_output.update_items] == ["ok"]
    assert logger.logged(
        LogLevel.ERROR,
        "[quantco/broken@main] Skipping repository: could not parse config",
    )
    assert not logger.logged(
        LogLevel.ERROR,
        "Traceback (most recent call last):",
    )
    (scan_failure,) = scan_output.scan_failures
    assert scan_failure.repository_ref == repositories[1]
    assert scan_failure.message == "could not parse config"
    assert scan_failure.details is not None
    assert "ValueError: could not parse config" in (scan_failure.details)
