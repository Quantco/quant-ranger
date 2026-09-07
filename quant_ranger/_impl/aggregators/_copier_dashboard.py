import json
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal, TypedDict, override

import typer
from packaging.version import Version
from pydantic import JsonValue

from quant_ranger._impl.artifacts import UpdateResultsArtifact
from quant_ranger._impl.github import github_web_url
from quant_ranger._impl.helpers import CliError
from quant_ranger._impl.logger import Logger
from quant_ranger._impl.models import UpdateItem, UpdateResult
from quant_ranger._impl.updaters._copier import (
    CopierDashboardOutput,
    CopierDashboardValidationError,
)
from quant_ranger._impl.updaters._copier._common import normalize_template_name

from ._base import Aggregator, AggregatorOptions

_REPOSITORIES = "Repositories"
_COPIER_ANSWERS = ".copier-answers.yml"
_TEMPLATE = "Template"
_VERSION = "Version"
_VALIDATION = "Validation"
_BASE_COLUMNS = (
    _REPOSITORIES,
    _COPIER_ANSWERS,
    _TEMPLATE,
    _VERSION,
    _VALIDATION,
)
_METADATA_FIELDS = {"_src_path": _TEMPLATE, "_commit": _VERSION}

type _DashboardValue = str | int | float | bool | None


class _DashboardRow(TypedDict):
    repository: str
    url: str
    values: dict[str, _DashboardValue]
    validationFailure: str


class _DashboardColumn(TypedDict):
    id: str
    kind: Literal["answer", "metadata", "repository"]


class CopierDashboardOptions(AggregatorOptions):
    output_file: Annotated[
        Path,
        typer.Option(
            "--output-file",
            "-o",
            help="Path at which to write the browser-ready dashboard JSON.",
        ),
    ]


class CopierDashboardAggregator(
    Aggregator[UpdateItem, CopierDashboardOutput, CopierDashboardOptions]
):
    name = "copier-dashboard"
    description = "Write Copier dashboard JSON."

    @override
    def aggregate(
        self,
        results: Sequence[UpdateResult[CopierDashboardOutput, UpdateItem]],
        logger: Logger,
        artifact: UpdateResultsArtifact,
    ) -> None:
        if artifact.scan_failures:
            failed_repositories = ", ".join(
                failure.repository_ref.display_name
                for failure in artifact.scan_failures
            )
            raise CliError(
                "Cannot build the Copier Dashboard because repository scanning "
                f"failed for: {failed_repositories}."
            )

        missing_outputs = [
            str(result.item) for result in results if result.output is None
        ]
        if missing_outputs:
            raise CliError(
                "Cannot build the Copier Dashboard because updater output is missing "
                f"for: {', '.join(missing_outputs)}."
            )

        outputs = sorted(
            (
                (result.item, result.output)
                for result in results
                if result.output is not None
            ),
            key=lambda entry: (
                entry[0].repository_ref.name,
                entry[0].repository_ref.full_name,
            ),
        )
        answer_fields = _answer_fields(
            [output for _, output in outputs],
        )
        column_ids = [*_BASE_COLUMNS, *answer_fields]
        web_url = github_web_url(artifact.github_api_url)
        rows = [
            _dashboard_row(item, output, column_ids, answer_fields, web_url)
            for item, output in outputs
        ]
        payload = {
            "generatedAt": artifact.generated_at.isoformat(),
            "columns": _dashboard_columns(column_ids),
            "rows": rows,
            "versions": _versions(rows),
        }

        output_file = self.options.output_file
        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(f"{json.dumps(payload, indent=2)}\n")
        except OSError as error:
            raise CliError(
                f"Failed to write Copier Dashboard data to {output_file}: {error}"
            ) from error

        logger.info(f"Wrote Copier Dashboard data to {output_file}.")


def _answer_fields(outputs: Sequence[CopierDashboardOutput]) -> list[str]:
    fields: set[str] = set()
    for output in outputs:
        if output.copier_answers is not None:
            fields.update(output.copier_answers)
        fields.update(
            error.field for error in output.validation_errors if error.field is not None
        )

    return sorted(fields - _METADATA_FIELDS.keys() - set(_BASE_COLUMNS))


def _dashboard_row(
    item: UpdateItem,
    output: CopierDashboardOutput,
    columns: Sequence[str],
    answer_fields: Sequence[str],
    github_url: str,
) -> _DashboardRow:
    values: dict[str, _DashboardValue] = {column: "" for column in columns}
    values[_REPOSITORIES] = item.repository_ref.full_name
    answers = output.copier_answers
    if answers is not None:
        values[_COPIER_ANSWERS] = True
        values[_TEMPLATE] = normalize_template_name(answers.get("_src_path"))
        version = answers.get("_commit")
        values[_VERSION] = version if isinstance(version, str) else ""
        values[_VALIDATION] = "Invalid" if output.validation_errors else "Valid"
        for field in answer_fields:
            values[field] = _dashboard_value(answers.get(field, ""))
    else:
        values[_COPIER_ANSWERS] = False

    for error in output.validation_errors:
        if error.field is not None and error.code != "missing":
            values[_ui_field(error.field)] = None

    return _DashboardRow(
        repository=item.repository_ref.full_name,
        url=f"{github_url}/{item.repository_ref.full_name}",
        values=values,
        validationFailure=_validation_failure(output.validation_errors),
    )


def _dashboard_value(value: JsonValue) -> _DashboardValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _ui_field(field: str) -> str:
    return _METADATA_FIELDS.get(field, field)


def _validation_failure(
    errors: Sequence[CopierDashboardValidationError],
) -> str:
    labels = dict.fromkeys(
        f"{error.field if error.field is not None else 'document'}={error.code}"
        for error in errors
    )
    return ", ".join(labels)


def _versions(rows: Sequence[_DashboardRow]) -> list[str]:
    versions = {
        version
        for row in rows
        if isinstance((version := row["values"][_VERSION]), str) and version
    }
    return sorted(versions, key=lambda value: (Version(value), value), reverse=True)


def _dashboard_columns(column_ids: Sequence[str]) -> list[_DashboardColumn]:
    columns: list[_DashboardColumn] = []
    for column in column_ids:
        columns.append(
            _DashboardColumn(
                id=column,
                kind=(
                    "repository"
                    if column == _REPOSITORIES
                    else "metadata"
                    if column in _BASE_COLUMNS
                    else "answer"
                ),
            )
        )
    return columns
