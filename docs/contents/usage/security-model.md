# Security model

quant-ranger is designed to maintain the repositories of your own organization.
It is not intended to process repositories controlled by third parties.

## What quant-ranger trusts

Repositories that quant-ranger processes are **partially trusted**.
They belong to your organization, but a person who can change one repository should not gain control over the others or over the machine running quant-ranger.
Dependencies and package channels referenced by a repository are treated the same way, since their contents are outside your direct control.

Updaters that may execute code defined by a repository isolate it:

- [`pixi-update`](../built-in-updaters/pixi.md#pixi-update) runs Pixi in a sandbox.
- [Copier updaters](../built-in-updaters/copier.md#template-trust) only execute template code for allowlisted templates.

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
