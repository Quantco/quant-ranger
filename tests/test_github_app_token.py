from dataclasses import dataclass, replace
from pathlib import Path
from textwrap import dedent
from typing import cast

import pytest

from quant_ranger._impl.github import GitHubClient
from quant_ranger._impl.models import (
    RepositoryRef,
    Status,
    UpdateItem,
    UpdateOutcome,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.testing import (
    FakeGitHubClient,
    RecordingCheckout,
    RecordingLogger,
)
from quant_ranger._impl.updaters._github_app_token import (
    DEFAULT_GITHUB_APP_TOKEN_ACTION,
    GitHubAppTokenOptions,
    GitHubAppTokenUpdateTask,
    rename_app_id_inputs,
)
from quant_ranger.site_config import DEFAULT_PULL_REQUEST_TEMPLATES, SiteConfig

DEFAULT_ACTION = DEFAULT_GITHUB_APP_TOKEN_ACTION
PINNED_REVISION = "7bd03711494f032dfa3be3558f7dc8787b0be333"
PINNED_ACTION = f"{DEFAULT_ACTION}@{PINNED_REVISION} # v3.1.0"

APP_TOKEN_WORKFLOW = (
    dedent(
        """
    jobs:
      example:
        runs-on: ubuntu-latest
        steps:
          - name: Generate token
            id: app-token
            uses: actions/create-github-app-token@v3
            with:
              app-id: ${{ secrets.APP_ID }}
              private-key: ${{ secrets.APP_PRIVATE_KEY }}
          - uses: actions/checkout@v6
            with:
              token: ${{ steps.app-token.outputs.token }}
    """
    )
    .lstrip()
    .replace(f"{DEFAULT_ACTION}@v3", PINNED_ACTION)
)

MIGRATED_APP_TOKEN_WORKFLOW = APP_TOKEN_WORKFLOW.replace(
    "app-id: ${{ secrets.APP_ID }}",
    "client-id: ${{ secrets.APP_ID }}",
)


def test_rename_app_id_inputs_renames_app_token_step() -> None:
    assert (
        rename_app_id_inputs(APP_TOKEN_WORKFLOW, DEFAULT_ACTION)
        == MIGRATED_APP_TOKEN_WORKFLOW
    )


def test_rename_app_id_inputs_matches_configured_action() -> None:
    content = APP_TOKEN_WORKFLOW.replace(DEFAULT_ACTION, "corp/app-token-fork")

    assert rename_app_id_inputs(content, DEFAULT_ACTION) == content
    assert "client-id: ${{ secrets.APP_ID }}" in rename_app_id_inputs(
        content, "corp/app-token-fork"
    )


@pytest.mark.parametrize(
    ("revision", "message"),
    [
        ("v3", "full commit SHA"),
        (PINNED_REVISION, "version comment"),
    ],
)
def test_rename_app_id_inputs_requires_commit_pin_and_version_comment(
    revision: str,
    message: str,
) -> None:
    content = APP_TOKEN_WORKFLOW.replace(
        PINNED_ACTION,
        f"{DEFAULT_ACTION}@{revision}",
    )

    with pytest.raises(ValueError, match=message):
        rename_app_id_inputs(content, DEFAULT_ACTION)


def test_rename_app_id_inputs_skips_unsupported_version() -> None:
    content = APP_TOKEN_WORKFLOW.replace("# v3.1.0", "# v3.0.0")

    assert rename_app_id_inputs(content, DEFAULT_ACTION) == content


def test_rename_app_id_inputs_rejects_uneditable_key() -> None:
    content = (
        f'steps:\n  - uses: {PINNED_ACTION}\n    with: {{"app\\u002did": value}}\n'
    )

    with pytest.raises(ValueError, match="unsupported YAML representation"):
        rename_app_id_inputs(content, DEFAULT_ACTION)


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(
            dedent(
                """
                steps:
                  - uses: actions/create-github-app-token-fork@v3
                    with:
                      app-id: keep-me
                """
            ).lstrip(),
            id="similar-action-name",
        ),
        pytest.param(
            dedent(
                """
                steps:
                  - name: Write example workflow
                    run: |
                      cat > workflow.yml <<'EOF'
                      uses: actions/create-github-app-token@v3
                      with:
                        app-id: ${{ secrets.APP_ID }}
                      EOF
                """
            ).lstrip(),
            id="run-script",
        ),
        pytest.param("# only a comment\n", id="empty-document"),
    ],
)
def test_rename_app_id_inputs_keeps_non_matching_content_unchanged(
    content: str,
) -> None:
    assert rename_app_id_inputs(content, DEFAULT_ACTION) == content


def test_rename_app_id_inputs_only_touches_with_block() -> None:
    content = (
        dedent(
            """
        steps:
          - uses: actions/create-github-app-token@v3
            env:
              app-id: keep-me
            with:
              app-id: ${{ secrets.APP_ID }}
        """
        )
        .lstrip()
        .replace(f"{DEFAULT_ACTION}@v3", PINNED_ACTION)
    )

    updated = rename_app_id_inputs(content, DEFAULT_ACTION)

    assert "client-id: ${{ secrets.APP_ID }}" in updated
    assert "app-id: keep-me" in updated


