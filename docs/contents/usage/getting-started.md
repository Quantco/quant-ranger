# Getting started

quant-ranger is distributed on [conda-forge](https://prefix.dev/channels/conda-forge/packages/quant-ranger) and [PyPI](https://pypi.org/project/quant-ranger/).
You need access to the repositories you want to update to use this tool.
The GitHub CLI is only required when using `--gh`.

## Install

We recommend Pixi, a package manager that installs conda and PyPI packages into isolated environments.
It resolves quant-ranger's non-Python dependencies, such as Git and Mergiraf, alongside the CLI itself, so a single command gives you a working installation.

See Pixi's [installation page](https://pixi.prefix.dev/latest/installation) for installation methods.

Run the CLI once without installing it:

```bash
pixi exec quant-ranger --help
```

For repeated use, install it globally:

```bash
pixi global install quant-ranger
quant-ranger --version
```

### Installing from PyPI

Installing `quant-ranger` as a conda package is strongly recommended because quant-ranger drives several external command-line tools that only conda can declare as dependencies.
The wheel on PyPI contains the same Python code, but if you install it with `pip`, you must make the tools listed under `[package.run-dependencies]` in [pixi.toml](https://github.com/Quantco/quant-ranger/blob/main/pixi.toml) available on your `PATH`.

Missing tools surface as runtime failures in the updaters that need them rather than as install-time errors.

The conda distribution is fully self-contained.

## Authenticate

For a local run, the shortest path is an existing GitHub CLI login:

```bash
gh auth login
gh auth status
```

Pass `--gh` to make quant-ranger read that login.
See [Token](authentication.md#token) and [GitHub App](authentication.md#github-app) for the other authentication paths.

## Preview an updater

Run `pixi-update` against one repository that contains `pixi.toml` and `pixi.lock`:

```bash
quant-ranger update \
  --gh \
  --repository octo-org/octo-repo \
  pixi-update
```

Replace the example repository with one your account can access.
quant-ranger scans the repository, creates a temporary checkout for each applicable item, runs the updater, and prints a result summary.

:::tip

The command above does not push a branch or modify a pull request. Use this mode to inspect updater behavior before publishing.
Add `--pr-details` to also print the proposed pull request and its full diff.

:::

An updater may report no items when its input files are absent. For example, `pixi-update` only applies to a `pixi.lock` with an adjacent `pixi.toml`.
Choose another command from the [built-in updater catalog](../built-in-updaters/index.md) if you want to try another updater.

## Publish the result

After reviewing the dry run, add `--publish-changes` to create pull requests:

```bash {4}
quant-ranger update \
  --gh \
  --repository octo-org/octo-repo \
  --publish-changes \
  pixi-update
```

For a root Pixi manifest, the `pixi-update` updater uses the deterministic `pixi-update/pixi.toml` branch.
Branch naming is updater-specific.
A later run rebuilds the update from the selected target branch, force-pushes that managed branch, and refreshes the pull request's title, body, and labels.
Every automatic commit by quant-ranger includes a `Quant-Ranger` trailer.

Before replacing an existing branch, quant-ranger checks every commit on its matching open pull request.
Commits authored by a GitHub bot or carrying the `Quant-Ranger` trailer are considered managed.
If it finds any other commit, it skips publication and leaves the branch and pull request unchanged.
`--force-push` overrides this protection only for explicitly selected repositories.
