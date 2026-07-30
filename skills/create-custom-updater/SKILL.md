---
name: create-custom-updater
description: Write and run one-off quant-ranger custom updaters. Use when asked to iterate over repositories with quant-ranger — applying a change, auditing state, or collecting information — or to write, debug, or run a CustomFileUpdater Python file.
license: BSD-3-Clause
---

# Create a custom updater

Implement one-off repository migrations as standalone Python files loaded by
quant-ranger's `custom` updater. Keep each updater narrow, idempotent, and safe to
run repeatedly. An updater does not have to open pull requests: read-only tasks
that audit repositories and report through log messages and outcome statuses are
equally valid. Use a built-in updater or plugin instead when the behavior must be
configurable, scheduled, or maintained long-term.

## Verify the environment

quant-ranger is usually installed as a conda package. Before writing any code,
confirm how it is invoked and that authentication works:

```bash
quant-ranger update --help   # in a Pixi project, prefix with `pixi run`
quant-ranger update custom --help
```

If the command is missing, ask the user to add quant-ranger to the environment
rather than installing it yourself.

Authentication options for GitHub access (in order):

1. `--gh` uses `gh auth token` when passed (requires a logged-in `gh` CLI).
2. GitHub App authentication reads `GH_APP_CLIENT_ID` and `GH_APP_PRIVATE_KEY`
   (PEM contents); both must be set together.
3. `GH_TOKEN`.
4. `GITHUB_TOKEN`.

Custom updater files require Python >= 3.14 (`typing.override`, PEP 695 generics).

## Check the source of truth

Inspect the installed version's public API and signatures directly:

```bash
python -c "import inspect; from quant_ranger.updaters import UpdateTask; print(inspect.signature(UpdateTask))"
python -c "from quant_ranger import UpdateOutcome; help(UpdateOutcome)"
python -c "from quant_ranger.scanners import Scanner; help(Scanner)"
```

The supported modules are `quant_ranger`, `quant_ranger.updaters`,
`quant_ranger.scanners`, `quant_ranger.aggregators`, and
`quant_ranger.site_config`. Do not import from `quant_ranger._impl`; it is
private and can change without notice.

The GitHub repository at <https://github.com/quantco/quant-ranger> is a fallback
only; its `main` branch may be newer than the installed version. For CLI options,
use the `--help` output instead of reading source.

Do not copy a built-in updater wholesale. Reuse only the patterns required for the
requested migration.

## Plan the update

Determine:

- What one update item is — each item becomes one task run with its own status:
  one item per repository (`UpdateItem`) when the migration touches the
  repository as a whole, or one item per matching file or path (`PathUpdateItem`
  or a custom item type) when the same transformation applies independently to
  multiple locations and each should succeed, fail, and be reported on its own.
- What is validated where: the scanner performs cheap applicability checks via
  the GitHub API before cloning and yields no items for out-of-scope
  repositories; the task performs everything that needs the working tree —
  up-to-date detection, applying the transformation, validation commands — and
  returns `SKIPPED` or `FAILURE` for applicable-but-not-updatable repositories.
- Which commands or file transformations perform the update — or whether the
  task is read-only and only reports.
- What pull request title, body, branch, and optional labels to use, when
  changes are published.
- Whether settings can be constants or must come from environment variables.

Start validation with one explicitly named repository. Do not begin with owner-wide
or installation-wide discovery.

## Choose a scanner

Use the narrowest scanner that identifies applicable repositories without cloning
them unnecessarily:

- Use `RepositoriesScanner()` to emit one update item for every selected repository.
- Use `RepositoryFileScanner(filename_pattern=...)` to emit one repository-level
  item only when a matching basename exists. The optional `missing_message=...`
  argument is logged in debug mode when nothing matches.
- Define a custom scanner when the task needs matching path information or
  multiple independent items per repository. Implement
  `scan_repository(repository_ref, context)`: return items, return an empty list
  for out-of-scope repositories, and raise when a repository should be scanned but
  cannot be. Scan without cloning via
  `context.github_client.find_files_by_name(...)` and `get_file_content(...)`.
  Inspect `help(Scanner)` for the full contract.

