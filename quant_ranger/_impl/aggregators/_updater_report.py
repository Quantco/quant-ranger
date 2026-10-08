import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Annotated, override
from urllib.parse import quote

import typer
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    JsonValue,
    ValidationError,
    field_serializer,
)

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


class _UpdaterReportModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class UpdaterReportSummary(_UpdaterReportModel):
    total: int
    updated: int
    up_to_date: int
    skipped: int
    failures: int
    scan_failures: int


class UpdaterReportResult(_UpdaterReportModel):
    repository: str
    url: str
    status: Status
    target: str | None = None
    target_url: str | None = None
    pull_request: int | None = None
    pull_request_url: str | None = None
    message: str | None = None
    details: str | None = None


class UpdaterReportScanFailure(_UpdaterReportModel):
    repository: str
    url: str
    message: str | None = None
    details: str | None = None


class UpdaterFeedSummary(_UpdaterReportModel):
    feed_id: str
    title: str
    updater: str
    updater_options: dict[str, JsonValue]
    generated_at: AwareDatetime
    dry_run: bool
    github_api_url: str
    summary: UpdaterReportSummary
    workflow_url: str | None = None

    @field_serializer("generated_at", when_used="json")
    def _serialize_generated_at(self, value: datetime) -> str:
        return value.isoformat()


class UpdaterReport(UpdaterFeedSummary):
    results: list[UpdaterReportResult]
    scan_failures: list[UpdaterReportScanFailure]


class UpdaterIndex(_UpdaterReportModel):
    feeds: list[UpdaterFeedSummary]


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
        report = UpdaterReport(
            feed_id=feed_id,
            title=self.options.title or artifact.updater,
            updater=artifact.updater,
            updater_options=artifact.updater_options,
            generated_at=artifact.generated_at,
            dry_run=artifact.dry_run,
            github_api_url=artifact.github_api_url,
            summary=summary,
            workflow_url=artifact.workflow_url,
            results=[_result_row(result, web_url) for result in results],
            scan_failures=[
                _scan_failure_row(failure, web_url)
                for failure in artifact.scan_failures
            ],
        )
        output_root = self.options.output_directory
        output_directory = output_root / feed_id
        try:
            output_directory.mkdir(parents=True, exist_ok=True)
            _write_model(output_directory / "latest.json", report)
            _update_index(output_root / "index.json", report)
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


def _update_index(path: Path, summary: UpdaterFeedSummary) -> None:
    if path.exists():
        try:
            index = UpdaterIndex.model_validate_json(path.read_text())
        except ValidationError as error:
            raise CliError(f"Invalid updater report index {path}: {error}") from error
    else:
        index = UpdaterIndex(feeds=[])
    feeds = [feed for feed in index.feeds if feed.feed_id != summary.feed_id]
    feeds.append(summary)
    feeds.sort(key=lambda feed: feed.feed_id)
    _write_model(path, UpdaterIndex(feeds=feeds))


def _summary(
    results: Sequence[UpdateResult],
    scan_failures: Sequence[ScanFailure],
) -> UpdaterReportSummary:
    return UpdaterReportSummary(
        total=len(results),
        updated=sum(result.result == Status.UPDATED for result in results),
        up_to_date=sum(result.result == Status.UP_TO_DATE for result in results),
        skipped=sum(result.result == Status.SKIPPED for result in results),
        failures=sum(result.result == Status.FAILURE for result in results),
        scan_failures=len(scan_failures),
    )


def _result_row(result: UpdateResult, github_url: str) -> UpdaterReportResult:
    item = result.item
    repository = item.repository_ref.full_name
    url = _repository_url(github_url, repository)
    target: str | None = None
    target_url: str | None = None
    if isinstance(item, PathUpdateItem) and item.path != PurePosixPath("."):
        target = str(item.path)
        branch = item.repository_ref.branch or "HEAD"
        target_url = f"{url}/blob/{quote(branch, safe='/')}/{quote(target, safe='/')}"
    else:
        item_label = str(item)
        repository_label = item.repository_ref.display_name
        if item_label != repository_label:
            target = item_label.removeprefix(f"{repository_label} ")
    pull_request_url = (
        f"{url}/pull/{result.pull_request_number}"
        if result.pull_request_number is not None
        else None
    )
    return UpdaterReportResult(
        repository=repository,
        url=url,
        status=result.result,
        target=target,
        target_url=target_url,
        pull_request=result.pull_request_number,
        pull_request_url=pull_request_url,
        message=result.message,
        details=result.details,
    )


def _scan_failure_row(
    failure: ScanFailure,
    github_url: str,
) -> UpdaterReportScanFailure:
    repository = failure.repository_ref.full_name
    return UpdaterReportScanFailure(
        repository=repository,
        url=_repository_url(github_url, repository),
        message=failure.message,
        details=failure.details,
    )


def _repository_url(github_url: str, repository: str) -> str:
    return f"{github_url.rstrip('/')}/{repository}"


def _write_model(path: Path, payload: BaseModel) -> None:
    path.write_text(f"{payload.model_dump_json(indent=2, exclude_none=True)}\n")
