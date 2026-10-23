import base64
import re
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier, Lock, get_ident
from types import SimpleNamespace
from typing import Any, cast, override

import jwt
import pytest
from github import GithubException
from github.GithubException import UnknownObjectException
from github.Installation import Installation
from github.PaginatedList import PaginatedList
from github.Repository import Repository
from rich.console import Group
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text

from quant_ranger._impl.github import (
    GitHubAppCredentials,
    GitHubClient,
    GitHubError,
    PullRequestOptions,
    app_installation_clients,
    resolve_github_app_credentials,
    resolve_github_token,
)
from quant_ranger._impl.helpers import CommandError, ExecOutput
from quant_ranger._impl.logger import LogLevel
from quant_ranger._impl.models import RepositoryRef
from quant_ranger._impl.testing import RecordingCheckout, RecordingLogger
from quant_ranger.site_config import CommitAuthor, SiteConfig


def test_resolve_github_token_uses_environment_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "gh-token")
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")

    assert resolve_github_token() == "gh-token"


def test_resolve_github_token_can_use_gh_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "gh-token")
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    calls: list[list[str]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        calls.append(command)
        return ExecOutput(exit_code=0, stdout="cli-token\n", stderr="")

    monkeypatch.setattr("quant_ranger._impl.github.get_exec_output_silently", fake_exec)

    assert resolve_github_token(use_gh=True) == "cli-token"
    assert calls == [["gh", "auth", "token"]]


def test_resolve_github_token_redacts_stdout_when_gh_cli_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        calls.append({"command": command, **kwargs})
        return ExecOutput(
            exit_code=1,
            stdout="secret-token\n",
            stderr="not logged in",
        )

    monkeypatch.setattr("quant_ranger._impl.github.get_exec_output_silently", fake_exec)

    with pytest.raises(CommandError) as error_info:
        resolve_github_token(use_gh=True)

    assert calls == [
        {
            "command": ["gh", "auth", "token"],
            "ignore_return_code": True,
        }
    ]
    assert error_info.value.output == ExecOutput(
        exit_code=1,
        stdout="(redacted)",
        stderr="not logged in",
    )


def test_resolve_github_token_returns_none_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert resolve_github_token() is None


def test_active_repositories_raises_github_error_when_owner_is_not_found() -> None:
    client = make_client(FakeGithub(organization=None))

    with pytest.raises(
        GitHubError,
        match="GitHub owner 'missing' was not found or is inaccessible.",
    ) as error_info:
        client.active_repositories("missing")

    assert isinstance(error_info.value.__cause__, UnknownObjectException)


def test_active_repositories_wraps_filter_errors() -> None:
    api_error = GithubException(500, {"message": "boom"})

    class FailingRepository:
        @property
        def archived(self) -> None:
            raise api_error

    organization = FakeOrganization([cast(FakeRepository, FailingRepository())])
    client = make_client(FakeGithub(organization=organization))

    with pytest.raises(
        GitHubError,
        match="Failed to fetch repositories from GitHub for quantco.",
    ) as error_info:
        client.active_repositories("quantco")

    assert error_info.value.__cause__ is api_error


def test_active_repositories_filters_and_caches_repositories() -> None:
    active_repo = FakeRepository(name="active", default_branch="main")
    tiny_repo = FakeRepository(name="tiny", default_branch="main", size=0)
    archived_repo = FakeRepository(name="archived", archived=True)
    branchless_repo = FakeRepository(name="branchless", default_branch=None)
    empty_repo = FakeRepository(
        name="empty",
        default_branch="main",
        size=0,
        branches=[],
    )
    github = FakeGithub(
        organization=FakeOrganization(
            [
                active_repo,
                tiny_repo,
                archived_repo,
                branchless_repo,
                empty_repo,
            ]
        )
    )
    logger = RecordingLogger()
    client = make_client(github, logger=logger)

    repositories = client.active_repositories("quantco")

    assert repositories == [
        RepositoryRef(owner="quantco", name="active", branch="main"),
        RepositoryRef(owner="quantco", name="tiny", branch="main"),
        RepositoryRef(owner="quantco", name="branchless"),
    ]
    assert client.get_github_repository(repositories[0]) is active_repo
    assert client.get_github_repository(repositories[1]) is tiny_repo
    assert client.get_github_repository(repositories[2]) is branchless_repo
    assert logger.logged(
        LogLevel.INFO, "skipped 1 archived repository and 1 empty repository"
    )


def test_installed_repositories_filters_and_caches_repositories() -> None:
    installed_repo = FakeRepository(name="installed", owner_login="quantco")
    installation = FakeInstallation(
        [
            installed_repo,
            FakeRepository(name="archived", owner_login="quantco", archived=True),
        ]
    )
    github = FakeGithub()
    logger = RecordingLogger()
    client = make_client(github, logger=logger, token=installation)

    discovered = client.installed_repositories()

    assert client.installation_owner == "quantco"
    assert discovered == [
        RepositoryRef(owner="quantco", name="installed", branch="main"),
    ]
    assert client.get_github_repository(discovered[0]) is installed_repo
    assert installation.get_repos_calls == 1
    assert github.get_user_calls == 0


@pytest.mark.parametrize(
    "token",
    ["secret-token", "ghu_github-app-user-token", "ghs_github-app-installation-token"],
)
def test_installed_repositories_rejects_string_tokens(
    token: str,
) -> None:
    github = FakeGithub()
    client = make_client(github, token=token)

    with pytest.raises(
        GitHubError,
        match="can only be used with GitHub App credentials",
    ):
        client.installed_repositories()

    assert github.get_user_calls == 0


def test_installed_repositories_wraps_github_api_errors() -> None:
    api_error = GithubException(500, {"message": "boom"})
    github = FakeGithub()
    client = make_client(github, token=FakeInstallation(error=api_error))

    with pytest.raises(
        GitHubError,
        match="Failed to fetch repositories accessible to the GitHub App installation.",
    ) as error_info:
        client.installed_repositories()

    assert error_info.value.__cause__ is api_error


def test_resolve_github_app_credentials_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_APP_CLIENT_ID", "123456")
    monkeypatch.setenv("GH_APP_PRIVATE_KEY", "pem-contents")

    assert resolve_github_app_credentials() == GitHubAppCredentials(
        client_id="123456",
        private_key="pem-contents",
    )


def test_resolve_github_app_credentials_returns_none_without_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GH_APP_CLIENT_ID", raising=False)
    monkeypatch.delenv("GH_APP_PRIVATE_KEY", raising=False)

    assert resolve_github_app_credentials() is None


@pytest.mark.parametrize(
    ("client_id", "private_key"),
    [("123456", ""), ("", "pem-contents")],
)
def test_resolve_github_app_credentials_rejects_partial_configuration(
    monkeypatch: pytest.MonkeyPatch,
    client_id: str,
    private_key: str,
) -> None:
    monkeypatch.setenv("GH_APP_CLIENT_ID", client_id)
    monkeypatch.setenv("GH_APP_PRIVATE_KEY", private_key)

    with pytest.raises(
        GitHubError,
        match="both GH_APP_CLIENT_ID and GH_APP_PRIVATE_KEY",
    ):
        resolve_github_app_credentials()


def test_app_installation_clients_creates_one_client_per_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installations = [
        FakeInstallation(owner_login="quantco"),
        FakeInstallation(owner_login="Other"),
    ]
    integration_calls: list[dict[str, Any]] = []

    class FakeIntegration:
        def __init__(self, **kwargs: Any) -> None:
            integration_calls.append(kwargs)

        def get_installations(self) -> list[FakeInstallation]:
            return installations

    monkeypatch.setattr("quant_ranger._impl.github.GithubIntegration", FakeIntegration)
    logger = RecordingLogger()

    clients = app_installation_clients(
        GitHubAppCredentials(client_id="123456", private_key="pem-contents"),
        logger=logger,
        api_url="https://github.example/api/v3",
        fallback_commit_author=SiteConfig().fallback_commit_author,
        publish_changes=False,
        force_push=True,
        show_pr_details=True,
        pr_details_diff_lines=20,
    )

    assert [client.installation_owner for client in clients] == ["quantco", "Other"]
    assert all(not client.publish_changes for client in clients)
    assert all(client.force_push for client in clients)
    assert all(client.show_pr_details for client in clients)
    assert all(client.pr_details_diff_lines == 20 for client in clients)
    assert all(client.api_url == "https://github.example/api/v3" for client in clients)
    assert len(integration_calls) == 1
    assert integration_calls[0]["base_url"] == "https://github.example/api/v3"
    assert logger.logged(LogLevel.INFO, "2 installations")

    # Per-installation loggers prefix messages with the owner so concurrent
    # installation runs are distinguishable.
    clients[0].logger.info("Scanning 4 repositories...")
    clients[1].logger.info("Scanning 4 repositories...")
    assert logger.logged(LogLevel.INFO, "[quantco] Scanning 4 repositories...")
    assert logger.logged(LogLevel.INFO, "[Other] Scanning 4 repositories...")


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(
            GithubException(401, {"message": "bad credentials"}),
            id="github-api-error",
        ),
        pytest.param(
            jwt.exceptions.InvalidKeyError("Could not parse the provided public key."),
            id="invalid-private-key",
        ),
    ],
)
def test_app_installation_clients_wraps_installation_discovery_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    class FailingIntegration:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def get_installations(self) -> list[SimpleNamespace]:
            raise error

    monkeypatch.setattr(
        "quant_ranger._impl.github.GithubIntegration", FailingIntegration
    )

    with pytest.raises(
        GitHubError,
        match="Failed to list installations for the GitHub App.",
    ) as error_info:
        app_installation_clients(
            GitHubAppCredentials(client_id="123456", private_key="pem-contents"),
            logger=RecordingLogger(),
            api_url="https://github.example/api/v3",
            fallback_commit_author=SiteConfig().fallback_commit_author,
        )

    assert error_info.value.__cause__ is error


