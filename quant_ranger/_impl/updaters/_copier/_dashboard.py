import json
from collections.abc import Mapping
from typing import ClassVar, override

import yaml
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter, ValidationError

from quant_ranger._impl.models import (
    Status,
    UpdateItem,
    UpdateOptions,
    UpdateOutcome,
    UpdateOutput,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.scanners import RepositoriesScanner

from .._base import Updater
from ._common import COPIER_ANSWERS_FILE, is_valid_version_tag

_METADATA_FIELDS = ("_src_path", "_commit")


class CopierDashboardValidationError(BaseModel):
    """One validation problem in a repository's Copier answers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str | None
    code: str
    message: str


class CopierDashboardOutput(UpdateOutput):
    """Raw Copier data and validation results collected for one repository."""

    copier_answers: dict[str, JsonValue] | None
    validation_errors: tuple[CopierDashboardValidationError, ...] = ()


class CopierDashboardUpdater(Updater[UpdateItem, CopierDashboardOutput, UpdateOptions]):
    """Collect Copier answers without materializing repository checkouts."""

    name: ClassVar[str] = "copier-dashboard"
    description: ClassVar[str] = "Collect Copier dashboard data."
    scanner = RepositoriesScanner()

    @override
    def _update(
        self,
        item: UpdateItem,
        context: RunContext,
    ) -> UpdateOutcome[CopierDashboardOutput]:
        content = context.github_client.get_file_content(
            item.repository_ref,
            COPIER_ANSWERS_FILE,
        )
        if content is None:
            return UpdateOutcome(
                result=Status.UP_TO_DATE,
                output=CopierDashboardOutput(
                    copier_answers=None,
                ),
            )

        copier_answers, validation_errors = _parse_and_validate_copier_answers(content)
        output = CopierDashboardOutput(
            copier_answers=copier_answers,
            validation_errors=validation_errors,
        )
        if validation_errors:
            return UpdateOutcome(
                result=Status.FAILURE,
                output=output,
                message=_validation_summary(validation_errors),
                details="\n".join(error.message for error in validation_errors),
            )

        return UpdateOutcome(result=Status.UP_TO_DATE, output=output)


def _parse_and_validate_copier_answers(
    content: str,
) -> tuple[
    dict[str, JsonValue],
    tuple[CopierDashboardValidationError, ...],
]:
    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError as error:
        return {}, (
            CopierDashboardValidationError(
                field=None,
                code="invalid-yaml",
                message=f"Could not parse {COPIER_ANSWERS_FILE}: {error}",
            ),
        )

    if not isinstance(parsed, Mapping):
        return {}, (
            CopierDashboardValidationError(
                field=None,
                code="not-a-mapping",
                message=f"{COPIER_ANSWERS_FILE} must contain a mapping.",
            ),
        )

    answers: dict[str, JsonValue] = {}
    validation_errors: list[CopierDashboardValidationError] = []
    for key, value in parsed.items():
        if not isinstance(key, str):
            validation_errors.append(
                CopierDashboardValidationError(
                    field=None,
                    code="non-string-key",
                    message=f"Copier answer key {key!r} is not a string.",
                )
            )
            continue

        try:
            validated = _JSON_VALUE.validate_python(value)
            json.dumps(validated, allow_nan=False)
            answers[key] = validated
        except ValidationError, ValueError:
            validation_errors.append(
                CopierDashboardValidationError(
                    field=key,
                    code="non-json-value",
                    message=f"Copier answer {key!r} is not JSON-compatible.",
                )
            )

    for field in _METADATA_FIELDS:
        if field not in parsed:
            validation_errors.append(
                CopierDashboardValidationError(
                    field=field,
                    code="missing",
                    message=f"Required Copier answer {field!r} is missing.",
                )
            )
        elif not isinstance(parsed[field], str):
            validation_errors.append(
                CopierDashboardValidationError(
                    field=field,
                    code="wrong-type",
                    message=f"Copier answer {field!r} must be a string.",
                )
            )
        elif field == "_commit" and not is_valid_version_tag(parsed[field]):
            validation_errors.append(
                CopierDashboardValidationError(
                    field=field,
                    code="not-a-version-tag",
                    message=(
                        "Copier answer '_commit' must be a PEP 440 version tag; "
                        "branches, commit hashes, and Git-describe revisions are not "
                        "released template versions."
                    ),
                )
            )

    return answers, tuple(validation_errors)


_JSON_VALUE = TypeAdapter(JsonValue)


def _validation_summary(
    validation_errors: tuple[CopierDashboardValidationError, ...],
) -> str:
    count = len(validation_errors)
    noun = "error" if count == 1 else "errors"
    return f"{COPIER_ANSWERS_FILE} has {count} validation {noun}."
