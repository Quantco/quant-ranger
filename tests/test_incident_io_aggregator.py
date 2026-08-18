from typing import Any

import pytest
import requests

from quant_ranger._impl.aggregators import IncidentIoAlertsAggregator
from quant_ranger._impl.aggregators._incident_io import _aggregator as aggregator_module
from quant_ranger._impl.helpers import CliError
from quant_ranger._impl.logger import LogLevel
from quant_ranger._impl.models import (
    RepositoryRef,
    ScanFailure,
    Status,
    UpdateItem,
    UpdateResult,
)
from quant_ranger._impl.testing import (
    RecordingLogger,
    make_update_results_artifact,
)


class _FakeIncidentIo:
    """IncidentIoClient stand-in that records high-level operations."""

    def __init__(self) -> None:
        self.options: dict[str, Any] | None = None
        self.sent_events: list[dict[str, Any]] = []
        self.alert_lookups: list[str] = []
        self.notes: list[tuple[str, str]] = []
        self.fail_repositories: set[str] = set()
        self.transport_error: requests.RequestException | None = None
        # Maps deduplication key to the ID of a currently firing alert.
        self.known_alerts: dict[str, str] = {}

    def __enter__(self) -> _FakeIncidentIo:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def send_alert_event(self, event: dict[str, Any]) -> str:
        if self.transport_error is not None:
            raise self.transport_error
        self.sent_events.append(event)
        repository = event.get("metadata", {}).get("repository")
        if repository in self.fail_repositories:
            response = requests.Response()
            response.status_code = 500
            response._content = b'{"type": "internal_error"}'
            raise requests.HTTPError("500 Server Error", response=response)
        return '{"status": "success"}'

    def find_firing_alert_id(self, deduplication_key: str) -> str | None:
        self.alert_lookups.append(deduplication_key)
        return self.known_alerts.get(deduplication_key)

    def attach_note(self, alert_id: str, content: str) -> None:
        self.notes.append((alert_id, content))


@pytest.fixture
def incident_io(monkeypatch: pytest.MonkeyPatch) -> _FakeIncidentIo:
    fake = _FakeIncidentIo()

    def client(**kwargs: Any) -> _FakeIncidentIo:
        fake.options = kwargs
        return fake

    monkeypatch.setattr(aggregator_module, "IncidentIoClient", client)
    return fake


def _options(**overrides: Any) -> Any:
    values: dict[str, Any] = {
        "alert_source_config_id": "source-1",
        "token": "secret-token",
        "management_token": "mgmt-token",
        "source_url": "https://github.com/quantco/example/actions/runs/1",
        "team": "example-team",
    }
    values.update(overrides)
    return IncidentIoAlertsAggregator.options_type.model_validate(values)


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


def test_sends_firing_and_resolved_events_per_repository(
    incident_io: _FakeIncidentIo,
) -> None:
    logger = RecordingLogger()

    IncidentIoAlertsAggregator(_options()).aggregate(
        [
            _result(Status.FAILURE, name="broken", message="boom"),
            _result(Status.FAILURE, name="broken", message="boom again"),
            _result(Status.UPDATED, name="healthy"),
        ],
        logger,
        make_update_results_artifact(
            [
                ScanFailure(
                    repository_ref=RepositoryRef(owner="quantco", name="scan-broken"),
                    message="scan failed",
                    details="scan traceback",
                )
            ]
        ),
    )

    events = {
        event["metadata"]["repository"]: event for event in incident_io.sent_events
    }
    assert set(events) == {
        "quantco/broken",
        "quantco/healthy",
        "quantco/scan-broken",
    }

    broken = events["quantco/broken"]
    assert broken["status"] == "firing"
    assert broken["title"] == "Updater Failed: copier in quantco/broken"
    assert broken["deduplication_key"] == "quant-ranger/quantco/broken"
    # The event carries no failure content; that lives in the note.
    assert "description" not in broken

    scan_broken = events["quantco/scan-broken"]
    assert scan_broken["status"] == "firing"

    healthy = events["quantco/healthy"]
    assert healthy["status"] == "resolved"

    assert incident_io.options == {
        "api_url": "https://api.incident.io",
        "alert_source_config_id": "source-1",
        "alert_source_token": "secret-token",
        "management_token": "mgmt-token",
    }

    assert logger.logged(LogLevel.INFO, "resolved alert event for quantco/healthy")


