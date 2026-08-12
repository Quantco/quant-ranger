# One-off updaters

A one-off updater is a trusted Python file loaded by the built-in `custom` command.
Use it for proofs of concept or non-recurring automation tasks.

## Limitations

One-off updaters have the following limitations:

- They cannot add command-specific CLI options.
- They cannot write quant-ranger result artifacts.
- They are loaded by path and are not discovered by other environments.

Use an [installable updater](installable-plugins.md#implement-an-updater) for these features or a versioned package.
Result processing belongs in an [installable aggregator](installable-plugins.md#implement-an-aggregator).

## Let a coding agent write it

The repository ships a [`create-custom-updater` skill](https://github.com/quantco/quant-ranger/blob/main/skills/create-custom-updater/SKILL.md) that teaches coding agents to write, debug, and run one-off updaters.
The conda-forge `quant-ranger` package depends on the matching skill package, so the skill is already present in your Pixi environment.
Run [pixi-skills](https://github.com/pavelzw/pixi-skills) through `pixi exec` to configure the skill for your coding agent:

```bash
pixi exec pixi-skills manage
```

The interactive prompt lets you select `create-custom-updater`, your coding agent, and whether to configure it for the current project or globally.
No separate installation of the skill is required.

Alternatively, install the skill directly from the repository with the [`skills` CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add quantco/quant-ranger --skill create-custom-updater
```

## Write the file

The file must export an object named `updater` that is an instance of `CustomFileUpdater`:

```python title="simple_custom_updater.py" showLineNumbers {26}
from typing import override

from quant_ranger import Status, UpdateItem, UpdateOutcome
from quant_ranger.scanners import RepositoriesScanner
from quant_ranger.updaters import CustomFileUpdater, UpdateTask


class SimpleCustomTask(UpdateTask[UpdateItem]):
    @override
    def run(self) -> UpdateOutcome:
        repository = self.item.repository_ref.display_name
        self.context.logger.info(f"Inspected {repository}.")
        return UpdateOutcome(
            result=Status.UP_TO_DATE,
            message="No changes made.",
        )


class SimpleCustomUpdater(CustomFileUpdater[UpdateItem]):
    name = "simple-custom"
    description = "Inspect each selected repository."
    scanner = RepositoriesScanner()
    task_type = SimpleCustomTask


updater = SimpleCustomUpdater()
```

`RepositoriesScanner` emits one `UpdateItem` per selected repository.
A custom [scanner](installable-plugins.md#scanner) can instead skip repositories or emit several items from one repository.

Inside `run()`, these attributes are available:

| Attribute                     | Purpose                                   |
| ----------------------------- | ----------------------------------------- |
| `self.checkout.absolute_path` | Root of the temporary repository checkout |
| `self.item`                   | Item produced by the scanner              |
| `self.context.github_client`  | Authenticated GitHub client               |
| `self.context.logger`         | Logger scoped to the current item         |

Return an `UpdateOutcome` with `UP_TO_DATE`, `UPDATED`, `SKIPPED`, or `FAILURE`.
Unexpected exceptions are recorded as failures and processing continues with the remaining items.

## Run it

Save the file anywhere and pass its path to `custom`. Shared update options go before `custom`.
`--path` belongs after it:

```bash {5}
quant-ranger update \
  --gh \
  --repository octo-org/octo-repo \
  custom \
  --path simple_custom_updater.py
```