To pass scanner findings to the task, subclass `UpdateItem` (a frozen Pydantic
model) and add the fields the task needs — use the built-in `PathUpdateItem`
subclass when a single path field suffices. Parameterize `Scanner[...]`,
`UpdateTask[...]`, and `CustomFileUpdater[...]` with the item type, and read it
in the task via `self.item`.

Define a custom scanner only when one repository-level item is insufficient. Do not
add scheduling to a one-off custom updater.

## Create the updater file

Define an `UpdateTask`, define a `CustomFileUpdater`, assign its scanner and task
type, and export an instantiated updater as lowercase `updater`:

```python
from typing import override

from quant_ranger import PullRequestOptions, Status, UpdateItem, UpdateOutcome
from quant_ranger.scanners import RepositoriesScanner
from quant_ranger.updaters import CustomFileUpdater, UpdateTask


class ExampleTask(UpdateTask[UpdateItem]):
    @override
    def run(self) -> UpdateOutcome:
        # Apply an idempotent transformation under self.checkout.absolute_path.
        example_file = self.checkout.absolute_path / "example.txt"
        example_file.write_text("example\n")

        if self.checkout.is_clean():
            return UpdateOutcome(
                result=Status.UP_TO_DATE,
                message="example.txt already up to date.",
            )

        self.checkout.add_all()
        pr_opened = self.context.github_client.create_pull_request(
            self.checkout,
            PullRequestOptions(
                title="Apply the example migration",
                body="Apply the one-off example migration.",
                source_branch="example-migration",
                quant_ranger_id=ExampleUpdater.name,
            ),
            self.context.logger,
        )
        return UpdateOutcome(
            result=Status.UPDATED if pr_opened else Status.SKIPPED,
        )


class ExampleUpdater(CustomFileUpdater[UpdateItem]):
    name = "example"
    description = "Apply the example one-off migration."
    scanner = RepositoriesScanner()
    task_type = ExampleTask


updater = ExampleUpdater()
```

Do not export the class itself or use another export name. Subclass
`CustomFileUpdater`, not `Updater`. Do not define `options_type`, constructor
arguments, or updater-specific CLI options. Read settings from environment variables
or define constants in the file when configuration is necessary. Validate required
environment variables before modifying a checkout, and never log secrets.

When the task publishes changes, do not commit, push, or open a pull request
separately. `create_pull_request` handles branching, committing, pushing, and
creating or updating the pull request, and it honors dry-run mode. Returning
`Status.UPDATED` alone does not publish anything. `PullRequestOptions` also
accepts `target_branch=` and `labels=`.

For a read-only task — auditing state, collecting information — skip the
pull-request call entirely and return `UP_TO_DATE` or `SKIPPED`. Logged findings
and outcome messages only end up in the run log; custom updaters do not support
`--results-file`. To persist findings, collect them in a module-level structure
in the updater file and write them to a file after all items ran, e.g. by
overriding `update_all` on the updater to call `super().update_all(...)` and
then dump the collected data. Tasks run in a thread pool when `--jobs` is
greater than one, so guard the shared structure with a lock.

## Implement the task

Perform checkout-specific work in `UpdateTask.run()`. Use:

- `self.checkout.absolute_path` as the repository root.
- `self.item` for scanner-produced input.
- `self.context.logger` for diagnostics (`info`, `debug`, `warning`, `error`).
- `self.context.github_client` for GitHub operations.

`GitHubClient.create_pull_request` automatically honors the run's dry-run or
publish mode.

Import `CommandError` and `get_exec_output_silently` from `quant_ranger`. Run
subprocesses with `get_exec_output_silently(command,
cwd=self.checkout.absolute_path, ...)`. It runs commands with a minimal
environment — only `PATH` and proxy variables are inherited — so pass any other
required variables explicitly via `env=`. Pass sensitive values through `env=` and
list them in `redact=` so they never appear in logs. Use `help()` or
`inspect.signature()` for the full helper signature and the
`RepositoryCheckout` methods (`is_clean`, `add_all`, `add`, `changed_files`,
`git_exec`).

## Select an outcome

Return the status that describes the task result:

