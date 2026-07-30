# Built-in updaters

Built-in updaters cover common repository maintenance without writing a plugin.
Each updater detects whether a repository is applicable and avoids changes when its required inputs are absent.

## GitHub Actions

| Command                                                  | Summary                                             |
| -------------------------------------------------------- | --------------------------------------------------- |
| [`zizmor`](github-actions.md#zizmor)                     | Fix selected GitHub Actions and Dependabot findings |
| [`github-app-token`](github-actions.md#github-app-token) | Rename the deprecated `app-id` action input         |

## Copier

| Command                                          | Summary                                                             |
| ------------------------------------------------ | ------------------------------------------------------------------- |
| [`copier`](copier.md#copier)                     | Advance a Copier-generated project to its newest template tag       |
| [`copier-migration`](copier.md#copier-migration) | Change one supported Copier answer at the current template revision |

## Pixi

| Command                                | Summary                                            |
| -------------------------------------- | -------------------------------------------------- |
| [`pixi-version`](pixi.md#pixi-version) | Update `pixi-version` pins in setup-pixi workflows |
| [`pixi-update`](pixi.md#pixi-update)   | Regenerate Pixi lockfiles                          |

## Node dependencies

| Command                                                   | Summary                                           |
| --------------------------------------------------------- | ------------------------------------------------- |
| [`node-dependency-cooldown`](node-dependency-cooldown.md) | Add release-age protections for Node dependencies |

## One-off updaters

| Command                                    | Summary                                        |
| ------------------------------------------ | ---------------------------------------------- |
| [`custom`](../plugins/one-off-updaters.md) | Run a trusted updater from a local Python file |

See [repository selection](../usage/running-updates.md#select-repositories), [preview and publication](../usage/running-updates.md#preview-and-publish-changes), and [concurrency](../usage/running-updates.md#concurrency-and-diagnostics) for shared options.
See [Configuration](../plugins/site-configuration.md#options) for deployment-wide defaults.

## Managed branches

Publication pushes each update item to a deterministic branch and opens one pull request from it.
`<angle brackets>` mark a suffix derived from the update item; the linked configuration changes the part before it.

| Command                    | Default branch                   | Configure with                                                                             |
| -------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------ |
| `zizmor`                   | `zizmor-fixes`                   | [Pull-request template](../plugins/site-configuration.md#customize-pull-request-templates) |
| `github-app-token`         | `github-app-token-client-id`     | [Pull-request template](../plugins/site-configuration.md#customize-pull-request-templates) |
| `node-dependency-cooldown` | `node-dependency-cooldown-fixes` | [Pull-request template](../plugins/site-configuration.md#customize-pull-request-templates) |
| `copier`                   | `copier-autoupdate-<tag>`        | Not configurable                                                                           |
| `copier-migration`         | `copier-migration-<migration>`   | [Copier migration](../plugins/site-configuration.md#define-copier-migrations)              |
| `pixi-version`             | `pixi-version-autoupdate`        | [`autoupdate-branch`](pixi.md#pixi-version) in the repository                              |
| `pixi-update`              | `pixi-update/<manifest path>`    | [`autoupdate-branch-prefix`](pixi.md#pixi-update) in each manifest                         |

quant-ranger checks [managed pull requests](../usage/running-updates.md#managed-pull-requests) prior to pushing to prevent overwriting manual changes on those branches.
