import json
import os
import re
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Annotated, Any, override

import tomlkit
import typer
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from tomlkit.exceptions import ParseError

from quant_ranger._impl.github import PullRequestOptions
from quant_ranger._impl.models import (
    Status,
    UpdateItem,
    UpdateOptions,
    UpdateOutcome,
    UpdateOutput,
)
from quant_ranger._impl.scanners import RepositoryFileScanner

from ._base import Updater, UpdateTask

NPM_CONFIG_FILE = ".npmrc"
BUN_CONFIG_FILE = "bunfig.toml"
PNPM_CONFIG_FILE = "pnpm-workspace.yaml"

BUN_LOCKFILE = "bun.lock"
PNPM_LOCKFILE = "pnpm-lock.yaml"
NPM_LOCKFILE = "package-lock.json"
NODE_LOCKFILES = (
    NPM_LOCKFILE,
    BUN_LOCKFILE,
    PNPM_LOCKFILE,
)
NODE_LOCKFILE_PATTERN = re.compile(
    "|".join(re.escape(lockfile) for lockfile in NODE_LOCKFILES)
)

DEFAULT_MINIMUM_RELEASE_AGE_DAYS = 7

# https://pnpm.io/settings#blockexoticsubdeps
PNPM_BLOCK_EXOTIC_SUBDEPS_LINE = "blockExoticSubdeps: true"


BUN_MINIMUM_RELEASE_AGE_PATTERN = re.compile(
    r"^(\s*)minimumReleaseAge\s*=\s*.+$",
    re.MULTILINE,
)
BUN_INSTALL_HEADER_PATTERN = re.compile(r"^\[install\]\s*$", re.MULTILINE)
BUN_MINIMUM_RELEASE_AGE_EXCLUDES_PATTERN = re.compile(
    r"^(\s*)minimumReleaseAgeExcludes\s*=\s*.+$",
    re.MULTILINE,
)
PNPM_MINIMUM_RELEASE_AGE_PATTERN = re.compile(
    r"^(\s*)minimumReleaseAge\s*:\s*(.+)$",
    re.MULTILINE,
)
PNPM_BLOCK_EXOTIC_SUBDEPS_PATTERN = re.compile(
    r"^(\s*)blockExoticSubdeps\s*:\s*(.+)$",
    re.MULTILINE,
)
PNPM_MINIMUM_RELEASE_AGE_EXCLUDE_BLOCK_PATTERN = re.compile(
    r"^([ \t]*)minimumReleaseAgeExclude\s*:\s*\n((?:[ \t]*-[ \t]+.+\n)+)",
    re.MULTILINE,
)
NPM_MINIMUM_RELEASE_AGE_PATTERN = re.compile(
    r"^(\s*)min-release-age\s*=\s*(.+)$",
    re.MULTILINE,
)
NPM_MINIMUM_RELEASE_AGE_EXCLUDE_PATTERN = re.compile(
    r"^(\s*)min-release-age-exclude\[\]\s*=\s*(.+)$",
    re.MULTILINE,
)

ConfigUpdater = Callable[[str], str | None]


def _normalize_minimum_release_age_excludes(
    excludes: Sequence[str],
) -> tuple[str, ...]:
    normalized: list[str] = []
    for exclude in excludes:
        normalized_exclude = exclude.strip()
        if not normalized_exclude or "\r" in exclude or "\n" in exclude:
            msg = "Minimum release age exclusions must be non-empty single-line values"
            raise ValueError(msg)
        if normalized_exclude not in normalized:
            normalized.append(normalized_exclude)
    return tuple(normalized)


def _validate_minimum_release_age_excludes(excludes: list[str]) -> list[str]:
    try:
        return list(_normalize_minimum_release_age_excludes(excludes))
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error


class BunInstallConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    minimum_release_age: Any | None = Field(default=None, alias="minimumReleaseAge")
    minimum_release_age_excludes: Any | None = Field(
        default=None, alias="minimumReleaseAgeExcludes"
    )


class BunConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    install: BunInstallConfig | None = None


class PnpmWorkspaceConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    minimum_release_age: Any | None = Field(default=None, alias="minimumReleaseAge")
    minimum_release_age_exclude: Any | None = Field(
        default=None, alias="minimumReleaseAgeExclude"
    )
    block_exotic_subdeps: Any | None = Field(
        default=None,
        alias="blockExoticSubdeps",
    )


