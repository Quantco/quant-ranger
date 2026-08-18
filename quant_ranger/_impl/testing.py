import re
import traceback
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any, override

from rich.console import Console, RenderableType

from quant_ranger._impl.artifacts import UpdateResultsArtifact
from quant_ranger._impl.git import RepositoryCheckout
from quant_ranger._impl.github import GitHubError, PullRequestOptions
from quant_ranger._impl.helpers import ExecOutput
from quant_ranger._impl.logger import Logger, LogLevel
from quant_ranger._impl.models import RepositoryRef, ScanFailure

type FakeKeychain = Callable[[dict[str, str]], list[str]]
"""Signature of the `fake_keychain` fixture: install an account → secret mapping into
the keychain fake and get back the list recording requested accounts."""


def make_update_results_artifact(
    scan_failures: Sequence[ScanFailure] = (),
) -> UpdateResultsArtifact:
    """Build a representative update-results artifact for aggregator tests."""
    return UpdateResultsArtifact(
        updater="copier",
        updater_options={},
        generated_at=datetime(2026, 7, 16, tzinfo=UTC),
        dry_run=True,
        github_api_url="https://api.github.com",
        results=[],
        scan_failures=list(scan_failures),
    )


class FakeKeychainExec:
    """`get_exec_output_silently` stand-in serving macOS Keychain lookups.

    Answers `security find-generic-password` calls from an account → secret
    mapping; unknown accounts report "not found". Requested accounts are
    recorded in `requested_accounts`.
    """

    def __init__(self, secrets: Mapping[str, str]) -> None:
        self.secrets = dict(secrets)
        self.requested_accounts: list[str] = []

    def __call__(self, command: Sequence[str], **kwargs: Any) -> ExecOutput:
        del kwargs
        assert list(command[:5]) == [
            "security",
            "find-generic-password",
            "-s",
            "rattler",
            "-a",
        ]
        account = command[5]
        self.requested_accounts.append(account)
        if account in self.secrets:
            return ExecOutput(exit_code=0, stdout=self.secrets[account], stderr="")
        return ExecOutput(exit_code=44, stdout="", stderr="not found")


@dataclass
class RecordingLogger:
    """Logger implementation for tests that records messages by level.

    Assertion conventions:

    - Prefer asserting on outcomes over log lines; assert on logs only when
      logging is the behavior under test.
    - Prefer `logged(level, contains)` over indexing into the per-level lists;
      positional assertions break when unrelated log lines change.
    - Exact `==` comparisons are reserved for asserting silence
      (`logger.warnings == []`), exact output formats, or pinning the complete
      message sequence of a small unit (via `records`).
    """

    show_progress: bool = False
    stream: StringIO = field(default_factory=StringIO)
    console: Console = field(init=False)
    records: list[tuple[LogLevel, str]] = field(default_factory=list)
    panels: list[tuple[str, RenderableType]] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Pin the color system so styled-output assertions see the same escape
        # codes regardless of the environment's TERM/COLORTERM capabilities.
        self.console = Console(
            file=self.stream,
            force_terminal=self.show_progress,
            color_system="truecolor",
        )

    @property
    def infos(self) -> list[str]:
        return self._messages(LogLevel.INFO)

    @property
    def debug_messages(self) -> list[str]:
        return self._messages(LogLevel.DEBUG)

    @property
    def warnings(self) -> list[str]:
        return self._messages(LogLevel.WARNING)

    @property
    def errors(self) -> list[str]:
        return self._messages(LogLevel.ERROR)

    def logged(self, level: LogLevel, contains: str) -> bool:
        """True if any recorded message at `level` contains `contains`."""
        return any(contains in message for message in self._messages(level))

    def _messages(self, level: LogLevel) -> list[str]:
        return [
            message for record_level, message in self.records if record_level == level
        ]

    def info(self, message: str) -> None:
        self.records.append((LogLevel.INFO, message))

    def info_panel(
        self,
        title: str,
        content: RenderableType,
    ) -> None:
        self.panels.append((title, content))

    def debug(self, message: str) -> None:
        self.records.append((LogLevel.DEBUG, message))

    def warning(self, message: str) -> None:
        self.records.append((LogLevel.WARNING, message))

    def error(self, message: str) -> None:
        self.records.append((LogLevel.ERROR, message))

    def exception(self, message: str, error: BaseException) -> None:
        details = "".join(traceback.format_exception(error)).rstrip("\n")
        self.error(f"{message}\n{details}")


