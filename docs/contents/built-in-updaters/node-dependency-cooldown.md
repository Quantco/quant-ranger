import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Node dependency cooldown

`node-dependency-cooldown` configures node projects to delay newly published packages before they become eligible for installation.
It detects supported lockfiles (bun, pnpm, npm) recursively and creates or updates the package-manager configuration beside each lockfile.

Run it with the default 7-day cooldown:

```console
quant-ranger update \
  --repository octo-org/octo-repo \
  node-dependency-cooldown
```

The resulting settings are:

<Tabs groupId="node-package-manager">
  <TabItem value="bun" label="Bun">

```toml title="bunfig.toml"
[install]
minimumReleaseAge = 604800
```

  </TabItem>
  <TabItem value="pnpm" label="pnpm">

```yaml title="pnpm-workspace.yaml"
minimumReleaseAge: 10080
blockExoticSubdeps: true
```

  </TabItem>
  <TabItem value="npm" label="npm">

```ini title=".npmrc"
min-release-age=7
```

  </TabItem>
</Tabs>

Mind that the units are different for bun (seconds), pnpm (minutes), and npm (days).

pnpm also gets [`blockExoticSubdeps: true`](https://pnpm.io/settings#blockexoticsubdeps), which rejects dependencies fetched from non-registry sources.
Existing stronger cooldowns are preserved.
Weaker values are raised to the requested minimum.

## Change the minimum age

`--minimum-release-age-days` accepts a positive whole number and applies the correct unit for every detected package manager:

```console {4}
quant-ranger update \
  --repository octo-org/octo-repo \
  node-dependency-cooldown \
  --minimum-release-age-days 14
```

## Exclude packages

[Bun's `minimumReleaseAgeExcludes`](https://bun.sh/docs/pm/cli/install#minimum-release-age) accepts exact package names.
[pnpm's `minimumReleaseAgeExclude`](https://pnpm.io/settings#minimumreleaseageexclude) and [npm's `min-release-age-exclude`](https://docs.npmjs.com/cli/v11/using-npm/config/#min-release-age-exclude) also accept patterns.
The options are therefore separate and repeatable:

```console {4-7}
quant-ranger update \
  --repository octo-org/octo-repo \
  node-dependency-cooldown \
  --bun-minimum-release-age-exclude @example/config \
  --bun-minimum-release-age-exclude @example/ui \
  --minimum-release-age-exclude '@example/*' \
  --minimum-release-age-exclude generated-package
```

This adds only missing entries and preserves existing exclusions:

<Tabs groupId="node-package-manager">
  <TabItem value="bun" label="Bun">

```toml title="bunfig.toml" {3}
[install]
minimumReleaseAge = 604800
minimumReleaseAgeExcludes = ["@example/config", "@example/ui"]
```

  </TabItem>
  <TabItem value="pnpm" label="pnpm">

```yaml title="pnpm-workspace.yaml" {2-4}
minimumReleaseAge: 10080
minimumReleaseAgeExclude:
  - "@example/*"
  - generated-package
blockExoticSubdeps: true
```

  </TabItem>
  <TabItem value="npm" label="npm">

```ini title=".npmrc" {2-3}
min-release-age=7
min-release-age-exclude[]=@example/*
min-release-age-exclude[]=generated-package
```

  </TabItem>
</Tabs>

:::note

Unrelated settings and comments are preserved.
If an existing configuration uses a form that cannot be edited safely, quant-ranger logs a warning and leaves that setting alone instead of rewriting the file broadly.

:::