| Status       | Use it when                                                                                                                            |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| `UP_TO_DATE` | The repository already has the requested state or the transformation produces no diff.                                                 |
| `UPDATED`    | Changes were prepared and the pull request was created, updated, or successfully simulated.                                            |
| `SKIPPED`    | The repository was applicable but intentionally left unchanged, such as when protected manual changes prevent updating a pull request. |
| `FAILURE`    | An expected operation failed and the updater can provide a concise message and useful details.                                         |

`UpdateOutcome` also accepts `message=` (one-line summary shown in the run log) and
`details=` (longer debug output, e.g. captured command output). Set both on
`FAILURE` outcomes.

Catch expected command or validation failures when a concise `Status.FAILURE`
outcome is more useful; `CommandError` from the command helper carries a summary
message and formatted output in `.details`. Allow unexpected exceptions to
propagate; quant-ranger converts them to failure results with tracebacks.

## Validate safely

Run one repository in dry-run mode first. Always pass `--pr-details-diff-lines`
so the run prints the pull-request diff — never judge a run by status counts
alone. Put common update options before `custom` and `--path` after it:

```bash
quant-ranger update \
  --repository owner/repository \
  --gh \
  --pr-details-diff-lines 200 \
  custom \
  --path ./custom_updater.py
```

`--repository` accepts `repo`, `owner/repo`, `repo@branch`, comma-separated lists,
and may be repeated. Add `--debug` only when diving deeper into a problem; it
logs subprocess commands and their captured output, which may include sensitive
values.

Dry-run mode is the default. Inspect the selected update items, the printed diff,
pull-request summary, and final status counts. Fix unexpected selection, wrong or
non-idempotent diffs, unsafe logging, or incorrect status reporting before
expanding the repository set.

Custom updaters do not support `--results-file`. Do not pass it.

## Publish changes

Publish only when the user explicitly requests it. Never publish blind: pass
`--publish-changes` only for repositories whose diff you have seen in a dry run
with `--pr-details-diff-lines` — the one repository being published, or all of
them when
publishing a widened selection — using the current version of the updater file.
Every edit to the updater invalidates earlier dry runs.

```bash
quant-ranger update \
  --repository owner/repository \
  --gh \
  --publish-changes \
  custom \
  --path ./custom_updater.py
```

Verify the resulting pull request before processing additional repositories. Do not
use `--force-push` unless the user explicitly authorizes overwriting manual changes;
it requires explicit `--repository` arguments. Dry runs may use any repository
selection — wide selections only become unsafe together with `--publish-changes`.

To widen scope after a verified single-repository run, omit `--repository` to
discover all active repositories of `--owner`, or pass
`--all-installed-repositories` (GitHub App credentials required; cannot be
combined with `--owner` or `--repository`). Use `--jobs N` for large runs.

## Diagnose common failures

- **Missing `updater` export:** Export an instantiated `CustomFileUpdater` as
  lowercase `updater`.
- **Invalid export type:** Subclass `CustomFileUpdater`, not the general `Updater`.
- **Custom options rejected:** Remove `options_type` and constructor arguments; use
  constants or environment variables.
- **Updater always reports changes:** Make the transformation idempotent and check
  `checkout.is_clean()`.
- **Changes are not published:** Stage changes and call `create_pull_request`;
  returning `UPDATED` alone does not publish anything.
- **Options are parsed incorrectly:** Place common update options before `custom` and
  `--path` after it.
- **Authentication errors:** Pass `--gh` with a logged-in `gh` CLI, set both
  `GH_APP_CLIENT_ID` and `GH_APP_PRIVATE_KEY`, or set
  `GH_TOKEN`/`GITHUB_TOKEN`.
- **No repositories are selected:** Check repository access, authentication,
  `--repository` syntax (`repo`, `owner/repo`, `repo@branch`), and scanner
  criteria.
- **Subprocess cannot find environment variables:** `get_exec_output_silently`
  inherits only `PATH` and proxy variables; pass everything else via `env=`.
- **Sensitive output appears in logs:** Stop, remove the sensitive output, and
  configure environment passing and `redact=` before rerunning.