@dataclass
class FakeGitHubClient:
    """`GitHubClient` stand-in for tests that records calls per method.

    Cast instances with `cast(GitHubClient, ...)` at the use site; only the
    methods a test exercises need to be configured.
    """

    token: str = "secret-token"
    logger: Logger = field(default_factory=RecordingLogger)
    installation_owner: str | None = None
    api_url: str = "https://api.github.com"
    github_server_host: str = "github.com"
    repository_url: str | None = None
    pr_opened: bool = True
    publish_changes: bool = False
    checkout: RepositoryCheckout | None = None
    active_by_owner: dict[str, list[RepositoryRef]] = field(default_factory=dict)
    installed: list[RepositoryRef] = field(default_factory=list)
    missing_refs: set[str] = field(default_factory=set)
    error: GitHubError | None = None
    files: dict[str, list[str]] = field(default_factory=dict)
    file_contents: dict[str, str] = field(default_factory=dict)
    latest_release: str = "v0.70.0"
    repo_tags: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    repo_tag_error: GitHubError | None = None
    tag_messages: dict[tuple[str, str, str], str | None] = field(default_factory=dict)
    active_repository_calls: list[str] = field(default_factory=list)
    installed_repository_calls: int = 0
    clone_calls: list[RepositoryRef] = field(default_factory=list)
    find_files_calls: list[tuple[RepositoryRef, str | re.Pattern[str]]] = field(
        default_factory=list
    )
    file_content_calls: list[tuple[RepositoryRef, str]] = field(default_factory=list)
    latest_release_calls: list[tuple[str, str]] = field(default_factory=list)
    repo_tag_calls: list[tuple[str, str]] = field(default_factory=list)
    pull_request_calls: list[dict[str, Any]] = field(default_factory=list)

    def installed_repositories(self) -> list[RepositoryRef]:
        self.installed_repository_calls += 1
        if self.error is not None:
            raise self.error
        return self.installed

    def active_repositories(self, owner: str) -> list[RepositoryRef]:
        self.active_repository_calls.append(owner)
        if self.error is not None:
            raise self.error
        return self.active_by_owner.get(owner, [])

    def check_ref_exists(self, repository_ref: RepositoryRef) -> bool:
        return repository_ref.display_name not in self.missing_refs

    def get_repository_url(self, repository_ref: RepositoryRef) -> str:
        return self.repository_url or (
            f"https://{self.github_server_host}/{repository_ref.full_name}"
        )

    def clone_repository(
        self,
        repository_ref: RepositoryRef,
        *,
        directory: Any = None,
    ) -> RepositoryCheckout:
        del directory
        self.clone_calls.append(repository_ref)
        if self.error is not None:
            raise self.error
        assert self.checkout is not None
        return self.checkout

    def find_files_by_name(
        self,
        repository_ref: RepositoryRef,
        filename: str | re.Pattern[str],
    ) -> list[str]:
        self.find_files_calls.append((repository_ref, filename))
        return self.files.get(repository_ref.full_name, [])

    def get_file_content(self, repository_ref: RepositoryRef, path: str) -> str | None:
        self.file_content_calls.append((repository_ref, path))
        return self.file_contents.get(
            f"{repository_ref.full_name}:{path}"
        ) or self.file_contents.get(path)

    def get_latest_release(self, owner: str, name: str) -> str:
        self.latest_release_calls.append((owner, name))
        return self.latest_release

    def get_repo_tags(self, owner: str, name: str) -> list[str]:
        self.repo_tag_calls.append((owner, name))
        if self.repo_tag_error is not None:
            raise self.repo_tag_error
        return self.repo_tags[(owner, name)]

    def get_repo_tag_message(self, owner: str, name: str, tag: str) -> str | None:
        return self.tag_messages[(owner, name, tag)]

    def create_pull_request(
        self,
        checkout: RepositoryCheckout,
        options: PullRequestOptions,
        logger: Logger,
    ) -> bool:
        self.pull_request_calls.append(
            {
                "checkout": checkout,
                "options": options,
                "logger": logger,
                "publish_changes": self.publish_changes,
            }
        )
        return self.pr_opened


class RecordingCheckout(RepositoryCheckout):
    """`RepositoryCheckout` that records git operations instead of running them.

    By default `is_clean()` reports dirty once `add`/`add_all` was called;
    `lock_clean=True` pins it to the `clean` value regardless of adds.
    """

    def __init__(
        self,
        path: str | Path,
        repository_ref: RepositoryRef | None = None,
        *,
        clean: bool = True,
        changed_files: Sequence[str] = (),
        lock_clean: bool = False,
    ) -> None:
        super().__init__(
            path,
            repository_ref
            or RepositoryRef(owner="quantco", name="example", branch="main"),
        )
        self.clean = clean
        self._changed_files = tuple(changed_files)
        self.lock_clean = lock_clean
        self.clean_checked = False
        self.added_paths: list[str] = []
        self.add_all_count = 0
        self.checked_out_branches: list[str] = []
        self.commits: list[dict[str, str]] = []
        self.pushed_branches: list[str] = []
        self.diff = ""

    @property
    def added(self) -> bool:
        return self.add_all_count > 0 or bool(self.added_paths)

    @override
    def add(self, path: str | Path) -> None:
        self.added_paths.append(str(path))

    @override
    def add_all(self) -> None:
        self.add_all_count += 1

    @override
    def is_clean(self) -> bool:
        self.clean_checked = True
        if self.lock_clean:
            return self.clean
        return self.clean and not self.added

    @override
    def checkout_branch(self, branch: str, logger: Logger) -> None:
        self.checked_out_branches.append(branch)

    @override
    def commit_with_author(
        self,
        message: str,
        *,
        author_name: str,
        author_email: str,
        user_name: str,
        user_email: str,
        quant_ranger_id: str,
        logger: Logger,
    ) -> None:
        self.commits.append(
            {
                "author_email": author_email,
                "author_name": author_name,
                "message": message,
                "quant_ranger_id": quant_ranger_id,
                "user_email": user_email,
                "user_name": user_name,
            }
        )

    @override
    def force_push_branch(
        self,
        source_branch: str,
        logger: Logger,
        *,
        config: Sequence[str] = (),
        redact: Sequence[str] = (),
    ) -> None:
        self.pushed_branches.append(source_branch)

    @override
    def changed_files(
        self,
        logger: Logger | None = None,
        *,
        staged: bool = False,
        path: str | Path | None = None,
    ) -> list[str]:
        del logger, staged
        if path is not None:
            # Like `git diff --name-only <path>`, match the path itself or files
            # below it when it is a directory.
            prefix = f"{str(path).rstrip('/')}/"
            return [
                file
                for file in self._changed_files
                if file == str(path) or file.startswith(prefix)
            ]
        return list(self._changed_files)

    @override
    def head_commit_files(self, logger: Logger | None = None) -> list[str]:
        del logger
        return list(self._changed_files)

    @override
    def head_commit_diff(self) -> str:
        return self.diff
