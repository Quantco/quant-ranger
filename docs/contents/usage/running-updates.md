# Running updates

Updaters share some global options, such as concurrency and repository selection:

```text
quant-ranger update [GLOBAL OPTIONS] UPDATER [UPDATER OPTIONS]
```

Global options must appear before the updater name.
The highlighted final line is therefore an updater-specific option.

```bash {5}
quant-ranger update \
  --repository octo-org/octo-repo \
  --jobs 4 \
  pixi-update \
  --schedule weekly
```

The [`quant-ranger update` reference](../reference/cli.md#quant-ranger-update) is the complete option list.

## Select repositories

### Explicit repositories

`--repository` (short form: `-r`) accepts `repository`, `owner/repository`, and either form with `@branch`.
Repeat the option or pass a comma-separated list:

```bash {4-5}
# The owner applies to bare repository names.
quant-ranger update \
  --owner octo-org \
  --repository api,frontend \
  --repository worker@release/2.x \
  pixi-update
```

`owner/repository` names need no `--owner`.
Bare names require one, either from the option or a [site configuration](../plugins/site-configuration.md#options) default.

Explicit repositories are checked before scanning.
A missing or inaccessible repository or branch stops the command with an error.

### Every repository of a single user or organization

Omit `--repository` to discover repositories owned by an organization or user.
archived and empty repositories are excluded:

```bash {2}
quant-ranger update \
  --owner octo-org \
  pixi-update
```

A [site configuration](../plugins/site-configuration.md) can provide the default owner.
An explicit `--owner` overrides it.

### Every GitHub App installation

With [GitHub App credentials](authentication.md#github-app), scan all active repositories made available to the GitHub App:

```bash {2}
quant-ranger update \
  --all-installed-repositories \
  pixi-update
```

This mode cannot be combined with `--owner` or `--repository`.

## Preview and publish changes

By default, tasks run in temporary checkouts and report what they would update, but quant-ranger does not push or modify pull requests.
Add `--pr-details` to a preview to see exactly what a PR would contain.
To show pull-request metadata and the full diff:

```bash {3}
quant-ranger update \
  --repository octo-org/octo-repo \
  --pr-details \
  pixi-update
```

For bounded CI logs, `--pr-details-diff-lines N` retains `N` diff lines and adds an elision marker when it truncates the diff.
It also implies `--pr-details`.

After reviewing the preview, add `--publish-changes` to push the updater's managed branch and create or refresh its pull request:

```bash {4}
quant-ranger update \
  --repository octo-org/octo-repo \
  --pr-details \
  --publish-changes \
  pixi-update
```

### Managed pull requests

Each updater publishes to a deterministic branch; the [managed branches table](../built-in-updaters/index.md#managed-branches) lists them.
Every quant-ranger commit includes an `Quant-Ranger` trailer.

When a matching pull request already exists, quant-ranger checks all of its commits before replacing the branch.
A commit is safe when GitHub identifies its author as a bot or its message contains the `Quant-Ranger` trailer.
Any other commit is treated as a manual change: quant-ranger leaves the branch and pull request unchanged.

If every commit is safe, quant-ranger force-pushes a freshly generated commit and updates the existing pull request's title, body, and labels.
`--force-push` bypasses the manual-change guard, but only for explicitly selected repositories.
It does not imply `--publish-changes`.

:::caution[Force-pushing managed branches]

Use `--force-push` only after checking the existing pull request.
It discards manual changes on the updater's branch.

:::

## Concurrency and diagnostics

`--jobs N` runs scanner and update tasks concurrently.
Start with a small value and increase it for large installations while watching API and runner limits.
The default is `1`.

```bash {3}
quant-ranger update \
  --owner octo-org \
  --jobs 4 \
  pixi-update
```

Use `--debug` to view more detailed logs and subprocess outputs.
Those logs may contain sensitive subprocess output, so avoid publishing them without review.

```bash {3}
quant-ranger update \
  --repository octo-org/octo-repo \
  --debug \
  pixi-update
```
