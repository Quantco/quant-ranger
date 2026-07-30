from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast, get_args

import pytest

from quant_ranger._impl.cli._helpers import command_signature
from quant_ranger._impl.git import RepositoryCheckout
from quant_ranger._impl.github import GitHubClient, PullRequestOptions
from quant_ranger._impl.helpers import CommandError, ExecOutput
from quant_ranger._impl.logger import LogLevel
from quant_ranger._impl.models import (
    RepositoryRef,
    Status,
    UpdateOutcome,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.testing import (
    FakeGitHubClient,
    RecordingCheckout,
    RecordingLogger,
)
from quant_ranger._impl.updaters._copier._migration import (
    CopierMigrationOptions,
    CopierMigrationTarget,
    CopierMigrationUpdateItem,
    CopierMigrationUpdater,
    CopierMigrationUpdateTask,
)
from quant_ranger.site_config import (
    CopierMigration,
    CopierMigrationValue,
    PullRequestTemplate,
    SiteConfig,
)

EXAMPLE_COPIER_MIGRATION = SiteConfig().copier_migrations["example"]
TEST_TEMPLATE = "github.com/quantco/copier-template-python-open-source"


def _site_config_with_example_templates(*templates: str) -> SiteConfig:
    return SiteConfig(
        copier_migrations={
            "example": replace(
                EXAMPLE_COPIER_MIGRATION,
                templates=frozenset(templates),
            )
        }
    )


def test_copier_migration_option_completes_configured_migrations() -> None:
    site_config = SiteConfig(
        copier_migrations={
            "first": EXAMPLE_COPIER_MIGRATION,
            "second": EXAMPLE_COPIER_MIGRATION,
        }
    )

    signature = command_signature(CopierMigrationOptions, site_config=site_config)
    _, option = get_args(signature.parameters["migration"].annotation)
    complete_migration = option.autocompletion

    assert complete_migration is not None
    assert complete_migration("s") == ["second"]


def test_copier_migration_scanner_emits_items_for_needed_migrations() -> None:
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    github_client = FakeGitHubClient(
        file_contents={
            ".copier-answers.yml": """
            _commit: v1.0.0
            _src_path: https://github.com/quantco/copier-template-python-open-source
            example_feature: false
            """
        }
    )

    scan_result = CopierMigrationUpdater(
        CopierMigrationOptions(migration="example")
    ).scanner.scan_all(
        [repository],
        RunContext(
            site_config=_site_config_with_example_templates(TEST_TEMPLATE),
            github_client=cast(GitHubClient, github_client),
            logger=RecordingLogger(),
        ),
    )

    assert scan_result.update_items == (
        CopierMigrationUpdateItem(
            repository_ref=repository,
            migration="example",
            migration_target=CopierMigrationTarget(
                migration_key="example_feature",
                desired_value=True,
            ),
            src_path="https://github.com/quantco/copier-template-python-open-source",
            github_server_host="github.com",
            copier_answers_content=github_client.file_contents[".copier-answers.yml"],
        ),
    )
    assert scan_result.scan_failures == ()


def test_copier_migration_scanner_skips_other_templates() -> None:
    def unexpected_resolver(
        _current_value: CopierMigrationValue,
    ) -> CopierMigrationValue:
        raise AssertionError("The resolver must not run for another template.")

    migration = replace(
        EXAMPLE_COPIER_MIGRATION,
        resolve_desired_value=unexpected_resolver,
    )
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        file_contents={
            ".copier-answers.yml": """
            _commit: v1.0.0
            _src_path: https://github.com/other/copier-template
            example_feature: false
            """
        }
    )

    scan_result = CopierMigrationUpdater(
        CopierMigrationOptions(migration="example")
    ).scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(copier_migrations={"example": migration}),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert scan_result.update_items == ()
    assert scan_result.scan_failures == ()
    assert logger.logged(
        LogLevel.DEBUG,
        "[quantco/example@main] Copier migration example does not apply to template "
        "github.com/other/copier-template.",
    )


