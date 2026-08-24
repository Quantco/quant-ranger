# Our Usage at QuantCo

quant-ranger was built to maintain the repositories of QuantCo's GitHub organization.
This page describes that setup as a worked example for your own deployment.
We use quant-ranger to keep repositories up-to-date with our [Copier](https://copier.readthedocs.io/) templates and run its [built-in upaters](built-in-updaters/index.md) for updates not handled by [Dependabot](https://github.com/dependabot).
For a detailed walkthrough, watch quant-ranger author Yannik Tausch's PyCon talk, [“Kickstart Coding at Scale: How Project Template Automation Unlocks Developer Productivity”](https://www.youtube.com/watch?v=HATspzsbLwk).

## Copier templates

[Copier](https://copier.readthedocs.io/) is a project scaffolding tool.
A Copier template is a Git repository containing [Jinja](https://jinja.palletsprojects.com/) templates.
The `copier.yml` file defines the questions whose answers are used to render those templates.
Copier records those answers, along with the template source and its revision, in a `.copier-answers.yml` file inside the generated project:

```yaml title=".copier-answers.yml"
_commit: v0.5.3
_src_path: https://github.com/Quantco/copier-template-python
project_slug: example-project
minimal_python_version: py311
use_devcontainer: false
```

That file is what makes Copier more than one-shot scaffolding.
`copier update` reads it, rerenders the project at a newer template revision with the recorded answers, and merges the result, so a template fix reaches every repository instead of only new ones.
quant-ranger's [Copier updaters](built-in-updaters/copier.md) automate that step.

At QuantCo, for instance, we use two major Copier templates for Python projects:

| Template                             | For                                    |
| ------------------------------------ | -------------------------------------- |
| `copier-template-python`             | Internal Python libraries and services |
| `copier-template-python-open-source` | Open-source Python packages            |

The open-source template is public at [Quantco/copier-template-python-open-source](https://github.com/Quantco/copier-template-python-open-source).
Its `copier.yml` asks a handful of questions and renders a complete repository.
The internal template asks more (application or library, conda packaging, container builds, documentation) but produces the same shape.

Each of our rendered repositories is built around [Pixi](https://pixi.sh), a package manager from the conda ecosystem that resolves conda and PyPI dependencies into a single lockfile and doubles as a task runner.

Our Copier templates additionally include (among more):

- lint hooks via [lefthook](https://lefthook.dev)
- CI workflows
- agent instructions (`AGENTS.md`, `CLAUDE.md`)

### Organization-wide migrations

One-off changes ship as [Copier migrations](plugins/site-configuration.md#define-copier-migrations) in the site config.
A migration changes a single Copier answer and rerenders the template, so the template does the heavy lifting and every affected repository receives the change as a reviewable pull request.

For example, the `py39-deprecate` migration raised `minimal_python_version` to `py310`, with a resolver that parses the current answer and skips repositories already above the floor.

This has allowed us to keep all repositories consistent and up to date with our latest recommendations.

## Running quant-ranger

We have a QuantCo-specific package that implements a [site config](plugins/site-configuration.md) to tailor quant-ranger to our setup.
This package could also add additional updaters.

All built-in updaters run on weekly schedules, spread across the day to distribute GitHub API usage over time.
See the [example workflows](usage/scheduling.md), which show our way of configuring schedules.
Repositories set their own cadence for the [Pixi updaters](built-in-updaters/pixi.md).
The template seeds `[tool.update]` in `pixi.toml`, which provides monthly updates by default.

Every scheduled run writes a [results file](usage/results-and-aggregation.md) for the [`incident-io-alerts` aggregator](built-in-aggregators/index.md#incident-io-alerts).
A failed update or scan raises a per-repository alert with the failure details attached, and the next clean run resolves it.
This way, we have a clear overview of broken repositories.