def test_github_client_does_not_cache_installation_token() -> None:
    installation = FakeInstallation()
    client = make_client(FakeGithub(), token=installation)

    assert client.token == "ghs_github-app-installation-token"
    installation.auth.token = "ghs_fresh-2"
    assert client.token == "ghs_fresh-2"


def test_get_github_repository_fetches_and_caches_repository() -> None:
    repository = FakeRepository(name="example")
    github = FakeGithub(repository=repository)
    client = make_client(github)
    repository_ref = RepositoryRef(owner="quantco", name="example")

    assert client.get_github_repository(repository_ref) is repository
    assert client.get_github_repository(repository_ref) is repository
    assert github.get_repo_calls == ["quantco/example"]


def test_github_client_uses_one_github_instance_per_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    barrier = Barrier(2)
    lock = Lock()
    created: list[tuple[int, Any]] = []

    def fake_github(**kwargs: Any) -> Any:
        instance = SimpleNamespace(kwargs=kwargs)
        with lock:
            created.append((get_ident(), instance))
        return instance

    monkeypatch.setattr("quant_ranger._impl.github.Github", fake_github)
    client = GitHubClient(
        "secret-token",
        logger=RecordingLogger(),
        api_url="https://github.example/api/v3",
        fallback_commit_author=SiteConfig().fallback_commit_author,
    )

    main_instance = client.github

    def worker_instance_id(_: int) -> int:
        barrier.wait(timeout=2)
        return id(client.github)

    with ThreadPoolExecutor(max_workers=2) as executor:
        worker_instance_ids = list(executor.map(worker_instance_id, range(2)))

    assert len(set(worker_instance_ids)) == 2
    assert id(main_instance) not in worker_instance_ids
    assert len(created) == 3