def test_copier_migration_scanner_uses_current_github_host() -> None:
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    github_client = FakeGitHubClient(
        github_server_host="github.example",
        file_contents={
            ".copier-answers.yml": """
            _commit: v1.0.0
            _src_path: https://github.example/quantco/copier-template-python-open-source
            example_feature: false
            """
        },
    )

    scan_result = CopierMigrationUpdater(
        CopierMigrationOptions(migration="example")
    ).scanner.scan_all(
        [repository],
        RunContext(
            site_config=_site_config_with_example_templates(
                "github.example/quantco/copier-template-python-open-source"
            ),
            github_client=cast(GitHubClient, github_client),
            logger=RecordingLogger(),
        ),
    )

    assert scan_result.update_items == (
        CopierMigrationUpdateItem(
            repository_ref=repository,
            migration="example",
            migration_target=CopierMigrationTarget(
                migration_key="example_feature",
                desired_value=True,
            ),
            src_path="https://github.example/quantco/copier-template-python-open-source",
            github_server_host="github.example",
            copier_answers_content=github_client.file_contents[".copier-answers.yml"],
        ),
    )
    assert scan_result.scan_failures == ()


def test_copier_migration_scanner_skips_when_repository_url_has_no_host() -> None:
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        repository_url="not-a-url",
        file_contents={
            ".copier-answers.yml": """
            _commit: v1.0.0
            _src_path: https://github.com/quantco/copier-template-python-open-source
            example_feature: false
            """
        },
    )

    scan_result = CopierMigrationUpdater(
        CopierMigrationOptions(migration="example")
    ).scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert scan_result.update_items == ()
    assert [failure.message for failure in scan_result.scan_failures] == [
        "Could not determine GitHub host from repository URL: not-a-url"
    ]
    assert logger.logged(
        LogLevel.ERROR,
        "[quantco/example@main] Skipping repository: Could not determine GitHub host "
        "from repository URL: not-a-url",
    )


def test_copier_migration_scanner_skips_repositories_without_copier_answers() -> None:
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()

    scan_result = CopierMigrationUpdater(
        CopierMigrationOptions(migration="example")
    ).scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, FakeGitHubClient()),
            logger=logger,
        ),
    )

    assert scan_result.update_items == ()
    assert scan_result.scan_failures == ()
    assert logger.logged(
        LogLevel.DEBUG, "[quantco/example@main] No .copier-answers.yml file found."
    )


def test_copier_migration_scanner_skips_invalid_copier_answers() -> None:
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(file_contents={".copier-answers.yml": "["})

    scan_result = CopierMigrationUpdater(
        CopierMigrationOptions(migration="example")
    ).scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert scan_result.update_items == ()
    assert len(scan_result.scan_failures) == 1
    failure_message = scan_result.scan_failures[0].message
    assert failure_message is not None
    assert failure_message.startswith("could not parse .copier-answers.yml:")
    assert logger.logged(
        LogLevel.ERROR,
        "[quantco/example@main] Skipping repository: could not parse "
        ".copier-answers.yml:",
    )


