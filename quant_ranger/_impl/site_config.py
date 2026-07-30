import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, field_validator

from quant_ranger._impl.git import RepositoryCheckout
from quant_ranger._impl.runtime import RunContext

_TEMPLATE_REPOSITORY_PATTERN = re.compile(r"^[^/\s]+/[^/\s]+/[^/\s]+$")


def _normalize_template_repositories(
    templates: Iterable[str],
    *,
    description: str,
) -> frozenset[str]:
    normalized = frozenset(template.lower() for template in templates)
    for template in sorted(normalized):
        if _TEMPLATE_REPOSITORY_PATTERN.fullmatch(template) is None:
            raise ValueError(
                f"Invalid {description} {template!r}: expected 'host/owner/name'."
            )
    return normalized


@dataclass(frozen=True, slots=True)
class PullRequestTemplate:
    title: str
    body: str
    branch_prefix: str


CopierMigrationValue = bool | int | str
"""A scalar value of a Copier answer in `.copier-answers.yml`.

Any other value type fails the scan of the affected repository.
"""


@dataclass(frozen=True, slots=True)
class CopierMigration:
    """Changes one answer in a repository's `.copier-answers.yml` by re-running `copier
    update` with the desired value and opening a pull request."""

    answer_key: str
    """The key in `.copier-answers.yml` whose value the migration changes.

    Repositories whose answers do not contain this key are skipped.
    """

    templates: frozenset[str]
    """The lowercase `host/owner/name` Copier templates this migration applies to."""

    resolve_desired_value: Callable[[CopierMigrationValue], CopierMigrationValue]
    """Maps an answer's current value to its desired value; returning the current value
    skips the repository as up to date.

    Raise a `ValueError` for current values the migration cannot handle.
    """

    pull_request_template: PullRequestTemplate
    """Title, body, and source-branch prefix of the migration pull request."""

    post_migration: Callable[[RepositoryCheckout, RunContext], None] | None = None
    """Optional cleanup hook that runs after `copier update` succeeded, before changes
    are committed."""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "templates",
            _normalize_template_repositories(
                self.templates,
                description="Copier migration template",
            ),
        )


DEFAULT_COPIER_MIGRATIONS: dict[str, CopierMigration] = {
    "example": CopierMigration(
        answer_key="example_feature",
        templates=frozenset({"github.com/example/copier-template"}),
        resolve_desired_value=lambda _current_value: True,
        pull_request_template=PullRequestTemplate(
            title="chore: Enable the example feature",
            body="This migration enables an example Copier template feature.",
            branch_prefix="copier-migration",
        ),
    )
}


@dataclass(frozen=True, slots=True)
class PullRequestTemplates:
    github_app_token: PullRequestTemplate
    node_dependency_cooldown: PullRequestTemplate
    zizmor: PullRequestTemplate


_GITHUB_APP_TOKEN_TEMPLATE = PullRequestTemplate(
    title="chore: Migrate create-github-app-token to client-id",
    body="""The `app-id` input of [`actions/create-github-app-token`](https://github.com/actions/create-github-app-token) is [deprecated in favor of `client-id`](https://github.com/actions/create-github-app-token/pull/353).
This PR renames the input in workflow and composite action files that use a compatible action revision. Existing App ID values continue to work with `client-id`, so no secrets or variables need to change. Older or unverified revisions are left unchanged because they may not support the new input.""",
    branch_prefix="github-app-token-client-id",
)

_NODE_DEPENDENCY_COOLDOWN_TEMPLATE = PullRequestTemplate(
    title="chore: Enforce Node supply chain protections",
    body="""This PR configures minimum dependency release ages for bun, pnpm and npm, and blocks exotic subdependencies in pnpm.

These settings delay installing newly published package versions that may have been compromised in a supply chain attack.
Exotic subdependencies can hide malicious code, so pnpm blocks them entirely.""",
    branch_prefix="node-dependency-cooldown-fixes",
)

