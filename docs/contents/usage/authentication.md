# Authentication

quant-ranger needs GitHub credentials to discover, read, and clone repositories.
Publishing additionally requires permission to push branches and manage pull requests.

**Available methods:**

|     | Method     | Best for                                    | Configuration                               |
| --- | ---------- | ------------------------------------------- | ------------------------------------------- |
| 1.  | GitHub CLI | Interactive local runs                      | `--gh`                                      |
| 2.  | Token      | Local scripts or a single-repository CI job | `GH_TOKEN` or `GITHUB_TOKEN`                |
| 3.  | GitHub App | Scheduled or organization-wide automation   | `GH_APP_CLIENT_ID` and `GH_APP_PRIVATE_KEY` |

The first supplied method is used (GitHub CLI → Token → GitHub App).

## 1. GitHub CLI

Authenticate once with `gh`, then opt in with `--gh`:

```bash {3}
gh auth login
quant-ranger update \
  --gh \
  --repository octo-org/octo-repo \
  pixi-update
```

quant-ranger invokes `gh auth token`.
It does not read the token from `gh` unless `--gh` is present.
A failed `gh auth token` command stops the run instead of falling back to an environment token.

## 2. GitHub Token {/* #token */}

Set either of the supported environment variables and omit `--gh`:

```bash {1}
export GH_TOKEN="your-token"
quant-ranger update \
  --repository octo-org/octo-repo \
  pixi-update
```

`GH_TOKEN` takes precedence over `GITHUB_TOKEN`.
The token must be able to read every selected repository.
Publishing requires permission to write repository contents and pull requests.
Changing files in `.github/workflows` may require workflow write access as well.

## 3. GitHub App {/* #github-app */}

Provide the app's client ID and the contents of its PEM private key:

```bash {1-2}
export GH_APP_CLIENT_ID="Iv28liJtSXW7BBBzgBxX"
export GH_APP_PRIVATE_KEY="$(cat <path/to/private-key.pem)"

quant-ranger update \
  --all-installed-repositories \
  pixi-update
```

For `GH_APP_CLIENT_ID` you can either use the Client ID (shown here) or App ID found in your app's settings.

Install the app on the organizations or repositories it should maintain.
Use these repository permissions:

| GitHub permission                                                                                                                               | Dry run      | Publishing                                                                 |
| ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------ | -------------------------------------------------------------------------- |
| [`Metadata`](https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps#repository-permissions-for-metadata)           | `Read-only`  | `Read-only`                                                                |
| [`Contents`](https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps#repository-permissions-for-contents)           | `Read-only`  | `Read and write`                                                           |
| [`Pull requests`](https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps#repository-permissions-for-pull-requests) | `Read-only`  | `Read and write`                                                           |
| [`Workflows`](https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps#repository-permissions-for-workflows)         | Not required | `Read and write` only when an updater may change `.github/workflows` files |

quant-ranger generates and refreshes installation tokens automatically.
`--all-installed-repositories` is available only with GitHub App credentials and processes the active, non-empty repositories exposed by every installation.

## GitHub Enterprise

Point the client at the REST API root, including `/api/v3` for a typical GitHub Enterprise Server installation:

```bash {2}
quant-ranger update \
  --github-api-url https://github.example.com/api/v3 \
  --repository octo-org/octo-repo \
  pixi-update
```

Instead of appending `--github-api-url` to every command, set a deployment-wide default with the [`default_github_api_url` site config filed](../plugins/site-configuration.md#options).
The selected credentials must belong to the same GitHub instance.

For GitHub Enterprise Cloud with data residency (`*.ghe.com`), the corresponding API URL is `https://api.your-subdomain.ghe.com`.