def test_copier_migration_scanner_skips_missing_and_unsupported_fields() -> None:
    repositories = [
        RepositoryRef(owner="quantco", name="missing", branch="main"),
        RepositoryRef(owner="quantco", name="null", branch="main"),
        RepositoryRef(owner="quantco", name="current", branch="main"),
    ]
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        file_contents={
            "quantco/missing:.copier-answers.yml": """
            _commit: v1.0.0
            _src_path: https://github.com/quantco/copier-template-python-open-source
            """,
            "quantco/null:.copier-answers.yml": """
            _commit: v1.0.0
            _src_path: https://github.com/quantco/copier-template-python-open-source
            example_feature: null
            """,
            "quantco/current:.copier-answers.yml": """
            _commit: v1.0.0
            _src_path: https://github.com/quantco/copier-template-python-open-source
            example_feature: true
            """,
        }
    )

    scan_result = CopierMigrationUpdater(
        CopierMigrationOptions(migration="example")
    ).scanner.scan_all(
        repositories,
        RunContext(
            site_config=_site_config_with_example_templates(TEST_TEMPLATE),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert scan_result.update_items == ()
    assert [failure.repository_ref.name for failure in scan_result.scan_failures] == [
        "null"
    ]
    assert scan_result.scan_failures[0].message == (
        "Copier answer example_feature has unsupported value None."
    )
    assert logger.logged(
        LogLevel.DEBUG,
        "[quantco/missing@main] Copier answers do not define example_feature; "
        "migration is not needed.",
    )
    assert logger.logged(
        LogLevel.ERROR,
        "[quantco/null@main] Skipping repository: Copier answer example_feature has "
        "unsupported value None.",
    )
    assert logger.logged(
        LogLevel.DEBUG,
        "[quantco/current@main] Copier answer example_feature already satisfies the "
        "desired state; migration is not needed.",
    )


def test_copier_migration_scanner_supports_configured_extra_answer_keys() -> None:
    copier_migrations = {
        "future-migration": CopierMigration(
            # This intentionally collides with an attribute on Pydantic models.
            answer_key="model_fields_set",
            templates=frozenset({TEST_TEMPLATE}),
            resolve_desired_value=lambda current_value: (
                current_value if current_value is True else True
            ),
            pull_request_template=EXAMPLE_COPIER_MIGRATION.pull_request_template,
        )
    }
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    github_client = FakeGitHubClient(
        file_contents={
            ".copier-answers.yml": """
            _commit: v1.0.0
            _src_path: https://github.com/quantco/copier-template-python-open-source
            model_fields_set: false
            """,
        }
    )

    scan_result = CopierMigrationUpdater(
        CopierMigrationOptions(migration="future-migration")
    ).scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(copier_migrations=copier_migrations),
            github_client=cast(GitHubClient, github_client),
            logger=RecordingLogger(),
        ),
    )

    assert scan_result.update_items == (
        CopierMigrationUpdateItem(
            repository_ref=repository,
            migration="future-migration",
            migration_target=CopierMigrationTarget(
                migration_key="model_fields_set",
                desired_value=True,
            ),
            src_path="https://github.com/quantco/copier-template-python-open-source",
            github_server_host="github.com",
            copier_answers_content=github_client.file_contents[".copier-answers.yml"],
        ),
    )
    assert scan_result.scan_failures == ()


@pytest.mark.parametrize(
    ("src_path", "message"),
    [
        (
            "http://github.com/quantco/copier-template-python-open-source",
            "invalid or unsupported template URL in .copier-answers.yml: "
            "http://github.com/quantco/copier-template-python-open-source",
        ),
        (
            "https://evil.example/quantco/copier-template-python-open-source",
            "template URL in .copier-answers.yml points to evil.example instead "
            "of github.com: https://evil.example/quantco/copier-template-python-open-source",
        ),
    ],
)
def test_copier_migration_scanner_errors_non_github_template_urls(
    src_path: str,
    message: str,
) -> None:
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        file_contents={
            ".copier-answers.yml": f"""
            _commit: v1.0.0
            _src_path: {src_path}
            example_feature: false
            """
        },
    )

    scan_result = CopierMigrationUpdater(
        CopierMigrationOptions(migration="example")
    ).scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert scan_result.update_items == ()
    assert [failure.message for failure in scan_result.scan_failures] == [message]
    assert logger.logged(
        LogLevel.ERROR,
        f"[quantco/example@main] Skipping repository: {message}",
    )


def test_copier_migration_scanner_rejects_template_urls_from_other_hosts() -> None:
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        github_server_host="github.example",
        file_contents={
            ".copier-answers.yml": """
            _commit: v1.0.0
            _src_path: https://github.com/quantco/copier-template-python-open-source
            example_feature: false
            """
        },
    )

    scan_result = CopierMigrationUpdater(
        CopierMigrationOptions(migration="example")
    ).scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert scan_result.update_items == ()
    assert [failure.message for failure in scan_result.scan_failures] == [
        "template URL in .copier-answers.yml points to github.com instead of "
        "github.example: https://github.com/quantco/copier-template-python-open-source"
    ]
    assert logger.logged(
        LogLevel.ERROR,
        "[quantco/example@main] Skipping repository: template URL in "
        ".copier-answers.yml points to github.com instead of github.example: "
        "https://github.com/quantco/copier-template-python-open-source",
    )