def _find_files_in_repo(root: Path, target_name: str) -> list[Path]:
    matches: list[Path] = []
    for directory, directory_names, filenames in os.walk(root):
        directory_names[:] = [name for name in directory_names if name != ".git"]
        if target_name in filenames:
            matches.append(Path(directory) / target_name)
    return matches


def _parse_bun_config(content: str) -> BunConfig:
    try:
        return BunConfig.model_validate(tomlkit.parse(content).unwrap())
    except (ParseError, ValidationError) as error:
        raise ValueError(f"Invalid bunfig.toml: {error}") from error


def _insert_bun_install_setting(
    content: str,
    setting_line: str,
    *,
    install: BunInstallConfig | None,
) -> str:
    install_header = BUN_INSTALL_HEADER_PATTERN.search(content)
    if install is not None and install_header is None:
        msg = "bunfig.toml has an [install] section in a form we cannot safely edit"
        raise ValueError(msg)

    insertion = f"{setting_line}\n"
    if install_header is None:
        if not content:
            return f"[install]\n{insertion}"
        separator = "" if content.endswith("\n") else "\n"
        return f"{content}{separator}\n[install]\n{insertion}"

    match_end = install_header.end()
    next_newline = content.find("\n", match_end)
    if next_newline == -1:
        return f"{content}\n{insertion}"

    insertion_point = next_newline + 1
    return content[:insertion_point] + insertion + content[insertion_point:]


def set_bun_minimum_release_age(
    content: str,
    *,
    minimum_release_age_days: int,
) -> str | None:
    minimum_release_age_seconds = minimum_release_age_days * 24 * 60 * 60
    setting_line = f"minimumReleaseAge = {minimum_release_age_seconds}"
    install = _parse_bun_config(content).install
    if install is not None and install.minimum_release_age is not None:
        if _is_number_at_least(
            install.minimum_release_age,
            minimum_release_age_seconds,
        ):
            return None
        if not BUN_MINIMUM_RELEASE_AGE_PATTERN.search(content):
            msg = "bunfig.toml has minimumReleaseAge in a form we cannot safely edit"
            raise ValueError(msg)
        return BUN_MINIMUM_RELEASE_AGE_PATTERN.sub(
            lambda match: f"{match.group(1)}{setting_line}",
            content,
            count=1,
        )

    return _insert_bun_install_setting(
        content,
        setting_line,
        install=install,
    )


def set_bun_minimum_release_age_excludes(
    content: str,
    *,
    excludes: Sequence[str],
) -> str | None:
    configured_excludes = _normalize_minimum_release_age_excludes(excludes)
    if not configured_excludes:
        return None

    install = _parse_bun_config(content).install
    if install is not None and install.minimum_release_age_excludes is not None:
        value = install.minimum_release_age_excludes
        if not isinstance(value, list) or not all(
            isinstance(entry, str) for entry in value
        ):
            msg = (
                "bunfig.toml has minimumReleaseAgeExcludes in a form "
                "we cannot safely edit"
            )
            raise ValueError(msg)

        required_excludes = set(configured_excludes)
        if required_excludes.issubset(set(value)):
            return None
        if not BUN_MINIMUM_RELEASE_AGE_EXCLUDES_PATTERN.search(content):
            msg = (
                "bunfig.toml has minimumReleaseAgeExcludes in a form "
                "we cannot safely edit"
            )
            raise ValueError(msg)
        missing = [entry for entry in configured_excludes if entry not in value]
        replacement = (
            "minimumReleaseAgeExcludes = ["
            + ", ".join(json.dumps(entry) for entry in value + missing)
            + "]"
        )
        return BUN_MINIMUM_RELEASE_AGE_EXCLUDES_PATTERN.sub(
            lambda match: f"{match.group(1)}{replacement}",
            content,
            count=1,
        )

    excludes_line = (
        "minimumReleaseAgeExcludes = ["
        + ", ".join(json.dumps(entry) for entry in configured_excludes)
        + "]"
    )
    return _insert_bun_install_setting(
        content,
        excludes_line,
        install=install,
    )