def test_github_client_repository_cache_is_thread_local() -> None:
    repository = FakeRepository(name="example")
    github = FakeGithub(repository=repository)
    client = make_client(github)
    repository_ref = RepositoryRef(owner="quantco", name="example")

    assert client.get_github_repository(repository_ref) is repository
    assert client.get_github_repository(repository_ref) is repository

    def worker_repositories() -> tuple[FakeRepository, FakeRepository]:
        return (
            cast(FakeRepository, client.get_github_repository(repository_ref)),
            cast(FakeRepository, client.get_github_repository(repository_ref)),
        )

    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(worker_repositories).result(timeout=2) == (
            repository,
            repository,
        )

    assert github.get_repo_calls == ["quantco/example", "quantco/example"]


def test_get_github_repository_raises_when_repository_is_not_found() -> None:
    github = FakeGithub()
    client = make_client(github)
    repository_ref = RepositoryRef(owner="quantco", name="missing")

    with pytest.raises(
        GitHubError,
        match="Repository quantco/missing was not found or is inaccessible",
    ):
        client.get_github_repository(repository_ref)

    assert github.get_repo_calls == ["quantco/missing"]


def test_get_repository_url_uses_repository_html_url() -> None:
    repository = FakeRepository(
        name="example",
        html_url="https://GitHub.Example/quantco/example",
    )
    github = FakeGithub(repository=repository)
    client = make_client(github)
    repository_ref = RepositoryRef(owner="quantco", name="example")

    assert client.get_repository_url(repository_ref) == repository.html_url
    assert client.get_repository_url(repository_ref) == repository.html_url
    assert github.get_repo_calls == ["quantco/example"]


def test_get_latest_release_returns_tag_name() -> None:
    repository = FakeRepository(name="pixi", latest_release_tag="v0.42.0")
    client = make_client(FakeGithub(repository=repository))

    assert client.get_latest_release("prefix-dev", "pixi") == "v0.42.0"


def test_get_latest_release_requires_tag_name() -> None:
    repository = FakeRepository(name="pixi", latest_release_tag="")
    client = make_client(FakeGithub(repository=repository))

    with pytest.raises(
        GitHubError,
        match="Latest release for prefix-dev/pixi has no tag name.",
    ):
        client.get_latest_release("prefix-dev", "pixi")


def test_get_latest_release_published_before_skips_recent_releases() -> None:
    repository = FakeRepository(
        name="pixi",
        latest_release_tag="v0.72.0",
        releases=[
            FakeRelease(tag_name="v0.72.0", published_at=_at("2026-08-24")),
            FakeRelease(tag_name="v0.71.0", published_at=_at("2026-08-20")),
            FakeRelease(tag_name="v0.70.0", published_at=_at("2026-08-10")),
        ],
    )
    client = make_client(FakeGithub(repository=repository))

    version = client.get_latest_release(
        "prefix-dev",
        "pixi",
        published_before=_at("2026-08-18"),
    )

    assert version == "v0.70.0"


def test_get_latest_release_published_before_skips_drafts_and_prereleases() -> None:
    repository = FakeRepository(
        name="pixi",
        releases=[
            FakeRelease(tag_name="v0.72.0", published_at=_at("2026-08-10"), draft=True),
            FakeRelease(
                tag_name="v0.71.0", published_at=_at("2026-08-09"), prerelease=True
            ),
            FakeRelease(tag_name="v0.70.0", published_at=_at("2026-08-08")),
        ],
    )
    client = make_client(FakeGithub(repository=repository))

    version = client.get_latest_release(
        "prefix-dev",
        "pixi",
        published_before=_at("2026-08-18"),
    )

    assert version == "v0.70.0"


def test_get_latest_release_published_before_falls_back_to_created_at() -> None:
    repository = FakeRepository(
        name="pixi",
        releases=[
            FakeRelease(
                tag_name="v0.70.0",
                published_at=None,
                created_at=_at("2026-08-10"),
            ),
        ],
    )
    client = make_client(FakeGithub(repository=repository))

    version = client.get_latest_release(
        "prefix-dev",
        "pixi",
        published_before=_at("2026-08-18"),
    )

    assert version == "v0.70.0"


def test_get_latest_release_published_before_requires_an_eligible_release() -> None:
    repository = FakeRepository(
        name="pixi",
        releases=[FakeRelease(tag_name="v0.72.0", published_at=_at("2026-08-24"))],
    )
    client = make_client(FakeGithub(repository=repository))

    with pytest.raises(
        GitHubError,
        match="prefix-dev/pixi has no release published at or before",
    ):
        client.get_latest_release(
            "prefix-dev",
            "pixi",
            published_before=_at("2026-08-18"),
        )


def test_get_repo_tags_returns_all_tag_names() -> None:
    repository = FakeRepository(name="template", tags=["v1.0.0", "v1.1.0"])
    client = make_client(FakeGithub(repository=repository))

    tags = client.get_repo_tags("quantco", "template")
    tags.append("local-mutation")
    repository.tags.append("v1.2.0")

    assert client.get_repo_tags("quantco", "template") == ["v1.0.0", "v1.1.0"]
    assert repository.get_tags_calls == 1


def test_get_repo_tag_message_reads_annotated_tag_message() -> None:
    repository = FakeRepository(
        name="template",
        annotated_tag_messages={"v1.0.0": "Annotated changelog"},
    )
    client = make_client(FakeGithub(repository=repository))

    assert (
        client.get_repo_tag_message("quantco", "template", "v1.0.0")
        == "Annotated changelog"
    )