def test_uses_custom_deduplication_key_prefix(incident_io: _FakeIncidentIo) -> None:
    logger = RecordingLogger()

    IncidentIoAlertsAggregator(
        _options(deduplication_key_prefix="quant-ranger/zizmor")
    ).aggregate(
        [_result(Status.FAILURE, message="boom")],
        logger,
        make_update_results_artifact(),
    )

    (event,) = incident_io.sent_events
    assert event["deduplication_key"] == "quant-ranger/zizmor/quantco/example"


def test_sends_source_url_and_team(incident_io: _FakeIncidentIo) -> None:
    logger = RecordingLogger()

    IncidentIoAlertsAggregator(
        _options(
            source_url="https://github.com/quantco/example/actions/runs/9",
            team="other-team",
        )
    ).aggregate([_result(Status.UPDATED)], logger, make_update_results_artifact())

    (event,) = incident_io.sent_events
    assert event["source_url"] == ("https://github.com/quantco/example/actions/runs/9")
    assert event["metadata"]["team"] == "other-team"


def test_strips_repository_branch_from_metadata(
    incident_io: _FakeIncidentIo,
) -> None:
    logger = RecordingLogger()

    IncidentIoAlertsAggregator(_options()).aggregate(
        [
            UpdateResult(
                result=Status.FAILURE,
                item=UpdateItem(
                    repository_ref=RepositoryRef(
                        owner="quantco", name="example", branch="main"
                    )
                ),
                message="boom",
            )
        ],
        logger,
        make_update_results_artifact(),
    )

    (body,) = incident_io.sent_events
    assert body["title"] == "Updater Failed: copier in quantco/example@main"
    assert body["deduplication_key"] == "quant-ranger/quantco/example@main"
    # The branch is dropped so catalog-backed repository attributes can match.
    assert body["metadata"]["repository"] == "quantco/example"


def test_separates_alerts_per_branch(incident_io: _FakeIncidentIo) -> None:
    logger = RecordingLogger()

    IncidentIoAlertsAggregator(_options()).aggregate(
        [
            UpdateResult(
                result=Status.FAILURE,
                item=UpdateItem(
                    repository_ref=RepositoryRef(
                        owner="quantco", name="example", branch=branch
                    )
                ),
                message="boom",
            )
            for branch in ("main", "dev")
        ],
        logger,
        make_update_results_artifact(),
    )

    keys = {event["deduplication_key"] for event in incident_io.sent_events}
    assert keys == {
        "quant-ranger/quantco/example@main",
        "quant-ranger/quantco/example@dev",
    }


def test_logs_api_response_at_debug_level(incident_io: _FakeIncidentIo) -> None:
    logger = RecordingLogger()

    IncidentIoAlertsAggregator(_options()).aggregate(
        [_result(Status.FAILURE, message="boom")],
        logger,
        make_update_results_artifact(),
    )

    assert logger.logged(
        LogLevel.DEBUG,
        'incident.io response for quantco/example: {"status": "success"}',
    )


