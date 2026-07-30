from collections.abc import Sequence
from typing import Annotated, Any, NamedTuple, override

import requests
import typer

from quant_ranger._impl.helpers import CliError
from quant_ranger._impl.logger import Logger
from quant_ranger._impl.models import (
    Diagnostics,
    RepositoryRef,
    ScanFailure,
    Status,
    UpdateItem,
    UpdateOutput,
    UpdateResult,
)

from .._base import Aggregator, AggregatorOptions
from ._client import IncidentIoClient


class _AlertEvent(NamedTuple):
    """An alert event payload with the note to attach, or None when resolved."""

    repository: str
    deduplication_key: str
    payload: dict[str, Any]
    note: str | None


class IncidentIoAlertsOptions(AggregatorOptions):
    alert_source_config_id: Annotated[
        str,
        typer.Option(
            "--alert-source-config-id",
            help="ID of the incident.io HTTP alert source to send events to.",
        ),
    ]
    token: Annotated[
        str,
        typer.Option(
            "--token",
            envvar="INCIDENT_IO_TOKEN",
            help="incident.io alert source bearer token.",
        ),
    ]
    management_token: Annotated[
        str,
        typer.Option(
            "--management-token",
            envvar="INCIDENT_IO_MANAGEMENT_TOKEN",
            help=(
                "incident.io API token with the alerts.view and alerts.edit "
                "scopes (distinct from the alert source token)."
            ),
        ),
    ]
    deduplication_key_prefix: Annotated[
        str,
        typer.Option(
            "--deduplication-key-prefix",
            help=(
                "Prefix for per-repository alert deduplication keys. Use a "
                "distinct prefix per updater pipeline (e.g. "
                "`quant-ranger/pixi-update`) so pipelines do not resolve each "
                "other's alerts."
            ),
        ),
    ] = "quant-ranger"
    source_url: Annotated[
        str,
        typer.Option(
            "--source-url",
            help=(
                "Link attached to each alert, e.g. the GitHub Actions run "
                "that produced the results file."
            ),
        ),
    ]
    team: Annotated[
        str,
        typer.Option(
            "--team",
            help=(
                "Team name sent as `team` metadata, for alert sources that "
                "route alerts by a team attribute."
            ),
        ),
    ]
    api_url: Annotated[
        str,
        typer.Option(
            "--api-url",
            help="incident.io API base URL.",
        ),
    ] = "https://api.incident.io"


class IncidentIoAlertsAggregator(
    Aggregator[UpdateItem, UpdateOutput, IncidentIoAlertsOptions]
):
    name = "incident-io-alerts"
    description = (
        "Send a per-repository incident.io alert event for failed update "
        "tasks and scan failures; repositories without failures send a "
        "resolved event."
    )

    @override
    def aggregate(
        self,
        results: Sequence[UpdateResult[UpdateOutput, UpdateItem]],
        logger: Logger,
        scan_failures: Sequence[ScanFailure],
        updater_name: str,
    ) -> None:
        events = _build_alert_events(
            results,
            scan_failures,
            updater_name=updater_name,
            deduplication_key_prefix=self.options.deduplication_key_prefix,
            source_url=self.options.source_url,
            team=self.options.team,
        )
        if not events:
            logger.info("No repositories in results; no alert events to send.")
            return

        failed_repositories: list[str] = []
        with IncidentIoClient(
            api_url=self.options.api_url,
            alert_source_config_id=self.options.alert_source_config_id,
            alert_source_token=self.options.token,
            management_token=self.options.management_token,
        ) as client:
            for alert in events:
                if not _send_alert_event(client, alert, logger):
                    failed_repositories.append(alert.repository)

        if failed_repositories:
            raise CliError(
                "Failed to send incident.io alert events for: "
                + ", ".join(failed_repositories)
            )


def _send_alert_event(
    client: IncidentIoClient,
    alert: _AlertEvent,
    logger: Logger,
) -> bool:
    """Send one alert event and return whether all client operations succeeded."""
    try:
        response = client.send_alert_event(alert.payload)
        logger.debug(f"incident.io response for {alert.repository}: {response}")
        if alert.note is not None:
            alert_id = client.find_firing_alert_id(alert.deduplication_key)
            if alert_id is None:
                logger.warning(
                    f"No firing alert found for {alert.deduplication_key!r}; "
                    "skipping note."
                )
            else:
                client.attach_note(alert_id, alert.note)
    except requests.exceptions.HTTPError as error:
        body = (
            error.response.text.strip() if error.response is not None else ""
        ) or "[empty body]"
        logger.error(
            f"Failed to send alert event for {alert.repository}: {error}: {body}"
        )
        return False
    except requests.exceptions.RequestException as error:
        # Transport failures would affect every remaining repository the same way,
        # so abort instead of continuing per repository.
        raise CliError(f"Could not reach incident.io: {error}") from error
    logger.info(f"Sent {alert.payload['status']} alert event for {alert.repository}.")
    return True


def _build_alert_events(
    results: Sequence[UpdateResult[UpdateOutput, UpdateItem]],
    scan_failures: Sequence[ScanFailure],
    *,
    updater_name: str,
    deduplication_key_prefix: str,
    source_url: str | None,
    team: str | None,
) -> list[_AlertEvent]:
    """Build one alert event and an optional note per repository.

    Repositories with failed update tasks or scan failures get a firing event; all other
    repositories in the results get a resolved event so a previously fired alert with
    the same deduplication key auto-resolves. The event itself carries no failure
    content: all failure messages and details go into a markdown note. incident.io
    never updates an already-firing alert from a deduplicated event, but the note is
    appended on every run.
    """
    # The failed activity and diagnostics per repository; repositories
    # without failures map to an empty list. A repository can fail multiple
    # times, e.g. for several update items.
    failures: dict[RepositoryRef, list[tuple[str, Diagnostics]]] = {}

    for result in results:
        entries = failures.setdefault(result.item.repository_ref, [])
        if result.result == Status.FAILURE:
            entries.append(("updating", result))
    for scan_failure in scan_failures:
        failures.setdefault(scan_failure.repository_ref, []).append(
            ("scanning", scan_failure)
        )

    events = []
    for repository_ref in sorted(failures, key=lambda ref: ref.display_name):
        display_name = repository_ref.display_name
        entries = failures[repository_ref]
        # The plain owner/name (no branch suffix) for incident.io
        metadata: dict[str, Any] = {"repository": repository_ref.full_name}
        if team is not None:
            metadata["team"] = team
        deduplication_key = f"{deduplication_key_prefix}/{display_name}"
        event: dict[str, Any] = {
            "title": f"Updater Failed: {updater_name} in {display_name}",
            "deduplication_key": deduplication_key,
            "status": "firing" if entries else "resolved",
            "metadata": metadata,
        }
        if source_url is not None:
            event["source_url"] = source_url
        note = _note(repository_ref, entries) if entries else None
        events.append(_AlertEvent(display_name, deduplication_key, event, note))
    return events


def _note(
    repository_ref: RepositoryRef,
    failures: Sequence[tuple[str, Diagnostics]],
) -> str:
    """Render the failure messages and details as markdown."""
    repository_link = (
        f"[{repository_ref.display_name}]"
        f"(https://github.com/{repository_ref.full_name})"
    )
    sections = []
    for activity, diagnostics in failures:
        section = (
            f"Failed during {activity} {repository_link}: "
            f"{diagnostics.message or 'No message'}"
        )
        if diagnostics.details:
            section += f"\n```\n{diagnostics.details.rstrip()}\n```"
        sections.append(section)
    return "\n\n".join(sections)
