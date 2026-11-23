import json
import os
import sys
import tomllib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import chain
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal, override
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    ValidationError,
)

from quant_ranger._impl.cli_options import ScheduleOption
from quant_ranger._impl.git import RepositoryCheckout
from quant_ranger._impl.github import (
    MAX_PULL_REQUEST_BODY_LENGTH,
    MAX_PULL_REQUEST_COMMENT_LENGTH,
    PullRequestOptions,
)
from quant_ranger._impl.helpers import (
    CommandError,
    ExecOutput,
    app_tempdir,
    get_exec_output_silently,
)
from quant_ranger._impl.logger import Logger, PrefixLogger
from quant_ranger._impl.models import (
    RepositoryRef,
    Schedule,
    Status,
    UpdateItem,
    UpdateOptions,
    UpdateOutcome,
    UpdateOutput,
    UpdateResult,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.sandbox import get_sandboxed_exec_output_silently
from quant_ranger._impl.scanners import Scanner

from .._base import Updater, UpdateTask
from ._auth import SandboxAuth, prepare_sandbox_auth
from ._checkout_copy import LockfileCopyError, checkout_copy, copy_back_lockfile

PIXI_LOCKFILE = "pixi.lock"
# Groups become a branch name segment. Alphanumerics, `_`, and `-` are always valid
# in a git ref segment. Without `/`, one group's branch cannot be a parent directory
# of another group's branch, which git does not allow.
GroupName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]
# Pixi connect timeouts behave inconsistently at the moment, so we combine it with our own timeout.
PIXI_UPDATE_TIMEOUT_SECONDS = 300


@dataclass(frozen=True, slots=True)
class PixiSandboxPaths:
    read_exec_paths: tuple[Path, ...]
    read_paths: tuple[Path, ...] = ()
    read_write_paths: tuple[Path, ...] = ()


MACOS_SANDBOX_PATHS = PixiSandboxPaths(
    read_exec_paths=(
        Path("/bin"),
        Path("/usr/bin"),
    ),
)
LINUX_SANDBOX_PATHS = PixiSandboxPaths(
    read_exec_paths=(
        Path("/bin"),
        Path("/usr/bin"),
        Path("/lib"),
        Path("/lib64"),
        Path("/usr/lib"),
        Path("/usr/lib64"),
    ),
    read_paths=(
        Path("/etc/ld.so.cache"),
        Path("/etc/resolv.conf"),
        Path("/etc/hosts"),
        Path("/dev/urandom"),
        Path("/dev/random"),
        # CA trust stores; /etc/ssl often only holds symlinks into the
        # distro-specific location, which the sandbox does not resolve.
        Path("/etc/ssl"),  # Debian/Ubuntu, Alpine
        Path("/etc/pki"),  # RHEL/Fedora/Alma/Rocky
        Path("/var/lib/ca-certificates"),  # openSUSE/SLES
        Path("/etc/ca-certificates"),  # Arch
    ),
    read_write_paths=(Path("/dev/null"),),
)


class PixiUpdateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    autoupdate_branch_prefix: str = Field(
        default="pixi-update",
        alias="autoupdate-branch-prefix",
    )
    autoupdate_commit_message: str = Field(
        default="chore: Update pixi lockfile",
        alias="autoupdate-commit-message",
    )
    autoupdate_pull_request_labels: list[str] = Field(
        default=["dependencies"],
        alias="autoupdate-pull-request-labels",
    )
    autoupdate_schedule: Schedule | Literal["never"] = Field(
        default=Schedule.MONTHLY,
        alias="autoupdate-schedule",
    )
    ignore_environments: list[str] = Field(
        default_factory=list,
        alias="ignore-environments",
    )
    ignore_platforms: list[str] = Field(
        default_factory=list,
        alias="ignore-platforms",
    )
    group: GroupName | None = Field(
        default=None,
        alias="group",
    )