def test_copier_migration_scanner_emits_items_for_untrusted_github_template_urls() -> (
    None
):
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        file_contents={
            ".copier-answers.yml": """
            _commit: v1.0.0
            _src_path: https://github.com/attacker/copier-template-python-open-source
            example_feature: false
            """
        },
    )

    scan_result = CopierMigrationUpdater(
        CopierMigrationOptions(migration="example")
    ).scanner.scan_all(
        [repository],
        RunContext(
            site_config=_site_config_with_example_templates(
                "github.com/attacker/copier-template-python-open-source"
            ),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert scan_result.update_items == (
        CopierMigrationUpdateItem(
            repository_ref=repository,
            migration="example",
            migration_target=CopierMigrationTarget(
                migration_key="example_feature",
                desired_value=True,
            ),
            src_path="https://github.com/attacker/copier-template-python-open-source",
            github_server_host="github.com",
            copier_answers_content=github_client.file_contents[".copier-answers.yml"],
        ),
    )
    assert scan_result.scan_failures == ()


def test_copier_migration_runs_copier_and_creates_pull_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command_calls: list[dict[str, Any]] = []
    execution_events: list[str] = []
    hook_calls: list[tuple[RepositoryCheckout, RunContext]] = []
    pull_request_template = PullRequestTemplate(
        title="chore: Apply custom migration",
        body="This pull request was configured by a migration provider.",
        branch_prefix="template-modernization",
    )

    def post_migration(
        checkout: RepositoryCheckout,
        context: RunContext,
    ) -> None:
        hook_calls.append((checkout, context))
        (checkout.absolute_path / "pixi.toml").write_text("[workspace]\n")
        execution_events.append("post-migration")

    copier_migrations = {
        "custom-migration": CopierMigration(
            answer_key="custom_flag",
            templates=EXAMPLE_COPIER_MIGRATION.templates,
            resolve_desired_value=lambda _current_value: True,
            pull_request_template=pull_request_template,
            post_migration=post_migration,
        )
    }

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        command_calls.append({"command": command, **kwargs})
        execution_events.append(command[0])
        return ExecOutput(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._copier._common.get_exec_output_silently",
        fake_exec,
    )

    site_config = SiteConfig(
        copier_migrations=copier_migrations,
        copier_trusted_templates={
            "github.com/quantco/copier-template-python-open-source"
        },
    )
    task_run = run_update_task(
        tmp_path,
        CopierMigrationOptions(migration="custom-migration"),
        publish_changes=False,
        migration_target=CopierMigrationTarget(
            migration_key="custom_flag",
            desired_value=True,
        ),
        site_config=site_config,
    )

    assert task_run.outcome.result == Status.UPDATED
    assert command_calls[0]["command"] == [
        "copier",
        "update",
        "--defaults",
        "--vcs-ref=:current:",
        "--data",
        "custom_flag=true",
        "--trust",
    ]
    assert command_calls[0]["cwd"] == tmp_path
    assert command_calls[0]["env"]["GIT_AUTHOR_NAME"] == "copier[bot]"
    assert "http.https://github.com/.extraHeader" in command_calls[0]["env"].values()
    assert "git@github.com:" in command_calls[0]["env"].values()
    assert command_calls[0]["redact"]
    assert command_calls[1]["command"] == [
        "mergiraf",
        "solve",
        "--keep-backup=false",
        "pixi.toml",
    ]
    assert command_calls[2]["command"] == ["pixi", "lock"]
    assert execution_events == ["copier", "mergiraf", "post-migration", "pixi"]
    assert task_run.github_client.pull_request_calls == [
        {
            "checkout": task_run.checkout,
            "options": PullRequestOptions(
                title=pull_request_template.title,
                body=pull_request_template.body,
                source_branch="template-modernization-custom-migration",
                target_branch="release",
                quant_ranger_id="copier-migration",
            ),
            "logger": task_run.logger,
            "publish_changes": False,
        }
    ]
    assert len(hook_calls) == 1
    hook_checkout, hook_context = hook_calls[0]
    assert hook_checkout is task_run.checkout
    assert hook_context.github_client is task_run.github_client
    assert hook_context.site_config is site_config
    assert hook_context.logger is task_run.logger
    assert not hook_context.github_client.publish_changes


def test_copier_migration_runs_untrusted_template_without_trust(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command_calls: list[dict[str, Any]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        command_calls.append({"command": command, **kwargs})
        return ExecOutput(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._copier._common.get_exec_output_silently",
        fake_exec,
    )

    task_run = run_update_task(
        tmp_path,
        CopierMigrationOptions(migration="example"),
        publish_changes=False,
        src_path="https://github.com/attacker/copier-template-python-open-source",
    )

    assert task_run.outcome.result == Status.UPDATED
    assert command_calls[0]["command"] == [
        "copier",
        "update",
        "--defaults",
        "--vcs-ref=:current:",
        "--data",
        "example_feature=true",
    ]
    assert task_run.logger.logged(
        LogLevel.INFO,
        "Copier template in quantco/example@release is not in "
        "quant-ranger's trusted-template allowlist: .copier-answers.yml: "
        "https://github.com/attacker/copier-template-python-open-source. Copier will run "
        "without --trust.",
    )
    assert (
        task_run.github_client.pull_request_calls[0]["options"].body
        == EXAMPLE_COPIER_MIGRATION.pull_request_template.body
    )


def test_copier_migration_returns_up_to_date_without_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._copier._common.get_exec_output_silently",
        lambda command, **kwargs: ExecOutput(exit_code=0, stdout="", stderr=""),
    )

    task_run = run_update_task(
        tmp_path,
        CopierMigrationOptions(migration="example"),
        clean=True,
    )

    assert task_run.outcome.result == Status.UP_TO_DATE
    assert task_run.logger.logged(
        LogLevel.DEBUG, "No changes detected after copier migration."
    )
    assert task_run.github_client.pull_request_calls == []


def test_copier_migration_skips_when_pull_request_was_not_opened(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._copier._common.get_exec_output_silently",
        lambda command, **kwargs: ExecOutput(exit_code=0, stdout="", stderr=""),
    )

    task_run = run_update_task(
        tmp_path,
        CopierMigrationOptions(migration="example"),
        pr_opened=False,
    )

    assert task_run.outcome.result == Status.SKIPPED
    assert len(task_run.github_client.pull_request_calls) == 1


def test_copier_migration_returns_failure_when_copier_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        del command, kwargs
        raise CommandError("copier failed", ExecOutput(1, "stdout", "stderr"))

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._copier._common.get_exec_output_silently",
        fake_exec,
    )

    task_run = run_update_task(
        tmp_path,
        CopierMigrationOptions(migration="example"),
    )

    assert task_run.outcome.result == Status.FAILURE
    assert task_run.outcome.message == "copier failed"
    assert task_run.logger.errors == []
    assert task_run.checkout.add_all_count == 0
    assert task_run.github_client.pull_request_calls == []


def test_copier_migration_returns_failure_when_checkout_answers_are_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command_calls: list[dict[str, Any]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        command_calls.append({"command": command, **kwargs})
        return ExecOutput(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._copier._common.get_exec_output_silently",
        fake_exec,
    )

    task_run = run_update_task(
        tmp_path,
        CopierMigrationOptions(migration="example"),
        write_checkout_answers=False,
    )

    assert task_run.outcome.result == Status.FAILURE
    assert task_run.outcome.message is not None
    assert task_run.outcome.message.startswith("Could not read .copier-answers.yml:")
    assert task_run.logger.errors == []
    assert command_calls == []


def test_copier_migration_uses_item_github_server_host(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command_calls: list[dict[str, Any]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        command_calls.append({"command": command, **kwargs})
        return ExecOutput(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._copier._common.get_exec_output_silently",
        fake_exec,
    )

    run_update_task(
        tmp_path,
        CopierMigrationOptions(migration="example"),
        src_path="https://github.example/quantco/copier-template-python-open-source",
        github_server_host="github.example",
        site_config=SiteConfig(
            copier_trusted_templates={
                "github.example/quantco/copier-template-python-open-source"
            }
        ),
    )

    assert command_calls[0]["command"] == [
        "copier",
        "update",
        "--defaults",
        "--vcs-ref=:current:",
        "--data",
        "example_feature=true",
        "--trust",
    ]
    assert (
        "http.https://github.example/.extraHeader" in command_calls[0]["env"].values()
    )
    assert "git@github.example:" in command_calls[0]["env"].values()


@pytest.mark.parametrize(
    "checkout_src_path",
    [
        "https://github.com/attacker/copier-template-python-open-source",
        "https://evil.example/quantco/copier-template-python-open-source",
    ],
)
def test_copier_migration_skips_when_checked_out_answers_changed(
    checkout_src_path: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command_calls: list[dict[str, Any]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        command_calls.append({"command": command, **kwargs})
        return ExecOutput(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._copier._common.get_exec_output_silently",
        fake_exec,
    )

    task_run = run_update_task(
        tmp_path,
        CopierMigrationOptions(migration="example"),
        checkout_src_path=checkout_src_path,
    )

    assert task_run.outcome.result == Status.SKIPPED
    assert (
        task_run.outcome.message
        == ".copier-answers.yml changed between scanning and checkout."
    )
    assert command_calls == []
    assert task_run.logger.warnings == []
    assert task_run.logger.errors == []


@pytest.mark.parametrize(
    ("desired_value", "expected"),
    [
        ("enabled", "key=enabled"),
        (True, "key=true"),
        (False, "key=false"),
    ],
)
def test_copier_argument_formats_desired_values(
    desired_value: str | bool,
    expected: str,
) -> None:
    target = CopierMigrationTarget(migration_key="key", desired_value=desired_value)

    assert target.copier_argument == expected


TRUSTED_TEMPLATE_SRC_PATH = (
    "https://github.com/quantco/copier-template-python-open-source"
)


@dataclass
class TaskRun:
    outcome: UpdateOutcome
    checkout: RecordingCheckout
    github_client: FakeGitHubClient
    logger: RecordingLogger


def run_update_task(
    tmp_path: Path,
    options: CopierMigrationOptions,
    *,
    clean: bool = False,
    publish_changes: bool = True,
    pr_opened: bool = True,
    write_checkout_answers: bool = True,
    src_path: str = TRUSTED_TEMPLATE_SRC_PATH,
    checkout_src_path: str | None = None,
    github_server_host: str = "github.com",
    migration_target: CopierMigrationTarget | None = None,
    site_config: SiteConfig | None = None,
) -> TaskRun:
    checkout_copier_answers_content = f"""
        _commit: v1.0.0
        _src_path: {checkout_src_path or src_path}

        """
    if write_checkout_answers:
        (tmp_path / ".copier-answers.yml").write_text(checkout_copier_answers_content)
    copier_answers_content = (
        checkout_copier_answers_content
        if checkout_src_path is None
        else f"""
        _commit: v1.0.0
        _src_path: {src_path}

        """
    )
    repository_ref = RepositoryRef(owner="quantco", name="example", branch="release")
    checkout = RecordingCheckout(
        tmp_path,
        repository_ref,
        clean=clean,
        changed_files=("pixi.toml",),
        lock_clean=True,
    )
    github_client = FakeGitHubClient(
        pr_opened=pr_opened, publish_changes=publish_changes
    )
    logger = RecordingLogger()
    if migration_target is None:
        migration_target = CopierMigrationTarget(
            migration_key="example_feature",
            desired_value=True,
        )

    outcome = CopierMigrationUpdateTask(
        checkout,
        RunContext(
            github_client=cast(GitHubClient, github_client),
            logger=logger,
            site_config=site_config if site_config is not None else SiteConfig(),
        ),
        item=CopierMigrationUpdateItem(
            repository_ref=repository_ref,
            migration=options.migration,
            migration_target=migration_target,
            src_path=src_path,
            github_server_host=github_server_host,
            copier_answers_content=copier_answers_content,
        ),
        options=options,
    ).run()

    return TaskRun(outcome, checkout, github_client, logger)
