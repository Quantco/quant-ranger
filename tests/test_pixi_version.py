from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
import tomlkit
from pydantic import ValidationError
from tomlkit.exceptions import ParseError

from quant_ranger._impl.github import GitHubClient, PullRequestOptions
from quant_ranger._impl.logger import LogLevel
from quant_ranger._impl.models import (
    RepositoryRef,
    Schedule,
    Status,
    UpdateOutcome,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.testing import (
    FakeGitHubClient,
    RecordingCheckout,
    RecordingLogger,
)
from quant_ranger._impl.updaters import PixiVersionUpdater
from quant_ranger._impl.updaters._pixi_version import (
    PixiTomlConfig,
    PixiVersionItem,
    PixiVersionOptions,
    PixiVersionUpdaterConfig,
)
from quant_ranger.site_config import SiteConfig

LATEST_PIXI_VERSION = "v0.70.0"
OUTDATED_WORKFLOW = """
steps:
  - uses: prefix-dev/setup-pixi@v0.9.1
    with:
      pixi-version: v0.69.0
"""
NESTED_OUTDATED_WORKFLOW = """
jobs:
  test:
    steps:
      - uses: prefix-dev/setup-pixi@v0.9.1
        with:
          pixi-version: "v0.69.0"
"""
IRRELEVANT_WORKFLOW = """
steps:
  - uses: actions/checkout@v4
"""
CURRENT_WORKFLOW = """
steps:
  - uses: prefix-dev/setup-pixi@v0.9.1
    with:
      pixi-version: v0.70.0
"""


def _pixi_version_updater() -> PixiVersionUpdater:
    return PixiVersionUpdater(
        PixiVersionOptions(setup_pixi_marker="prefix-dev/setup-pixi")
    )


def parse_config(contents: str) -> PixiVersionUpdaterConfig:
    try:
        parsed = tomlkit.parse(contents).unwrap()
        return PixiTomlConfig.model_validate(parsed).tool.pixi_version_updater
    except (ValidationError, ParseError) as error:
        raise ValueError(f"Invalid pixi.toml: {error}") from error


def test_parse_config_uses_defaults_without_section() -> None:
    config = parse_config("")

    assert config.autoupdate_branch == "pixi-version-autoupdate"
    assert config.autoupdate_commit_message == "chore: Update pixi version"
    assert config.autoupdate_schedule == "monthly"
    assert config.autoupdate_pull_request_labels == ["dependencies"]


def test_parse_config_rejects_invalid_toml() -> None:
    with pytest.raises(ValueError, match="Invalid pixi.toml"):
        parse_config("[")


def test_parse_config_accepts_toml_1_1_multiline_inline_tables() -> None:
    config = parse_config(
        """
        #:tombi toml-version = "v1.1.0"

        [feature.integration.tasks]
        backend-dev = {
          cmd = "uvicorn intake_ai.main:app",
          env = { INTAKE_GUEST_AUTH_ENABLED = "true" },
        }

        [tool.pixi-version-updater]
        autoupdate-branch = "pixi-updates"
        """
    )

    assert config.autoupdate_branch == "pixi-updates"


def test_parse_config_reads_pixi_version_updater_section() -> None:
    config = parse_config(
        """
        [tool.pixi-version-updater]
        autoupdate-branch = "pixi-updates"
        autoupdate-commit-message = "chore: Bump pixi"
        autoupdate-schedule = "weekly"
        autoupdate-pull-request-labels = ["dependencies", "pixi"]
        """
    )

    assert config.autoupdate_branch == "pixi-updates"
    assert config.autoupdate_commit_message == "chore: Bump pixi"
    assert config.autoupdate_schedule == "weekly"
    assert config.autoupdate_pull_request_labels == ["dependencies", "pixi"]


@pytest.mark.parametrize(
    ("schedule", "expected"),
    [
        ("quarterly", Schedule.QUARTERLY),
        ("never", "never"),
    ],
)
def test_parse_config_reads_schedule(
    schedule: str,
    expected: Schedule | str,
) -> None:
    config = parse_config(
        f"""
        [tool.pixi-version-updater]
        autoupdate-schedule = "{schedule}"
        """
    )

    assert config.autoupdate_schedule == expected


def test_pixi_version_update_creates_pull_request_for_changed_workflows(
    tmp_path: Path,
) -> None:
    write_config(
        tmp_path,
        """
        autoupdate-branch = "pixi-updates"
        autoupdate-commit-message = "chore: Bump pixi"
        autoupdate-pull-request-labels = ["dependencies", "pixi"]
        """,
    )
    workflow = write_workflow(
        tmp_path,
        NESTED_OUTDATED_WORKFLOW,
    )
    updater = _pixi_version_updater()
    github_client = FakeGitHubClient()
    task_run = run_update_task(
        tmp_path,
        branch="release",
        publish_changes=False,
        updater=updater,
        github_client=github_client,
    )
    # A second task from the same updater reuses the resolved version.
    second_run = run_update_task(
        tmp_path,
        branch="release",
        publish_changes=False,
        updater=updater,
        github_client=github_client,
    )

    assert task_run.outcome.result == Status.UPDATED
    assert second_run.outcome.result == Status.UP_TO_DATE
    assert "pixi-version: v0.70.0" in workflow.read_text()
    assert github_client.latest_release_calls == [("prefix-dev", "pixi")]
    assert task_run.checkout.add_all_count == 1
    assert len(task_run.github_client.pull_request_calls) == 1
    call = task_run.github_client.pull_request_calls[0]
    assert call["checkout"] is task_run.checkout
    assert call["options"] == PullRequestOptions(
        title="chore: Bump pixi",
        body="Update to [pixi v0.70.0](https://github.com/prefix-dev/pixi/releases/tag/v0.70.0)",
        source_branch="pixi-updates",
        target_branch="release",
        labels=["dependencies", "pixi"],
        quant_ranger_id="pixi-version",
    )
    assert call["publish_changes"] is False


def test_pixi_version_update_uses_pixi_version_option(
    tmp_path: Path,
) -> None:
    workflow = write_workflow(tmp_path)

    task_run = run_update_task(
        tmp_path,
        options=PixiVersionOptions(
            pixi_version="v0.71.0", setup_pixi_marker="prefix-dev/setup-pixi"
        ),
    )

    assert task_run.outcome.result == Status.UPDATED
    assert "pixi-version: v0.71.0" in workflow.read_text()
    assert task_run.github_client.latest_release_calls == []
    assert task_run.github_client.pull_request_calls[0]["options"].body == (
        "Update to [pixi v0.71.0](https://github.com/prefix-dev/pixi/releases/tag/v0.71.0)"
    )


def test_pixi_version_update_uses_setup_pixi_marker_option(
    tmp_path: Path,
) -> None:
    workflow = write_workflow(
        tmp_path,
        OUTDATED_WORKFLOW.replace("prefix-dev/setup-pixi", "quantco/setup-pixi-fork"),
    )

    up_to_date_run = run_update_task(tmp_path)
    task_run = run_update_task(
        tmp_path,
        options=PixiVersionOptions(setup_pixi_marker="quantco/setup-pixi-fork"),
    )

    assert up_to_date_run.outcome.result == Status.UP_TO_DATE
    assert task_run.outcome.result == Status.UPDATED
    assert "pixi-version: v0.70.0" in workflow.read_text()


def test_pixi_version_update_skips_when_pull_request_was_not_created(
    tmp_path: Path,
) -> None:
    write_workflow(tmp_path)

    task_run = run_update_task(
        tmp_path,
        github_client=FakeGitHubClient(pr_opened=False),
    )

    assert task_run.outcome.result == Status.SKIPPED


def test_pixi_version_update_returns_up_to_date_without_workflow_dir(
    tmp_path: Path,
) -> None:
    task_run = run_update_task(tmp_path)

    assert task_run.outcome.result == Status.UP_TO_DATE
    assert task_run.logger.logged(
        LogLevel.DEBUG, "No .github/workflows directory found"
    )
    assert task_run.logger.logged(LogLevel.DEBUG, "All workflow files are up-to-date")


def test_pixi_version_update_ignores_irrelevant_and_current_workflows(
    tmp_path: Path,
) -> None:
    write_workflow(
        tmp_path,
        IRRELEVANT_WORKFLOW,
        name="docs.yml",
    )
    write_workflow(
        tmp_path,
        CURRENT_WORKFLOW,
    )

    task_run = run_update_task(tmp_path)

    assert task_run.outcome.result == Status.UP_TO_DATE


def test_pixi_repository_scanner_only_emits_items_for_repositories_with_lockfiles() -> (
    None
):
    repositories = [
        RepositoryRef(owner="quantco", name="with-lockfile", branch="main"),
        RepositoryRef(owner="quantco", name="without-lockfile", branch="main"),
    ]
    logger = RecordingLogger()

    items = _pixi_version_updater().scanner.scan_all(
        repositories,
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(
                GitHubClient,
                FakeGitHubClient(
                    files={
                        "quantco/with-lockfile": ["pixi.lock"],
                        "quantco/without-lockfile": [],
                    }
                ),
            ),
            logger=logger,
        ),
    )

    assert items.update_items == (
        PixiVersionItem(
            repository_ref=repositories[0],
            config=PixiVersionUpdaterConfig(),
        ),
    )
    assert logger.logged(LogLevel.INFO, "Generated 1 update item.")


