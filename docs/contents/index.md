---
slug: /
title: Introduction
description: Automated repository maintenance across GitHub organizations.
hide_title: true
---

import useBaseUrl from '@docusaurus/useBaseUrl';

<div className="project-title">
  <img
    className="project-title__logo"
    src={useBaseUrl('/img/quant-ranger-bot-transparent.png')}
    alt=""
  />
  <h1>quant-ranger</h1>
</div>

quant-ranger is an easily extensible Python CLI application for automating maintenance work across repositories in your GitHub organization.
It scans GitHub repositories to discover update tasks that need to be completed, runs them in a fresh checkout, and can publish the result as a managed pull request.

Compared with dependency-updating tools like [Renovate](https://docs.renovatebot.com/), quant-ranger is designed to be more versatile.
Its flexible pipeline can also create issues or perform other GitHub API work beyond opening pull requests.

Run it locally or integrate the same commands into [GitHub Actions workflows](usage/scheduling.md).

```bash title="Preview a Pixi lockfile update and its diff"
pixi exec quant-ranger update \
  --gh \
  --repository octo-org/octo-repo \
  --pr-details \
  pixi-update
```

We recommend using quant-ranger with [Pixi](https://pixi.prefix.dev/latest/).
The default feature-set integrates well with an organization that already uses Pixi and [Copier templates](https://copier.readthedocs.io/en/stable/).
However, customizations allow it to adapt to other environments as well.
See how [QuantCo uses this tool internally](quant-ranger-at-quantco.md).

Start with [installation](usage/getting-started.md#install), then [preview an updater](usage/getting-started.md#preview-an-updater) and [publish the result](usage/getting-started.md#publish-the-result).
The [built-in updater catalog](built-in-updaters/index.md) lists the built-in maintenance tasks.
[One-off updaters](plugins/one-off-updaters.md#write-the-file) and [installable plugins](plugins/installable-plugins.md#package-layout) can add more updaters and result aggregators.

For the exact command syntax, see the generated [update reference](reference/cli.md#quant-ranger-update) or [aggregate reference](reference/cli.md#quant-ranger-aggregate).
The [Python API reference](reference/python-api.md) documents the plugin interfaces.
