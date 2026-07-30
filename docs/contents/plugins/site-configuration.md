import CodeBlock from '@theme/CodeBlock';
import examplePluginPyproject from '!!raw-loader!../../../examples/plugin/pyproject.toml';
import siteConfigExample from '!!raw-loader!../../../examples/plugin/quant_ranger_example_plugin/site_config.py';

# Site configuration

`SiteConfig` provides deployment-wide defaults.

## Define a site config

The repository's
[example site config](https://github.com/quantco/quant-ranger/blob/main/examples/plugin/quant_ranger_example_plugin/site_config.py)
populates every available field:

<CodeBlock
  language="python"
  title="quant_ranger_example_plugin/site_config.py"
  showLineNumbers>
{siteConfigExample}
</CodeBlock>

Overall, this configuration class contains:

- Trusted Copier templates (here [copier-template-python-open-source](https://github.com/Quantco/copier-template-python-open-source))
- PR descriptions and branch prefixes for updaters
- Copier migrations
- Miscellaneous settings such as GitHub API URL, commit author, etc.

The example's full `pyproject.toml` registers the site config alongside its updater and aggregator:

This allowlists [copier-template-python-open-source](https://github.com/Quantco/copier-template-python-open-source), Quantco's reviewed open-source Python project template.
Add your own templates the same way.

<CodeBlock
  language="toml"
  title="examples/plugin/pyproject.toml"
  metastring="{20-21}"
  showLineNumbers>
{examplePluginPyproject}
</CodeBlock>

### Install the site config

The example plugin includes the site config shown above.
Follow [Install and verify](installable-plugins.md#install-and-verify) to install it into the same environment as quant-ranger.

### Verify it is loaded

```bash
quant-ranger update --help
```

The `--owner` option shows the configured `default_owner` as its default.

## Options

| Field                            | Type                            | Purpose                                                                                                                                                                                                                                                                   |
| -------------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `default_owner`                  | `str \| None`                   | Owner for bare names in [repository selection](../usage/running-updates.md#explicit-repositories). `--owner` overrides it.                                                                                                                                                |
| `default_github_api_url`         | `str`                           | REST API root for [GitHub Enterprise](../usage/authentication.md#github-enterprise). `--github-api-url` overrides it.                                                                                                                                                     |
| `pixi_version_setup_pixi_marker` | `str`                           | Default marker used by [`pixi-version`](../built-in-updaters/pixi.md#pixi-version).                                                                                                                                                                                       |
| `pull_request_templates`         | `PullRequestTemplates`          | Titles, bodies, and branch prefixes used by [`zizmor`](../built-in-updaters/github-actions.md#zizmor), [`github-app-token`](../built-in-updaters/github-actions.md#github-app-token), and [`node-dependency-cooldown`](../built-in-updaters/node-dependency-cooldown.md). |
| `fallback_commit_author`         | `CommitAuthor`                  | Commit identity used with [GitHub App authentication](../usage/authentication.md#github-app). Personal tokens use the authenticated user.                                                                                                                                 |
| `copier_trusted_templates`       | `frozenset[str]`                | Complete `host/owner/repository` allowlist used by [Copier template trust](../built-in-updaters/copier.md#template-trust).                                                                                                                                                |
| `copier_migrations`              | `Mapping[str, CopierMigration]` | Named migrations exposed by [`copier-migration`](../built-in-updaters/copier.md#copier-migration). Setting this replaces the built-in example entirely.                                                                                                                   |

See the
[`SiteConfig` source](https://github.com/quantco/quant-ranger/blob/main/quant_ranger/_impl/site_config.py)
for the current built-in values.

### Customize pull-request templates

`PullRequestTemplates` contains templates for [`zizmor`](../built-in-updaters/github-actions.md#zizmor), [`node-dependency-cooldown`](../built-in-updaters/node-dependency-cooldown.md), and [`github-app-token`](../built-in-updaters/github-actions.md#github-app-token).
Copier migrations own their pull-request text instead.
Each template sets the title, the body, and the `branch_prefix` of its [managed branch](../built-in-updaters/index.md#managed-branches).
Use `dataclasses.replace` when only one template differs:

```python showLineNumbers {10-17}
from dataclasses import replace

from quant_ranger.site_config import (
    DEFAULT_PULL_REQUEST_TEMPLATES,
    PullRequestTemplate,
    SiteConfig,
)

site_config = SiteConfig(
    pull_request_templates=replace(
        DEFAULT_PULL_REQUEST_TEMPLATES,
        zizmor=PullRequestTemplate(
            title="chore: apply GitHub Actions fixes",
            body="Automated fixes produced by quant-ranger.",
            branch_prefix="zizmor-updater",
        ),
    ),
)
```

### Define Copier migrations

The [`copier-migration` updater](../built-in-updaters/copier.md#copier-migration) uses each `CopierMigration` to select the lowercase `host/owner/name` templates it applies to and an answer key from `.copier-answers.yml`.
Its resolver receives the current boolean, integer, or string value and returns the desired value.
Returning the current value skips the repository as up to date.
The migration also owns its pull-request template and may provide an optional post-migration hook.
A migration's templates control only its eligibility.
`copier_trusted_templates` independently controls whether Copier receives `--trust`.

```python showLineNumbers {8-19}
from quant_ranger.site_config import (
    CopierMigration,
    PullRequestTemplate,
    SiteConfig,
)

site_config = SiteConfig(
    copier_migrations={
        "enable-feature": CopierMigration(
            answer_key="enable_feature",
            templates=frozenset({"github.com/octo-org/python-template"}),
            resolve_desired_value=lambda _current_value: True,
            pull_request_template=PullRequestTemplate(
                title="chore: Enable the feature",
                body="Enable the Copier template feature.",
                branch_prefix="copier-migration",
            ),
        )
    },
)
```

:::warning[Trusted Copier templates execute code]

`copier_trusted_templates` entries are normalized to lowercase and must use `host/owner/repository` form.
Only list repositories whose release tags are protected and reviewed.
Copier receives the runner's GitHub token.

:::
