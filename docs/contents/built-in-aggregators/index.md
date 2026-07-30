# Built-in aggregators

Aggregators process the structured JSON written by an update run.
They do not rescan repositories or rerun an updater.
See [Results and aggregation](../usage/results-and-aggregation.md#save-a-results-file) for the complete update-to-aggregation workflow.

:::warning[Plugins]

When the results come from [updaters supplied through a plugin](../plugins/installable-plugins.md), the producing updater must be installed when the artifact is read.
quant-ranger uses its registered item and output types to validate every result before running the aggregator.

To produce a different report or upload results elsewhere, implement [your own aggregator](../plugins/installable-plugins.md#implement-an-aggregator).
The repository's [`status-summary` example](https://github.com/quantco/quant-ranger/blob/main/examples/plugin/quant_ranger_example_plugin/aggregator.py) is a complete minimal implementation.

:::

## `log-failures`

`log-failures` prints:

- updater tasks whose result is `failure`.
- repositories that failed while scanning.

It prints “No failures” when neither exists.
Recorded failures do not make the aggregator itself exit nonzero.
Use it as a reporting step.

```bash title="Report recorded failures"
quant-ranger aggregate log-failures results.json
```

These excerpts come from a real run.
Repository names are anonymized and traceback details are redacted:

```console
Quantco/apple@main ───────────────────────────────────────────
Command copier update --vcs-ref=v0.5.3 --defaults exited with code 4.
↳
stderr:
-------
Template uses potentially unsafe feature: tasks.

Quantco/banana@main (scan) ───────────────────────────────────
Incompatible _commit format 'v0.4.1-60-g881f631'; only tags are allowed.
↳
[traceback redacted]

Quantco/cherry@main (scan) ───────────────────────────────────
Repository Quantco/copier-template-orange was not found or is inaccessible.
↳
[traceback redacted]
```

## `incident-io-alerts`

`incident-io-alerts` keeps one [incident.io](https://incident.io/) alert per repository for the configured deduplication-key prefix:

- a failed update or scan sends a firing event and attaches the diagnostics as an alert note.
- a repository without failures sends a resolved event for the same deduplication key.

Create an incident.io HTTP alert source, then provide its ID and token.
Adding notes also requires a separate API token with the `alerts.view` and `alerts.edit` scopes:

```bash title="Send alert events from a CI run"
export INCIDENT_IO_TOKEN="..."
export INCIDENT_IO_MANAGEMENT_TOKEN="..."

quant-ranger aggregate incident-io-alerts \
  --alert-source-config-id "$ALERT_SOURCE_CONFIG_ID" \
  --deduplication-key-prefix quant-ranger/pixi-update \
  --source-url "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID" \
  --team platform \
  results.json
```

Use a distinct `--deduplication-key-prefix` for each updater pipeline so one pipeline cannot resolve another's alerts.
The default is `quant-ranger`.
`--token` and `--management-token` can replace the two environment variables.
`--api-url` overrides the incident.io API root.

See the [CLI reference](../reference/cli.md#quant-ranger-aggregate-incident-io-alerts) for the exact arguments.
