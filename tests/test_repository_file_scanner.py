import re
from re import Pattern
from typing import cast

import pytest

from quant_ranger._impl.github import GitHubClient
from quant_ranger._impl.logger import LogLevel
from quant_ranger._impl.models import RepositoryRef, UpdateItem
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.testing import FakeGitHubClient, RecordingLogger
from quant_ranger.scanners import RepositoryFileScanner
from quant_ranger.site_config import SiteConfig


@pytest.mark.parametrize(
    ("filename_pattern", "files"),
    [
        ("pixi.lock", ["pixi.lock", "subproject/pixi.lock"]),
        (
            re.compile(r"(?:pixi|conda)\.lock"),
            ["pixi.lock", "subproject/conda.lock"],
        ),
    ],
)
def test_repository_file_scanner_emits_repository_item_when_matching_files_exist(
    filename_pattern: str | Pattern[str],
    files: list[str],
) -> None:
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(files={repository_ref.full_name: files})
    scanner = RepositoryFileScanner(filename_pattern=filename_pattern)

    scan_output = scanner.scan_all(
        [repository_ref],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert scan_output.update_items == (UpdateItem(repository_ref=repository_ref),)
    assert github_client.find_files_calls == [(repository_ref, filename_pattern)]
    assert logger.logged(LogLevel.INFO, "Generated 1 update item.")


def test_repository_file_scanner_logs_missing_files() -> None:
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()
    scanner = RepositoryFileScanner(
        filename_pattern="pixi.lock",
        missing_message="No pixi.lock file found",
    )

    items = scanner.scan_repository(
        repository_ref,
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, FakeGitHubClient()),
            logger=logger,
        ),
    )

    assert items == []
    assert logger.debug_messages == ["No pixi.lock file found."]
