import time
from typing import Any, Self

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

REQUEST_TIMEOUT_SECONDS = 30

# incident.io limits alert ingestion to 120 events/minute per alert source.
# Source: https://docs.incident.io/incidents/auto-create
ALERT_EVENTS_PER_MINUTE = 100

# Management API keys are limited to 1,200 requests/minute by default.
# Source: https://docs.incident.io/api-reference/introduction
MANAGEMENT_REQUESTS_PER_MINUTE = 1_000


# Retry connection failures and 429 responses, but never read timeouts:
# the request may already have been processed, and replaying it is ambiguous.
_RETRY_POLICY = Retry(
    total=3,
    connect=3,
    read=0,
    status=3,
    other=0,
    allowed_methods=frozenset({"GET", "POST"}),
    status_forcelist=frozenset({429}),
    respect_retry_after_header=True,
    backoff_factor=1,
    backoff_jitter=0.5,
    backoff_max=60,
    raise_on_status=False,
)


class _RequestRateLimiter:
    """Evenly space requests below a configured per-minute limit."""

    def __init__(self, requests_per_minute: int) -> None:
        self._minimum_interval = 60 / requests_per_minute
        self._next_request_at = 0.0

    def wait(self) -> None:
        delay = self._next_request_at - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self._next_request_at = time.monotonic() + self._minimum_interval


class IncidentIoClient:
    """Small incident.io client with endpoint-specific rate limiting."""

    def __init__(
        self,
        *,
        api_url: str,
        alert_source_config_id: str,
        alert_source_token: str,
        management_token: str,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._alert_source_config_id = alert_source_config_id
        self._alert_source_token = alert_source_token
        self._management_token = management_token
        # Alert ingestion has a much stricter limit than the management API,
        # so each gets its own pacing.
        self._alert_limiter = _RequestRateLimiter(ALERT_EVENTS_PER_MINUTE)
        self._management_limiter = _RequestRateLimiter(MANAGEMENT_REQUESTS_PER_MINUTE)
        self._session = requests.Session()
        self._session.mount(f"{self._api_url}/", HTTPAdapter(max_retries=_RETRY_POLICY))

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._session.close()

    def send_alert_event(self, event: dict[str, Any]) -> str:
        response = self._request(
            "POST",
            f"{self._api_url}/v2/alert_events/http/{self._alert_source_config_id}",
            self._alert_limiter,
            token=self._alert_source_token,
            json=event,
        )
        return response.text.strip()

    def find_firing_alert_id(self, deduplication_key: str) -> str | None:
        response = self._request(
            "GET",
            f"{self._api_url}/v2/alerts",
            self._management_limiter,
            token=self._management_token,
            params={
                "deduplication_key[is]": deduplication_key,
                "status[one_of]": "firing",
                # incident.io requires an explicit page size (>= 1); the
                # deduplication key uniquely identifies at most one alert.
                "page_size": 1,
            },
        )
        alerts = response.json()["alerts"]
        return alerts[0]["id"] if alerts else None

    def attach_note(self, alert_id: str, content: str) -> None:
        self._request(
            "POST",
            f"{self._api_url}/v1/alert_notes",
            self._management_limiter,
            token=self._management_token,
            json={"alert_id": alert_id, "content": content},
        )

    def _request(
        self,
        method: str,
        url: str,
        limiter: _RequestRateLimiter,
        *,
        token: str,
        **kwargs: Any,
    ) -> requests.Response:
        limiter.wait()
        response = self._session.request(
            method,
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT_SECONDS,
            **kwargs,
        )
        response.raise_for_status()
        return response
