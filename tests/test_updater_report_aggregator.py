import json
from pathlib import Path, PurePosixPath
from typing import override

import pytest

from quant_ranger._impl.aggregators._updater_report import (
    UpdaterReportAggregator,
    UpdaterReportOptions,
)
from quant_ranger._impl.helpers import CliError
from quant_ranger._impl.models import (
    PathUpdateItem,
    RepositoryRef,
    ScanFailure,
    Status,
    UpdateItem,
    UpdateResult,
)
from quant_ranger._impl.testing import RecordingLogger, make_update_results_artifact


class LabeledUpdateItem(UpdateItem):
    label: str

    @override
    def __str__(self) -> str:
        return f"{self.repository_ref.display_name} {self.label}"


def test_updater_report_writes_latest_json(tmp_path: Path) -> None:
    aggregator = UpdaterReportAggregator(
        UpdaterReportOptions(
            output_directory=tmp_path,
            title="Weekly Pixi updates",
        )
    )
    logger = RecordingLogger()
    scan_failures = [
        ScanFailure(
            repository_ref=RepositoryRef(owner="acme", name="unreadable"),
            message="Invalid YAML.",
            details="full parser traceback",
        )
    ]

    aggregator.aggregate(
        [
            UpdateResult(
                result=Status.UPDATED,
                item=PathUpdateItem(
                    repository_ref=RepositoryRef(
                        owner="acme", name="one", branch="release/2026"
                    ),
                    path=PurePosixPath("environments/dev config/pixi.lock"),
                ),
                pull_request_number=42,
            ),
            UpdateResult(
                result=Status.FAILURE,
                item=UpdateItem(
                    repository_ref=RepositoryRef(owner="acme", name="broken")
                ),
                message="Command failed.",
                details="full command output\nfull traceback",
            ),
            UpdateResult(
                result=Status.UP_TO_DATE,
                item=UpdateItem(
                    repository_ref=RepositoryRef(owner="acme", name="current")
                ),
            ),
            UpdateResult(
                result=Status.UP_TO_DATE,
                item=LabeledUpdateItem(
                    repository_ref=RepositoryRef(owner="acme", name="labeled"),
                    label="release configuration",
                ),
            ),
        ],
        logger,
        make_update_results_artifact(
            scan_failures,
            dry_run=False,
            github_api_url="https://github.example/api/v3",
            updater="pixi-update",
            updater_options={"schedule": "weekly"},
            workflow_url="https://github.example/acme/ranger/actions/runs/123",
        ),
    )

    index = json.loads((tmp_path / "index.json").read_text())
    assert len(index["feeds"]) == 1
    feed_id = index["feeds"][0]["feed_id"]
    latest = json.loads((tmp_path / feed_id / "latest.json").read_text())
    header = {
        "feed_id": feed_id,
        "title": "Weekly Pixi updates",
        "updater": "pixi-update",
        "updater_options": {"schedule": "weekly"},
        "generated_at": "2026-07-16T00:00:00+00:00",
        "dry_run": False,
        "github_api_url": "https://github.example/api/v3",
        "summary": {
            "total": 4,
            "updated": 1,
            "up_to_date": 2,
            "skipped": 0,
            "failures": 1,
            "scan_failures": 1,
        },
        "workflow_url": "https://github.example/acme/ranger/actions/runs/123",
    }
    assert index["feeds"] == [header]
    assert latest == {
        **header,
        "results": [
            {
                "repository": "acme/one",
                "url": "https://github.example/acme/one",
                "status": "updated",
                "target": "environments/dev config/pixi.lock",
                "target_url": "https://github.example/acme/one/blob/release/2026/environments/dev%20config/pixi.lock",
                "pull_request": 42,
                "pull_request_url": "https://github.example/acme/one/pull/42",
            },
            {
                "repository": "acme/broken",
                "url": "https://github.example/acme/broken",
                "status": "failure",
                "message": "Command failed.",
                "details": "full command output\nfull traceback",
            },
            {
                "repository": "acme/current",
                "url": "https://github.example/acme/current",
                "status": "up-to-date",
            },
            {
                "repository": "acme/labeled",
                "url": "https://github.example/acme/labeled",
                "status": "up-to-date",
                "target": "release configuration",
            },
        ],
        "scan_failures": [
            {
                "repository": "acme/unreadable",
                "url": "https://github.example/acme/unreadable",
                "message": "Invalid YAML.",
                "details": "full parser traceback",
            }
        ],
    }
    assert logger.infos == [f"Wrote updater report to {tmp_path / feed_id}."]


def test_updater_report_index_distinguishes_options_and_replaces_same_feed(
    tmp_path: Path,
) -> None:
    aggregator = UpdaterReportAggregator(
        UpdaterReportOptions(output_directory=tmp_path)
    )

    for schedule in ("weekly", "monthly", "weekly"):
        aggregator.aggregate(
            [],
            RecordingLogger(),
            make_update_results_artifact(
                dry_run=False,
                updater="pixi-update",
                updater_options={"schedule": schedule},
            ),
        )

    index = json.loads((tmp_path / "index.json").read_text())
    assert len(index["feeds"]) == 2
    assert {feed["updater_options"]["schedule"] for feed in index["feeds"]} == {
        "monthly",
        "weekly",
    }


def test_updater_report_reports_unwritable_output(tmp_path: Path) -> None:
    output_parent = tmp_path / "not-a-directory"
    output_parent.write_text("occupied")
    aggregator = UpdaterReportAggregator(
        UpdaterReportOptions(output_directory=output_parent / "reports")
    )

    with pytest.raises(CliError, match="Failed to write updater report"):
        aggregator.aggregate(
            [],
            RecordingLogger(),
            make_update_results_artifact(dry_run=False, updater="pixi-update"),
        )
