# quant-ranger example plugin

A minimal plugin package for quant-ranger.

| Module           | Provides                                                                                        |
| ---------------- | ----------------------------------------------------------------------------------------------- |
| `scanner.py`     | `PythonProjectScanner`, which emits one typed item per repository with a named `pyproject.toml` |
| `updater.py`     | The `ensure-config` command with a typed `--enabled/--disabled` option                          |
| `aggregator.py`  | The `status-summary` command with a typed `--summary-label` option                              |
| `site_config.py` | A site config provider that sets deployment-wide defaults                                       |

The entry points are declared in [`pyproject.toml`](pyproject.toml).

## Try it

This directory is a self-contained Pixi workspace.
Run the CLI from here and the `ensure-config` and `status-summary` commands appear in help:

```bash
pixi run quant-ranger update --help
pixi run quant-ranger aggregate --help
```

## Run it from GitHub Actions

[`.github/workflows`](.github/workflows) holds a reusable updater workflow and two callers that schedule it.
They run `pixi run quant-ranger update` in this workspace, so the plugin's commands and site config are available without any extra configuration.
GitHub only reads workflows from a repository's root `.github`; copy them to your own repository root to use them.

The site config is registered through the `quant_ranger.site_config` entry point group and sets site-wide defaults such as the default `--owner` and the
trusted copier template allowlist.
