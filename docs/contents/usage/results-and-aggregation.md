# Results and aggregation

Every update task records a status.
A run can also save the individual results and repository scan failures as JSON for another command or CI step.

## Save a results file

Pass `--results-file` before the updater name:

```bash {3}
quant-ranger update \
  --repository octo-org/octo-repo \
  --results-file results.json \
  pixi-update
```

The file identifies the updater and contains its typed task results plus any repositories that failed during scanning.
It can be uploaded as a CI artifact, processed by another tool, or passed to an aggregator.

The [`custom` one-off updater](../plugins/one-off-updaters) does not support `--results-file`.
Its script must write any required output itself.

## Run an aggregator

An aggregator requires an artifact from an earlier update run.
Create it by passing `--results-file PATH` to `quant-ranger update`, then pass the same path after the aggregator name:

```bash
quant-ranger aggregate log-failures results.json
```

Aggregators validate and read existing files.
They do not scan repositories or rerun the updater.
The producing updater must be installed so quant-ranger can load its item and output types.

See [built-in aggregators](../built-in-aggregators/index.md).
