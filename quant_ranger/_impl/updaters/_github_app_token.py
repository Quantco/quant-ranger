import os
import re
from pathlib import Path
from typing import Annotated, override

import typer
import yaml
from packaging.version import Version
from yaml.tokens import AliasToken

from quant_ranger._impl.github import PullRequestOptions
from quant_ranger._impl.models import (
    Status,
    UpdateItem,
    UpdateOptions,
    UpdateOutcome,
    UpdateOutput,
)
from quant_ranger._impl.scanners import RepositoriesScanner

from ._base import Updater, UpdateTask

DEFAULT_GITHUB_APP_TOKEN_ACTION = "actions/create-github-app-token"
_MINIMUM_CLIENT_ID_VERSION = Version("3.1")
_COMMIT_SHA_PATTERN = re.compile(r"[0-9a-fA-F]{40}")
_PINNED_VERSION_COMMENT_PATTERN = re.compile(
    r"\s+#\s*"
    r"(?P<version>v(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*)){0,2})"
    r"\s*"
)


class GitHubAppTokenOptions(UpdateOptions):
    action: Annotated[
        str,
        typer.Option(
            "--action",
            help=(
                "Action identifier without `@revision`. Renames `app-id` only "
                "in full-SHA-pinned steps whose version comment is v3.1 or "
                "later within v3."
            ),
        ),
    ] = DEFAULT_GITHUB_APP_TOKEN_ACTION


def rename_app_id_inputs(content: str, action: str) -> str:
    """Rename the `app-id` input to `client-id` in steps using `action`.

    The YAML is parsed only to locate the `app-id` keys of `with:` blocks in
    steps using the action; the renames are then applied as in-place text
    edits, so formatting and comments are preserved. Raises `ValueError` for
    invalid YAML.
    """
    try:
        document = yaml.compose(content)
        has_aliases = any(isinstance(token, AliasToken) for token in yaml.scan(content))
    except yaml.YAMLError as error:
        raise ValueError(f"Invalid workflow YAML: {error}") from error
    if has_aliases:
        raise ValueError("YAML aliases are not supported")
    if document is None:
        return content

    key_nodes = sorted(
        _find_app_id_key_nodes(document, content, action),
        key=lambda node: node.start_mark.index,
        reverse=True,
    )
    for node in key_nodes:
        start, end = node.start_mark.index, node.end_mark.index
        replacement = content[start:end].replace("app-id", "client-id")
        if replacement == content[start:end]:
            raise ValueError("app-id input uses an unsupported YAML representation")
        content = content[:start] + replacement + content[end:]
    return content


def _find_app_id_key_nodes(
    node: yaml.Node,
    content: str,
    action: str,
) -> list[yaml.ScalarNode]:
    """Collect `app-id` key nodes from matching steps, recursively."""
    # A sequence (e.g. `steps:`) holds no keys itself; recurse into its items.
    if isinstance(node, yaml.SequenceNode):
        key_nodes: list[yaml.ScalarNode] = []
        for child in node.value:
            key_nodes.extend(_find_app_id_key_nodes(child, content, action))
        return key_nodes
    # A scalar is a leaf; notably a whole `run: |` script is one opaque
    # scalar, so text that merely looks like a step is never matched.
    if not isinstance(node, yaml.MappingNode):
        return []

    # A mapping's value is a list of (key, value) node pairs. A step using
    # the action is a mapping with a matching `uses` scalar and a `with`
    # mapping; collect the `app-id` key nodes of that `with` block.
    key_nodes = []
    entries = {
        key.value: value
        for key, value in node.value
        if isinstance(key, yaml.ScalarNode)
    }
    uses, with_node = entries.get("uses"), entries.get("with")
    if (
        isinstance(uses, yaml.ScalarNode)
        and _uses_supported_action_revision(uses, content, action)
        and isinstance(with_node, yaml.MappingNode)
    ):
        app_id_keys = [
            key
            for key, _ in with_node.value
            if isinstance(key, yaml.ScalarNode) and key.value == "app-id"
        ]
        client_id_keys = [
            key
            for key, _ in with_node.value
            if isinstance(key, yaml.ScalarNode) and key.value == "client-id"
        ]
        if len(app_id_keys) > 1 or len(client_id_keys) > 1:
            raise ValueError("Duplicate app-id or client-id inputs are not supported")
        if app_id_keys and client_id_keys:
            raise ValueError("Renaming app-id would create a duplicate client-id input")
        if app_id_keys:
            key_nodes.extend(app_id_keys)

    # Steps are nested arbitrarily deep (document -> jobs -> job -> steps).
    for _, value in node.value:
        key_nodes.extend(_find_app_id_key_nodes(value, content, action))
    return key_nodes


