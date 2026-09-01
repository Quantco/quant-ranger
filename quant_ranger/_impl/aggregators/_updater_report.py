import json
import re
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, override
from urllib.parse import quote

import typer

from quant_ranger._impl.artifacts import UpdateResultsArtifact
from quant_ranger._impl.github import github_web_url
from quant_ranger._impl.helpers import CliError
from quant_ranger._impl.logger import Logger
from quant_ranger._impl.models import (
    PathUpdateItem,
    ScanFailure,
    Status,
    UpdateItem,
    UpdateOutput,
    UpdateResult,
)

from ._base import Aggregator, AggregatorOptions


class UpdaterReportOptions(AggregatorOptions):
    output_directory: Annotated[
        Path,
        typer.Option(
            "--output-directory",
            "-o",
            help="Updater data root in which to write the index and report directory.",
        ),
    ]
    title: Annotated[
        str | None,
        typer.Option(
            "--title",
            help="Display title; defaults to the updater name.",
        ),
    ] = None


class UpdaterReportAggregator(
    Aggregator[UpdateItem, UpdateOutput, UpdaterReportOptions]
):
    name = "updater-report"
    description = "Write public JSON for one updater feed."

    @override
    def aggregate(
        self,
        results: Sequence[UpdateResult[UpdateOutput, UpdateItem]],
        logger: Logger,
        artifact: UpdateResultsArtifact,
    ) -> None:
        web_url = github_web_url(artifact.github_api_url)
        summary = _summary(results, artifact.scan_failures)
        feed_id = _feed_id(artifact.updater, artifact.updater_options)
        header: dict[str, Any] = {
            "feed_id": feed_id,
            "title": self.options.title or artifact.updater,
            "updater": artifact.updater,
            "updater_options": artifact.updater_options,
            "generated_at": artifact.generated_at.isoformat(),
            "dry_run": artifact.dry_run,
            "github_api_url": artifact.github_api_url,
            "summary": summary,
        }
        if artifact.workflow_url is not None:
            header["workflow_url"] = artifact.workflow_url

        latest = {
            **header,
            "results": [_result_row(result, web_url) for result in results],
            "scan_failures": [
                _scan_failure_row(failure, web_url)
                for failure in artifact.scan_failures
            ],
        }
        output_root = self.options.output_directory
        output_directory = output_root / feed_id
        try:
            output_directory.mkdir(parents=True, exist_ok=True)
            _write_json(output_directory / "latest.json", latest)
            _update_index(output_root / "index.json", header)
        except OSError as error:
            raise CliError(
                f"Failed to write updater report to {output_directory}: {error}"
            ) from error

        logger.info(f"Wrote updater report to {output_directory}.")


def _feed_id(updater: str, updater_options: Mapping[str, object]) -> str:
    identity = json.dumps(
        {"updater": updater, "updater_options": updater_options},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    prefix = re.sub(r"[^a-z0-9]+", "-", updater.lower()).strip("-") or "updater"
    return f"{prefix}-{sha256(identity.encode()).hexdigest()[:12]}"


def _update_index(path: Path, summary: dict[str, Any]) -> None:
    feeds: list[dict[str, Any]] = (
        json.loads(path.read_text())["feeds"] if path.exists() else []
    )
    feeds = [feed for feed in feeds if feed.get("feed_id") != summary["feed_id"]]
    feeds.append(summary)
    feeds.sort(key=lambda feed: str(feed["feed_id"]))
    _write_json(path, {"feeds": feeds})


def _summary(
    results: Sequence[UpdateResult],
    scan_failures: Sequence[ScanFailure],
) -> dict[str, int]:
    return {
        "total": len(results),
        "updated": sum(result.result == Status.UPDATED for result in results),
        "up_to_date": sum(result.result == Status.UP_TO_DATE for result in results),
        "skipped": sum(result.result == Status.SKIPPED for result in results),
        "failures": sum(result.result == Status.FAILURE for result in results),
        "scan_failures": len(scan_failures),
    }


def _result_row(result: UpdateResult, github_url: str) -> dict[str, Any]:
    item = result.item
    repository = item.repository_ref.full_name
    row: dict[str, Any] = {
        "repository": repository,
        "url": _repository_url(github_url, repository),
        "status": result.result.value,
    }
    if isinstance(item, PathUpdateItem) and item.path != PurePosixPath("."):
        target = str(item.path)
        branch = item.repository_ref.branch or "HEAD"
        row["target"] = target
        row["target_url"] = (
            f"{row['url']}/blob/{quote(branch, safe='/')}/{quote(target, safe='/')}"
        )
    else:
        item_label = str(item)
        repository_label = item.repository_ref.display_name
        if item_label != repository_label:
            row["target"] = item_label.removeprefix(f"{repository_label} ")
    if result.pull_request_number is not None:
        row["pull_request"] = result.pull_request_number
        row["pull_request_url"] = f"{row['url']}/pull/{result.pull_request_number}"
    if result.message is not None:
        row["message"] = result.message
    if result.details is not None:
        row["details"] = result.details
    return row


def _scan_failure_row(failure: ScanFailure, github_url: str) -> dict[str, Any]:
    repository = failure.repository_ref.full_name
    row: dict[str, Any] = {
        "repository": repository,
        "url": _repository_url(github_url, repository),
    }
    if failure.message is not None:
        row["message"] = failure.message
    if failure.details is not None:
        row["details"] = failure.details
    return row


def _repository_url(github_url: str, repository: str) -> str:
    return f"{github_url.rstrip('/')}/{repository}"


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(f"{json.dumps(payload, indent=2)}\n")