class PixiToolSection(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    update: PixiUpdateConfig = PixiUpdateConfig()


type PixiChannel = str | dict[str, Any]


class PixiChannelSection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    channels: list[PixiChannel] = Field(default_factory=list)


class PixiPlatformSection(PixiChannelSection):
    platforms: list[str]


class PixiPackageSection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    build: PixiChannelSection | None = None


class PixiManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tool: PixiToolSection = PixiToolSection()
    environments: dict[str, Any] = {"default": []}
    project: PixiPlatformSection | None = None
    workspace: PixiPlatformSection | None = None
    feature: dict[str, PixiChannelSection] = Field(default_factory=dict)
    package: PixiPackageSection | None = None


class PixiGroup(BaseModel):
    """Settings shared by the lockfiles of one group.

    Conflicting manifest settings do not fail the group; `warnings` explains which
    values were used.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    branch_prefix: str
    commit_message: str
    schedule: Schedule | Literal["never"]
    labels: list[str]
    warnings: list[str]


class PixiLockfile(BaseModel):
    """A pixi lockfile and its parsed adjacent manifest."""

    model_config = ConfigDict(frozen=True)

    path: PurePosixPath
    manifest: PixiManifest

    @property
    def manifest_path(self) -> PurePosixPath:
        return self.path.parent / "pixi.toml"


class PixiUpdateItem(UpdateItem):
    """Update item for the lockfiles published in one pull request.

    An ungrouped item holds a single lockfile; a group holds all its lockfiles that are
    due, sorted by path.
    """

    lockfiles: list[PixiLockfile]
    group: PixiGroup | None = None

    @override
    def __str__(self) -> str:
        if self.group is not None:
            return f"{self.repository_ref.display_name} group {self.group.name}"
        return f"{self.repository_ref.display_name} {self.lockfiles[0].path}"


class PixiUpdateScanner(Scanner[PixiUpdateItem]):
    """Scanner for pixi lockfiles matching scheduled runs."""

    def __init__(self, schedule: Schedule | None = None) -> None:
        self.schedule = schedule

    @override
    def scan_repository(
        self,
        repository_ref: RepositoryRef,
        context: RunContext,
    ) -> Sequence[PixiUpdateItem]:
        paths = context.github_client.find_files_by_name(
            repository_ref,
            PIXI_LOCKFILE,
        )
        if not paths:
            context.logger.debug("No pixi.lock file found.")
            return []

        lockfiles: list[PixiLockfile] = []
        for path in paths:
            manifest = self._read_manifest(repository_ref, path, context)
            if manifest is not None:
                lockfiles.append(
                    PixiLockfile(path=PurePosixPath(path), manifest=manifest)
                )
        # Groups are resolved before schedule filtering so that manifests that are not
        # due in this run are taken into account as well.
        groups = _resolve_groups(lockfiles)
        for group in groups.values():
            for warning in group.warnings:
                context.logger.warning(warning)

        items: list[PixiUpdateItem] = []
        grouped: dict[str, list[PixiLockfile]] = {}
        for lockfile in lockfiles:
            config = lockfile.manifest.tool.update
            # `never` opts out of autoupdates entirely, so it is honored even in
            # an unfiltered run; the other values only select a cadence.
            if config.autoupdate_schedule == "never":
                context.logger.debug(
                    f"Skipping {lockfile.path}: configured schedule is never."
                )
                continue

            group = None if config.group is None else groups[config.group]
            # All lockfiles of a group are due together, so that none of them is
            # dropped from the group's open pull request.
            configured_schedule = (
                config.autoupdate_schedule if group is None else group.schedule
            )
            if self.schedule is not None and self.schedule != configured_schedule:
                context.logger.debug(
                    f"Skipping {lockfile.path}: configured schedule is "
                    f"{configured_schedule}; current scheduled run is {self.schedule}."
                )
                continue

            if group is None:
                items.append(
                    PixiUpdateItem(repository_ref=repository_ref, lockfiles=[lockfile])
                )
            else:
                grouped.setdefault(group.name, []).append(lockfile)

        items.extend(
            PixiUpdateItem(
                repository_ref=repository_ref,
                lockfiles=sorted(members, key=lambda lockfile: lockfile.path),
                group=groups[name],
            )
            for name, members in grouped.items()
        )
        return items

    def _read_manifest(
        self,
        repository_ref: RepositoryRef,
        path: str,
        context: RunContext,
    ) -> PixiManifest | None:
        manifest_path = (PurePosixPath(path).parent / "pixi.toml").as_posix()
        contents = context.github_client.get_file_content(repository_ref, manifest_path)
        if contents is None:
            context.logger.debug(f"Skipping {path}: no {manifest_path} found.")
            return None

        try:
            parsed = tomllib.loads(contents)
            return PixiManifest.model_validate(parsed)
        except (ValidationError, tomllib.TOMLDecodeError) as error:
            context.logger.error(
                f"Skipping {path}: could not parse pixi manifest: {error}"
            )
            return None


def truncate_pull_request_body(
    body: str,
    *,
    max_length: int = MAX_PULL_REQUEST_BODY_LENGTH,
    subject: str = "pull request body",
) -> str:
    """Cut `body` at a line boundary so that it fits within `max_length` characters.

    `subject` names the truncated text in the notice that precedes it.
    """
    if len(body) <= max_length:
        return body

    notice = "\n".join(
        [
            "> [!WARNING]",
            f"> This {subject} was truncated because it exceeded GitHub's "
            "maximum length",
            f"> of {MAX_PULL_REQUEST_BODY_LENGTH} characters. Check out the branch "
            "locally to inspect the full set of changes or generate the full diff yourself "
            "using https://pixi.sh/latest/integration/extensions/pixi_diff/.",
            "",
            "",
        ]
    )
    truncation_marker = "\n\n*... (truncated)*"

    # Fit the notice and marker within the limit, then snap to a line boundary.
    budget = max_length - len(notice) - len(truncation_marker)
    truncated_body = body[:budget]
    last_newline = truncated_body.rfind("\n")
    if last_newline > 0:
        truncated_body = truncated_body[:last_newline]

    return f"{notice}{truncated_body}{truncation_marker}"


class PixiUpdateOptions(UpdateOptions):
    schedule: ScheduleOption = None


@dataclass(frozen=True, slots=True)
class LockfileUpdate:
    """Outcome of `pixi update` for one lockfile and the report of its changes."""

    lockfile: PixiLockfile
    outcome: UpdateOutcome
    report: str = ""


class PixiUpdateTask(UpdateTask[PixiUpdateItem, UpdateOutput, PixiUpdateOptions]):
    def __init__(
        self,
        checkout: RepositoryCheckout,
        context: RunContext,
        *,
        item: PixiUpdateItem,
        options: PixiUpdateOptions,
        auth: SandboxAuth,
        config_locations: tuple[Path, ...],
    ) -> None:
        super().__init__(checkout, context, item=item, options=options)
        self._auth = auth
        self._config_locations = config_locations

    @override
    def run(self) -> UpdateOutcome:
        updates = [self._update_lockfile(lockfile) for lockfile in self.item.lockfiles]
        changed = [
            update for update in updates if update.outcome.result == Status.UPDATED
        ]
        published = bool(changed) and self._publish(changed)
        return _item_outcome(updates, published=published)

    def _publish(self, updates: Sequence[LockfileUpdate]) -> bool:
        """Open or update the pull request carrying the given lockfile updates."""
        for update in updates:
            self.checkout.add(update.lockfile.path.as_posix())

        target_branch = self.checkout.repository_ref.branch
        if self.item.group is None:
            (update,) = updates
            options = _pull_request_options(update, target_branch=target_branch)
        else:
            options = _group_pull_request_options(
                self.item.group, updates, target_branch=target_branch
            )
        return self.context.github_client.create_pull_request(
            self.checkout,
            options,
            self.context.logger,
        )

    def _update_lockfile(self, lockfile: PixiLockfile) -> LockfileUpdate:
        """Run `pixi update` for one lockfile and report the changes."""
        # Within a group, the item's log prefix does not identify the lockfile.
        logger = self.context.logger
        if len(self.item.lockfiles) > 1:
            logger = PrefixLogger(f"[{lockfile.path}] ", logger)
        manifest = lockfile.manifest
        config = manifest.tool.update
        relative_lockfile_path = Path(lockfile.path)
        relative_lockfile_directory = relative_lockfile_path.parent
        logger.debug(f"Lockfile directory: {relative_lockfile_directory.as_posix()}")

        # A symlink in the lockfile directory could point the sandbox's writable
        # working directory and the lockfile destination outside of the checkout.
        # The copy has the same layout, so checking the checkout covers both.
        checkout_path = self.checkout.absolute_path.resolve()
        lockfile_directory = checkout_path / relative_lockfile_directory
        if lockfile_directory.resolve() != lockfile_directory:
            return LockfileUpdate(
                lockfile,
                UpdateOutcome(
                    result=Status.FAILURE,
                    message=(
                        f"{relative_lockfile_directory.as_posix()} must not be "
                        "a symlink or inside a symlinked directory."
                    ),
                ),
            )

        # Pixi runs on a private copy of the checkout; only the resulting lockfile
        # is transferred back. Each lockfile also gets its own writable cache so a
        # malicious repository cannot poison the cache used by other tasks or the
        # user.
        with (
            checkout_copy(self.checkout.absolute_path) as workspace,
            app_tempdir(prefix="quant-ranger-pixi-cache-") as cache_dir,
        ):
            update_command = [
                "pixi",
                "update",
                "--no-progress",
                "--json",
                "--no-install",
                "--manifest-path",
                str(workspace / lockfile.manifest_path),
                *self._pixi_update_flags(manifest, config),
            ]
            try:
                output = _run_pixi_update(
                    update_command,
                    cwd=workspace / relative_lockfile_directory,
                    logger=logger,
                    auth=self._auth,
                    cache_dir=cache_dir,
                    config_locations=self._config_locations,
                )
            except CommandError as error:
                return LockfileUpdate(
                    lockfile,
                    UpdateOutcome(
                        result=Status.FAILURE,
                        message=str(error),
                        details=error.details,
                    ),
                )
            if output.stdout.strip() == "{}":
                return LockfileUpdate(lockfile, UpdateOutcome(result=Status.UP_TO_DATE))

            try:
                copy_back_lockfile(
                    workspace,
                    relative_lockfile_path,
                    self.checkout.absolute_path / relative_lockfile_path,
                )
            except LockfileCopyError as error:
                return LockfileUpdate(
                    lockfile,
                    UpdateOutcome(
                        result=Status.FAILURE,
                        message=f"pixi update did not produce a usable lockfile: {error}",
                    ),
                )

        # Generate diff using:
        # https://pixi.sh/latest/integration/extensions/pixi_diff/
        updates = get_exec_output_silently(
            ["pixi-diff-to-markdown"],
            cwd=self.checkout.absolute_path / relative_lockfile_directory,
            input=output.stdout,
            logger=logger,
        ).stdout.strip()

        return LockfileUpdate(
            lockfile, UpdateOutcome(result=Status.UPDATED), report=updates
        )

    def _pixi_update_flags(
        self,
        manifest: PixiManifest,
        config: PixiUpdateConfig,
    ) -> list[str]:
        flags: list[str] = []

        if config.ignore_environments:
            all_environments = list(manifest.environments)
            if "default" not in manifest.environments:
                all_environments = ["default", *all_environments]
            environments = [
                environment
                for environment in all_environments
                if environment not in config.ignore_environments
            ]
            flags.extend(
                flag for environment in environments for flag in ("-e", environment)
            )

        if config.ignore_platforms:
            platform_section = manifest.project or manifest.workspace
            if platform_section is None:
                raise ValueError(
                    "Invalid pixi manifest, either [project] or [workspace] "
                    "section is missing"
                )
            platforms = [
                platform
                for platform in platform_section.platforms
                if platform not in config.ignore_platforms
            ]
            flags.extend(platform for value in platforms for platform in ("-p", value))

        return flags


def _resolve_groups(lockfiles: Sequence[PixiLockfile]) -> dict[str, PixiGroup]:
    """Resolve the settings of every group from its manifests.

    Manifests with schedule `never` are never updated and therefore not part of a group.
    """
    members: dict[str, list[PixiLockfile]] = {}
    for lockfile in sorted(lockfiles, key=lambda lockfile: lockfile.path):
        config = lockfile.manifest.tool.update
        if config.group is not None and config.autoupdate_schedule != "never":
            members.setdefault(config.group, []).append(lockfile)
    return {name: _resolve_group(name, group) for name, group in members.items()}


def _resolve_group(name: str, members: Sequence[PixiLockfile]) -> PixiGroup:
    """Resolve one group's settings from the values its manifests set explicitly.

    Manifests that leave a setting unset do not count as disagreeing. Labels of all
    manifests are merged.
    """
    warnings: list[str] = []
    explicit_labels = _explicit_values(
        members,
        "autoupdate_pull_request_labels",
        lambda config: config.autoupdate_pull_request_labels,
    )
    labels = chain.from_iterable(labels for _, labels in explicit_labels)
    return PixiGroup(
        name=name,
        branch_prefix=_group_setting(
            name,
            members,
            "autoupdate_branch_prefix",
            lambda config: config.autoupdate_branch_prefix,
            warnings,
        ),
        commit_message=_group_setting(
            name,
            members,
            "autoupdate_commit_message",
            lambda config: config.autoupdate_commit_message,
            warnings,
        ),
        schedule=_group_setting(
            name,
            members,
            "autoupdate_schedule",
            lambda config: config.autoupdate_schedule,
            warnings,
        ),
        labels=list(dict.fromkeys(labels))
        if explicit_labels
        else PixiUpdateConfig().autoupdate_pull_request_labels,
        warnings=warnings,
    )


def _explicit_values[T](
    members: Sequence[PixiLockfile],
    field: str,
    value: Callable[[PixiUpdateConfig], T],
) -> list[tuple[PurePosixPath, T]]:
    """Return the values of the manifests that set `field` explicitly, by manifest.

    `value` reads the same field as `field` names; it only adds type safety.
    """
    return [
        (member.manifest_path, value(member.manifest.tool.update))
        for member in members
        if field in member.manifest.tool.update.model_fields_set
    ]


def _group_setting[T](
    name: str,
    members: Sequence[PixiLockfile],
    field: str,
    value: Callable[[PixiUpdateConfig], T],
    warnings: list[str],
) -> T:
    """Return the value of the first manifest by path that sets `field` explicitly.

    Falls back to the default if no manifest sets it, and appends a warning to
    `warnings` if manifests set different values.
    """
    explicit = _explicit_values(members, field, value)
    if not explicit:
        return value(PixiUpdateConfig())

    manifest_path, chosen = explicit[0]
    if len({setting for _, setting in explicit}) > 1:
        key = PixiUpdateConfig.model_fields[field].alias
        warnings.append(
            f"The manifests of group `{name}` set different `{key}` values; "
            f"using `{chosen}` from `{manifest_path}`."
        )
    return chosen


def _item_outcome(
    updates: Sequence[LockfileUpdate],
    *,
    published: bool,
) -> UpdateOutcome:
    """Combine the outcomes of an item's lockfiles into the outcome of the item.

    Any failing lockfile fails the item, even if the changed lockfiles were published.
    """
    failures = [update for update in updates if update.outcome.result == Status.FAILURE]
    if len(updates) == 1 and failures:
        # The item's name already identifies its only lockfile.
        return failures[0].outcome
    if failures:
        message = "; ".join(
            f"{update.lockfile.path}: {update.outcome.message}" for update in failures
        )
        if published:
            message += " (the other changed lockfiles were published)"
        details = "\n\n".join(
            f"{update.lockfile.path}:\n{update.outcome.details}"
            for update in failures
            if update.outcome.details
        )
        return UpdateOutcome(
            result=Status.FAILURE, message=message, details=details or None
        )
    if published:
        return UpdateOutcome(result=Status.UPDATED)
    if any(update.outcome.result == Status.UPDATED for update in updates):
        return UpdateOutcome(result=Status.SKIPPED)
    return UpdateOutcome(result=Status.UP_TO_DATE)


def _pull_request_options(
    update: LockfileUpdate,
    *,
    target_branch: str | None,
) -> PullRequestOptions:
    lockfile = update.lockfile
    config = lockfile.manifest.tool.update
    title = config.autoupdate_commit_message
    if lockfile.path.parent != PurePosixPath("."):
        title = f"{title} ({lockfile.path})"
    return PullRequestOptions(
        title=title,
        body=truncate_pull_request_body(update.report),
        source_branch=(
            f"{config.autoupdate_branch_prefix}/{_branch_path(lockfile.manifest_path)}"
        ),
        target_branch=target_branch,
        labels=config.autoupdate_pull_request_labels,
        quant_ranger_id=PixiUpdateUpdater.name,
    )


def _branch_path(path: PurePosixPath) -> str:
    """Turn a repository path into a valid git branch name suffix.

    Git rejects ref components that start with a dot or end with `.lock`, so a
    manifest in `.github/` would otherwise yield an unusable branch name.
    """
    return "/".join(_branch_component(part) for part in path.parts)


def _branch_component(part: str) -> str:
    if part.startswith("."):
        part = f"_{part[1:]}"
    if part.endswith(".lock"):
        part = f"{part.removesuffix('.lock')}_lock"
    return part


def _group_pull_request_options(
    group: PixiGroup,
    updates: Sequence[LockfileUpdate],
    *,
    target_branch: str | None,
) -> PullRequestOptions:
    leading = []
    if group.warnings:
        warning_lines = "\n".join(f"> - {warning}" for warning in group.warnings)
        leading.append(f"> [!WARNING]\n{warning_lines}")
    body, comments = _split_group_report(leading, updates)
    return PullRequestOptions(
        title=f"{group.commit_message} ({group.name})",
        body=body,
        # The `group/` namespace keeps group branches apart from the manifest-path
        # branches of ungrouped lockfiles.
        source_branch=f"{group.branch_prefix}/group/{group.name}",
        target_branch=target_branch,
        labels=group.labels,
        quant_ranger_id=PixiUpdateUpdater.name,
        comments=tuple(comments),
    )


def _split_group_report(
    leading: Sequence[str],
    updates: Sequence[LockfileUpdate],
) -> tuple[str, list[str]]:
    """Distribute the per-lockfile sections of a group over the body and comments.

    Sections are never split: the body holds the leading sections that fit, and the
    remaining ones are packed in order into as few comments as possible. Only a
    single section that is too long for a comment on its own is truncated.
    """
    sections = [_group_section(update) for update in updates]
    body = "\n\n".join([*leading, *sections])
    if len(body) <= MAX_PULL_REQUEST_BODY_LENGTH:
        return body, []

    in_body = len(sections) - 1
    while True:
        note = _continuation_note(updates[in_body:])
        body = "\n\n".join([*leading, *sections[:in_body], note])
        if len(body) <= MAX_PULL_REQUEST_BODY_LENGTH or in_body == 0:
            break
        in_body -= 1

    comments: list[str] = []
    for update in updates[in_body:]:
        section = _group_section(update, max_length=MAX_PULL_REQUEST_COMMENT_LENGTH)
        if (
            comments
            and len(comments[-1]) + len("\n\n") + len(section)
            <= MAX_PULL_REQUEST_COMMENT_LENGTH
        ):
            comments[-1] = f"{comments[-1]}\n\n{section}"
        else:
            comments.append(section)
    # Only many warnings could make the body too long even without any section.
    return truncate_pull_request_body(body), comments


def _group_section(update: LockfileUpdate, *, max_length: int | None = None) -> str:
    heading = f"## `{update.lockfile.manifest_path}`\n\n"
    report = update.report
    if max_length is not None:
        report = truncate_pull_request_body(
            report, max_length=max_length - len(heading), subject="report"
        )
    return f"{heading}{report}"


def _continuation_note(updates: Sequence[LockfileUpdate]) -> str:
    manifests = "\n".join(
        f"> - `{update.lockfile.manifest_path}`" for update in updates
    )
    return (
        "> [!NOTE]\n"
        "> The reports of these manifests did not fit into the pull request "
        "description and continue in the comments below:\n"
        f"{manifests}"
    )


def _run_pixi_update(
    command: list[str],
    *,
    cwd: Path,
    logger: Logger,
    auth: SandboxAuth,
    cache_dir: Path,
    config_locations: Sequence[Path],
) -> ExecOutput:
    cache_dir = cache_dir.resolve()
    env = dict(auth.credential_env or {})
    env["PIXI_CACHE_DIR"] = str(cache_dir)
    env["HOME"] = _pixi_update_home()
    ssl_cert_read_paths: tuple[Path, ...] = ()
    ssl_cert_file = os.environ.get("SSL_CERT_FILE")
    if ssl_cert_file:
        env["SSL_CERT_FILE"] = ssl_cert_file
        # Grant the symlink and its target; the sandbox does not resolve symlinks.
        ssl_cert_path = Path(ssl_cert_file)
        ssl_cert_read_paths = (ssl_cert_path, ssl_cert_path.resolve())
    sandbox_paths = _pixi_update_sandbox_paths()
    return get_sandboxed_exec_output_silently(
        command,
        cwd=cwd,
        env=env,
        timeout=PIXI_UPDATE_TIMEOUT_SECONDS,
        logger=logger,
        network=True,
        read_exec_paths=(cache_dir, *sandbox_paths.read_exec_paths),
        read_paths=(
            *auth.credential_read_paths,
            *config_locations,
            *sandbox_paths.read_paths,
            *ssl_cert_read_paths,
        ),
        redact=auth.redact,
        read_write_paths=(cwd, cache_dir, *sandbox_paths.read_write_paths),
        tempdir=True,
    )


def _pixi_info() -> Mapping[str, JsonValue]:
    output = get_exec_output_silently(["pixi", "info", "--json"])
    try:
        pixi_info = json.loads(output.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("`pixi info --json` did not return JSON.") from error

    if not isinstance(pixi_info, dict):
        raise ValueError("`pixi info --json` returned a non-object value.")

    return pixi_info


def _pixi_config_locations(pixi_info: Mapping[str, JsonValue]) -> tuple[Path, ...]:
    """Paths of the pixi configuration files pixi reads on this machine."""
    config_locations = pixi_info.get("config_locations")
    if not isinstance(config_locations, list):
        raise ValueError(
            "`pixi info --json` did not return a list of config_locations."
        )

    paths: list[Path] = []
    for location in config_locations:
        if not isinstance(location, str):
            raise ValueError(
                "`pixi info --json` did not return a list of config_locations."
            )
        paths.append(Path(location))
    return tuple(paths)


def _pixi_update_home() -> str:
    try:
        return os.environ["HOME"]
    except KeyError as error:
        raise RuntimeError(
            "Pixi update requires the HOME environment variable to be set."
        ) from error


def _pixi_update_sandbox_paths() -> PixiSandboxPaths:
    # Pixi build backends can invoke system tools from the host.
    if sys.platform == "darwin":
        return MACOS_SANDBOX_PATHS
    if sys.platform.startswith("linux"):
        return LINUX_SANDBOX_PATHS
    raise RuntimeError(f"Pixi update sandboxing is not supported on {sys.platform!r}.")


class PixiUpdateUpdater(Updater[PixiUpdateItem, UpdateOutput, PixiUpdateOptions]):
    name = "pixi-update"
    description = (
        "Regenerate Pixi lockfiles. Runs sandboxed `pixi update --no-install` "
        "for each lockfile with an adjacent `pixi.toml`."
    )
    task_type = PixiUpdateTask

    @override
    def __init__(self, options: PixiUpdateOptions) -> None:
        super().__init__(options)
        self.scanner = PixiUpdateScanner(schedule=self.options.schedule)
        self._auth: SandboxAuth | None = None
        self._config_locations: tuple[Path, ...] | None = None

    @override
    def make_task(
        self,
        item: PixiUpdateItem,
        checkout: RepositoryCheckout,
        context: RunContext,
    ) -> PixiUpdateTask:
        if self._auth is None or self._config_locations is None:
            msg = "Pixi sandbox auth has not been prepared."
            raise RuntimeError(msg)
        return PixiUpdateTask(
            checkout=checkout,
            context=context,
            item=item,
            options=self.options,
            auth=self._auth,
            config_locations=self._config_locations,
        )

    @override
    def update_all(
        self,
        update_items: Iterable[PixiUpdateItem],
        context: RunContext,
        *,
        concurrency: int = 1,
    ) -> list[UpdateResult[UpdateOutput, PixiUpdateItem]]:
        update_items = list(update_items)
        pixi_info = _pixi_info()
        with app_tempdir(prefix="quant-ranger-pixi-auth-") as auth_tempdir:
            self._auth = _sandbox_auth_for_manifests(
                [
                    lockfile.manifest
                    for item in update_items
                    for lockfile in item.lockfiles
                ],
                context.logger,
                auth_tempdir=auth_tempdir,
                pixi_info=pixi_info,
            )
            self._config_locations = _pixi_config_locations(pixi_info)
            try:
                return super().update_all(
                    update_items,
                    context,
                    concurrency=concurrency,
                )
            finally:
                self._auth = None
                self._config_locations = None


def _sandbox_auth_for_manifests(
    manifests: Sequence[PixiManifest],
    logger: Logger,
    *,
    auth_tempdir: Path,
    pixi_info: Mapping[str, JsonValue],
) -> SandboxAuth:
    channel_hosts: list[str] = []
    for manifest in manifests:
        channel_hosts.extend(_channel_hosts(manifest))
    return prepare_sandbox_auth(
        tuple(dict.fromkeys(channel_hosts)),
        logger,
        tempdir=auth_tempdir,
        pixi_info=pixi_info,
    )


def _channel_hosts(manifest: PixiManifest) -> tuple[str, ...]:
    """Hostnames of the channels the manifest requests packages from."""
    channel_hosts: list[str] = []
    sections = [
        manifest.workspace,
        manifest.project,
        *manifest.feature.values(),
        manifest.package.build if manifest.package is not None else None,
    ]
    for section in sections:
        if section is None:
            continue
        for channel in section.channels:
            url = channel if isinstance(channel, str) else channel.get("channel")
            if not isinstance(url, str):
                continue
            parsed = urlsplit(url)
            if parsed.scheme in {"http", "https"} and parsed.hostname is not None:
                channel_hosts.append(parsed.hostname)

    return tuple(dict.fromkeys(channel_hosts))