def _set_bun_minimum_release_age_excludes_if_age_can_be_enforced(
    content: str,
    *,
    excludes: Sequence[str],
    minimum_release_age_days: int,
) -> str | None:
    updated = set_bun_minimum_release_age_excludes(content, excludes=excludes)
    if updated is None:
        return None

    try:
        set_bun_minimum_release_age(
            content,
            minimum_release_age_days=minimum_release_age_days,
        )
    except ValueError:
        # The standalone age updater runs next and reports the unsafe form. Avoid
        # adding exemptions when it cannot first enforce the core cooldown.
        return None

    # Validate the prospective exclusion output too. If it cannot be parsed or
    # secured, surface that as an exclusion warning before the age-only pass.
    age_updated = set_bun_minimum_release_age(
        updated,
        minimum_release_age_days=minimum_release_age_days,
    )
    age_candidate = updated if age_updated is None else age_updated
    install = _parse_bun_config(age_candidate).install
    if install is None or not _is_number_at_least(
        install.minimum_release_age,
        minimum_release_age_days * 24 * 60 * 60,
    ):
        return None

    return updated


def set_pnpm_minimum_release_age(
    content: str,
    *,
    minimum_release_age_days: int,
) -> str | None:
    minimum_release_age_minutes = minimum_release_age_days * 24 * 60
    setting_line = f"minimumReleaseAge: {minimum_release_age_minutes}"
    parsed = _parse_pnpm_workspace_config(content)
    # could technically be null in YAML (even if that doesn't make much sense)
    if "minimum_release_age" in parsed.model_fields_set:
        value = parsed.minimum_release_age
        if _is_number_at_least(value, minimum_release_age_minutes):
            return None
        if not PNPM_MINIMUM_RELEASE_AGE_PATTERN.search(content):
            msg = (
                "pnpm-workspace.yaml has minimumReleaseAge in a form "
                "we cannot safely edit"
            )
            raise ValueError(msg)
        return PNPM_MINIMUM_RELEASE_AGE_PATTERN.sub(
            lambda match: f"{match.group(1)}{setting_line}",
            content,
            count=1,
        )

    separator = "" if not content or content.endswith("\n") else "\n"
    return f"{content}{separator}{setting_line}\n"


def set_pnpm_block_exotic_subdeps(content: str) -> str | None:
    parsed = _parse_pnpm_workspace_config(content)
    if "block_exotic_subdeps" in parsed.model_fields_set:
        value = parsed.block_exotic_subdeps
        if value is True:
            return None
        if not PNPM_BLOCK_EXOTIC_SUBDEPS_PATTERN.search(content):
            msg = (
                "pnpm-workspace.yaml has blockExoticSubdeps in a form "
                "we cannot safely edit"
            )
            raise ValueError(msg)
        return PNPM_BLOCK_EXOTIC_SUBDEPS_PATTERN.sub(
            lambda match: f"{match.group(1)}{PNPM_BLOCK_EXOTIC_SUBDEPS_LINE}",
            content,
            count=1,
        )

    separator = "" if not content or content.endswith("\n") else "\n"
    return f"{content}{separator}{PNPM_BLOCK_EXOTIC_SUBDEPS_LINE}\n"


def set_pnpm_minimum_release_age_excludes(
    content: str,
    *,
    excludes: Sequence[str],
) -> str | None:
    configured_excludes = _normalize_minimum_release_age_excludes(excludes)
    if not configured_excludes:
        return None

    parsed = _parse_pnpm_workspace_config(content)

    if "minimum_release_age_exclude" in parsed.model_fields_set:
        value = parsed.minimum_release_age_exclude
        if not isinstance(value, list):
            msg = (
                "pnpm-workspace.yaml has minimumReleaseAgeExclude in a form "
                "we cannot safely edit"
            )
            raise ValueError(msg)
        missing = [entry for entry in configured_excludes if entry not in value]
        if not missing:
            return None
        match = PNPM_MINIMUM_RELEASE_AGE_EXCLUDE_BLOCK_PATTERN.search(content)
        if match is None:
            msg = (
                "pnpm-workspace.yaml has minimumReleaseAgeExclude in a form "
                "we cannot safely edit"
            )
            raise ValueError(msg)
        first_item_line = match.group(2).splitlines()[0]
        list_indent = first_item_line[
            : len(first_item_line) - len(first_item_line.lstrip(" \t"))
        ]
        new_items = "".join(
            f"{list_indent}- {json.dumps(entry)}\n" for entry in missing
        )
        insert_at = match.end()
        return content[:insert_at] + new_items + content[insert_at:]

    separator = "" if not content or content.endswith("\n") else "\n"
    new_key = "minimumReleaseAgeExclude:\n" + "".join(
        f"- {json.dumps(entry)}\n" for entry in configured_excludes
    )
    return f"{content}{separator}{new_key}"