def test_get_repo_tag_message_reads_lightweight_tag_release_body() -> None:
    repository = FakeRepository(
        name="template",
        release_bodies={"v1.0.0": "Release changelog"},
    )
    client = make_client(FakeGithub(repository=repository))

    assert (
        client.get_repo_tag_message("quantco", "template", "v1.0.0")
        == "Release changelog"
    )


def test_get_repo_tag_message_returns_none_without_release_body() -> None:
    repository = FakeRepository(name="template", release_bodies={"v1.0.0": ""})
    client = make_client(FakeGithub(repository=repository))

    assert client.get_repo_tag_message("quantco", "template", "v1.0.0") is None


def test_get_repo_tag_message_returns_none_without_release() -> None:
    repository = FakeRepository(name="template")
    client = make_client(FakeGithub(repository=repository))

    assert client.get_repo_tag_message("quantco", "template", "v1.0.0") is None


def test_find_files_by_name_returns_matching_blob_paths() -> None:
    repository = FakeRepository(
        name="example",
        tree=[
            FakeGitTreeEntry(path="pixi.lock"),
            FakeGitTreeEntry(path="nested/pixi.lock"),
            FakeGitTreeEntry(path="package-lock.json"),
            FakeGitTreeEntry(path="pixi.toml"),
            FakeGitTreeEntry(path="docs/pixi.lock", type="tree"),
        ],
    )
    client = make_client(FakeGithub(repository=repository))

    assert client.find_files_by_name(
        RepositoryRef(owner="quantco", name="example"),
        re.compile(r"(?:pixi\.lock|package-lock\.json)"),
    ) == ["pixi.lock", "nested/pixi.lock", "package-lock.json"]


def test_find_files_by_name_accepts_plain_filename() -> None:
    repository = FakeRepository(
        name="example",
        tree=[
            FakeGitTreeEntry(path="pixi.lock"),
            FakeGitTreeEntry(path="nested/pixi.lock"),
            FakeGitTreeEntry(path="package-lock.json"),
            FakeGitTreeEntry(path="docs/pixi.lock", type="tree"),
        ],
    )
    client = make_client(FakeGithub(repository=repository))

    assert client.find_files_by_name(
        RepositoryRef(owner="quantco", name="example"),
        "pixi.lock",
    ) == ["pixi.lock", "nested/pixi.lock"]


def test_find_files_by_name_returns_empty_for_missing_tree() -> None:
    logger = RecordingLogger()
    repository = FakeRepository(
        name="example",
        tree_error=GithubException(404, {"message": "No tree"}),
    )
    client = make_client(FakeGithub(repository=repository), logger=logger)

    assert (
        client.find_files_by_name(
            RepositoryRef(owner="quantco", name="example", branch="main"),
            "pixi.lock",
        )
        == []
    )
    assert logger.logged(
        LogLevel.DEBUG,
        "Failed to find pixi.lock in quantco/example@main: No tree (HTTP 404)",
    )


@pytest.mark.parametrize("status", [409, 500])
def test_find_files_by_name_logs_and_reraises_unexpected_github_errors(
    status: int,
) -> None:
    logger = RecordingLogger()
    error = GithubException(status, {"message": "boom"})
    repository = FakeRepository(name="example", tree_error=error)
    client = make_client(FakeGithub(repository=repository), logger=logger)

    with pytest.raises(GithubException) as exc_info:
        client.find_files_by_name(
            RepositoryRef(owner="quantco", name="example", branch="main"),
            "pixi.lock",
        )

    assert exc_info.value is error
    assert logger.logged(
        LogLevel.ERROR, "Error while searching for pixi.lock in quantco/example@main."
    )


def test_get_file_content_returns_decoded_file() -> None:
    repository = FakeRepository(
        name="example",
        file_contents={"pixi.toml": "[workspace]\nname = 'example'\n"},
    )
    client = make_client(FakeGithub(repository=repository))

    assert (
        client.get_file_content(
            RepositoryRef(owner="quantco", name="example", branch="main"),
            "pixi.toml",
        )
        == "[workspace]\nname = 'example'\n"
    )


def test_get_file_content_returns_none_for_missing_file() -> None:
    repository = FakeRepository(name="example")
    client = make_client(FakeGithub(repository=repository))

    assert (
        client.get_file_content(
            RepositoryRef(owner="quantco", name="example", branch="main"),
            "pixi.toml",
        )
        is None
    )


def test_get_file_content_returns_none_for_trees() -> None:
    repository = FakeRepository(name="example", file_contents={"config": ["nested"]})
    client = make_client(FakeGithub(repository=repository))

    assert (
        client.get_file_content(
            RepositoryRef(owner="quantco", name="example", branch="main"),
            "config",
        )
        is None
    )


def test_check_ref_exists_accepts_default_and_explicit_branches() -> None:
    repository = FakeRepository(
        name="example",
        default_branch="main",
        branches=["main", "release"],
    )
    client = make_client(FakeGithub(repository=repository))

    assert client.check_ref_exists(RepositoryRef(owner="quantco", name="example"))
    assert client.check_ref_exists(
        RepositoryRef(owner="quantco", name="example", branch="release")
    )


@pytest.mark.parametrize(
    "repository_ref",
    [
        RepositoryRef(owner="quantco", name="example", branch="missing"),
        RepositoryRef(owner="quantco", name="missing"),
    ],
)
def test_check_ref_exists_returns_false_for_missing_refs_or_repositories(
    repository_ref: RepositoryRef,
) -> None:
    repository = FakeRepository(
        name="example",
        default_branch="main",
        branches=["main"],
    )
    client = make_client(FakeGithub(repository=repository))

    assert not client.check_ref_exists(repository_ref)


