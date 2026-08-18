import base64
import os
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import jwt
from github import Auth, Github, GithubException, GithubIntegration
from github.Commit import Commit
from github.GithubException import UnknownObjectException
from github.Installation import Installation
from github.PaginatedList import PaginatedList
from github.PullRequest import PullRequest
from github.Repository import Repository as GitHubRepository
from rich.console import Group
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text

from quant_ranger._impl.git import (
    QUANT_RANGER_TRAILER,
    RepositoryCheckout,
    git_config_args,
)
from quant_ranger._impl.helpers import (
    CommandError,
    ExecOutput,
    get_exec_output_silently,
    pluralize,
    truncate_lines,
)
from quant_ranger._impl.logger import Logger, PrefixLogger, progress
from quant_ranger._impl.models import RepositoryRef
from quant_ranger._impl.site_config import CommitAuthor


@dataclass(frozen=True, slots=True)
class PullRequestOptions:
    title: str
    body: str
    source_branch: str
    quant_ranger_id: str
    target_branch: str | None = None
    labels: list[str] = field(default_factory=list)


# See: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github#githubs-token-formats
_GITHUB_APP_INSTALLATION_TOKEN_PREFIX = "ghs_"


class GitHubError(RuntimeError):
    """Wrapper for errors raised by GitHub operations."""


def github_web_url(api_url: str) -> str:
    """Derive the web URL used by GitHub.com, GHE Cloud, and GHES."""
    api_url = api_url.rstrip("/")
    if api_url.endswith("/api/v3"):
        return api_url.removesuffix("/api/v3")
    return api_url.replace("://api.", "://", 1)


def git_basic_auth(token: str) -> str:
    credential = f"x-access-token:{token}".encode()
    return base64.b64encode(credential).decode()


def _filename_matches(filename: str | re.Pattern[str], basename: str) -> bool:
    if isinstance(filename, str):
        return basename == filename
    return filename.fullmatch(basename) is not None


@dataclass(frozen=True, slots=True)
class GitHubAppCredentials:
    client_id: str
    private_key: str


def resolve_github_app_credentials() -> GitHubAppCredentials | None:
    """Resolve GitHub App credentials from the environment.

    Reads `GH_APP_CLIENT_ID` and `GH_APP_PRIVATE_KEY` (PEM contents). Returns
    None when neither is set; raises when only one of the two is set.
    """
    client_id = os.environ.get("GH_APP_CLIENT_ID") or None
    private_key = os.environ.get("GH_APP_PRIVATE_KEY") or None

    if client_id is None and private_key is None:
        return None
    if client_id is None or private_key is None:
        raise GitHubError(
            "GitHub App authentication needs both GH_APP_CLIENT_ID and "
            "GH_APP_PRIVATE_KEY (PEM contents) to be set."
        )
    return GitHubAppCredentials(client_id=client_id, private_key=private_key)


def resolve_github_token(*, use_gh: bool = False) -> str | None:
    """Resolve a GitHub token for local CLI runs."""
    if use_gh:
        # Doesn't pass logger to avoid logging any secrets at debug level.

        output = get_exec_output_silently(
            ["gh", "auth", "token"], ignore_return_code=True
        )
        if output.exit_code == 0:
            return output.stdout.strip() or None

        # Strip stdout to not expose potential token
        raise CommandError(
            "Failed to get GitHub token from `gh auth token`.",
            output=ExecOutput(
                exit_code=output.exit_code,
                stdout="(redacted)",
                stderr=output.stderr,
            ),
        )

    for env_var in ("GH_TOKEN", "GITHUB_TOKEN"):
        env_token = os.environ.get(env_var)
        if env_token:
            return env_token

    return None


