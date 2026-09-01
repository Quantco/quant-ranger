from pathlib import PurePosixPath

import pytest
from pydantic import ValidationError

from quant_ranger._impl.models import (
    PathUpdateItem,
    RepositoryRef,
    Status,
    UpdateItem,
    UpdateOutcome,
    UpdateOutput,
    UpdateResult,
)


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("example", RepositoryRef(owner="quantco", name="example")),
        (
            "example@release",
            RepositoryRef(owner="quantco", name="example", branch="release"),
        ),
        ("Other/example", RepositoryRef(owner="Other", name="example")),
        (
            "Other/example@release",
            RepositoryRef(owner="Other", name="example", branch="release"),
        ),
    ],
)
def test_repository_ref_parse(spec: str, expected: RepositoryRef) -> None:
    assert (
        RepositoryRef.parse(
            spec,
            default_owner="quantco",
        )
        == expected
    )


def test_repository_ref_parse_uses_default_branch() -> None:
    assert RepositoryRef.parse(
        "example",
        default_owner="quantco",
        default_branch="main",
    ) == RepositoryRef(owner="quantco", name="example", branch="main")


def test_repository_ref_parse_accepts_explicit_owner_without_default() -> None:
    assert RepositoryRef.parse(
        "Other/example",
        default_owner=None,
    ) == RepositoryRef(owner="Other", name="example")


def test_repository_ref_parse_requires_owner_when_default_is_missing() -> None:
    with pytest.raises(ValueError, match="requires a default owner"):
        RepositoryRef.parse("example", default_owner=None)


@pytest.mark.parametrize("spec", ["", "/example", "owner/", "a/b/c"])
def test_repository_ref_parse_rejects_invalid_specs(spec: str) -> None:
    with pytest.raises(ValueError, match="Invalid repository spec"):
        RepositoryRef.parse(spec, default_owner="quantco")


def test_repository_ref_display_names() -> None:
    assert RepositoryRef(owner="quantco", name="example").full_name == "quantco/example"
    assert (
        RepositoryRef(owner="quantco", name="example").display_name == "quantco/example"
    )
    assert (
        RepositoryRef(owner="quantco", name="example", branch="main").display_name
        == "quantco/example@main"
    )
    assert (
        RepositoryRef(owner="quantco", name="example").display_name == "quantco/example"
    )
    assert (
        RepositoryRef(owner="quantco", name="example", branch="main").display_name
        == "quantco/example@main"
    )


def test_models_reject_extra_fields_and_are_frozen() -> None:
    with pytest.raises(ValidationError):
        RepositoryRef.model_validate(
            {"owner": "quantco", "name": "example", "extra": "field"}
        )

    item = UpdateItem(repository_ref=RepositoryRef(owner="quantco", name="example"))
    with pytest.raises(ValidationError):
        setattr(item, "path", "other")


def test_update_item_defaults_and_log_prefix() -> None:
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")

    root_item = UpdateItem(repository_ref=repository_ref)
    path_item = PathUpdateItem(repository_ref=repository_ref, path="pixi.lock")

    assert str(root_item) == "quantco/example@main"
    assert str(path_item) == "quantco/example@main pixi.lock"
    assert path_item.path == PurePosixPath("pixi.lock")
    assert root_item.log_prefix() == "[quantco/example@main]"
    assert path_item.log_prefix() == "[quantco/example@main pixi.lock]"


def test_update_result_from_outcome_copies_item_output_and_details() -> None:
    item = PathUpdateItem(
        repository_ref=RepositoryRef(owner="quantco", name="example"),
        path="pixi.lock",
    )
    outcome = UpdateOutcome[RecordingOutput](
        result=Status.UPDATED,
        pull_request_number=42,
        output=RecordingOutput(changed=True),
        message="done",
        details="Traceback: boom",
    )

    result = UpdateResult.from_outcome(outcome, item=item)

    assert result == UpdateResult(
        result=Status.UPDATED,
        item=item,
        pull_request_number=42,
        output=RecordingOutput(changed=True),
        message="done",
        details=outcome.details,
    )


def test_diagnostics_serialize_exceptions() -> None:
    try:
        raise ValueError("boom\nmore details")
    except ValueError as error:
        outcome = UpdateOutcome.from_exception(error, result=Status.FAILURE)

    assert outcome.message == "boom\nmore details"
    assert outcome.details is not None
    assert outcome.details.startswith("Traceback (most recent call last):")
    assert "test_diagnostics_serialize_exceptions" in outcome.details
    assert outcome.details.endswith("ValueError: boom\nmore details")


def test_diagnostics_fall_back_to_exception_type_for_empty_messages() -> None:
    try:
        raise ValueError()
    except ValueError as error:
        outcome = UpdateOutcome.from_exception(error, result=Status.FAILURE)

    assert outcome.message == "ValueError"


def test_models_dump_json_compatible_values() -> None:
    result = UpdateResult[RecordingOutput](
        result=Status.SKIPPED,
        item=PathUpdateItem(
            repository_ref=RepositoryRef(owner="quantco", name="example"),
            path="pixi.lock",
        ),
        output=RecordingOutput(changed=False),
    )

    assert result.model_dump(mode="json") == {
        "result": "skipped",
        "item": {
            "repository_ref": {
                "owner": "quantco",
                "name": "example",
                "branch": None,
            },
            "path": "pixi.lock",
        },
        "pull_request_number": None,
        "output": {"changed": False},
        "message": None,
        "details": None,
    }


class RecordingOutput(UpdateOutput):
    changed: bool