def test_list_open_pull_requests_filters_target_branch() -> None:
    main_pr = FakePullRequest(number=1, base_ref="main")
    release_pr = FakePullRequest(number=2, base_ref="release")
    repository = FakeRepository(
        name="example",
        pulls=[main_pr, release_pr],
    )
    client = make_client(FakeGithub(repository=repository))

    pull_requests = client.list_open_pull_requests(
        RepositoryRef(owner="quantco", name="example"),
        source_branch="update-branch",
        target_branch="main",
    )

    assert pull_requests == [main_pr]
    assert repository.pull_queries == [
        {"state": "open", "head": "quantco:update-branch"}
    ]


def test_list_open_pull_requests_filters_forked_repository_head_locally() -> None:
    matching_pr = FakePullRequest(number=1, base_ref="main")
    other_branch_pr = FakePullRequest(
        number=2,
        base_ref="main",
        head_ref="other-branch",
    )
    other_owner_pr = FakePullRequest(
        number=3,
        base_ref="main",
        head_owner="other-owner",
    )
    repository = FakeRepository(
        name="example",
        fork=True,
        pulls=[matching_pr, other_branch_pr, other_owner_pr],
    )
    client = make_client(FakeGithub(repository=repository))

    pull_requests = client.list_open_pull_requests(
        RepositoryRef(owner="quantco", name="example"),
        source_branch="update-branch",
        target_branch="main",
    )

    assert pull_requests == [matching_pr]
    assert repository.pull_queries == [{"state": "open", "base": "main"}]


