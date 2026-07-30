from typing import cast

from quant_ranger._impl.github import GitHubClient
from quant_ranger._impl.models import RepositoryRef, UpdateItem
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.testing import RecordingLogger
from quant_ranger.scanners import RepositoriesScanner
from quant_ranger.site_config import SiteConfig


def test_repositories_scanner_emits_one_empty_root_item_per_repository() -> None:
    scanner = RepositoriesScanner()
    repositories = [
        RepositoryRef(owner="quantco", name="first", branch="main"),
        RepositoryRef(owner="quantco", name="second", branch="main"),
    ]

    assert scanner.item_type is UpdateItem

    scan_output = scanner.scan_all(
        repositories,
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, object()),
            logger=RecordingLogger(),
        ),
    )

    assert scan_output.update_items == (
        UpdateItem(repository_ref=repositories[0]),
        UpdateItem(repository_ref=repositories[1]),
    )
