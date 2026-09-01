# quant-ranger

[![CI](https://img.shields.io/github/actions/workflow/status/quantco/quant-ranger/ci.yml?style=flat-square&branch=main)](https://github.com/quantco/quant-ranger/actions/workflows/ci.yml)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue?style=flat-square)](https://ranger.quantco.tech/)
[![conda-forge](https://img.shields.io/conda/vn/conda-forge/quant-ranger?logoColor=white&logo=conda-forge&style=flat-square)](https://prefix.dev/channels/conda-forge/packages/quant-ranger)
[![pypi-version](https://img.shields.io/pypi/v/quant-ranger.svg?logo=pypi&logoColor=white&style=flat-square)](https://pypi.org/project/quant-ranger)
[![python-version](https://img.shields.io/pypi/pyversions/quant-ranger?logoColor=white&logo=python&style=flat-square)](https://pypi.org/project/quant-ranger)

Automated repository maintenance across GitHub organizations. quant-ranger
discovers applicable work, runs typed update tasks in fresh checkouts, and can
publish the results as pull requests.

## Getting started

Run the CLI directly from conda-forge with Pixi:

```bash
pixi exec quant-ranger --help
```

For repeated use, install it globally:

```bash
pixi global install quant-ranger
```

Run an updater in dry-run mode with an existing GitHub CLI login:

```bash
quant-ranger update --gh --repository octo-org/octo-repo pixi-update
```

Add `--publish-changes` before the updater name to create or update a pull
request.

See the [documentation](https://ranger.quantco.tech/) for updaters,
authentication, automation, extension APIs, and the
[CLI reference](https://ranger.quantco.tech/).

### Installing from PyPI

Installing `quant-ranger` as a conda package is strongly recommended because quant-ranger drives several external command-line tools that only conda can declare as dependencies.
The wheel on PyPI contains the same Python code, but if you install it with `pip`, you must make the tools listed under `[package.run-dependencies]` in [pixi.toml](https://github.com/Quantco/quant-ranger/blob/main/pixi.toml) available on your `PATH`.

Missing tools surface as runtime failures in the updaters that need them rather than as install-time errors.

The conda distribution is fully self-contained.

## Development

Everything runs from the source checkout through Pixi. The first `pixi run`
creates the environment:

```bash
git clone https://github.com/quantco/quant-ranger
cd quant-ranger
pixi run pre-commit-install
pixi run test
pixi run lint
```

Run the CLI from the checkout with `pixi run quant-ranger ...`. Documentation
tasks are described in [`docs/README.md`](docs/README.md).

### Static frontend

The package includes an optional static frontend for browser-readable updater
reports. Export it without Node.js using
`quant-ranger frontend export --output-directory _site`.

See [Hosting the frontend](https://ranger.quantco.cloud/usage/hosting-frontend)
for local serving and a GitHub Pages deployment workflow.