def test_pixi_repository_scanner_logs_missing_lockfiles_at_debug_level() -> None:
    repository = RepositoryRef(owner="quantco", name="without-lockfile", branch="main")
    logger = RecordingLogger()

    items = _pixi_version_updater().scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(
                GitHubClient,
                FakeGitHubClient(files={"quantco/without-lockfile": []}),
            ),
            logger=logger,
        ),
    )

    assert items.update_items == ()
    assert logger.logged(
        LogLevel.DEBUG, "[quantco/without-lockfile@main] No pixi.lock file found."
    )


def test_pixi_repository_scanner_filters_schedule_mismatches() -> None:
    repository = RepositoryRef(owner="quantco", name="with-lockfile", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        files={"quantco/with-lockfile": ["pixi.lock"]},
        file_contents={
            "pixi.toml": """
            [tool.pixi-version-updater]
            autoupdate-schedule = "monthly"
            """,
        },
    )

    items = PixiVersionUpdater(
        PixiVersionOptions(
            schedule=Schedule.WEEKLY, setup_pixi_marker="prefix-dev/setup-pixi"
        )
    ).scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert items.update_items == ()
    assert github_client.file_content_calls == [(repository, "pixi.toml")]
    assert logger.logged(
        LogLevel.DEBUG,
        "[quantco/with-lockfile@main] Skipping repository: configured schedule is "
        "monthly; current scheduled run is weekly.",
    )


