import json
from collections.abc import Iterator
from typing import Any

import pytest
import requests

from quant_ranger._impl.aggregators._incident_io import _client as incident_io_client
from quant_ranger._impl.aggregators._incident_io._client import IncidentIoClient


class _FakeRequests:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.responses: list[requests.Response] = []

    # Patched onto `requests.Session` as an already-bound method, so the
    # session instance is not passed.
    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        self.requests.append({"method": method, "url": url, **kwargs})
        if self.responses:
            return self.responses.pop(0)
        return _response({"status": "success"})


def _response(payload: dict[str, Any]) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(payload).encode()
    return response


@pytest.fixture
def fake_requests(monkeypatch: pytest.MonkeyPatch) -> _FakeRequests:
    fake = _FakeRequests()
    monkeypatch.setattr(requests.Session, "request", fake.request)
    return fake


@pytest.fixture
def client(fake_requests: _FakeRequests) -> Iterator[IncidentIoClient]:
    with IncidentIoClient(
        api_url="https://incident.example/",
        alert_source_config_id="source-1",
        alert_source_token="alert-token",
        management_token="management-token",
    ) as value:
        yield value


def test_client_sends_alert_event(
    client: IncidentIoClient,
    fake_requests: _FakeRequests,
) -> None:
    assert client.send_alert_event({"status": "firing"}) == '{"status": "success"}'

    assert fake_requests.requests == [
        {
            "method": "POST",
            "url": "https://incident.example/v2/alert_events/http/source-1",
            "timeout": incident_io_client.REQUEST_TIMEOUT_SECONDS,
            "json": {"status": "firing"},
            "headers": {"Authorization": "Bearer alert-token"},
        }
    ]


def test_client_finds_firing_alert(
    client: IncidentIoClient,
    fake_requests: _FakeRequests,
) -> None:
    fake_requests.responses.append(_response({"alerts": [{"id": "alert-1"}]}))

    assert client.find_firing_alert_id("quant-ranger/example") == "alert-1"
    assert fake_requests.requests == [
        {
            "method": "GET",
            "url": "https://incident.example/v2/alerts",
            "timeout": incident_io_client.REQUEST_TIMEOUT_SECONDS,
            "params": {
                "deduplication_key[is]": "quant-ranger/example",
                "status[one_of]": "firing",
                "page_size": 1,
            },
            "headers": {"Authorization": "Bearer management-token"},
        }
    ]


def test_client_returns_none_when_firing_alert_is_missing(
    client: IncidentIoClient,
    fake_requests: _FakeRequests,
) -> None:
    fake_requests.responses.append(_response({"alerts": []}))

    assert client.find_firing_alert_id("quant-ranger/example") is None


def test_client_attaches_note(
    client: IncidentIoClient,
    fake_requests: _FakeRequests,
) -> None:
    client.attach_note("alert-1", "Failure details")

    assert fake_requests.requests == [
        {
            "method": "POST",
            "url": "https://incident.example/v1/alert_notes",
            "timeout": incident_io_client.REQUEST_TIMEOUT_SECONDS,
            "json": {"alert_id": "alert-1", "content": "Failure details"},
            "headers": {"Authorization": "Bearer management-token"},
        }
    ]


def test_client_raises_on_error_response(
    client: IncidentIoClient,
    fake_requests: _FakeRequests,
) -> None:
    error_response = _response({"type": "internal_error"})
    error_response.status_code = 500
    fake_requests.responses.append(error_response)

    with pytest.raises(requests.HTTPError):
        client.send_alert_event({"status": "firing"})


def test_client_paces_requests_per_endpoint(
    client: IncidentIoClient,
    fake_requests: _FakeRequests,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 0.0
    sleeps: list[float] = []

    def monotonic() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    monkeypatch.setattr(incident_io_client.time, "monotonic", monotonic)
    monkeypatch.setattr(incident_io_client.time, "sleep", sleep)

    for _ in range(3):
        client.send_alert_event({"status": "firing"})
    # The management endpoints are paced independently of alert ingestion,
    # so the first management request does not wait.
    client.attach_note("alert-1", "Failure details")

    alert_interval = 60 / incident_io_client.ALERT_EVENTS_PER_MINUTE
    assert sleeps == pytest.approx([alert_interval] * 2)
