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
)
from quant_ranger.site_config import SiteConfig


def test_copier_dashboard_validation_failure_includes_all_details() -> None:
    repository = RepositoryRef(owner="octo-org", name="example")
    github_client = FakeGitHubClient(
        file_contents={".copier-answers.yml": "_commit: main\n"}
    )

    outcome = CopierDashboardUpdater(UpdateOptions())._update(
        UpdateItem(repository_ref=repository),
        RunContext(
            github_client=cast(GitHubClient, github_client),
            site_config=SiteConfig(),
            logger=RecordingLogger(),
        ),
    )

    assert outcome.result == Status.FAILURE
    assert outcome.message == ".copier-answers.yml has 2 validation errors."
    assert outcome.details == (
        "Required Copier answer '_src_path' is missing.\n"
        "Copier answer '_commit' must be a PEP 440 version tag; branches, commit "
        "hashes, and Git-describe revisions are not released template versions."
    )


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
    assert payload["generated_at"] == artifact.generated_at.isoformat()
    assert payload["columns"] == [
        "Repositories",
        ".copier-answers.yml",
        "Template",
        "Version",
        "Validation",
        "build_docs",
    ]
    assert payload["version_options"] == [
        {"template": None, "versions": ["v2.0.0"]},
        {"template": "python", "versions": ["v2.0.0"]},
    ]
    assert payload["answer_groups"] == [
        {
            "id": "boolean-template-options",
            "title": "Boolean Template Options",
            "template": None,
            "fields": ["build_docs"],
        },
        {
            "id": "python-boolean-template-options",
            "title": "Boolean Template Options",
            "template": "python",
            "fields": ["build_docs"],
        },
    ]
    assert [row["repository"] for row in payload["rows"]] == [
        "quantco/with-copier",
        "quantco/without-copier",
    ]
    assert payload["rows"][0]["url"] == "https://github.example/quantco/with-copier"
    assert payload["rows"][0]["values"]["build_docs"] is True
    assert payload["rows"][1]["values"][".copier-answers.yml"] is False


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
