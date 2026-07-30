---
description: Run quant-ranger updaters unattended on a schedule with GitHub Actions.
---

import CodeBlock from '@theme/CodeBlock';
import reusableUpdater from '!!raw-loader!../../../examples/plugin/.github/workflows/updater.yml';
import pixiUpdateUpdater from '!!raw-loader!../../../examples/plugin/.github/workflows/updater-pixi-update.yml';
import copierUpdater from '!!raw-loader!../../../examples/plugin/.github/workflows/updater-copier.yml';

# Scheduling updates

A workflow can simply install the CLI and run `quant-ranger update`, the same command described in [Running updates](running-updates.md).

Here we showcase a reusable workflow that wraps the quant-ranger CLI and how you can use it to run updaters.
The examples come from the [example plugin
workspace](https://github.com/quantco/quant-ranger/tree/main/examples/plugin): a
repository whose Pixi environment provides quant-ranger and a plugin.

| Workflow               | Responsibility                                                     |
| ---------------------- | ------------------------------------------------------------------ |
| One reusable workflow  | Installs quant-ranger and builds the command line                  |
| One caller per updater | Owns that updater's schedule, defaults, and manual-dispatch inputs |

:::warning

These are just starters, so adjust them to fit your setup.

:::

## The reusable workflow

This workflow takes an updater name and the global options as typed inputs, then assembles the argv for a single `quant-ranger update` call.

<CodeBlock language="yaml" title=".github/workflows/updater.yml" showLineNumbers>
  {reusableUpdater}
</CodeBlock>

Without `repositories`, the workflow falls back to `--all-installed-repositories`, which processes every repository the app is installed on.
See [Select repositories](running-updates.md#select-repositories).

### Credentials

The workflow reads GitHub App credentials from one variable and one secret:

| Name                 | Kind                | Contents                     |
| -------------------- | ------------------- | ---------------------------- |
| `GH_APP_CLIENT_ID`   | Repository variable | The app's client ID (app ID) |
| `GH_APP_PRIVATE_KEY` | Repository secret   | The app's PEM private key    |

[GitHub App](authentication.md#github-app) lists the repository permissions the app needs, which differ between dry runs and publishing.

### Loading plugins

quant-ranger discovers plugin updaters, aggregators, and site configs through the entry points of installed packages, so an [installable plugin](../plugins/installable-plugins.md) only has to be present in the same environment as the CLI.
The easiest way to guarantee this is to define all your plugins inside a repository and then just depend on quant-ranger, like the example does.

## Schedules for the pixi-update updater

`pixi-update` reads an `autoupdate-schedule` value from each repository's `pixi.toml` and can filter on it with `--schedule`.
We have separate cron jobs for each of those schedules and select the schedule option of quant-ranger accordingly.
This allows us to easily re-run those scheduled updaters manually if needed.

<CodeBlock language="yaml" title=".github/workflows/updater-pixi-update.yml" showLineNumbers>
  {pixiUpdateUpdater}
</CodeBlock>

The `resolve-schedule` job maps the cron string to a `--schedule` value and decides whether to run at all.
This is necessary because we set the monthly/quaterly schedules to run on the same weekday.
Otherwise, they might randomly overlap and drain the GitHub API rate limit.

See [Schedule filtering](../built-in-updaters/pixi.md#schedule-filtering) for how `--schedule` compares against each repository's configuration.

## Schedules for other updaters

Most updaters have no schedule filter at the moment.
In this case we can just forward useful inputs to manual dispatch inputs and set up a schedule.
Here an example using the [`copier` updater](../built-in-updaters/copier.md):

<CodeBlock language="yaml" title=".github/workflows/updater-copier.yml" showLineNumbers>
  {copierUpdater}
</CodeBlock>

This is the same shape as the `pixi-update` caller minus the `resolve-schedule` job, with `updater-args: ""` because the [`copier` updater](../built-in-updaters/copier.md) takes no options of its own.
Add one such file per updater you want to run.

## Processing results

To add further steps, add `--results-file` and pass the file to an aggregator.
See [Results and aggregation](results-and-aggregation.md) and the [built-in aggregators](../built-in-aggregators/index.md).
