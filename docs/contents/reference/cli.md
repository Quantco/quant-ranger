---
custom_edit_url: null
hide_table_of_contents: true
---

import TOCInline from '@theme/TOCInline';

# CLI reference

:::note[Built-in commands]

This page lists built-in commands. Installed plugins may add commands, and site
configuration may change runtime defaults.

:::

**Commands on this page**

<TOCInline toc={toc} minHeadingLevel={2} maxHeadingLevel={3} />

Run repository maintenance and process results.

**Usage**:

```console
$ quant-ranger [OPTIONS] [COMMAND] [ARGS]...
```

**Options**:

* `--version`: Show program&#x27;s version number and exit.
* `--install-completion`: Install completion for the current shell.
* `--show-completion`: Show completion for the current shell, to copy it or customize the installation.
* `--help`: Show this message and exit.

**Commands**:

* `update`: Run repository update tasks.
* `aggregate`: Process update results.
* `frontend`: Export the static frontend.

## `quant-ranger update`

Run repository update tasks. Runs are dry by default. Pass --publish-changes to push branches and create or update pull requests.

**Usage**:

```console
$ quant-ranger update [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `-r, --repository TEXT`: Repository to process. Repeat this option or use comma-separated values. Accepts repo, owner/repo, and either form with @branch.
* `--owner TEXT`: Owner for bare repository names. When --repository is omitted, discover active, non-empty repositories for this owner.
* `--all-installed-repositories`: Process all repositories this GitHub App has access to, across all installations. This option can only be used with GitHub App credentials and cannot be combined with --owner or --repository.
* `--gh`: Use `gh auth token` for GitHub authentication. Takes precedence over GitHub App credentials, GH_TOKEN, and GITHUB_TOKEN.
* `--github-api-url TEXT`: GitHub API base URL.  [default: https://api.github.com]
* `-j, --jobs INTEGER RANGE`: Number of scanner and updater tasks to run concurrently.  [default: 1; x&gt;=1]
* `-d, --debug`: Enable verbose diagnostic logging. This may include sensitive subprocess stdout or stderr.
* `--publish-changes`: Push managed branches and create or update pull requests. Without this, quant-ranger does not push or modify pull requests.
* `--force-push`: Allow overwriting managed pull request branches that contain manual changes. Requires --repository and does not enable publishing.
* `--results-file PATH`: Write task results and scan failures to a JSON artifact for `aggregate`. Unsupported by `custom`.
* `--pr-details`: Show pull request details, including the full diff.
* `--pr-details-diff-lines INTEGER RANGE`: Trim pull request detail diffs and enable --pr-details.  [x&gt;=1]
* `--help`: Show this message and exit.

**Commands**:

* `zizmor`: Fix configured zizmor findings.
* `copier-dashboard`: Collect repository data for the Copier...
* `copier`: Update a Copier template.
* `copier-migration`: Apply a Copier-answer migration.
* `pixi-version`: Update pinned Pixi versions.
* `pixi-update`: Regenerate Pixi lockfiles.
* `node-dependency-cooldown`: Configure Node dependency cooldowns.
* `github-app-token`: Migrate GitHub App token inputs.
* `custom`: Run a trusted Python updater.

### `quant-ranger update zizmor`

Fix configured zizmor findings. Applies the packaged automatic fixes to GitHub Actions and Dependabot configuration.

**Usage**:

```console
$ quant-ranger update zizmor [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `quant-ranger update copier-dashboard`

Collect repository data for the Copier Dashboard.

**Usage**:

```console
$ quant-ranger update copier-dashboard [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `quant-ranger update copier`

Update a Copier template. Advances root `.copier-answers.yml` projects to the newest PEP 440 tag.

**Usage**:

```console
$ quant-ranger update copier [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `quant-ranger update copier-migration`

Apply a Copier-answer migration. Changes a supported template answer without advancing the template revision.

**Usage**:

```console
$ quant-ranger update copier-migration [OPTIONS]
```

**Options**:

* `--migration [example]`: Copier migration to run.  [required]
* `--help`: Show this message and exit.

### `quant-ranger update pixi-version`

Update pinned Pixi versions. Rewrites marked setup-pixi workflow entries to a selected or latest release.

**Usage**:

```console
$ quant-ranger update pixi-version [OPTIONS]
```

**Options**:

* `--schedule [weekly|monthly|quarterly]`: Filter to update configurations whose schedule matches this value. Omit to include every cadence. Configurations set to `never` are always excluded.
* `--pixi-version TEXT`: Update to this pixi version (e.g. v0.70.0) instead of resolving the latest release from GitHub.
* `--setup-pixi-marker TEXT`: Only update workflow files containing this marker, e.g. when using a fork of setup-pixi.  [default: (prefix-dev/setup-pixi)]
* `--help`: Show this message and exit.

### `quant-ranger update pixi-update`

Regenerate Pixi lockfiles. Runs sandboxed `pixi update --no-install` for each lockfile with an adjacent `pixi.toml`.

**Usage**:

```console
$ quant-ranger update pixi-update [OPTIONS]
```

**Options**:

* `--schedule [weekly|monthly|quarterly]`: Filter to update configurations whose schedule matches this value. Omit to include every cadence. Configurations set to `never` are always excluded.
* `--help`: Show this message and exit.

### `quant-ranger update node-dependency-cooldown`

Configure Node dependency cooldowns. Adds release-age protections for Bun, pnpm, and npm.

**Usage**:

```console
$ quant-ranger update node-dependency-cooldown [OPTIONS]
```

**Options**:

* `--minimum-release-age-days INTEGER RANGE`: Minimum package release age to enforce, in whole days.  [default: 7; x&gt;=1]
* `--bun-minimum-release-age-exclude TEXT`: Package name to exempt from Bun minimum release age checks. Repeat for multiple packages; existing exclusions are preserved.
* `--minimum-release-age-exclude TEXT`: Package name or pattern to exempt from pnpm and npm minimum release age checks. Repeat for multiple values; existing exclusions are preserved.
* `--help`: Show this message and exit.

### `quant-ranger update github-app-token`

Migrate GitHub App token inputs. Renames `app-id` to `client-id` in eligible SHA-pinned v3 steps.

**Usage**:

```console
$ quant-ranger update github-app-token [OPTIONS]
```

**Options**:

* `--action TEXT`: Action identifier without `@revision`. Renames `app-id` only in full-SHA-pinned steps whose version comment is v3.1 or later within v3.  [default: actions/create-github-app-token]
* `--help`: Show this message and exit.

### `quant-ranger update custom`

Run a trusted Python updater. Imports a file that exports a `CustomFileUpdater` instance named `updater`.

**Usage**:

```console
$ quant-ranger update custom [OPTIONS]
```

**Options**:

* `-p, --path FILE`: Trusted Python file to import and execute without a sandbox. It must export `updater`, a `CustomFileUpdater` instance.  [required]
* `--help`: Show this message and exit.

## `quant-ranger aggregate`

Process update results. Run an aggregator over the JSON artifact created by passing `--results-file PATH` to `quant-ranger update`.

**Usage**:

```console
$ quant-ranger aggregate [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `-d, --debug`: Enable verbose diagnostic logging. This may include sensitive subprocess stdout or stderr.
* `--help`: Show this message and exit.

**Commands**:

* `log-failures`: Print recorded failures.
* `incident-io-alerts`: Send a per-repository incident.io alert...
* `copier-dashboard`: Write browser-ready JSON for the Copier...

### `quant-ranger aggregate log-failures`

Print recorded failures. Includes failed updater tasks and repository scans; recorded failures do not make this command exit nonzero.

**Usage**:

```console
$ quant-ranger aggregate log-failures [OPTIONS] RESULTS_FILE
```

**Arguments**:

* `RESULTS_FILE`: JSON artifact created by `quant-ranger update --results-file PATH`.  [required]

**Options**:

* `--help`: Show this message and exit.

### `quant-ranger aggregate incident-io-alerts`

Send a per-repository incident.io alert event for failed update tasks and scan failures; repositories without failures send a resolved event.

**Usage**:

```console
$ quant-ranger aggregate incident-io-alerts [OPTIONS] RESULTS_FILE
```

**Arguments**:

* `RESULTS_FILE`: JSON artifact created by `quant-ranger update --results-file PATH`.  [required]

**Options**:

* `--alert-source-config-id TEXT`: ID of the incident.io HTTP alert source to send events to.  [required]
* `--token TEXT`: incident.io alert source bearer token.  [env var: INCIDENT_IO_TOKEN; required]
* `--management-token TEXT`: incident.io API token with the alerts.view and alerts.edit scopes (distinct from the alert source token).  [env var: INCIDENT_IO_MANAGEMENT_TOKEN; required]
* `--deduplication-key-prefix TEXT`: Prefix for per-repository alert deduplication keys. Use a distinct prefix per updater pipeline (e.g. `quant-ranger/pixi-update`) so pipelines do not resolve each other&#x27;s alerts.  [default: quant-ranger]
* `--source-url TEXT`: Link attached to each alert, e.g. the GitHub Actions run that produced the results file.  [required]
* `--team TEXT`: Team name sent as `team` metadata, for alert sources that route alerts by a team attribute.  [required]
* `--api-url TEXT`: incident.io API base URL.  [default: https://api.incident.io]
* `--help`: Show this message and exit.

### `quant-ranger aggregate copier-dashboard`

Write browser-ready JSON for the Copier Dashboard.

**Usage**:

```console
$ quant-ranger aggregate copier-dashboard [OPTIONS] RESULTS_FILE
```

**Arguments**:

* `RESULTS_FILE`: JSON results file written by `quant-ranger update`.  [required]

**Options**:

* `-o, --output-file PATH`: Path at which to write the browser-ready dashboard JSON.  [required]
* `--help`: Show this message and exit.

## `quant-ranger frontend`

Export the packaged static frontend for self-hosting.

**Usage**:

```console
$ quant-ranger frontend [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `export`: Write the frontend to a directory.

### `quant-ranger frontend export`

Write the packaged static frontend to a directory.

**Usage**:

```console
$ quant-ranger frontend export [OPTIONS]
```

**Options**:

* `-o, --output-directory PATH`: Directory in which to write the static site.  [required]
* `--help`: Show this message and exit.