def _uses_supported_action_revision(
    uses: yaml.ScalarNode,
    content: str,
    action: str,
) -> bool:
    prefix = f"{action}@"
    if not uses.value.startswith(prefix):
        return False
    ref = uses.value.removeprefix(prefix)
    if _COMMIT_SHA_PATTERN.fullmatch(ref) is None:
        raise ValueError(f"{action} must be pinned to a full commit SHA")

    version_comment = _pinned_version_comment(content, uses)
    if version_comment is None:
        raise ValueError(f"{action}@{ref} must have a version comment")
    version = Version(version_comment)
    return version.major == 3 and version >= _MINIMUM_CLIENT_ID_VERSION


def _pinned_version_comment(content: str, uses: yaml.ScalarNode) -> str | None:
    line_suffix = content[uses.end_mark.index :].partition("\n")[0]
    match = _PINNED_VERSION_COMMENT_PATTERN.fullmatch(line_suffix.rstrip("\r"))
    if match is None:
        return None
    return match.group("version")


class GitHubAppTokenUpdateTask(
    UpdateTask[UpdateItem, UpdateOutput, GitHubAppTokenOptions]
):
    @override
    def run(self) -> UpdateOutcome:
        candidate_files = self._find_candidate_files()
        if not candidate_files:
            self.context.logger.debug("No workflow or action files found")
            return UpdateOutcome(result=Status.UP_TO_DATE)
        updated_files = self._update_files(candidate_files)
        if not updated_files:
            self.context.logger.debug("All workflow and action files are up-to-date")
            return UpdateOutcome(result=Status.UP_TO_DATE)
        self.checkout.add_all()

        pull_request_template = (
            self.context.site_config.pull_request_templates.github_app_token
        )
        pull_request = self.context.github_client.create_pull_request(
            self.checkout,
            PullRequestOptions(
                title=pull_request_template.title,
                body=pull_request_template.body,
                source_branch=pull_request_template.branch_prefix,
                target_branch=self.checkout.repository_ref.branch,
                quant_ranger_id=GitHubAppTokenUpdater.name,
            ),
            self.context.logger,
        )

        return UpdateOutcome(
            result=Status.UPDATED if pull_request.updated else Status.SKIPPED,
            pull_request_number=pull_request.number,
        )

    def _find_candidate_files(self) -> list[Path]:
        """Find YAML files under `.github` and composite action metadata files.

        Action files (`action.yml`/`action.yaml`) can live in any directory:
        at the repository root for action repositories, or nested for local
        composite actions.
        """
        root = self.checkout.absolute_path
        github_dir = root / ".github"
        candidates = {
            entry
            for suffix in ("yml", "yaml")
            for entry in github_dir.rglob(f"*.{suffix}")
            if entry.is_file()
        }

        for directory, directory_names, filenames in os.walk(root):
            directory_names[:] = [name for name in directory_names if name != ".git"]
            for action_file in ("action.yml", "action.yaml"):
                if action_file in filenames:
                    candidates.add(Path(directory) / action_file)

        return sorted(candidates)

    def _update_files(self, candidate_files: list[Path]) -> list[Path]:
        updated_files: list[Path] = []
        for candidate_file in candidate_files:
            relative_path = candidate_file.relative_to(self.checkout.absolute_path)
            content = candidate_file.read_text()
            try:
                updated_content = rename_app_id_inputs(content, self.options.action)
            except ValueError as error:
                raise ValueError(f"{relative_path}: {error}") from error
            if updated_content != content:
                candidate_file.write_text(updated_content)
                updated_files.append(candidate_file)

        return updated_files


class GitHubAppTokenUpdater(Updater[UpdateItem, UpdateOutput, GitHubAppTokenOptions]):
    name = "github-app-token"
    description = (
        "Migrate GitHub App token inputs. Renames `app-id` to `client-id` in "
        "eligible SHA-pinned v3 steps."
    )
    scanner = RepositoriesScanner()
    task_type = GitHubAppTokenUpdateTask
