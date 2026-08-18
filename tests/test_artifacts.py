import json
from datetime import datetime
from pathlib import Path

import pytest

from quant_ranger._impl.artifacts import (
    parse_update_results,
    read_results_file,
    resolve_updater_type,
    write_results_file,
)
from quant_ranger._impl.helpers import CliError
from quant_ranger._impl.models import (
    RepositoryRef,
    ScanFailure,
    Status,
    UpdateItem,
    UpdateOptions,
    UpdateResult,
)
from quant_ranger._impl.updaters import ZizmorUpdater


def test_write_results_file_writes_updater_results_and_scan_failures(
    tmp_path: Path,
) -> None:
    results_file = _write_sample_results_file(tmp_path / "results.json")

    artifact = read_results_file(results_file)
    assert artifact.updater == "zizmor"
    assert artifact.updater_options == {}
    assert artifact.dry_run is True
    assert artifact.github_api_url == "https://github.example/api/v3"
    assert (
        artifact.workflow_url == "https://github.example/acme/ranger/actions/runs/123"
    )
    assert isinstance(artifact.generated_at, datetime)
    assert artifact.scan_failures == [_sample_scan_failure()]
    assert artifact.results == [
        {
            "result": "updated",
            "item": {
                "repository_ref": {
                    "owner": "quantco",
                    "name": "example",
                    "branch": None,
                }
            },
            "output": None,
            "message": None,
            "details": None,
        }
    ]


def test_write_results_file_wraps_write_errors(tmp_path: Path) -> None:
    with pytest.raises(CliError, match="Failed to write results file"):
        _write_sample_results_file(tmp_path)


def test_read_results_file_rejects_extra_fields(tmp_path: Path) -> None:
    results_file = _write_sample_results_file(tmp_path / "results.json")
    payload = read_results_file(results_file).model_dump(mode="json")
    payload["unexpected"] = True
    results_file.write_text(f"{json.dumps(payload)}\n")

    with pytest.raises(CliError, match="Invalid results file"):
        read_results_file(results_file)


def test_read_results_file_requires_scan_failures(tmp_path: Path) -> None:
    results_file = _write_sample_results_file(tmp_path / "results.json")
    payload = read_results_file(results_file).model_dump(mode="json")
    del payload["scan_failures"]
    results_file.write_text(f"{json.dumps(payload)}\n")

    with pytest.raises(CliError, match="Invalid results file"):
        read_results_file(results_file)


def test_read_results_file_wraps_read_errors(tmp_path: Path) -> None:
    with pytest.raises(CliError, match="Failed to read results file"):
        read_results_file(tmp_path / "missing.json")


def test_read_results_file_wraps_invalid_json(tmp_path: Path) -> None:
    results_file = tmp_path / "results.json"
    results_file.write_text("{")

    with pytest.raises(CliError, match="Invalid results file"):
        read_results_file(results_file)


def test_resolve_updater_type_returns_registered_updater() -> None:
    assert resolve_updater_type("zizmor", (ZizmorUpdater,)) is ZizmorUpdater


def test_parse_update_results_parses_results(
    tmp_path: Path,
) -> None:
    results_file = _write_sample_results_file(tmp_path / "results.json")
    artifact = read_results_file(results_file)

    results = parse_update_results(
        artifact,
        updater_type=ZizmorUpdater,
    )

    assert results == [_sample_result()]


def test_resolve_updater_type_rejects_unknown_updater() -> None:
    with pytest.raises(CliError, match="Unknown updater"):
        resolve_updater_type("unknown", (ZizmorUpdater,))


def test_parse_update_results_rejects_invalid_result_json(tmp_path: Path) -> None:
    results_file = _write_sample_results_file(tmp_path / "results.json")
    artifact = read_results_file(results_file)
    raw_result = artifact.results[0]
    raw_item = raw_result["item"]
    assert isinstance(raw_item, dict)
    raw_item["unknown"] = "value"

    with pytest.raises(CliError, match="Invalid update results"):
        parse_update_results(
            artifact,
            updater_type=ZizmorUpdater,
        )


def _write_sample_results_file(results_file: Path) -> Path:
    write_results_file(
        results_file,
        updater=ZizmorUpdater(UpdateOptions()),
        results=[_sample_result()],
        scan_failures=[_sample_scan_failure()],
        dry_run=True,
        github_api_url="https://github.example/api/v3",
        workflow_url="https://github.example/acme/ranger/actions/runs/123",
    )
    return results_file


def _sample_scan_failure() -> ScanFailure:
    return ScanFailure(
        repository_ref=RepositoryRef(owner="quantco", name="broken"),
        message="Could not parse config.",
    )


def _sample_result() -> UpdateResult:
    return UpdateResult(
        result=Status.UPDATED,
        item=UpdateItem(repository_ref=RepositoryRef(owner="quantco", name="example")),
    )