def app_installation_clients(
    credentials: GitHubAppCredentials,
    *,
    logger: Logger,
    api_url: str,
    fallback_commit_author: CommitAuthor | None,
    publish_changes: bool = False,
    force_push: bool = False,
    show_pr_details: bool = False,
    pr_details_diff_lines: int | None = None,
) -> list[GitHubClient]:
    """Return one client per installation of the GitHub App.

    Each client authenticates as its installation and refreshes the installation token
    automatically, so runs are not bound by the one-hour token lifetime.
    """
    app_auth = Auth.AppAuth(credentials.client_id, credentials.private_key)
    integration = GithubIntegration(auth=app_auth, base_url=api_url)
    try:
        installations = list(integration.get_installations())
    # JWT signing raises jwt.InvalidKeyError (or ValueError) for malformed
    # private keys before any request is made.
    except (GithubException, jwt.PyJWTError, ValueError) as error:
        raise GitHubError(
            "Failed to list installations for the GitHub App. Check the client "
            "ID and private key."
        ) from error

    clients = [
        GitHubClient(
            installation,
            # Prefix all logging with the org/user so the per-installation
            # runs are distinguishable.
            logger=PrefixLogger(f"[{installation.account.login}] ", logger),
            api_url=api_url,
            fallback_commit_author=fallback_commit_author,
            publish_changes=publish_changes,
            force_push=force_push,
            show_pr_details=show_pr_details,
            pr_details_diff_lines=pr_details_diff_lines,
        )
        for installation in installations
    ]
    logger.info(
        f"Authenticated as a GitHub App with {pluralize(len(clients), 'installation')}."
    )
    return clients