def test_rename_app_id_inputs_preserves_comments_and_quoting() -> None:
    content = (
        dedent(
            """
        steps:
          # Generate an installation token.
          - uses: 'actions/create-github-app-token@v3'
            with:
              app-id: ${{ secrets.APP_ID }}  # the App ID
        """
        )
        .lstrip()
        .replace(
            f"'{DEFAULT_ACTION}@v3'",
            f"'{DEFAULT_ACTION}@{PINNED_REVISION}' # v3.1.0",
        )
    )

    updated = rename_app_id_inputs(content, DEFAULT_ACTION)

    assert updated == content.replace("app-id:", "client-id:")


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        (
            "{client-id: preferred, app-id: fallback}",
            "would create a duplicate client-id",
        ),
        (
            "{app-id: first, app-id: second}",
            "Duplicate app-id or client-id",
        ),
    ],
)
def test_rename_app_id_inputs_rejects_duplicate_or_conflicting_inputs(
    inputs: str,
    message: str,
) -> None:
    content = f"steps:\n  - uses: {PINNED_ACTION}\n    with: {inputs}\n"

    with pytest.raises(ValueError, match=message):
        rename_app_id_inputs(content, DEFAULT_ACTION)


def test_rename_app_id_inputs_rejects_files_with_aliases() -> None:
    content = (
        "shared: &shared {value: shared}\n"
        "copy: *shared\n"
        "steps:\n"
        f"  - uses: {PINNED_ACTION}\n"
        "    with: {app-id: independent}\n"
    )

    with pytest.raises(ValueError, match="YAML aliases are not supported"):
        rename_app_id_inputs(content, DEFAULT_ACTION)


def test_rename_app_id_inputs_rejects_invalid_yaml() -> None:
    with pytest.raises(ValueError, match="Invalid workflow YAML"):
        rename_app_id_inputs("steps:\n  - uses: [unclosed\n", DEFAULT_ACTION)


def test_github_app_token_includes_file_path_in_invalid_yaml_error(
    tmp_path: Path,
) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "broken.yml").write_text("steps:\n  - uses: [unclosed\n")

    with pytest.raises(ValueError, match=r".github/workflows/broken\.yml"):
        run_update_task(tmp_path)


def test_github_app_token_updates_yaml_under_dot_github_and_opens_pull_request(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / ".github" / "config" / "token.yaml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(APP_TOKEN_WORKFLOW)
    pull_request_template = replace(
        DEFAULT_PULL_REQUEST_TEMPLATES.github_app_token,
        branch_prefix="migrate-app-token-client-id",
    )

    task_run = run_update_task(
        tmp_path,
        site_config=SiteConfig(
            pull_request_templates=replace(
                DEFAULT_PULL_REQUEST_TEMPLATES,
                github_app_token=pull_request_template,
            )
        ),
    )

    assert task_run.outcome.result == Status.UPDATED
    assert config_file.read_text() == MIGRATED_APP_TOKEN_WORKFLOW
    assert task_run.checkout.add_all_count == 1
    [pull_request_call] = task_run.github_client.pull_request_calls
    options = pull_request_call["options"]
    assert options.title == pull_request_template.title
    assert options.body == pull_request_template.body
    assert options.source_branch == "migrate-app-token-client-id"
    assert options.quant_ranger_id == "github-app-token"


def test_github_app_token_is_up_to_date_when_workflows_already_migrated(
    tmp_path: Path,
) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "release.yml").write_text(MIGRATED_APP_TOKEN_WORKFLOW)

    task_run = run_update_task(tmp_path)

    assert task_run.outcome.result == Status.UP_TO_DATE
    assert task_run.checkout.add_all_count == 0
    assert not task_run.github_client.pull_request_calls


def test_github_app_token_is_up_to_date_without_candidate_files(
    tmp_path: Path,
) -> None:
    task_run = run_update_task(tmp_path)

    assert task_run.outcome.result == Status.UP_TO_DATE
    assert task_run.logger.debug_messages == ["No workflow or action files found"]
    assert not task_run.github_client.pull_request_calls


def test_github_app_token_updates_root_action_file_and_ignores_dot_git(
    tmp_path: Path,
) -> None:
    action = (
        dedent(
            """
        runs:
          using: composite
          steps:
            - uses: actions/create-github-app-token@v3
              with:
                app-id: ${{ inputs.app-id }}
        """
        )
        .lstrip()
        .replace(f"{DEFAULT_ACTION}@v3", PINNED_ACTION)
    )
    (tmp_path / "action.yml").write_text(action)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "action.yml").write_text(action)

    task_run = run_update_task(tmp_path)

    assert task_run.outcome.result == Status.UPDATED
    assert "client-id: ${{ inputs.app-id }}" in (tmp_path / "action.yml").read_text()
    assert (tmp_path / ".git" / "action.yml").read_text() == action


def test_github_app_token_skips_when_pull_request_is_not_created(
    tmp_path: Path,
) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "release.yml").write_text(APP_TOKEN_WORKFLOW)

    task_run = run_update_task(
        tmp_path,
        github_client=FakeGitHubClient(pr_opened=False),
    )

    assert task_run.outcome.result == Status.SKIPPED
    assert task_run.github_client.pull_request_calls


@dataclass
class TaskRun:
    outcome: UpdateOutcome
    checkout: RecordingCheckout
    github_client: FakeGitHubClient
    logger: RecordingLogger


def run_update_task(
    tmp_path: Path,
    *,
    github_client: FakeGitHubClient | None = None,
    site_config: SiteConfig | None = None,
) -> TaskRun:
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")
    checkout = RecordingCheckout(tmp_path, repository_ref)
    github_client = github_client or FakeGitHubClient()
    logger = RecordingLogger()

    outcome = GitHubAppTokenUpdateTask(
        checkout,
        RunContext(
            github_client=cast(GitHubClient, github_client),
            site_config=site_config or SiteConfig(),
            logger=logger,
        ),
        item=UpdateItem(repository_ref=repository_ref),
        options=GitHubAppTokenOptions(),
    ).run()

    return TaskRun(outcome, checkout, github_client, logger)