def set_npm_minimum_release_age(
    content: str,
    *,
    minimum_release_age_days: int,
) -> str | None:
    setting_line = f"min-release-age={minimum_release_age_days}"
    match = NPM_MINIMUM_RELEASE_AGE_PATTERN.search(content)
    if match is not None:
        try:
            value = int(match.group(2).strip())
        except ValueError as error:
            msg = ".npmrc has min-release-age in an invalid form"
            raise ValueError(msg) from error
        if value >= minimum_release_age_days:
            return None
        return NPM_MINIMUM_RELEASE_AGE_PATTERN.sub(
            lambda match: f"{match.group(1)}{setting_line}",
            content,
            count=1,
        )

    separator = "" if not content or content.endswith("\n") else "\n"
    return f"{content}{separator}{setting_line}\n"


def set_npm_minimum_release_age_excludes(
    content: str,
    *,
    excludes: Sequence[str],
) -> str | None:
    configured_excludes = _normalize_minimum_release_age_excludes(excludes)
    if not configured_excludes:
        return None

    existing_excludes = {
        match.group(2).strip()
        for match in NPM_MINIMUM_RELEASE_AGE_EXCLUDE_PATTERN.finditer(content)
    }
    missing = [entry for entry in configured_excludes if entry not in existing_excludes]
    if not missing:
        return None

    separator = "" if not content or content.endswith("\n") else "\n"
    new_lines = "".join(f"min-release-age-exclude[]={entry}\n" for entry in missing)
    return f"{content}{separator}{new_lines}"


def _parse_pnpm_workspace_config(content: str) -> PnpmWorkspaceConfig:
    try:
        parsed: object = yaml.safe_load(content)
        if parsed is None:
            return PnpmWorkspaceConfig()
        return PnpmWorkspaceConfig.model_validate(parsed)
    except (yaml.YAMLError, ValidationError) as error:
        raise ValueError(f"Invalid pnpm-workspace.yaml: {error}") from error