class GitHubClient:
    """Small PyGithub-backed client used by updater helpers."""

    def __init__(
        self,
        token_or_installation: str | Installation,
        logger: Logger,
        api_url: str,
        fallback_commit_author: CommitAuthor | None,
        publish_changes: bool = False,
        force_push: bool = False,
        show_pr_details: bool = False,
        pr_details_diff_lines: int | None = None,
    ) -> None:
        self._token_or_installation = token_or_installation
        self.logger = logger
        self.api_url = api_url
        self.fallback_commit_author = fallback_commit_author
        self.publish_changes = publish_changes
        self.force_push = force_push
        self.show_pr_details = show_pr_details
        self.pr_details_diff_lines = pr_details_diff_lines
        self._thread_local = threading.local()
        if isinstance(token_or_installation, str):
            auth = Auth.Token(token_or_installation)
        else:
            # An Installation obtained via app-JWT auth carries an
            # AppInstallationAuth that mints and auto-refreshes tokens.
            auth = token_or_installation.requester.auth
        self._github_factory: Callable[[], Github] = lambda: Github(
            auth=auth,
            base_url=api_url,
            per_page=100,
        )

        self._repo_tags: dict[str, tuple[str, ...]] = {}
        self._repo_tags_lock = threading.RLock()

        self._commit_author_data: CommitAuthor | None = None
        self._commit_author_lock = threading.RLock()

    @property
    def token(self) -> str:
        """Return a currently valid token.

        For an installation, reading the token from its auth refreshes it when it is
        about to expire.
        """
        if isinstance(self._token_or_installation, str):
            return self._token_or_installation
        return cast(
            Auth.AppInstallationAuth, self._token_or_installation.requester.auth
        ).token

    @property
    def installation_owner(self) -> str | None:
        """Return the login of the account the installation belongs to."""
        if isinstance(self._token_or_installation, str):
            return None
        return self._token_or_installation.account.login

    @property
    def _is_installation_auth(self) -> bool:
        return isinstance(
            self._token_or_installation, Installation
        ) or _is_github_app_installation_token(self.token)

    @property
    def github(self) -> Github:
        github = getattr(self._thread_local, "github", None)
        if github is None:
            github = self._github_factory()
            self._thread_local.github = github
        return github

    @property
    def _repositories(self) -> dict[str, GitHubRepository]:
        repositories: dict[str, GitHubRepository] | None = getattr(
            self._thread_local,
            "repositories",
            None,
        )
        if repositories is None:
            repositories = {}
            self._thread_local.repositories = repositories
        return repositories

    def installed_repositories(self) -> list[RepositoryRef]:
        """Return repositories available to the app installation.

        Requesting all installed repositories is only possible with GitHub App
        credentials.
        """
        if not isinstance(installation := self._token_or_installation, Installation):
            raise GitHubError(
                "`--all-installed-repositories` can only be used with GitHub App "
                "credentials."
            )

        self.logger.info("Discovering installed GitHub App repositories...")
        try:
            return self._filter_active_repositories(installation.get_repos())
        except GithubException as error:
            raise GitHubError(
                "Failed to fetch repositories accessible to the GitHub App installation."
            ) from error

    def active_repositories(self, owner: str) -> list[RepositoryRef]:
        self.logger.info(f"Discovering repositories in {owner}...")

        try:
            repos = self.github.get_organization(owner).get_repos(type="all")
            return self._filter_active_repositories(repos)
        except UnknownObjectException as error:
            raise GitHubError(
                f"GitHub owner {owner!r} was not found or is inaccessible."
            ) from error
        except GithubException as error:
            raise GitHubError(
                f"Failed to fetch repositories from GitHub for {owner}."
            ) from error

    def _filter_active_repositories(
        self,
        repos: PaginatedList[GitHubRepository],
    ) -> list[RepositoryRef]:
        active: list[RepositoryRef] = []
        archived_count = 0
        empty_count = 0
        repositories = self._repositories

        for repo in progress(
            repos,
            logger=self.logger,
            description="Fetching repositories",
            total=repos.totalCount,
        ):
            if repo.archived:
                archived_count += 1
                continue
            if repo.size == 0:
                # Size is in kilobytes, so do a slower branch lookup for truly empty repos.
                # repo.size == 0 may still contain repos with a size below 1 KB but not zero!
                try:
                    # For truly empty repositories default_branch will be `main` for GitHub.
                    # But it doesn't actually exist and raise an exception that we test.
                    repo.get_branch(repo.default_branch)
                except UnknownObjectException:
                    empty_count += 1
                    continue

            repository = RepositoryRef(
                owner=repo.owner.login,
                name=repo.name,
                branch=repo.default_branch,
            )
            repositories[repository.full_name] = repo
            active.append(repository)
        self.logger.info(
            f"Discovered {pluralize(len(active), 'active repository', 'active repositories')} "
            f"and skipped {pluralize(archived_count, 'archived repository', 'archived repositories')} "
            f"and {pluralize(empty_count, 'empty repository', 'empty repositories')}."
        )
        return active

    def get_github_repository(self, repository_ref: RepositoryRef) -> GitHubRepository:
        repositories = self._repositories
        if repository_ref.full_name in repositories:
            return repositories[repository_ref.full_name]

        try:
            github_repo = self.github.get_repo(repository_ref.full_name)
        except UnknownObjectException as error:
            raise GitHubError(
                f"Repository {repository_ref.full_name} was not found or is inaccessible."
            ) from error

        repositories[repository_ref.full_name] = github_repo
        return github_repo

    def get_repository_url(self, repository_ref: RepositoryRef) -> str:
        return self.get_github_repository(repository_ref).html_url

    def get_latest_release(self, owner: str, name: str) -> str:
        repository_ref = RepositoryRef(owner=owner, name=name)
        release = self.get_github_repository(repository_ref).get_latest_release()

        tag_name = release.tag_name
        if not tag_name:
            raise GitHubError(
                f"Latest release for {repository_ref.full_name} has no tag name."
            )
        return tag_name

    def get_repo_tags(self, owner: str, name: str) -> list[str]:
        repository_ref = RepositoryRef(owner=owner, name=name)
        with self._repo_tags_lock:
            if repository_ref.full_name not in self._repo_tags:
                self._repo_tags[repository_ref.full_name] = tuple(
                    tag.name
                    for tag in self.get_github_repository(repository_ref).get_tags()
                )
            return list(self._repo_tags[repository_ref.full_name])

    def get_repo_tag_message(self, owner: str, name: str, tag: str) -> str | None:
        repository_ref = RepositoryRef(owner=owner, name=name)
        github_repo = self.get_github_repository(repository_ref)
        tag_ref = github_repo.get_git_ref(f"tags/{tag}")

        if tag_ref.object.type == "tag":
            return github_repo.get_git_tag(tag_ref.object.sha).message

        try:
            release = github_repo.get_release(tag)
        except UnknownObjectException:
            return None
        return release.body or None

    def find_files_by_name(
        self,
        repository_ref: RepositoryRef,
        filename: str | re.Pattern[str],
    ) -> list[str]:
        github_repo = self.get_github_repository(repository_ref)
        branch = repository_ref.branch or github_repo.default_branch
        filename_description = (
            filename if isinstance(filename, str) else filename.pattern
        )

        try:
            tree = github_repo.get_git_tree(branch, recursive=True)
        except GithubException as error:
            # Skip branches with no files (404), those throw an error for this function
            if error.status in {404}:
                self.logger.debug(
                    f"Failed to find {filename_description} in "
                    f"{repository_ref.display_name}: "
                    f"{error.data.get('message', 'Unknown error')} "
                    f"(HTTP {error.status})"
                )
                return []

            self.logger.error(
                f"Error while searching for {filename_description} in "
                f"{repository_ref.display_name}."
            )
            raise error

        return [
            item.path
            for item in tree.tree
            if item.path is not None
            and item.type == "blob"
            and _filename_matches(filename, Path(item.path).name)
        ]

    def get_file_content(self, repository_ref: RepositoryRef, path: str) -> str | None:
        github_repo = self.get_github_repository(repository_ref)
        branch = repository_ref.branch or github_repo.default_branch
        try:
            content = github_repo.get_contents(path, ref=branch)
        except UnknownObjectException:
            return None

        if isinstance(content, list):
            return None

        return content.decoded_content.decode()

    def list_open_pull_requests(
        self,
        repository_ref: RepositoryRef,
        source_branch: str,
        target_branch: str,
    ) -> list[PullRequest]:
        github_repo = self.get_github_repository(repository_ref)
        # GitHub's head filter misses same-org fork PRs, so list by base branch
        # and filter locally to avoid trying to create a duplicate PR.
        if github_repo.fork:
            pull_requests = github_repo.get_pulls(
                state="open",
                base=target_branch,
            )
            return [
                pull_request
                for pull_request in pull_requests
                if pull_request.head.ref == source_branch
                and pull_request.head.user.login.lower() == repository_ref.owner.lower()
            ]

        pull_requests = github_repo.get_pulls(
            state="open",
            head=f"{repository_ref.owner}:{source_branch}",
        )
        return [
            pull_request
            for pull_request in pull_requests
            if pull_request.base.ref == target_branch
        ]

    def clone_repository(
        self,
        repository_ref: RepositoryRef,
        *,
        directory: str | Path | None = None,
    ) -> RepositoryCheckout:
        checkout_path = Path(directory or repository_ref.name)
        github_repo = self.get_github_repository(repository_ref)
        branch = repository_ref.branch or github_repo.default_branch
        extra_args = ["-b", branch] if repository_ref.branch else []
        get_exec_output_silently(
            [
                "git",
                *git_config_args(self._git_auth_config()),
                "clone",
                "--depth",
                "1",
                github_repo.clone_url,
                *extra_args,
                str(checkout_path),
            ],
            logger=self.logger,
            redact=self._git_auth_secrets(),
            env={"GIT_LFS_SKIP_SMUDGE": "1"},
        )
        return RepositoryCheckout(
            checkout_path,
            repository_ref,
        )

    def create_pull_request(
        self,
        repository_checkout: RepositoryCheckout,
        options: PullRequestOptions,
        logger: Logger,
    ) -> bool:
        target_branch = (
            options.target_branch
            or self.get_github_repository(
                repository_checkout.repository_ref
            ).default_branch
        )
        author = self._commit_author()
        repository_checkout.checkout_branch(options.source_branch, logger)
        repository_checkout.commit_with_author(
            options.title,
            author_name=author.name,
            author_email=author.email,
            user_name=author.name,
            user_email=author.email,
            quant_ranger_id=options.quant_ranger_id,
            logger=logger,
        )

        logger.debug("Creating or updating a pull request...")
        open_pull_requests = self.list_open_pull_requests(
            repository_checkout.repository_ref,
            options.source_branch,
            target_branch,
        )

        pull_request: PullRequest | None = None
        if open_pull_requests:
            logger.debug("Found existing pull request.")
            pull_request = open_pull_requests[0]
            commits = list(pull_request.get_commits())
            if any(not _is_safe_to_overwrite(commit) for commit in commits):
                if not self.force_push:
                    logger.info("Pull request has manual changes. Refusing to update.")
                    return False
                logger.warning(
                    "Pull request has manual changes. Overwriting them because "
                    "--force-push is set."
                )

        if self.show_pr_details:
            logger.info_panel(
                "Pull request details",
                _pull_request_details(
                    options,
                    changed_file_count=len(
                        repository_checkout.head_commit_files(logger)
                    ),
                    target_branch=target_branch,
                    diff=repository_checkout.head_commit_diff(),
                    diff_lines=self.pr_details_diff_lines,
                ),
            )

        if not self.publish_changes:
            return True

        repository_checkout.force_push_branch(
            options.source_branch,
            logger,
            config=self._git_auth_config(),
            redact=self._git_auth_secrets(),
        )

        if pull_request is not None:
            pull_request.edit(title=options.title, body=options.body)
            logger.debug("Successfully updated pull request.")
        else:
            pull_request = self.get_github_repository(
                repository_checkout.repository_ref
            ).create_pull(
                title=options.title,
                body=options.body,
                head=options.source_branch,
                base=target_branch,
            )
            logger.debug("Successfully created a pull request.")

        if options.labels:
            pull_request.add_to_labels(*options.labels)
        return True

    def _commit_author(self) -> CommitAuthor:
        with self._commit_author_lock:
            if self._commit_author_data is None:
                if self._is_installation_auth:
                    if self.fallback_commit_author is None:
                        raise GitHubError(
                            "A fallback commit author is required when using GitHub "
                            "App authentication. Configure `fallback_commit_author` in "
                            "the site config."
                        )
                    self.logger.debug(
                        "Falling back to the "
                        f"{self.fallback_commit_author.name} commit author."
                    )
                    self._commit_author_data = self.fallback_commit_author
                    return self._commit_author_data

                user = self.github.get_user()
                self._commit_author_data = CommitAuthor(
                    name=user.login,
                    email=f"{user.id}+{user.login}@users.noreply.github.com",
                )
            return self._commit_author_data

    def _git_auth_config(self) -> list[str]:
        return [f"http.extraHeader=AUTHORIZATION: basic {git_basic_auth(self.token)}"]

    def _git_auth_secrets(self) -> list[str]:
        return [self.token, git_basic_auth(self.token)]

    def check_ref_exists(self, repository_ref: RepositoryRef) -> bool:
        try:
            github_repo = self.get_github_repository(repository_ref)
            branch = repository_ref.branch or github_repo.default_branch
            github_repo.get_branch(branch)
            return True
        except UnknownObjectException, GitHubError:
            return False


