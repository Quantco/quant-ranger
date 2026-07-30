# quant-ranger documentation

The site is built with Docusaurus. Run all documentation tasks from the
repository root through the Pixi `docs` environment.

## Develop locally

```bash
pixi run -e docs docs-start
```

`docs-start` runs the development server with hot reload. Use it while writing
or editing pages.

## Preview the production site

```bash
pixi run -e docs docs-serve
```

`docs-serve` first creates a production build and then serves the generated
static files. Use it to verify the site as it will be deployed. Unlike
`docs-start`, it does not hot-reload source changes.

## Run checks

```bash
pixi run -e docs docs-check
```

This runs the TypeScript check and production build used in CI. Run either step
individually with `docs-typecheck` or `docs-build`.

## Generate reference pages

The start and build tasks regenerate `docs/contents/reference/cli.md` and
`docs/contents/reference/python-api.md`. To generate them without starting or
building the site, run:

```bash
pixi run -e docs docs-reference
```
