import json
from pathlib import Path
from typing import cast

import pytest

from quant_ranger._impl.aggregators._copier_dashboard import (
    CopierDashboardAggregator,
    CopierDashboardOptions,
)
from quant_ranger._impl.github import GitHubClient
from quant_ranger._impl.helpers import CliError
from quant_ranger._impl.models import (
    RepositoryRef,
    ScanFailure,
    Status,
    UpdateItem,
    UpdateOptions,
    UpdateOutcome,
    UpdateResult,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.testing import (
    FakeGitHubClient,
    RecordingLogger,
    make_update_results_artifact,
)
from quant_ranger._impl.updaters._copier._dashboard import (
    CopierDashboardOutput,
    CopierDashboardUpdater,
    CopierDashboardValidationError,
)
from quant_ranger.site_config import SiteConfig


def test_copier_dashboard_validation_failure_includes_all_details() -> None:
    outcome = _update_dashboard("_commit: main\n")

    assert outcome.result == Status.FAILURE
    assert outcome.message == ".copier-answers.yml has 2 validation errors."
    assert outcome.details == (
        "Required Copier answer '_src_path' is missing.\n"
        "Copier answer '_commit' must be a PEP 440 version tag; branches, commit "
        "hashes, and Git-describe revisions are not released template versions."
    )


def test_copier_dashboard_handles_repository_without_answers() -> None:
    outcome = _update_dashboard(None)

    assert outcome.result == Status.UP_TO_DATE
    assert outcome.output == CopierDashboardOutput(copier_answers=None)


def test_copier_dashboard_accepts_valid_answers() -> None:
    outcome = _update_dashboard(
        "_src_path: gh:quantco/copier-template-python\n_commit: v1.2.3\n"
    )

    assert outcome.result == Status.UP_TO_DATE
    assert outcome.output is not None
    assert outcome.output.validation_errors == ()
    assert outcome.output.copier_answers == {
        "_src_path": "gh:quantco/copier-template-python",
        "_commit": "v1.2.3",
    }


@pytest.mark.parametrize(
    ("content", "expected_code"),
    [
        pytest.param("answer: [\n", "invalid-yaml", id="invalid-yaml"),
        pytest.param("- answer\n", "not-a-mapping", id="not-a-mapping"),
        pytest.param(
            "1: value\n_src_path: gh:quantco/template\n_commit: v1.0.0\n",
            "non-string-key",
            id="non-string-key",
        ),
        pytest.param(
            "_src_path: 42\n_commit: 1\n",
            "wrong-type",
            id="wrong-metadata-type",
        ),
        pytest.param(
            "_src_path: gh:quantco/template\n_commit: v1.0.0\nvalue: .nan\n",
            "non-json-value",
            id="non-json-value",
        ),
    ],
)
def test_copier_dashboard_rejects_malformed_answers(
    content: str,
    expected_code: str,
) -> None:
    outcome = _update_dashboard(content)

    assert outcome.result == Status.FAILURE
    assert outcome.output is not None
    assert expected_code in {error.code for error in outcome.output.validation_errors}


def test_copier_dashboard_aggregator_writes_browser_ready_data(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "data" / "copier" / "latest.json"
    aggregator = CopierDashboardAggregator(
        CopierDashboardOptions(output_file=output_file)
    )
    artifact = make_update_results_artifact(
        github_api_url="https://github.example/api/v3"
    )

    aggregator.aggregate(
        [
            UpdateResult(
                result=Status.UP_TO_DATE,
                item=_item("without-copier"),
                output=CopierDashboardOutput(copier_answers=None),
            ),
            UpdateResult(
                result=Status.UP_TO_DATE,
                item=_item("with-copier"),
                output=CopierDashboardOutput(
                    copier_answers={
                        "_src_path": "gh:quantco/copier-template-python.git",
                        "_commit": "v2.0.0",
                        "build_docs": True,
                    }
                ),
            ),
        ],
        RecordingLogger(),
        artifact,
    )

    payload = json.loads(output_file.read_text())
    assert payload["generatedAt"] == artifact.generated_at.isoformat()
    assert payload["columns"] == [
        {
            "id": "Repositories",
            "filter": {"kind": "values", "optionOrder": "frequency"},
            "kind": "repository",
        },
        {"id": ".copier-answers.yml", "filter": None, "kind": "metadata"},
        {
            "id": "Template",
            "filter": {"kind": "values", "optionOrder": "frequency"},
            "kind": "metadata",
        },
        {
            "id": "Version",
            "filter": {"kind": "values", "optionOrder": "version"},
            "kind": "metadata",
        },
        {
            "id": "Validation",
            "filter": {"kind": "values", "optionOrder": "frequency"},
            "kind": "metadata",
        },
        {
            "id": "build_docs",
            "filter": {"kind": "values", "optionOrder": "answer"},
            "kind": "answer",
        },
    ]
    assert payload["versions"] == ["v2.0.0"]
    assert [row["repository"] for row in payload["rows"]] == [
        "quantco/with-copier",
        "quantco/without-copier",
    ]
    assert payload["rows"][0]["url"] == "https://github.example/quantco/with-copier"
    assert payload["rows"][0]["values"]["build_docs"] is True
    assert payload["rows"][1]["values"][".copier-answers.yml"] is False


def test_copier_dashboard_aggregator_marks_invalid_metadata(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "latest.json"
    validation_error = CopierDashboardValidationError(
        field="_src_path",
        code="wrong-type",
        message="Copier answer '_src_path' must be a string.",
    )

    CopierDashboardAggregator(
        CopierDashboardOptions(output_file=output_file)
    ).aggregate(
        [
            UpdateResult(
                result=Status.FAILURE,
                item=_item("invalid-template"),
                output=CopierDashboardOutput(
                    copier_answers={"_src_path": 42, "_commit": "v1.0.0"},
                    validation_errors=(validation_error,),
                ),
            )
        ],
        RecordingLogger(),
        make_update_results_artifact(),
    )

    row = json.loads(output_file.read_text())["rows"][0]
    assert row["values"]["Template"] is None
    assert row["validationFailure"] == "_src_path=wrong-type"


def test_copier_dashboard_aggregator_reports_unwritable_output(
    tmp_path: Path,
) -> None:
    output_parent = tmp_path / "file"
    output_parent.write_text("not a directory")
    output_file = output_parent / "latest.json"
    aggregator = CopierDashboardAggregator(
        CopierDashboardOptions(output_file=output_file)
    )

    with pytest.raises(
        CliError,
        match="Failed to write Copier Dashboard data",
    ):
        aggregator.aggregate([], RecordingLogger(), make_update_results_artifact())


@pytest.mark.parametrize("failure", ["scan", "missing-output"])
def test_copier_dashboard_aggregator_rejects_incomplete_data(
    failure: str,
    tmp_path: Path,
) -> None:
    artifact = make_update_results_artifact(
        (
            [ScanFailure(repository_ref=_item("unreadable").repository_ref)]
            if failure == "scan"
            else []
        ),
    )
    results: list[UpdateResult[CopierDashboardOutput, UpdateItem]] = [
        UpdateResult(
            result=Status.FAILURE,
            item=_item("incomplete"),
            output=None,
        )
    ]
    aggregator = CopierDashboardAggregator(
        CopierDashboardOptions(output_file=tmp_path / "latest.json")
    )

    with pytest.raises(CliError, match="Cannot build the Copier Dashboard"):
        aggregator.aggregate(results, RecordingLogger(), artifact)


def _item(name: str) -> UpdateItem:
    return UpdateItem(repository_ref=RepositoryRef(owner="quantco", name=name))


def _update_dashboard(content: str | None) -> UpdateOutcome[CopierDashboardOutput]:
    github_client = FakeGitHubClient(
        file_contents=({".copier-answers.yml": content} if content is not None else {})
    )
    return CopierDashboardUpdater(UpdateOptions())._update(
        _item("example"),
        RunContext(
            github_client=cast(GitHubClient, github_client),
            site_config=SiteConfig(),
            logger=RecordingLogger(),
        ),
    )