def _is_safe_to_overwrite(commit: Commit) -> bool:
    return _commit_author_type(commit) == "Bot" or _commit_has_quant_ranger_trailer(
        commit
    )


def _is_github_app_installation_token(token: str) -> bool:
    return token.startswith(_GITHUB_APP_INSTALLATION_TOKEN_PREFIX)


def _commit_has_quant_ranger_trailer(commit: Commit) -> bool:
    return any(
        line.startswith(f"{QUANT_RANGER_TRAILER}:")
        for line in _commit_message(commit).splitlines()
    )


def _commit_author_type(commit: Commit) -> str | None:
    return getattr(commit.author, "type", None)


def _commit_message(commit: Commit) -> str:
    commit_data = getattr(commit, "commit", None)
    return getattr(commit_data, "message", "")


def _pull_request_details(
    options: PullRequestOptions,
    *,
    changed_file_count: int,
    target_branch: str,
    diff: str,
    diff_lines: int | None,
) -> Group:
    labels = ", ".join(options.labels) or "none"
    metadata = (
        f"{options.source_branch} -> {target_branch}, "
        f"{pluralize(changed_file_count, 'changed file')}, "
        f"body {len(options.body)} chars, labels: {labels}"
    )
    if diff_lines is not None:
        diff = truncate_lines(diff, max_lines=diff_lines)
    return Group(
        Text(options.title, style="bold"),
        Text(metadata),
        Rule(style="default"),
        Syntax(
            diff or "(no changes)",
            "diff",
            theme="ansi_dark",
            background_color="default",
        ),
    )
