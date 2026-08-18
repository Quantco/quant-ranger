---
description: Export and host the static quant-ranger frontend.
---

import CodeBlock from '@theme/CodeBlock';
import deployFrontend from '!!raw-loader!../../../examples/github-pages/deploy-frontend.yml';
import copierDashboard from '!!raw-loader!../../../examples/github-pages/copier-dashboard.yml';

# Hosting the frontend

quant-ranger includes a static frontend for browser-readable updater reports.
It is distributed as prebuilt files in the quant-ranger package, but it is not hosted or deployed automatically.

Export the frontend from an installed version of quant-ranger:

```bash
quant-ranger frontend export --output-directory _site
```

The command copies `index.html` and the versioned assets into `_site`.
It does not copy or remove anything under `_site/data`, so updating the frontend does not erase reports produced by independent workflows.
No Node.js installation is needed.

## Preview the frontend locally

Serve the exported directory with any static file server. For example:

```bash
python -m http.server --directory _site 8000
```

Then open [http://localhost:8000/](http://localhost:8000/).
The production deployment is still completely static: GitHub Pages serves the HTML, JavaScript, and JSON files over HTTPS, with no application server.
Opening `_site/index.html` directly with a `file://` URL is unsupported because browsers prevent locally loaded JavaScript from fetching adjacent JSON files.

## Deploy the frontend to GitHub Pages

The following workflow assumes:

- quant-ranger is available through the repository's Pixi environment.
- this dashboard is the only site stored on the `gh-pages` branch.

Run the workflow once to create the `gh-pages` branch.
Then configure GitHub Pages to deploy from the root of that branch before adding data-refresh workflows.

<CodeBlock language="yaml" title=".github/workflows/deploy-frontend.yml">
  {deployFrontend}
</CodeBlock>

Rerun it after updating quant-ranger to publish a newer frontend.
`keep_files` retains the data already present on the Pages branch.
All workflows that write to this branch must use the same `quant-ranger-pages` concurrency group so that their deployments cannot overlap.

## Publish the Copier inventory

The Copier inventory uses its specialized updater and aggregator to write
`data/copier/latest.json`.

<CodeBlock language="yaml" title=".github/workflows/copier-dashboard.yml">
  {copierDashboard}
</CodeBlock>

Changing its schedule or repository selection does not require rebuilding the frontend.

## Authenticate data-refresh workflows

The data-refresh examples use a `QUANT_RANGER_TOKEN` repository secret for repository access.
Use a fine-grained token or GitHub App credentials that can read the repositories being scanned.
The workflow's built-in `github.token` is used separately to update the `gh-pages` branch.

## Updating only JSON

Frontend releases and report data have independent lifecycles:

| Change                    | Files deployed                          |
| ------------------------- | --------------------------------------- |
| New quant-ranger frontend | `index.html` and `assets/`              |
| Copier inventory refresh  | `data/copier/latest.json`               |

The examples use [`peaceiris/actions-gh-pages`](https://github.com/peaceiris/actions-gh-pages) because it supports retaining the rest of a Pages branch while deploying a subdirectory.
GitHub's Pages artifact deployment replaces the complete site and is therefore better suited to deployments where one workflow owns every file.
