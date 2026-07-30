# GitHub Actions updaters

These updaters make narrowly scoped changes to GitHub Actions files.

## `zizmor`

The updater runs [zizmor](https://docs.zizmor.sh/) from the repository root:

```console
zizmor \
  --config <packaged-zizmor.yml> \
  --fix=all \
  --no-exit-codes \
  .
```

`<packaged-zizmor.yml>` is a packaged configuration that enables exactly two rules:

- [`ref-version-mismatch`](https://docs.zizmor.sh/audits/#ref-version-mismatch) corrects the version comment beside a hash-pinned action.
  - Fixing it needs the GitHub API to resolve which tag the pinned commit belongs to, so the updater forwards its GitHub credentials to zizmor.
  - Incorrect ref-versions can break Dependabot updates.
- [`dependabot-cooldown`](https://docs.zizmor.sh/audits/#dependabot-cooldown) statically checks and adds a cooldown period to Dependabot configuration files, which is important for supply chain security.

We recommend enforcing the remaining rules of zizmor with a pre-commit hook in each repository.

Currently, these are the only two available rules, but we plan to make them configurable in a future quant-ranger release.

A repository with no auditable inputs is skipped.
Changes use the updater's [managed branch](index.md#managed-branches).

```console
quant-ranger update \
  --repository octo-org/octo-repo \
  zizmor
```

## `github-app-token`

`github-app-token` migrates workflows and composite actions from the deprecated `app-id` input to `client-id` for v3.1 or newer releases within major v3 of [`actions/create-github-app-token`](https://github.com/actions/create-github-app-token),
following the input change introduced in [actions/create-github-app-token#353](https://github.com/actions/create-github-app-token/pull/353).
The configured secret or variable is not renamed.

```diff title=".github/workflows/release.yml"
       - name: Create installation token
         uses: actions/create-github-app-token@7bd03711494f032dfa3be3558f7dc8787b0be333 # v3.1.0
         with:
-          app-id: ${{ secrets.APP_ID }}
+          client-id: ${{ secrets.APP_ID }}
           private-key: ${{ secrets.APP_PRIVATE_KEY }}
```

Eligible action uses must be pinned to a full commit SHA with a `# v3.1.0`-style version comment.
A matching use without either fails that repository instead of guessing its version.
Verifiable releases outside the supported v3 range are left unchanged.

```console
quant-ranger update \
  --repository octo-org/octo-repo \
  github-app-token
```

For a compatible fork, pass its identifier without a revision:

```console {4}
quant-ranger update \
  --repository octo-org/octo-repo \
  github-app-token \
  --action octo-org/create-github-app-token
```
