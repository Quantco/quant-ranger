# Copier updaters

[Copier](https://copier.readthedocs.io/) renders projects from a template and records the template, its revision, and the given answers in a `.copier-answers.yml` file, so later template improvements can be replayed onto the generated project.
[The write-up on our usage of quant-ranger at QuantCo](../quant-ranger-at-quantco.md) shows how templates and these updaters keep a whole organization's repositories in sync.

Both Copier updaters follow the same pipeline and differ only in what they change:

1. Read the root `.copier-answers.yml`.
2. Rerender the project: `copier` at the newest template tag, `copier-migration` with one changed answer.
3. Resolve remaining conflicts with [Mergiraf](https://mergiraf.org/) and run `pixi lock` if the root `pixi.toml` changed.
4. Open a pull request.

The `_src_path` in the answers file may use the `gh:owner/name`, HTTPS, or SSH form; templates on the repository's GitHub Enterprise host are supported.

## Template trust

```yaml title=".copier-answers.yml"
_src_path: gh:octo-org/python-template
_commit: v2.4.0
project_name: example-project
minimal_python_version: py314
```

:::warning[Template trust]

Copier templates can execute code.
quant-ranger passes `--trust` only when the exact template repository is allowlisted in the deployment's site config.
The allowlist is empty by default, so Copier runs untrusted.
Review [Configuration](../plugins/site-configuration.md#define-copier-migrations) before allowing template hooks to execute.

:::

## `copier`

`copier` advances the project to the newest template tag.
During scanning it:

1. Reads `_src_path` and `_commit` from the answers file.
2. Fetches template tags from the same GitHub host as the target repository.
3. Ignores non-version tags and selects the newest tag newer than `_commit` using PEP 440 ordering.

The update task then runs `copier update --defaults` at the selected tag:

```console
copier update \
  --vcs-ref=<latest-tag> \
  --defaults
```

`--vcs-ref` tells Copier which template revision to render.
quant-ranger passes the tag selected during scanning.

`--trust` is appended only for an allowlisted template.

`_commit` must itself be a PEP 440 version tag.
Branch names, commit hashes, and Git-describe values are not automatic release boundaries and are rejected.

```console
quant-ranger update \
  --repository octo-org/octo-repo \
  copier
```

The resulting pull request includes the tag messages for every release crossed by the update, and its [managed branch](index.md#managed-branches) ends in the selected tag.
If no newer version tag exists, the repository is up to date.

## `copier-migration`

`copier-migration` changes one answer without updating the template version.
During scanning, quant-ranger reads the current `_commit` and the answer being migrated from `.copier-answers.yml`.
Copier still rerenders the project, so generated files may change along with the answers file.

It invokes Copier from the repository root:

```console
copier update \
  --defaults \
  --vcs-ref=:current: \
  --data <answer-key>=<desired-value>
```

`--vcs-ref` tells Copier which template revision to render.
The special `:current:` value reuses the `_commit` from `.copier-answers.yml`, so the migration does not advance the template.

`--trust` follows the same allowlist as the regular Copier updater.

The available migrations are defined by the deployment's site config in [`copier_migrations`](../plugins/site-configuration.md#define-copier-migrations).
`--migration` accepts the configured names.
Each migration declares the templates it applies to, the answer key it changes, a resolver that maps the current value to the desired value, and the pull-request template.
The built-in default contains one neutral `example` migration that sets `example_feature` to `true`.

The answer must already exist in the file.
A missing key or a value already at the desired state is skipped rather than introduced implicitly.

```console {4}
quant-ranger update \
  --repository octo-org/octo-repo \
  copier-migration \
  --migration example
```

Conceptually, this migration changes:

```diff title=".copier-answers.yml"
-example_feature: false
+example_feature: true
```

Run different migrations separately.
Each uses its own [managed branch](index.md#managed-branches) ending in the migration name.
