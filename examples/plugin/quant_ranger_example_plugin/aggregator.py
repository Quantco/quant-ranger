from collections.abc import Sequence
from typing import Annotated, override

import typer

from quant_ranger import (
    Logger,
    Status,
    UpdateItem,
    UpdateOutput,
    UpdateResult,
    UpdateResultsArtifact,
)
from quant_ranger.aggregators import Aggregator, AggregatorOptions


class StatusSummaryOptions(AggregatorOptions):
    summary_label: Annotated[
        str,
        typer.Option(
            "--summary-label",
            help="Label shown before the status counts.",
        ),
    ] = "status summary"


class StatusSummaryAggregator(
    Aggregator[UpdateItem, UpdateOutput, StatusSummaryOptions],
):
    name = "status-summary"
    description = "Summarize update results by status."

    @override
    def aggregate(
        self,
        results: Sequence[UpdateResult[UpdateOutput, UpdateItem]],
        logger: Logger,
        artifact: UpdateResultsArtifact,
    ) -> None:
        counts = {status: 0 for status in Status}
        for result in results:
            counts[result.result] += 1

        logger.info(
            f"{artifact.updater} {self.options.summary_label}: "
            f"{counts[Status.SKIPPED]} skipped, "
            f"{counts[Status.UPDATED]} updated, "
            f"{counts[Status.UP_TO_DATE]} up-to-date, "
            f"{counts[Status.FAILURE]} failed, "
            f"{len(artifact.scan_failures)} failed during scanning."
        )
