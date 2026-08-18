---
description: Export and host the static quant-ranger frontend.
---

import CodeBlock from '@theme/CodeBlock';
import deployFrontend from '!!raw-loader!../../../examples/github-pages/deploy-frontend.yml';

# Hosting the frontend

quant-ranger includes a static frontend for browser-readable updater reports.
It is distributed as prebuilt files in the quant-ranger package, but it is not hosted or deployed automatically.

Export the frontend from an installed version of quant-ranger:

```bash
quant-ranger frontend export --output-directory _site
```

The command copies `index.html` and the versioned assets into `_site`.
It does not copy report data or remove anything already under `_site/data`, so updating the frontend does not erase data produced by independent workflows.
No Node.js installation is needed.

## Preview the frontend locally

Serve the exported directory with any static file server. For example:

```bash
python -m http.server --directory _site 8000
```

Then open [http://localhost:8000/](http://localhost:8000/).
The production deployment is still completely static: GitHub Pages serves the HTML, JavaScript, and JSON files over HTTPS, with no application server.
Opening `_site/index.html` directly with a `file://` URL is the unsupported case because browsers prevent JavaScript loaded from a local file from fetching adjacent JSON files.

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
`keep_files` retains report JSON already present on the Pages branch.