def test_attaches_note_to_firing_alert(incident_io: _FakeIncidentIo) -> None:
    incident_io.known_alerts["quant-ranger/quantco/example"] = "alert-1"
    logger = RecordingLogger()

    IncidentIoAlertsAggregator(_options()).aggregate(
        [
            _result(
                Status.FAILURE,
                message="boom",
                details="Traceback (most recent call last):\n  boom\n",
            ),
            _result(Status.UPDATED, name="healthy"),
        ],
        logger,
        make_update_results_artifact(),
    )

    assert incident_io.alert_lookups == ["quant-ranger/quantco/example"]

    # Only the firing repository gets a note; the resolved one does not.
    assert incident_io.notes == [
        (
            "alert-1",
            "Failed during updating "
            "[quantco/example](https://github.com/quantco/example): boom\n"
            "```\nTraceback (most recent call last):\n  boom\n```",
        )
    ]


def test_attaches_note_without_details(incident_io: _FakeIncidentIo) -> None:
    incident_io.known_alerts["quant-ranger/quantco/example"] = "alert-1"
    logger = RecordingLogger()

    IncidentIoAlertsAggregator(_options()).aggregate(
        [_result(Status.FAILURE, message="boom")],
        logger,
        make_update_results_artifact(),
    )

    # A failure without details still produces a note with the message.
    assert incident_io.notes == [
        (
            "alert-1",
            "Failed during updating "
            "[quantco/example](https://github.com/quantco/example): boom",
        )
    ]


def test_skips_note_when_alert_lookup_finds_nothing(
    incident_io: _FakeIncidentIo,
) -> None:
    logger = RecordingLogger()

    IncidentIoAlertsAggregator(_options()).aggregate(
        [_result(Status.FAILURE, message="boom", details="traceback")],
        logger,
        make_update_results_artifact(),
    )

    assert incident_io.notes == []
    assert logger.logged(LogLevel.WARNING, "skipping note")
    assert logger.logged(LogLevel.INFO, "firing alert event for quantco/example")


def test_reports_failures_without_message(incident_io: _FakeIncidentIo) -> None:
    incident_io.known_alerts["quant-ranger/quantco/example"] = "alert-1"
    logger = RecordingLogger()

    IncidentIoAlertsAggregator(_options()).aggregate(
        [_result(Status.FAILURE)],
        logger,
        make_update_results_artifact(
            [ScanFailure(repository_ref=RepositoryRef(owner="quantco", name="example"))]
        ),
    )

    ((_, content),) = incident_io.notes
    assert "Failed during updating" in content
    assert "Failed during scanning" in content
    assert content.count("No message") == 2


def test_no_repositories_sends_nothing(incident_io: _FakeIncidentIo) -> None:
    logger = RecordingLogger()

    IncidentIoAlertsAggregator(_options()).aggregate(
        [], logger, make_update_results_artifact()
    )

    assert incident_io.sent_events == []
    assert logger.logged(LogLevel.INFO, "no alert events to send")


def test_raises_cli_error_when_server_is_unreachable(
    incident_io: _FakeIncidentIo,
) -> None:
    incident_io.transport_error = requests.ConnectionError("connection refused")
    logger = RecordingLogger()

    with pytest.raises(CliError, match="Could not reach incident.io"):
        IncidentIoAlertsAggregator(_options()).aggregate(
            [_result(Status.FAILURE, message="boom")],
            logger,
            make_update_results_artifact(),
        )


def test_raises_cli_error_when_sending_fails(
    incident_io: _FakeIncidentIo,
) -> None:
    incident_io.fail_repositories.add("quantco/example")
    logger = RecordingLogger()

    with pytest.raises(CliError, match="quantco/example"):
        IncidentIoAlertsAggregator(_options()).aggregate(
            [
                _result(Status.FAILURE, message="boom"),
                _result(Status.UPDATED, name="healthy"),
            ],
            logger,
            make_update_results_artifact(),
        )

    assert logger.logged(LogLevel.ERROR, "quantco/example")
    # The error message includes the response body from incident.io.
    assert logger.logged(LogLevel.ERROR, "internal_error")
    # The healthy repository's event is still sent despite the earlier failure.
    assert logger.logged(LogLevel.INFO, "resolved alert event for quantco/healthy")
