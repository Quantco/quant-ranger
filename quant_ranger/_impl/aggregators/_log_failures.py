from collections.abc import Sequence
from typing import override

from rich.console import Group, RenderableType
from rich.rule import Rule
from rich.text import Text

from quant_ranger._impl.artifacts import UpdateResultsArtifact
from quant_ranger._impl.logger import Logger
from quant_ranger._impl.models import (
    Diagnostics,
    Status,
    UpdateItem,
    UpdateOutput,
    UpdateResult,
)

from ._base import Aggregator, AggregatorOptions

UPDATE_FAILURE_STYLE = "red"
SCAN_FAILURE_STYLE = "dark_orange"


class LogFailuresAggregator(Aggregator[UpdateItem, UpdateOutput, AggregatorOptions]):
    name = "log-failures"
    description = (
        "Print recorded failures. Includes failed updater tasks and repository "
        "scans; recorded failures do not make this command exit nonzero."
    )

    @override
    def aggregate(
        self,
        results: Sequence[UpdateResult[UpdateOutput, UpdateItem]],
        logger: Logger,
        artifact: UpdateResultsArtifact,
    ) -> None:
        failures = [result for result in results if result.result == Status.FAILURE]
        if not failures and not artifact.scan_failures:
            logger.info("No failures.")
            return

        for failure in failures:
            logger.console.print(
                _failure_entry(str(failure.item), failure, style=UPDATE_FAILURE_STYLE)
            )
        for scan_failure in artifact.scan_failures:
            logger.console.print(
                _failure_entry(
                    f"{scan_failure.repository_ref.display_name} (scan)",
                    scan_failure,
                    style=SCAN_FAILURE_STYLE,
                )
            )


def _failure_entry(title: str, diagnostics: Diagnostics, *, style: str) -> Group:
    parts: list[RenderableType] = [
        Rule(Text(title, style=f"bold {style}"), style=style, align="left"),
        Text(diagnostics.message or "No message", style="bold"),
    ]
    if diagnostics.details:
        parts.append(Text("↳", style=style))
        parts.append(Text(diagnostics.details.rstrip("\n")))
    parts.append(Text())
    return Group(*parts)