def test_pixi_repository_scanner_reads_scheduled_config_once_per_repository() -> None:
    repository = RepositoryRef(owner="quantco", name="with-lockfiles", branch="main")
    github_client = FakeGitHubClient(
        files={"quantco/with-lockfiles": ["pixi.lock", "subproject/pixi.lock"]},
        file_contents={
            "pixi.toml": """
            [tool.pixi-version-updater]
            autoupdate-schedule = "monthly"
            """,
        },
    )

    items = PixiVersionUpdater(
        PixiVersionOptions(
            schedule=Schedule.WEEKLY, setup_pixi_marker="prefix-dev/setup-pixi"
        )
    ).scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=RecordingLogger(),
        ),
    )

    assert items.update_items == ()
    assert github_client.file_content_calls == [(repository, "pixi.toml")]


def test_pixi_repository_scanner_uses_default_schedule_without_remote_config() -> None:
    repository = RepositoryRef(owner="quantco", name="with-lockfile", branch="main")
    github_client = FakeGitHubClient(
        files={"quantco/with-lockfile": ["pixi.lock"]},
    )

    items = PixiVersionUpdater(
        PixiVersionOptions(
            schedule=Schedule.MONTHLY, setup_pixi_marker="prefix-dev/setup-pixi"
        )
    ).scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=RecordingLogger(),
        ),
    )

    assert items.update_items == (
        PixiVersionItem(
            repository_ref=repository,
            config=PixiVersionUpdaterConfig(),
        ),
    )
    assert github_client.file_content_calls == [(repository, "pixi.toml")]


def test_pixi_repository_scanner_uses_default_config_for_invalid_config() -> None:
    repository = RepositoryRef(owner="quantco", name="with-lockfile", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        files={"quantco/with-lockfile": ["pixi.lock"]},
        file_contents={
            "pixi.toml": """
            [tool.pixi-version-updater]
            autoupdate-schedule = "daily"
            """,
        },
    )

    items = _pixi_version_updater().scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert items.update_items == (
        PixiVersionItem(
            repository_ref=repository,
            config=PixiVersionUpdaterConfig(),
        ),
    )
    assert logger.logged(
        LogLevel.WARNING,
        "Could not parse pixi.toml; using default pixi-version updater config: ",
    )
    assert logger.logged(LogLevel.WARNING, "validation errors for PixiTomlConfig")


def write_config(tmp_path: Path, body: str) -> None:
    (tmp_path / "pixi.toml").write_text(
        f"""
        [tool.pixi-version-updater]
        {body.strip()}
        """
    )


def write_workflow(
    tmp_path: Path,
    content: str = OUTDATED_WORKFLOW,
    *,
    name: str = "ci.yml",
) -> Path:
    workflow = tmp_path / ".github" / "workflows" / name
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(content)
    return workflow


@dataclass
class TaskRun:
    outcome: UpdateOutcome
    checkout: RecordingCheckout
    github_client: FakeGitHubClient
    logger: RecordingLogger


def run_update_task(
    tmp_path: Path,
    *,
    branch: str | None = "main",
    publish_changes: bool = True,
    github_client: FakeGitHubClient | None = None,
    logger: RecordingLogger | None = None,
    config: PixiVersionUpdaterConfig | None = None,
    options: PixiVersionOptions | None = None,
    updater: PixiVersionUpdater | None = None,
) -> TaskRun:
    repository_ref = RepositoryRef(owner="quantco", name="example", branch=branch)
    checkout = RecordingCheckout(tmp_path, repository_ref)
    github_client = github_client or FakeGitHubClient()
    github_client.publish_changes = publish_changes
    logger = logger or RecordingLogger()
    if config is None:
        config_path = tmp_path / "pixi.toml"
        config = (
            parse_config(config_path.read_text())
            if config_path.exists()
            else PixiVersionUpdaterConfig()
        )

    context = RunContext(
        site_config=SiteConfig(),
        github_client=cast(GitHubClient, github_client),
        logger=logger,
    )
    outcome = (
        (
            updater
            or PixiVersionUpdater(
                options or PixiVersionOptions(setup_pixi_marker="prefix-dev/setup-pixi")
            )
        )
        .make_task(
            PixiVersionItem(repository_ref=repository_ref, config=config),
            checkout,
            context,
        )
        .run()
    )

    return TaskRun(outcome, checkout, github_client, logger)