def test_clone_repository_uses_extraheader_and_credential_less_clone_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        calls.append({"command": command, **kwargs})
        return ExecOutput(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr("quant_ranger._impl.github.get_exec_output_silently", fake_exec)
    repository = FakeRepository(
        name="example",
        clone_url="https://github.example/quantco/example.git",
        branches=["main"],
    )
    client = make_client(FakeGithub(repository=repository))
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")

    checkout = client.clone_repository(repository_ref, directory=tmp_path / "checkout")

    assert checkout.repository_ref == repository_ref
    assert calls == [
        {
            "command": [
                "git",
                "-c",
                f"http.extraHeader=AUTHORIZATION: basic {base64.b64encode(b'x-access-token:secret-token').decode()}",
                "clone",
                "--depth",
                "1",
                "https://github.example/quantco/example.git",
                "-b",
                "main",
                str(tmp_path / "checkout"),
            ],
            "logger": client.logger,
            "redact": [
                "secret-token",
                base64.b64encode(b"x-access-token:secret-token").decode(),
            ],
            "env": {"GIT_LFS_SKIP_SMUDGE": "1"},
        }
    ]


def test_clone_repository_without_explicit_branch_omits_branch_option(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        calls.append({"command": command, **kwargs})
        return ExecOutput(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr("quant_ranger._impl.github.get_exec_output_silently", fake_exec)
    repository = FakeRepository(
        name="example",
        clone_url="https://github.example/quantco/example.git",
    )
    client = make_client(FakeGithub(repository=repository))

    checkout = client.clone_repository(
        RepositoryRef(owner="quantco", name="example"),
        directory=tmp_path / "checkout",
    )

    assert checkout.repository_ref == RepositoryRef(owner="quantco", name="example")
    assert calls == [
        {
            "command": [
                "git",
                "-c",
                f"http.extraHeader=AUTHORIZATION: basic {base64.b64encode(b'x-access-token:secret-token').decode()}",
                "clone",
                "--depth",
                "1",
                "https://github.example/quantco/example.git",
                str(tmp_path / "checkout"),
            ],
            "logger": client.logger,
            "redact": [
                "secret-token",
                base64.b64encode(b"x-access-token:secret-token").decode(),
            ],
            "env": {"GIT_LFS_SKIP_SMUDGE": "1"},
        }
    ]


def test_create_pull_request_without_publishing_shows_and_trims_details(
    tmp_path: Path,
) -> None:
    repository = FakeRepository(name="example")
    client = make_client(
        FakeGithub(repository=repository),
        publish_changes=False,
        show_pr_details=True,
        pr_details_diff_lines=20,
    )
    logger = RecordingLogger()
    checkout = RecordingCheckout(
        tmp_path,
        RepositoryRef(owner="quantco", name="example"),
        changed_files=("file",),
    )
    diff_lines = [f"diff {index}" for index in range(30)]
    checkout.diff = "\n".join(diff_lines)

    client.create_pull_request(
        checkout,
        PullRequestOptions(
            title="Updated title",
            body="Updated body",
            source_branch="update-branch",
            quant_ranger_id="zizmor",
        ),
        logger,
    )

    title, content = logger.panels[0]
    assert title == "Pull request details"
    assert isinstance(content, Group)
    pull_request_title, metadata, separator, diff = content.renderables
    assert isinstance(pull_request_title, Text)
    assert str(pull_request_title) == "Updated title"
    assert pull_request_title.style == "bold"
    assert isinstance(metadata, Text)
    assert str(metadata) == (
        "update-branch -> main, 1 changed file, body 12 chars, labels: none"
    )
    assert isinstance(separator, Rule)
    assert isinstance(diff, Syntax)
    diff_preview = diff.code
    assert len(diff_preview.splitlines()) == 21
    assert "[... 10 lines truncated ...]" in diff_preview
    assert not logger.logged(LogLevel.DEBUG, "Pull request 'Updated title'")


def test_create_pull_request_creates_new_pull_request_with_labels(
    tmp_path: Path,
) -> None:
    repository = FakeRepository(name="example")
    client = make_client(FakeGithub(repository=repository), show_pr_details=True)
    logger = RecordingLogger()
    checkout = RecordingCheckout(
        tmp_path, RepositoryRef(owner="quantco", name="example")
    )
    checkout.diff = "diff --git a/file b/file\n+Updated body"

    created_or_updated = client.create_pull_request(
        checkout,
        PullRequestOptions(
            title="Updated title",
            body="Updated body",
            source_branch="update-branch",
            quant_ranger_id="zizmor",
            target_branch="main",
            labels=["dependencies"],
        ),
        logger,
    )

    assert created_or_updated
    assert checkout.checked_out_branches == ["update-branch"]
    assert checkout.commits == [
        {
            "author_email": "1+octocat@users.noreply.github.com",
            "author_name": "octocat",
            "message": "Updated title",
            "quant_ranger_id": "zizmor",
            "user_email": "1+octocat@users.noreply.github.com",
            "user_name": "octocat",
        }
    ]
    assert checkout.pushed_branches == ["update-branch"]
    title, content = logger.panels[0]
    assert title == "Pull request details"
    assert isinstance(content, Group)
    diff = content.renderables[3]
    assert isinstance(diff, Syntax)
    assert diff.code == checkout.diff
    assert repository.created_pulls == [
        {
            "base": "main",
            "body": "Updated body",
            "head": "update-branch",
            "title": "Updated title",
        }
    ]
    assert repository.pulls[0].labels == ["dependencies"]


def test_create_pull_request_updates_only_matching_target_branch(
    tmp_path: Path,
) -> None:
    other_target_pr = FakePullRequest(number=1, base_ref="release")
    matching_pr = FakePullRequest(number=2, base_ref="main")
    repository = FakeRepository(
        name="example",
        pulls=[other_target_pr, matching_pr],
    )
    client = make_client(FakeGithub(repository=repository))
    checkout = RecordingCheckout(
        tmp_path, RepositoryRef(owner="quantco", name="example")
    )

    created_or_updated = client.create_pull_request(
        checkout,
        PullRequestOptions(
            title="Updated title",
            body="Updated body",
            source_branch="update-branch",
            quant_ranger_id="zizmor",
            target_branch="main",
        ),
        RecordingLogger(),
    )

    assert created_or_updated
    assert other_target_pr.edits == []
    assert matching_pr.edits == [{"title": "Updated title", "body": "Updated body"}]
    assert repository.created_pulls == []
    assert checkout.pushed_branches == ["update-branch"]


def test_create_pull_request_updates_human_quant_ranger_commit(
    tmp_path: Path,
) -> None:
    pull_request = FakePullRequest(
        number=1,
        base_ref="main",
        commits=[
            FakeCommit(
                author_type="User",
                message=(
                    "chore: Fix GitHub Actions findings with zizmor\n\n"
                    "Quant-Ranger: zizmor"
                ),
            )
        ],
    )
    repository = FakeRepository(name="example", pulls=[pull_request])
    client = make_client(FakeGithub(repository=repository))
    checkout = RecordingCheckout(
        tmp_path, RepositoryRef(owner="quantco", name="example")
    )

    created_or_updated = client.create_pull_request(
        checkout,
        PullRequestOptions(
            title="Updated title",
            body="Updated body",
            source_branch="update-branch",
            quant_ranger_id="zizmor",
            target_branch="main",
        ),
        RecordingLogger(),
    )

    assert created_or_updated
    assert pull_request.edits == [{"title": "Updated title", "body": "Updated body"}]
    assert checkout.pushed_branches == ["update-branch"]


def test_create_pull_request_updates_commit_without_author_but_with_trailer(
    tmp_path: Path,
) -> None:
    pull_request = FakePullRequest(
        number=1,
        base_ref="main",
        commits=[
            FakeCommit(
                author_type=None,
                message=(
                    "chore: Fix GitHub Actions findings with zizmor\n\n"
                    "Quant-Ranger: zizmor"
                ),
            )
        ],
    )
    repository = FakeRepository(name="example", pulls=[pull_request])
    client = make_client(FakeGithub(repository=repository))
    checkout = RecordingCheckout(
        tmp_path, RepositoryRef(owner="quantco", name="example")
    )

    created_or_updated = client.create_pull_request(
        checkout,
        PullRequestOptions(
            title="Updated title",
            body="Updated body",
            source_branch="update-branch",
            quant_ranger_id="zizmor",
            target_branch="main",
        ),
        RecordingLogger(),
    )

    assert created_or_updated
    assert pull_request.edits == [{"title": "Updated title", "body": "Updated body"}]
    assert checkout.pushed_branches == ["update-branch"]


def test_create_pull_request_refuses_human_commit_without_trailer(
    tmp_path: Path,
) -> None:
    pull_request = FakePullRequest(
        number=1,
        base_ref="main",
        commits=[FakeCommit(author_type="User", message="manual edit")],
    )
    repository = FakeRepository(name="example", pulls=[pull_request])
    client = make_client(FakeGithub(repository=repository))
    checkout = RecordingCheckout(
        tmp_path, RepositoryRef(owner="quantco", name="example")
    )

    created_or_updated = client.create_pull_request(
        checkout,
        PullRequestOptions(
            title="Updated title",
            body="Updated body",
            source_branch="update-branch",
            quant_ranger_id="zizmor",
            target_branch="main",
        ),
        RecordingLogger(),
    )

    assert not created_or_updated
    assert pull_request.edits == []
    assert checkout.pushed_branches == []


def test_create_pull_request_without_publishing_refuses_unowned_commit(
    tmp_path: Path,
) -> None:
    pull_request = FakePullRequest(
        number=1,
        base_ref="main",
        commits=[FakeCommit(author_type="User", message="manual edit")],
    )
    repository = FakeRepository(name="example", pulls=[pull_request])
    client = make_client(FakeGithub(repository=repository), publish_changes=False)
    logger = RecordingLogger()
    checkout = RecordingCheckout(
        tmp_path, RepositoryRef(owner="quantco", name="example")
    )

    created_or_updated = client.create_pull_request(
        checkout,
        PullRequestOptions(
            title="Updated title",
            body="Updated body",
            source_branch="update-branch",
            quant_ranger_id="zizmor",
            target_branch="main",
        ),
        logger,
    )

    assert not created_or_updated
    assert pull_request.edits == []
    assert checkout.pushed_branches == []
    assert logger.warnings == []


def test_create_pull_request_overwrites_manual_changes_with_force_push(
    tmp_path: Path,
) -> None:
    pull_request = FakePullRequest(
        number=1,
        base_ref="main",
        commits=[FakeCommit(author_type="User", message="manual edit")],
    )
    repository = FakeRepository(name="example", pulls=[pull_request])
    logger = RecordingLogger()
    client = make_client(FakeGithub(repository=repository), logger=logger)
    client.force_push = True
    checkout = RecordingCheckout(
        tmp_path, RepositoryRef(owner="quantco", name="example")
    )

    created_or_updated = client.create_pull_request(
        checkout,
        PullRequestOptions(
            title="Updated title",
            body="Updated body",
            source_branch="update-branch",
            quant_ranger_id="zizmor",
            target_branch="main",
        ),
        logger,
    )

    assert created_or_updated
    assert pull_request.edits == [{"title": "Updated title", "body": "Updated body"}]
    assert checkout.pushed_branches == ["update-branch"]
    assert any("--force-push" in warning for warning in logger.warnings)


def test_github_client_fetches_commit_author_lazily() -> None:
    github = FakeGithub(repository=FakeRepository(name="example"))
    client = make_client(github)

    assert github.get_user_calls == 0
    assert client._commit_author() == CommitAuthor(
        name="octocat",
        email="1+octocat@users.noreply.github.com",
    )
    assert client._commit_author() == CommitAuthor(
        name="octocat",
        email="1+octocat@users.noreply.github.com",
    )
    assert github.get_user_calls == 1


def test_github_client_skips_user_lookup_for_installation_token_prefix() -> None:
    github = FakeGithub(repository=FakeRepository(name="example"))
    logger = RecordingLogger()
    fallback_commit_author = CommitAuthor(
        name="example-ranger[bot]",
        email="1+example-ranger[bot]@users.noreply.github.com",
    )
    client = make_client(
        github,
        logger=logger,
        token="ghs_installation-token",
        fallback_commit_author=fallback_commit_author,
    )

    assert client._commit_author() == fallback_commit_author
    assert client._commit_author() == fallback_commit_author
    assert github.get_user_calls == 0
    assert logger.debug_messages == [
        "Falling back to the example-ranger[bot] commit author."
    ]


def test_github_client_requires_fallback_author_for_installation_token() -> None:
    github = FakeGithub(repository=FakeRepository(name="example"))
    client = make_client(github, token="ghs_installation-token")

    with pytest.raises(GitHubError, match="fallback commit author is required"):
        client._commit_author()

    assert github.get_user_calls == 0


class FakeInstallation(Installation):
    """Stand-in for `github.Installation.Installation` in client tests."""

    def __init__(
        self,
        repositories: list[FakeRepository] | None = None,
        error: GithubException | None = None,
        owner_login: str = "quantco",
        auth: Any | None = None,
    ) -> None:
        self.repositories = [] if repositories is None else repositories
        self.error = error
        self.owner_login = owner_login
        self.auth = auth or SimpleNamespace(token="ghs_github-app-installation-token")
        self.get_repos_calls = 0

    @property
    @override
    def account(self) -> Any:
        return SimpleNamespace(login=self.owner_login)

    @property
    @override
    def requester(self) -> Any:
        return SimpleNamespace(auth=self.auth)

    @override
    def get_repos(self) -> PaginatedList[Repository]:
        self.get_repos_calls += 1
        if self.error is not None:
            raise self.error
        return cast(PaginatedList[Repository], FakePaginatedList(self.repositories))


def make_client(
    github: FakeGithub,
    *,
    logger: RecordingLogger | None = None,
    token: str | FakeInstallation = "secret-token",
    api_url: str = "https://github.example/api/v3",
    publish_changes: bool = True,
    show_pr_details: bool = False,
    pr_details_diff_lines: int | None = None,
    fallback_commit_author: CommitAuthor | None = None,
) -> GitHubClient:
    client = GitHubClient(
        cast(Any, token),
        logger=logger or RecordingLogger(),
        api_url=api_url,
        show_pr_details=show_pr_details,
        pr_details_diff_lines=pr_details_diff_lines,
        fallback_commit_author=fallback_commit_author,
        publish_changes=publish_changes,
    )
    client._github_factory = lambda: cast(Any, github)
    return client


@dataclass
class FakeGithub:
    repository: FakeRepository | None = None
    organization: FakeOrganization | None = None
    user_error: GithubException | None = None
    get_repo_calls: list[str] = field(default_factory=list)
    get_user_calls: int = 0

    def get_repo(self, full_name: str) -> FakeRepository:
        self.get_repo_calls.append(full_name)
        if (
            self.repository is None
            or full_name.rsplit("/", maxsplit=1)[-1] != self.repository.name
        ):
            raise UnknownObjectException(404, {"message": "Not Found"})
        return self.repository

    def get_organization(self, owner: str) -> FakeOrganization:
        if owner != "quantco" or self.organization is None:
            raise UnknownObjectException(404, {"message": "Not Found"})
        return self.organization

    def get_user(self) -> FakeUser:
        self.get_user_calls += 1
        if self.user_error is not None:
            raise self.user_error
        return FakeUser(login="octocat", id=1)


@dataclass
class FakeOrganization:
    repositories: Sequence[FakeRepository]

    def get_repos(self, type: str) -> FakePaginatedList:
        assert type == "all"
        return FakePaginatedList(self.repositories)


class FakePaginatedList(list[Any]):
    @property
    def totalCount(self) -> int:  # noqa: N802
        return len(self)


@dataclass
class FakeGitTreeEntry:
    path: str | None
    type: str = "blob"


def _at(date: str) -> datetime:
    return datetime.fromisoformat(date).replace(tzinfo=UTC)


@dataclass
class FakeRelease:
    tag_name: str
    published_at: datetime | None = None
    created_at: datetime | None = None
    draft: bool = False
    prerelease: bool = False


@dataclass
class FakeRepository:
    name: str
    owner_login: str = "quantco"
    default_branch: str | None = "main"
    fork: bool = False
    size: int = 1
    archived: bool = False
    html_url: str = "https://github.example/quantco/example"
    clone_url: str = "https://github.example/quantco/example.git"
    branches: list[str] = field(default_factory=lambda: ["main"])
    latest_release_tag: str = "v1.0.0"
    releases: list[FakeRelease] = field(default_factory=list)
    tree: list[FakeGitTreeEntry] = field(default_factory=list)
    tree_error: GithubException | None = None
    file_contents: dict[str, str | list[str]] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    get_tags_calls: int = 0
    annotated_tag_messages: dict[str, str] = field(default_factory=dict)
    release_bodies: dict[str, str] = field(default_factory=dict)
    pulls: list[FakePullRequest] = field(default_factory=list)
    created_pulls: list[dict[str, str]] = field(default_factory=list)
    pull_queries: list[dict[str, str]] = field(default_factory=list)

    @property
    def owner(self) -> Any:
        return SimpleNamespace(login=self.owner_login)

    def get_pulls(
        self,
        state: str,
        head: str | None = None,
        base: str | None = None,
    ) -> list[FakePullRequest]:
        query = {"state": state}
        if head is not None:
            query["head"] = head
        if base is not None:
            query["base"] = base
        self.pull_queries.append(query)
        if self.fork and head is not None:
            return []

        pull_requests = self.pulls
        if head is not None:
            head_owner, _, head_ref = head.partition(":")
            pull_requests = [
                pull_request
                for pull_request in pull_requests
                if pull_request.head.user.login.lower() == head_owner.lower()
                and pull_request.head.ref == head_ref
            ]
        if base is not None:
            pull_requests = [
                pull_request
                for pull_request in pull_requests
                if pull_request.base.ref == base
            ]
        return pull_requests

    def get_branch(self, branch: str) -> object:
        if branch not in self.branches:
            raise UnknownObjectException(404, {"message": "Not Found"})
        return object()

    def get_latest_release(self) -> Any:
        return SimpleNamespace(tag_name=self.latest_release_tag)

    def get_releases(self) -> list[FakeRelease]:
        return self.releases

    def get_tags(self) -> list[Any]:
        self.get_tags_calls += 1
        return [SimpleNamespace(name=tag) for tag in self.tags]

    def get_git_ref(self, ref: str) -> Any:
        prefix, tag = ref.split("/", maxsplit=1)
        assert prefix == "tags"
        if tag in self.annotated_tag_messages:
            return SimpleNamespace(
                object=SimpleNamespace(type="tag", sha=f"sha-for-{tag}")
            )
        return SimpleNamespace(object=SimpleNamespace(type="commit", sha="commit-sha"))

    def get_git_tag(self, tag_sha: str) -> Any:
        prefix = "sha-for-"
        assert tag_sha.startswith(prefix)
        tag = tag_sha.removeprefix(prefix)
        return SimpleNamespace(message=self.annotated_tag_messages[tag])

    def get_release(self, tag: str) -> Any:
        if tag not in self.release_bodies:
            raise UnknownObjectException(404, {"message": "Not Found"})
        return SimpleNamespace(body=self.release_bodies[tag])

    def get_git_tree(self, branch: str, *, recursive: bool) -> Any:
        assert recursive
        if branch not in self.branches:
            raise UnknownObjectException(404, {"message": "Not Found"})
        if self.tree_error is not None:
            raise self.tree_error
        return SimpleNamespace(tree=self.tree)

    def get_contents(self, path: str, *, ref: str | None) -> Any:
        if ref not in self.branches:
            raise UnknownObjectException(404, {"message": "Not Found"})
        if path not in self.file_contents:
            raise UnknownObjectException(404, {"message": "Not Found"})
        content = self.file_contents[path]
        if isinstance(content, list):
            return content
        return SimpleNamespace(decoded_content=content.encode())

    def create_pull(
        self,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> FakePullRequest:
        self.created_pulls.append(
            {"base": base, "body": body, "head": head, "title": title}
        )
        pull_request = FakePullRequest(number=100, base_ref=base)
        self.pulls.append(pull_request)
        return pull_request


@dataclass
class FakePullRequest:
    number: int
    base_ref: str
    head_ref: str = "update-branch"
    head_owner: str = "quantco"
    edits: list[dict[str, str]] = field(default_factory=list)
    commits: list[Any] = field(default_factory=lambda: [FakeCommit()])
    labels: list[str] = field(default_factory=list)

    @property
    def base(self) -> Any:
        return SimpleNamespace(ref=self.base_ref)

    @property
    def head(self) -> Any:
        return SimpleNamespace(
            ref=self.head_ref,
            user=SimpleNamespace(login=self.head_owner),
        )

    def edit(self, *, title: str, body: str) -> None:
        self.edits.append({"title": title, "body": body})

    def get_commits(self) -> list[Any]:
        return self.commits

    def add_to_labels(self, *labels: str) -> None:
        self.labels.extend(labels)


@dataclass
class FakeCommit:
    author_type: str | None = "Bot"
    message: str = ""

    @property
    def author(self) -> Any:
        if self.author_type is None:
            return None
        return SimpleNamespace(type=self.author_type)

    @property
    def commit(self) -> Any:
        return SimpleNamespace(message=self.message)


@dataclass
class FakeUser:
    login: str
    id: int
