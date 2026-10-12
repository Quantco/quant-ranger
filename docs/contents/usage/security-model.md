# Security model

quant-ranger is designed to maintain the repositories of your own organization.
It is not intended to process repositories controlled by third parties.

## What quant-ranger trusts

Repositories that quant-ranger processes are **partially trusted**.
They belong to your organization, but a person who can change one repository should not gain control over the others or over the machine running quant-ranger.
Dependencies and package channels referenced by a repository are treated the same way, since their contents are outside your direct control.

Partially trusted means that quant-ranger may execute code defined by a repository, but only with limited access:

- [`pixi-update`](../built-in-updaters/pixi.md#pixi-update) runs Pixi, which may execute build backends declared by the repository or its dependencies, in a sandbox.
  The sandbox permits network access and only the files Pixi needs.
  Code running inside it can read the conda channel credentials that quant-ranger forwards into the sandbox for [private channels](../built-in-updaters/pixi.md#pixi-update).
  Since a repository chooses its own channels, assume it can obtain every channel credential available to the run.
  The sandbox does not receive the GitHub credentials of the run.
- [Copier updaters](../built-in-updaters/copier.md#template-trust) only execute template code for allowlisted templates.

:::warning[The sandbox is best-effort]

The `pixi-update` sandbox is experimental and only a temporary, best-effort mitigation; it may not stop every attack.
Code that escapes it runs with the privileges and credentials of the quant-ranger process, including the GitHub credentials of the run.
The proper fix is for Pixi to refuse executing untrusted code while resolving dependencies, see [prefix-dev/pixi#6385](https://github.com/prefix-dev/pixi/issues/6385).
Until then, also apply the measures from [Credentials are shared across a run](#credentials-are-shared-across-a-run) to limit the impact of a sandbox escape.

:::

The following are **fully trusted** and run without a sandbox:

- [One-off updaters](../plugins/one-off-updaters.md) loaded with the `custom` command
- [Installable plugins](../plugins/installable-plugins.md) and [site configuration](../plugins/site-configuration.md)
- The quant-ranger installation and the tools it invokes

## Credentials are shared across a run

A single run uses the same credentials for every repository it processes.
With a [GitHub App](authentication.md), that includes an installation token for every repository the app is installed on.

Limit what a run can access:

- Install the GitHub App only on the repositories quant-ranger should maintain, and grant only the [permissions](authentication.md) the enabled updaters need.
- Run quant-ranger as an unprivileged user, never as root.
- Prefer ephemeral runners, such as GitHub-hosted runners, that do not keep state between runs.
- Only provide credentials for the private channels that the processed repositories need.

## Reporting vulnerabilities

Report security issues through [GitHub's private vulnerability reporting](https://github.com/quantco/quant-ranger/security/advisories/new), not through public issues.