_ZIZMOR_TEMPLATE = PullRequestTemplate(
    title="chore: Fix GitHub Actions findings with zizmor",
    body="""This PR automatically fixes findings in GitHub Actions workflows using [`zizmor`](https://github.com/woodruffw/zizmor).

The following rules are enabled:
- **ref-version-mismatch**: A ref-version-mismatch occurs when an action is hash-pinned but the associated tag comment (e.g. `# v3.8.1`) does not match the pinned commit. This can cause tools like Dependabot to silently ignore the comment instead of refreshing it.
- **dependabot-cooldown**: Ensures that dependabot configurations include a cooldown period.""",
    branch_prefix="zizmor-fixes",
)


DEFAULT_PULL_REQUEST_TEMPLATES = PullRequestTemplates(
    github_app_token=_GITHUB_APP_TOKEN_TEMPLATE,
    node_dependency_cooldown=_NODE_DEPENDENCY_COOLDOWN_TEMPLATE,
    zizmor=_ZIZMOR_TEMPLATE,
)


@dataclass(frozen=True, slots=True)
class CommitAuthor:
    name: str
    email: str


class SiteConfig(BaseModel):
    """Site-wide configuration provided by a `quant_ranger.site_config` plugin.

    A plugin package exposes a `SiteConfig` instance through the
    `quant_ranger.site_config` entry point group, for example to point
    quant-ranger at a GitHub Enterprise instance:

    ```toml
    [project.entry-points."quant_ranger.site_config"]
    corp = "my_plugin:site_config"
    ```

    At most one site config plugin may be installed. Every field has a
    builtin default, so `SiteConfig()` describes the stock github.com setup
    and is used when no plugin is installed.
    """

    model_config = ConfigDict(frozen=True)

    default_owner: str | None = None
    """Default owner for repository names that omit an owner; the `--owner` CLI option
    wins.

    Set to `None` to require either `--owner` or
    `--all-installed-repositories`.
    """

    default_github_api_url: str = "https://api.github.com"
    """Default GitHub API base URL; the `--github-api-url` CLI option wins."""

    pixi_version_setup_pixi_marker: str = "prefix-dev/setup-pixi"
    """Default marker for workflow files the pixi-version updater may touch; the
    `--setup-pixi-marker` CLI option wins."""

    pull_request_templates: PullRequestTemplates = DEFAULT_PULL_REQUEST_TEMPLATES
    """Titles, bodies, and source-branch prefixes for configurable pull requests."""

    copier_migrations: Mapping[str, CopierMigration] = DEFAULT_COPIER_MIGRATIONS
    """Named Copier migrations available through `--migration`.

    Setting this replaces the builtin example entirely.
    """

    fallback_commit_author: CommitAuthor | None = None
    """Optional commit author used for GitHub App authentication via private-key
    credentials or an installation token. Personal tokens keep committing as the
    authenticated user.

    Configure this when using GitHub App credentials so commits are attributed and
    verified correctly. GitHub noreply email schema:

    `<account-id>+<login>@users.noreply.github.com`

    Other GitHub instances may use a different schema.
    """

    copier_trusted_templates: frozenset[str] = frozenset()
    """The lowercase `host/owner/name` copier templates that may run with `--trust`.
    Setting this replaces the builtin allowlist entirely.

    For example:
    `frozenset({"github.com/quantco/copier-template-python-open-source"})`.

    Trusted templates execute arbitrary code with the runner's GitHub token.
    Before listing a template, we strongly recommend that its repository has a branch ruleset
    protecting `main` and a tag ruleset protecting all tags. Both ruleset names
    should clearly mark the repository as trusted by quant-ranger, for example:
    "don't remove, template is trusted by quant-ranger".
    """

    @field_validator("copier_trusted_templates", mode="after")
    @classmethod
    def _normalize_trusted_templates(
        cls,
        value: frozenset[str],
    ) -> frozenset[str]:
        return _normalize_template_repositories(
            value,
            description="trusted template",
        )
