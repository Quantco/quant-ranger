from quant_ranger._impl.aggregators import LogFailuresAggregator
from quant_ranger._impl.models import (
    RepositoryRef,
    ScanFailure,
    Status,
    UpdateItem,
    UpdateResult,
)
from quant_ranger._impl.testing import RecordingLogger
from quant_ranger.aggregators import AggregatorOptions


def test_log_failures_aggregator_logs_failed_tasks() -> None:
    logger = RecordingLogger()

    LogFailuresAggregator(AggregatorOptions()).aggregate(
        [
            _result(Status.UPDATED),
            _result(Status.FAILURE, name="broken", message="\nboom\nmore details"),
            _result(
                Status.FAILURE,
                name="error",
                message="captured\nmore details",
                details="Traceback (most recent call last):\n  hidden stack",
            ),
            _result(Status.SKIPPED, name="skipped", message="not relevant"),
            _result(Status.FAILURE, name="silent"),
        ],
        logger,
        [_scan_failure()],
        "copier",
    )

    output = logger.stream.getvalue()
    assert logger.infos == []
    assert "quantco/broken" in output
    assert "boom" in output
    assert "more details" in output
    assert "quantco/error" in output
    assert "captured" in output
    assert output.count("more details") == 2
    assert "hidden stack" in output
    assert "quantco/silent" in output
    assert "No message" in output
    assert "quantco/scan-broken (scan)" in output
    assert "scan failed" in output
    assert "scan traceback" in output
    assert "quantco/skipped" not in output
    assert "not relevant" not in output


def test_log_failures_aggregator_logs_no_failures() -> None:
    logger = RecordingLogger()

    LogFailuresAggregator(AggregatorOptions()).aggregate(
        [
            _result(Status.UPDATED),
            _result(Status.UP_TO_DATE),
            _result(Status.SKIPPED),
        ],
        logger,
        (),
        "copier",
    )

    assert logger.infos == ["No failures."]


def test_failure_entry_logs_plain_message_without_details_marker() -> None:
    logger = RecordingLogger(show_progress=True)

    LogFailuresAggregator(AggregatorOptions()).aggregate(
        [_result(Status.FAILURE, message="plain failure")],
        logger,
        (),
        "copier",
    )

    output = logger.stream.getvalue()
    assert "plain failure" in output
    assert "↳" not in output


def test_failure_entry_separates_details_from_bold_message() -> None:
    logger = RecordingLogger(show_progress=True)

    LogFailuresAggregator(AggregatorOptions()).aggregate(
        [_result(Status.FAILURE, message="boom", details="Traceback: boom\n")],
        logger,
        (),
        "copier",
    )

    output = logger.stream.getvalue()
    bold = "\x1b[1m"
    assert f"{bold}boom" in output
    assert "↳" in output
    assert output.index("boom") < output.index("↳") < output.index("Traceback: boom")


def test_failure_entry_styles_header_by_failure_source() -> None:
    logger = RecordingLogger(show_progress=True)

    LogFailuresAggregator(AggregatorOptions()).aggregate(
        [_result(Status.FAILURE, message="boom")],
        logger,
        [_scan_failure()],
        "copier",
    )

    output = logger.stream.getvalue()
    bold_red = "\x1b[1;31m"
    bold_dark_orange = "\x1b[1;38;5;208m"
    assert f"{bold_red}quantco/example" in output
    assert f"{bold_dark_orange}quantco/scan-broken (scan)" in output


def _result(
    status: Status,
    name: str = "example",
    message: str | None = None,
    details: str | None = None,
) -> UpdateResult:
    return UpdateResult(
        result=status,
        item=UpdateItem(repository_ref=RepositoryRef(owner="quantco", name=name)),
        message=message,
        details=details,
    )


def _scan_failure() -> ScanFailure:
    return ScanFailure(
        repository_ref=RepositoryRef(owner="quantco", name="scan-broken"),
        message="scan failed",
        details="scan traceback",
    )
