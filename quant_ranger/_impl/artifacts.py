from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError

from quant_ranger._impl.helpers import CliError
from quant_ranger._impl.models import ScanFailure, UpdateResult

if TYPE_CHECKING:
    from quant_ranger._impl.updaters import AnyUpdater


class UpdateResultsArtifact(BaseModel):
    """Portable artifact written by update runs and consumed by aggregators."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    updater: str
    updater_options: dict[str, JsonValue]
    generated_at: datetime
    dry_run: bool
    github_api_url: str
    workflow_url: str | None = None
    results: list[dict[str, JsonValue]]
    scan_failures: list[ScanFailure]


def write_results_file(
    results_file: Path,
    *,
    updater: AnyUpdater,
    results: Sequence[UpdateResult],
    scan_failures: Sequence[ScanFailure],
    dry_run: bool,
    github_api_url: str,
    workflow_url: str | None = None,
) -> None:
    # Store updater-specific result models as opaque JSON objects in the artifact.
    # Aggregators can parse them with the resolved updater type later, which keeps
    # the artifact envelope generic and the parsing path straightforward.
    serialized_results = [result.model_dump(mode="json") for result in results]
    artifact = UpdateResultsArtifact(
        updater=updater.name,
        updater_options=cast(
            dict[str, JsonValue], updater.options.model_dump(mode="json")
        ),
        generated_at=datetime.now(UTC),
        dry_run=dry_run,
        github_api_url=github_api_url.rstrip("/"),
        workflow_url=workflow_url,
        results=serialized_results,
        scan_failures=scan_failures,
    )
    try:
        results_file.write_text(f"{artifact.model_dump_json(indent=2)}\n")
    except OSError as error:
        raise CliError(
            f"Failed to write results file {results_file}: {error}"
        ) from error


def read_results_file(results_file: Path) -> UpdateResultsArtifact:
    try:
        return UpdateResultsArtifact.model_validate_json(results_file.read_text())
    except OSError as error:
        raise CliError(
            f"Failed to read results file {results_file}: {error}"
        ) from error
    except ValidationError as error:
        raise CliError(f"Invalid results file {results_file}: {error}") from error


def resolve_updater_type(
    updater_name: str,
    updater_types: Sequence[type[AnyUpdater]],
) -> type[AnyUpdater]:
    for updater_type in updater_types:
        if updater_type.name == updater_name:
            return updater_type

    raise CliError(
        f"Unknown updater in results file: {updater_name!r}. "
        "Make sure the updater is installed and registered."
    )


def parse_update_results(
    artifact: UpdateResultsArtifact,
    *,
    updater_type: type[AnyUpdater],
) -> list[UpdateResult]:
    result_model = UpdateResult[
        updater_type.output_type,
        updater_type.item_type,
    ]
    try:
        results = [
            result_model.model_validate(raw_result) for raw_result in artifact.results
        ]
    except ValidationError as error:
        raise CliError(f"Invalid update results in results file: {error}") from error

    return results
