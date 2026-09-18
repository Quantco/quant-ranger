import json
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal, override
from urllib.parse import urlsplit

import tomlkit
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    ValidationError,
)
from tomlkit.exceptions import ParseError

from quant_ranger._impl.cli_options import ScheduleOption
from quant_ranger._impl.git import RepositoryCheckout
from quant_ranger._impl.github import PullRequestOptions
from quant_ranger._impl.helpers import (
    CommandError,
    ExecOutput,
    app_tempdir,
    get_exec_output_silently,
)
from quant_ranger._impl.logger import Logger
from quant_ranger._impl.models import (
    PathUpdateItem,
    RepositoryRef,
    Schedule,
    Status,
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

PIXI_LOCKFILE = "pixi.lock"
# Groups become branch name segments, so they are restricted to characters that
# are always valid in a git ref. The anchors make the pattern match the whole name.
GroupName = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$"),
]
# Pixi connect timeouts behave inconsistently at the moment, so we combine it with our own timeout.
PIXI_UPDATE_TIMEOUT_SECONDS = 300


@dataclass(frozen=True, slots=True)
class PixiSandboxEnvironment:
    """Prepared sandbox inputs shared by every task of one updater run."""

    auth: SandboxAuth
    config_locations: tuple[Path, ...]


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


class PixiUpdateItem(PathUpdateItem):
    """Update item for one pixi lockfile and its parsed manifest."""

    manifest: PixiManifest


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
        lockfiles = context.github_client.find_files_by_name(
            repository_ref,
            PIXI_LOCKFILE,
        )
        if not lockfiles:
            context.logger.debug("No pixi.lock file found.")
            return []

        items: list[PixiUpdateItem] = []
        for path in lockfiles:
            manifest = self._read_manifest(repository_ref, path, context)
            if manifest is None:
                continue

            configured_schedule = manifest.tool.update.autoupdate_schedule
            # `never` opts out of autoupdates entirely, so it is honored even in
            # an unfiltered run; the other values only select a cadence.
            if configured_schedule == "never":
                context.logger.debug(f"Skipping {path}: configured schedule is never.")
                continue

            if self.schedule is not None and self.schedule != configured_schedule:
                context.logger.debug(
                    f"Skipping {path}: configured schedule is "
                    f"{configured_schedule}; current scheduled run is {self.schedule}."
                )
                continue

            items.append(
                PixiUpdateItem(
                    repository_ref=repository_ref,
                    path=path,
                    manifest=manifest,
                )
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
            parsed = tomlkit.parse(contents).unwrap()
            return PixiManifest.model_validate(parsed)
        except (ValidationError, ParseError) as error:
            context.logger.error(
                f"Skipping {path}: could not parse pixi manifest: {error}"
            )
            return None


MAX_PULL_REQUEST_BODY_LENGTH = 65_536


def truncate_pull_request_body(body: str) -> str:
    if len(body) <= MAX_PULL_REQUEST_BODY_LENGTH:
        return body

    notice = "\n".join(
        [
            "> [!WARNING]",
            "> This pull request body was truncated because it exceeded GitHub's "
            "maximum length",
            f"> of {MAX_PULL_REQUEST_BODY_LENGTH} characters. Check out the branch "
            "locally to inspect the full set of changes or generate the full diff yourself "
            "using https://pixi.sh/latest/integration/extensions/pixi_diff/.",
            "",
            "",
        ]
    )
    truncation_marker = "\n\n*... (truncated)*"

    # Fit the notice and marker within GitHub's limit, then snap to a line boundary.
    budget = MAX_PULL_REQUEST_BODY_LENGTH - len(notice) - len(truncation_marker)
    truncated_body = body[:budget]
    last_newline = truncated_body.rfind("\n")
    if last_newline > 0:
        truncated_body = truncated_body[:last_newline]

    return f"{notice}{truncated_body}{truncation_marker}"


class PixiUpdateOptions(UpdateOptions):
    schedule: ScheduleOption = None


@dataclass(frozen=True, slots=True)
class PixiRegeneration:
    """Result of regenerating one lockfile plus the report of its changes."""

    outcome: UpdateOutcome
    report: str | None = None


@dataclass(frozen=True, slots=True)
class PixiUpdateTarget:
    """One changed lockfile and the dependency report of its update."""

    item: PixiUpdateItem
    report: str


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
        self._relative_lockfile_directory = Path(item.path).parent
        self.context.logger.debug(
            f"Lockfile directory: {self._relative_lockfile_directory.as_posix()}"
        )

    @property
    def config(self) -> PixiUpdateConfig:
        return self.item.manifest.tool.update

    @property
    def _relative_manifest_path(self) -> Path:
        return self._relative_lockfile_directory / "pixi.toml"

    @property
    def _absolute_lockfile_directory(self) -> Path:
        return self.checkout.absolute_path / self._relative_lockfile_directory

    @property
    def _absolute_manifest_path(self) -> Path:
        return self.checkout.absolute_path / self._relative_manifest_path

    @override
    def run(self) -> UpdateOutcome:
        regeneration = self.regenerate()
        if regeneration.outcome.result != Status.UPDATED:
            return regeneration.outcome

        assert regeneration.report is not None
        target = PixiUpdateTarget(item=self.item, report=regeneration.report)
        if not self.publish(targets=(target,)):
            return UpdateOutcome(result=Status.SKIPPED)
        return regeneration.outcome

    def regenerate(self) -> PixiRegeneration:
        """Regenerate the lockfile and return its outcome and dependency report.

        Updating and publishing are separate steps so that several lockfiles can share
        one pull request without re-running Pixi for them.
        """
        manifest = self.item.manifest
        config = manifest.tool.update

        update_command = [
            "pixi",
            "update",
            "--no-progress",
            "--json",
            "--no-install",
            "--manifest-path",
            str(self._absolute_manifest_path),
            *self._pixi_update_flags(manifest, config),
        ]

        # Each task gets its own writable cache so a malicious repository
        # cannot poison the cache used by other tasks or the user.
        with app_tempdir(prefix="quant-ranger-pixi-cache-") as cache_dir:
            try:
                output = _run_pixi_update(
                    update_command,
                    cwd=self._absolute_lockfile_directory,
                    logger=self.context.logger,
                    auth=self._auth,
                    cache_dir=cache_dir,
                    config_locations=self._config_locations,
                )
            except CommandError as error:
                return PixiRegeneration(
                    UpdateOutcome(
                        result=Status.FAILURE,
                        message=str(error),
                        details=error.details,
                    )
                )
        if output.stdout.strip() == "{}":
            return PixiRegeneration(UpdateOutcome(result=Status.UP_TO_DATE))

        # Generate diff using:
        # https://pixi.sh/latest/integration/extensions/pixi_diff/
        updates = get_exec_output_silently(
            ["pixi-diff-to-markdown"],
            cwd=self._absolute_lockfile_directory,
            input=output.stdout,
            logger=self.context.logger,
        ).stdout.strip()

        return PixiRegeneration(
            UpdateOutcome(result=Status.UPDATED),
            report=updates,
        )

    def publish(self, *, targets: Sequence[PixiUpdateTarget]) -> bool:
        """Open or update the pull request carrying the given lockfile updates."""
        config = self.config
        for target in targets:
            self.checkout.add(Path(target.item.path).as_posix())

        return self.context.github_client.create_pull_request(
            self.checkout,
            PullRequestOptions(
                title=_pull_request_title(config, targets),
                body=truncate_pull_request_body(_pull_request_body(targets)),
                source_branch=_source_branch(config, targets),
                target_branch=self.checkout.repository_ref.branch,
                labels=config.autoupdate_pull_request_labels,
                quant_ranger_id=PixiUpdateUpdater.name,
            ),
            self.context.logger,
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


def _validate_group_settings(items: Sequence[PixiUpdateItem]) -> None:
    """Reject grouped manifests whose publication settings disagree.

    A group publishes one pull request, so settings that describe that pull request must
    be identical across the group instead of silently picking one manifest's.
    """
    settings = {
        (
            item.manifest.tool.update.autoupdate_branch_prefix,
            item.manifest.tool.update.autoupdate_commit_message,
            tuple(item.manifest.tool.update.autoupdate_pull_request_labels),
        )
        for item in items
    }
    if len(settings) <= 1:
        return

    paths = ", ".join(
        sorted((Path(item.path).parent / "pixi.toml").as_posix() for item in items)
    )
    msg = (
        "Manifests grouped under the same `group` must share "
        "`autoupdate-branch-prefix`, `autoupdate-commit-message`, and "
        f"`autoupdate-pull-request-labels`; conflicting values in {paths}."
    )
    raise ValueError(msg)


def _pull_request_title(
    config: PixiUpdateConfig,
    targets: Sequence[PixiUpdateTarget],
) -> str:
    group = config.group
    if group is not None:
        return f"{config.autoupdate_commit_message} ({group})"
    (target,) = targets
    lockfile_path = Path(target.item.path)
    if lockfile_path.parent == Path("."):
        return config.autoupdate_commit_message
    return f"{config.autoupdate_commit_message} ({lockfile_path.as_posix()})"


def _source_branch(
    config: PixiUpdateConfig,
    targets: Sequence[PixiUpdateTarget],
) -> str:
    group = config.group
    if group is not None:
        return f"{config.autoupdate_branch_prefix}/{group}"
    (target,) = targets
    manifest_path = Path(target.item.path).parent / "pixi.toml"
    return f"{config.autoupdate_branch_prefix}/{manifest_path.as_posix()}"


def _pull_request_body(targets: Sequence[PixiUpdateTarget]) -> str:
    if len(targets) == 1 and targets[0].item.manifest.tool.update.group is None:
        return targets[0].report

    sections = [
        f"## `{(Path(target.item.path).parent / 'pixi.toml').as_posix()}`\n\n"
        f"{target.report}"
        for target in targets
    ]
    return "\n\n".join(sections)


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
        self._sandbox: PixiSandboxEnvironment | None = None

    @override
    def make_task(
        self,
        item: PixiUpdateItem,
        checkout: RepositoryCheckout,
        context: RunContext,
    ) -> PixiUpdateTask:
        sandbox = self._require_sandbox()
        return PixiUpdateTask(
            checkout=checkout,
            context=context,
            item=item,
            options=self.options,
            auth=sandbox.auth,
            config_locations=sandbox.config_locations,
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
            self._sandbox = PixiSandboxEnvironment(
                auth=_sandbox_auth_for_manifests(
                    [item.manifest for item in update_items],
                    context.logger,
                    auth_tempdir=auth_tempdir,
                    pixi_info=pixi_info,
                ),
                config_locations=_pixi_config_locations(pixi_info),
            )
            try:
                return super().update_all(
                    update_items,
                    context,
                    concurrency=concurrency,
                )
            finally:
                self._sandbox = None

    @override
    def _update_units(
        self,
        update_items: Sequence[PixiUpdateItem],
    ) -> list[tuple[PixiUpdateItem, ...]]:
        units: list[tuple[PixiUpdateItem, ...]] = []
        groups: dict[tuple[RepositoryRef, str], list[PixiUpdateItem]] = {}
        for item in update_items:
            group = item.manifest.tool.update.group
            if group is None:
                units.append((item,))
                continue
            groups.setdefault((item.repository_ref, group), []).append(item)

        # Items without a group stay in their own unit. Grouped items share one unit,
        # so their lockfiles are regenerated in one checkout and published together.
        units.extend(tuple(items) for items in groups.values())
        return units

    @override
    def _run_unit(
        self,
        unit: tuple[PixiUpdateItem, ...],
        context: RunContext,
    ) -> list[UpdateResult[UpdateOutput, PixiUpdateItem]]:
        if len(unit) == 1:
            return [self._run_item(unit[0], context)]
        return self._regenerate_group(unit, context)

    def _regenerate_group(
        self,
        items: tuple[PixiUpdateItem, ...],
        context: RunContext,
    ) -> list[UpdateResult[UpdateOutput, PixiUpdateItem]]:
        try:
            with app_tempdir(f"quant-ranger-{self.name}-") as checkout_path:
                checkout = context.github_client.clone_repository(
                    items[0].repository_ref,
                    directory=checkout_path,
                )
                return self._regenerate_and_publish(items, checkout, context)
        except Exception as error:
            return [self._failure_result(item, error, context) for item in items]

    def _regenerate_and_publish(
        self,
        items: Sequence[PixiUpdateItem],
        checkout: RepositoryCheckout,
        context: RunContext,
    ) -> list[UpdateResult[UpdateOutput, PixiUpdateItem]]:
        _validate_group_settings(items)
        results: list[UpdateResult[UpdateOutput, PixiUpdateItem]] = []
        targets: list[PixiUpdateTarget] = []
        for item in items:
            item_context = self._item_context(item, context)
            try:
                regeneration = self.make_task(item, checkout, item_context).regenerate()
            except Exception as error:
                results.append(self._failure_result(item, error, context))
                continue

            results.append(
                self._record_outcome(
                    item,
                    regeneration.outcome,
                    unexpected_error=None,
                    logger=item_context.logger,
                )
            )
            if regeneration.outcome.result == Status.UPDATED:
                assert regeneration.report is not None
                targets.append(PixiUpdateTarget(item=item, report=regeneration.report))

        if not targets:
            return results

        # Publishing uses the first item's configuration; grouped items opt in
        # explicitly, so this is the group's shared configuration by construction.
        task = self.make_task(targets[0].item, checkout, context)
        if task.publish(targets=tuple(targets)):
            return results

        return [
            UpdateResult(result=Status.SKIPPED, item=result.item)
            if result.result == Status.UPDATED
            else result
            for result in results
        ]

    def _require_sandbox(self) -> PixiSandboxEnvironment:
        if self._sandbox is None:
            msg = "Pixi sandbox auth has not been prepared."
            raise RuntimeError(msg)
        return self._sandbox


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