def _is_number_at_least(value: object, threshold: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= threshold


def _config_updaters(
    *,
    minimum_release_age_days: int,
    bun_minimum_release_age_excludes: Sequence[str],
    minimum_release_age_excludes: Sequence[str],
) -> tuple[tuple[str, str, ConfigUpdater], ...]:
    updaters: list[tuple[str, str, ConfigUpdater]] = []
    # Bun settings are inserted directly below [install]. Apply the guarded exclusion
    # first so the release age remains above it in the resulting file.
    if bun_minimum_release_age_excludes:
        updaters.append(
            (
                BUN_CONFIG_FILE,
                BUN_LOCKFILE,
                partial(
                    _set_bun_minimum_release_age_excludes_if_age_can_be_enforced,
                    excludes=bun_minimum_release_age_excludes,
                    minimum_release_age_days=minimum_release_age_days,
                ),
            )
        )
    updaters.extend(
        (
            (
                BUN_CONFIG_FILE,
                BUN_LOCKFILE,
                partial(
                    set_bun_minimum_release_age,
                    minimum_release_age_days=minimum_release_age_days,
                ),
            ),
            (
                PNPM_CONFIG_FILE,
                PNPM_LOCKFILE,
                partial(
                    set_pnpm_minimum_release_age,
                    minimum_release_age_days=minimum_release_age_days,
                ),
            ),
        )
    )
    if minimum_release_age_excludes:
        updaters.append(
            (
                PNPM_CONFIG_FILE,
                PNPM_LOCKFILE,
                partial(
                    set_pnpm_minimum_release_age_excludes,
                    excludes=minimum_release_age_excludes,
                ),
            )
        )
    updaters.extend(
        (
            (PNPM_CONFIG_FILE, PNPM_LOCKFILE, set_pnpm_block_exotic_subdeps),
            (
                NPM_CONFIG_FILE,
                NPM_LOCKFILE,
                partial(
                    set_npm_minimum_release_age,
                    minimum_release_age_days=minimum_release_age_days,
                ),
            ),
        )
    )
    if minimum_release_age_excludes:
        updaters.append(
            (
                NPM_CONFIG_FILE,
                NPM_LOCKFILE,
                partial(
                    set_npm_minimum_release_age_excludes,
                    excludes=minimum_release_age_excludes,
                ),
            )
        )
    return tuple(updaters)


class NodeDependencyCooldownOptions(UpdateOptions):
    minimum_release_age_days: Annotated[
        int,
        typer.Option(
            "--minimum-release-age-days",
            min=1,
            help="Minimum package release age to enforce, in whole days.",
        ),
    ] = Field(default=DEFAULT_MINIMUM_RELEASE_AGE_DAYS, ge=1)
    # Bun does not support wildcard minimumReleaseAgeExcludes yet, so it needs a
    # separate option for exact package names:
    # https://github.com/oven-sh/bun/issues/23689
    bun_minimum_release_age_excludes: Annotated[
        list[str],
        typer.Option(
            "--bun-minimum-release-age-exclude",
            callback=_validate_minimum_release_age_excludes,
            help=(
                "Package name to exempt from Bun minimum release age checks. "
                "Repeat for multiple packages; existing exclusions are preserved."
            ),
        ),
    ] = Field(default_factory=list)
    minimum_release_age_excludes: Annotated[
        list[str],
        typer.Option(
            "--minimum-release-age-exclude",
            callback=_validate_minimum_release_age_excludes,
            help=(
                "Package name or pattern to exempt from pnpm and npm minimum "
                "release age checks. Repeat for multiple values; existing "
                "exclusions are preserved."
            ),
        ),
    ] = Field(default_factory=list)


class NodeDependencyCooldownTask(
    UpdateTask[UpdateItem, UpdateOutput, NodeDependencyCooldownOptions]
):
    @override
    def run(self) -> UpdateOutcome:
        self.context.logger.debug("Running Node dependency cooldown update task.")

        for config_name, lockfile_name, updater in _config_updaters(
            minimum_release_age_days=self.options.minimum_release_age_days,
            bun_minimum_release_age_excludes=(
                self.options.bun_minimum_release_age_excludes
            ),
            minimum_release_age_excludes=self.options.minimum_release_age_excludes,
        ):
            lockfile_paths = _find_files_in_repo(
                self.checkout.absolute_path,
                lockfile_name,
            )
            for lockfile_path in lockfile_paths:
                self._update_config_for_lockfile(
                    lockfile_path,
                    config_name,
                    updater,
                )

        if self.checkout.is_clean():
            self.context.logger.debug(
                "No changes needed; minimumReleaseAge already set."
            )
            return UpdateOutcome(result=Status.UP_TO_DATE)

        pull_request_template = (
            self.context.site_config.pull_request_templates.node_dependency_cooldown
        )
        pull_request = self.context.github_client.create_pull_request(
            self.checkout,
            PullRequestOptions(
                title=pull_request_template.title,
                body=pull_request_template.body,
                source_branch=pull_request_template.branch_prefix,
                target_branch=self.checkout.repository_ref.branch,
                quant_ranger_id=NodeDependencyCooldownUpdater.name,
            ),
            self.context.logger,
        )

        return UpdateOutcome(
            result=Status.UPDATED if pull_request.updated else Status.SKIPPED,
            pull_request_number=pull_request.number,
        )

    def _update_config_for_lockfile(
        self,
        lockfile_path: Path,
        config_name: str,
        updater: ConfigUpdater,
    ) -> None:
        config_path = lockfile_path.parent / config_name
        relative_config_path = config_path.relative_to(self.checkout.absolute_path)

        existing = ""
        config_exists = True
        try:
            existing = config_path.read_text()
        except FileNotFoundError:
            config_exists = False
        except OSError as error:
            msg = f"Could not read {relative_config_path}: {error}"
            raise RuntimeError(msg) from error

        try:
            updated = updater(existing)
        except ValueError as error:
            self.context.logger.warning(
                f"Could not update {relative_config_path}: {error}"
            )
            return

        if updated is None:
            return

        config_path.write_text(updated)
        self.checkout.add(relative_config_path)

        verb = "Updated" if config_exists else "Created config and updated"
        self.context.logger.debug(f"{verb} {relative_config_path}")


class NodeDependencyCooldownUpdater(
    Updater[UpdateItem, UpdateOutput, NodeDependencyCooldownOptions]
):
    name = "node-dependency-cooldown"
    description = (
        "Configure Node dependency cooldowns. Adds release-age protections for "
        "Bun, pnpm, and npm."
    )
    scanner = RepositoryFileScanner(
        filename_pattern=NODE_LOCKFILE_PATTERN,
        missing_message="No supported Node package manager lockfile found",
    )
    task_type = NodeDependencyCooldownTask
