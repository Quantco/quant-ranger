from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

from quant_ranger._impl.github import GitHubClient, GitHubError, PullRequestOptions
from quant_ranger._impl.helpers import CommandError, ExecOutput
from quant_ranger._impl.logger import LogLevel
from quant_ranger._impl.models import (
    RepositoryRef,
    Status,
    UpdateOptions,
    UpdateOutcome,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.testing import (
    FakeGitHubClient,
    RecordingCheckout,
    RecordingLogger,
)
from quant_ranger._impl.updaters import CopierUpdater
from quant_ranger._impl.updaters._copier._common import (
    is_trusted_template,
    parse_copier_answers,
    parse_template_repository_for_host,
    run_pixi_lock_if_manifest_changed,
)
from quant_ranger._impl.updaters._copier._update import (
    COPIER_PR_BODY_TEMPLATE,
    CopierTemplateUpdate,
    CopierUpdateItem,
    CopierUpdateTask,
    get_sorted_newer_tags,
)
from quant_ranger.site_config import SiteConfig


def _copier_updater() -> CopierUpdater:
    return CopierUpdater(UpdateOptions())


@pytest.mark.parametrize(
    ("src_path", "expected"),
    [
        (
            "gh:quantco/copier-template",
            RepositoryRef(owner="quantco", name="copier-template"),
        ),
        (
            "https://github.com/quantco/copier-template.git",
            RepositoryRef(owner="quantco", name="copier-template"),
        ),
        (
            "github.com/quantco/copier-template",
            RepositoryRef(owner="quantco", name="copier-template"),
        ),
        (
            "git@github.com:quantco/copier-template.git",
            RepositoryRef(owner="quantco", name="copier-template"),
        ),
    ],
)
def test_parse_template_repository_for_host_accepts_supported_urls(
    src_path: str,
    expected: RepositoryRef,
) -> None:
    assert parse_template_repository_for_host(src_path, "github.com") == expected


def test_parse_template_repository_for_host_rejects_unknown_urls() -> None:
    with pytest.raises(ValueError, match="invalid or unsupported template URL"):
        parse_template_repository_for_host("../local-template", "github.com")
    with pytest.raises(ValueError, match="invalid or unsupported template URL"):
        parse_template_repository_for_host(
            "http://github.com/quantco/template", "github.com"
        )
    with pytest.raises(
        ValueError, match="points to evil.example instead of github.com"
    ):
        parse_template_repository_for_host(
            "https://evil.example/quantco/template", "github.com"
        )


def test_parse_template_repository_for_host_accepts_configured_hosts() -> None:
    assert parse_template_repository_for_host(
        "https://github.example/quantco/copier-template.git",
        github_server_host="github.example",
    ) == RepositoryRef(owner="quantco", name="copier-template")
    assert parse_template_repository_for_host(
        "git@github.example:quantco/copier-template.git",
        github_server_host="github.example",
    ) == RepositoryRef(owner="quantco", name="copier-template")
    with pytest.raises(
        ValueError, match="points to github.com instead of github.example"
    ):
        parse_template_repository_for_host(
            "gh:quantco/copier-template",
            github_server_host="github.example",
        )
    with pytest.raises(
        ValueError, match="points to evil.example instead of github.example"
    ):
        parse_template_repository_for_host(
            "https://evil.example/quantco/copier-template",
            github_server_host="github.example",
        )


def test_parse_copier_answers_rejects_invalid_answers() -> None:
    with pytest.raises(ValueError, match="could not parse .copier-answers.yml"):
        parse_copier_answers("_src_path: gh:quantco/template\n")


@pytest.mark.parametrize(
    ("src_path", "trusted"),
    [
        ("gh:quantco/copier-template-python-open-source", True),
        ("https://github.com/quantco/copier-template-python-open-source", True),
        ("https://github.com/quantco/copier-template-python-open-source.git", True),
        ("git@github.com:quantco/copier-template-python-open-source.git", True),
        ("https://github.example/quantco/copier-template-python-open-source", True),
        ("https://github.example/quantco/copier-template-python-open-source.git", True),
        ("git@github.example:quantco/copier-template-python-open-source.git", True),
        # The gh: shorthand only refers to github.com repositories.
        ("gh:other/copier-template-python-open-source", False),
    ],
)
def test_trusted_templates_cover_configured_hosts(
    src_path: str,
    trusted: bool,
) -> None:
    trusted_templates = frozenset(
        {
            "github.com/quantco/copier-template-python-open-source",
            "github.example/quantco/copier-template-python-open-source",
        }
    )

    assert is_trusted_template(src_path, trusted_templates) is trusted


TRUSTED_TEMPLATES = frozenset({"github.com/quantco/copier-template-python-open-source"})


@pytest.mark.parametrize(
    "src_path",
    [
        # GitHub treats the host and owner/repo case-insensitively, so casing
        # variants of an allowlisted template resolve to the same trusted repo.
        "https://github.com/quantco/copier-template-python-open-source",
        "https://GitHub.com/quantco/Copier-Template-Python-Open-Source",
        "git@github.com:quantco/copier-template-python-open-source.git",
        "gh:quantco/Copier-Template-Python-Open-Source",
    ],
)
def test_is_trusted_template_accepts_case_variants(src_path: str) -> None:
    assert is_trusted_template(src_path, TRUSTED_TEMPLATES)


@pytest.mark.parametrize(
    "src_path",
    [
        # Non-allowlisted quantco template.
        "https://github.com/quantco/copier-template",
        # Allowlisted owner/name on an attacker-controlled host.
        "https://evil.example/quantco/copier-template-python-open-source",
        # Allowlisted name owned by an attacker.
        "https://github.com/attacker/copier-template-python-open-source",
        # Trailing slash is not the recorded spelling.
        "https://github.com/quantco/copier-template-python-open-source/",
        # Unparsable / local path.
        "../local-template",
    ],
)
def test_is_trusted_template_rejects_untrusted_src_paths(src_path: str) -> None:
    assert not is_trusted_template(src_path, TRUSTED_TEMPLATES)


def test_is_trusted_template_replaces_allowlist_with_trusted_templates() -> None:
    trusted = {"github.example/quantco/copier-template-python-open-source"}

    assert is_trusted_template(
        "https://github.example/quantco/copier-template-python-open-source",
        trusted,
    )
    # The provided allowlist replaces the builtin one entirely.
    assert not is_trusted_template(
        "https://github.com/quantco/copier-template-python-open-source",
        trusted,
    )
    assert not is_trusted_template(
        "https://github.example/attacker/copier-template-python-open-source",
        trusted,
    )


def test_get_sorted_newer_tags_uses_version_sorting_and_commit_tags() -> None:
    assert get_sorted_newer_tags(
        ["not-a-version", "v1.1.0", "v1.0.1", "v1.0.0"],
        "v1.0.0",
    ) == ["v1.0.1", "v1.1.0"]


def test_get_sorted_newer_tags_rejects_unknown_current_ref() -> None:
    with pytest.raises(ValueError, match="only tags are allowed"):
        get_sorted_newer_tags(["v1.0.0"], "main")


def test_get_sorted_newer_tags_rejects_git_describe_ref() -> None:
    with pytest.raises(ValueError, match="only tags are allowed"):
        get_sorted_newer_tags(["v1.1.1"], "v1.1.0-2-gabcdef")


def test_copier_scanner_emits_items_for_newer_template_tags() -> None:
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    github_client = FakeGitHubClient(
        file_contents={
            ".copier-answers.yml": """
            _commit: v1.0.0
            _src_path: https://github.com/quantco/copier-template-python-open-source
            """
        },
        repo_tags={
            ("quantco", "copier-template-python-open-source"): ["v1.0.0", "v1.1.0"]
        },
    )

    items = _copier_updater().scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=RecordingLogger(),
        ),
    )

    assert items.update_items == (
        CopierUpdateItem(
            repository_ref=repository,
            template_update=CopierTemplateUpdate(
                template_repository=RepositoryRef(
                    owner="quantco",
                    name="copier-template-python-open-source",
                ),
                sorted_newer_tags=["v1.1.0"],
                src_path="https://github.com/quantco/copier-template-python-open-source",
                github_server_host="github.com",
                copier_answers_content=github_client.file_contents[
                    ".copier-answers.yml"
                ],
            ),
        ),
    )


def test_copier_scanner_skips_repositories_without_copier_answers() -> None:
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()

    items = _copier_updater().scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, FakeGitHubClient()),
            logger=logger,
        ),
    )

    assert items.update_items == ()
    assert logger.logged(
        LogLevel.DEBUG, "[quantco/example@main] No .copier-answers.yml file found."
    )


def test_copier_scanner_skips_invalid_copier_answers() -> None:
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(file_contents={".copier-answers.yml": "["})

    items = _copier_updater().scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert items.update_items == ()
    assert logger.logged(
        LogLevel.ERROR,
        "[quantco/example@main] Skipping repository: could not parse .copier-answers.yml:",
    )


def test_copier_scanner_skips_when_repository_url_has_no_host() -> None:
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        repository_url="not-a-url",
        file_contents={
            ".copier-answers.yml": """
            _commit: v1.0.0
            _src_path: https://github.com/quantco/copier-template-python-open-source
            """
        },
    )

    items = _copier_updater().scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert items.update_items == ()
    assert logger.logged(
        LogLevel.ERROR,
        "[quantco/example@main] Skipping repository: Could not determine GitHub host "
        "from repository URL: not-a-url",
    )


def test_copier_scanner_skips_unknown_current_template_ref() -> None:
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        file_contents={
            ".copier-answers.yml": """
            _commit: main
            _src_path: https://github.com/quantco/copier-template-python-open-source
            """
        },
        repo_tags={("quantco", "copier-template-python-open-source"): ["v1.0.0"]},
    )

    items = _copier_updater().scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert items.update_items == ()
    assert logger.logged(
        LogLevel.ERROR,
        "[quantco/example@main] Skipping repository: Incompatible _commit format "
        "'main'; only tags are allowed.",
    )


def test_copier_scanner_skips_repositories_without_newer_tags() -> None:
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        file_contents={
            ".copier-answers.yml": """
            _commit: v1.1.0
            _src_path: https://github.com/quantco/copier-template-python-open-source
            """
        },
        repo_tags={
            ("quantco", "copier-template-python-open-source"): ["v1.0.0", "v1.1.0"]
        },
    )

    items = _copier_updater().scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert items.update_items == ()
    assert logger.logged(
        LogLevel.DEBUG,
        "[quantco/example@main] No newer copier template tags found.",
    )


@pytest.mark.parametrize(
    ("src_path", "message"),
    [
        (
            "http://github.com/quantco/copier-template",
            "invalid or unsupported template URL in .copier-answers.yml: "
            "http://github.com/quantco/copier-template",
        ),
        (
            "https://evil.example/quantco/copier-template",
            "template URL in .copier-answers.yml points to evil.example instead "
            "of github.com: https://evil.example/quantco/copier-template",
        ),
    ],
)
def test_copier_scanner_errors_non_github_template_urls(
    src_path: str,
    message: str,
) -> None:
    repository = RepositoryRef(owner="quantco", name="copier-template", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        file_contents={
            ".copier-answers.yml": f"""
            _commit: v1.0.0
            _src_path: {src_path}
            """
        },
    )

    items = _copier_updater().scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert items.update_items == ()
    assert github_client.repo_tag_calls == []
    assert logger.logged(
        LogLevel.ERROR,
        f"[quantco/copier-template@main] Skipping repository: {message}",
    )


def test_copier_scanner_errors_inaccessible_template_repository() -> None:
    repository = RepositoryRef(owner="quantco", name="copier-template", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        file_contents={
            ".copier-answers.yml": """
            _commit: v1.0.0
            _src_path: https://github.com/quantco/copier-template-python-open-source
            """
        },
        repo_tag_error=GitHubError(
            "Repository quantco/copier-template-python-open-source was not found or is inaccessible."
        ),
    )

    items = _copier_updater().scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert items.update_items == ()
    assert github_client.repo_tag_calls == [
        ("quantco", "copier-template-python-open-source")
    ]
    assert logger.logged(
        LogLevel.ERROR,
        "[quantco/copier-template@main] Skipping repository: Repository "
        "quantco/copier-template-python-open-source was not found or is inaccessible.",
    )


def test_copier_scanner_emits_items_for_untrusted_github_template_urls() -> None:
    repository = RepositoryRef(owner="quantco", name="example", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        file_contents={
            ".copier-answers.yml": """
            _commit: v1.0.0
            _src_path: https://github.com/attacker/copier-template-python-open-source
            """
        },
        repo_tags={
            ("attacker", "copier-template-python-open-source"): ["v1.0.0", "v1.1.0"]
        },
    )

    items = _copier_updater().scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert items.update_items == (
        CopierUpdateItem(
            repository_ref=repository,
            template_update=CopierTemplateUpdate(
                template_repository=RepositoryRef(
                    owner="attacker",
                    name="copier-template-python-open-source",
                ),
                sorted_newer_tags=["v1.1.0"],
                src_path="https://github.com/attacker/copier-template-python-open-source",
                github_server_host="github.com",
                copier_answers_content=github_client.file_contents[
                    ".copier-answers.yml"
                ],
            ),
        ),
    )
    assert github_client.repo_tag_calls == [
        ("attacker", "copier-template-python-open-source")
    ]


def test_copier_update_runs_copier_and_creates_pull_request(
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

    task_run = run_update_task(tmp_path, publish_changes=False)

    assert task_run.outcome.result == Status.UPDATED
    assert command_calls[0]["command"] == [
        "copier",
        "update",
        "--vcs-ref=v1.2.0",
        "--defaults",
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
    assert command_calls[2]["command"] == [
        "mergiraf",
        "solve",
        "--keep-backup=false",
        "README.md",
    ]
    assert command_calls[3]["command"] == ["pixi", "lock"]
    assert command_calls[3]["cwd"] == tmp_path
    assert task_run.checkout.add_all_count == 1
    assert task_run.github_client.pull_request_calls == [
        {
            "checkout": task_run.checkout,
            "options": PullRequestOptions(
                title="chore: Update copier template to v1.2.0",
                body=COPIER_PR_BODY_TEMPLATE.format(
                    changelog="## v1.1.0\nHello octocat\n\n## v1.2.0\nMissing Changelog"
                ),
                source_branch="copier-autoupdate-v1.2.0",
                target_branch="release",
                quant_ranger_id="copier",
            ),
            "logger": task_run.logger,
            "publish_changes": False,
        }
    ]


def test_copier_update_runs_untrusted_template_without_trust(
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
        publish_changes=False,
        src_path="https://github.com/attacker/copier-template-python-open-source",
        template_owner="attacker",
    )

    assert task_run.outcome.result == Status.UPDATED
    assert command_calls[0]["command"] == [
        "copier",
        "update",
        "--vcs-ref=v1.2.0",
        "--defaults",
    ]
    assert task_run.logger.logged(
        LogLevel.INFO,
        "Copier template in quantco/example@release is not in "
        "quant-ranger's trusted-template allowlist: .copier-answers.yml: "
        "https://github.com/attacker/copier-template-python-open-source. Copier will run "
        "without --trust.",
    )
    assert task_run.github_client.pull_request_calls[0]["options"].body == (
        COPIER_PR_BODY_TEMPLATE.format(
            changelog="## v1.1.0\nHello octocat\n\n## v1.2.0\nMissing Changelog"
        )
    )


def test_copier_update_returns_up_to_date_without_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._copier._common.get_exec_output_silently",
        lambda command, **kwargs: ExecOutput(exit_code=0, stdout="", stderr=""),
    )

    task_run = run_update_task(tmp_path, clean=True)

    assert task_run.outcome.result == Status.UP_TO_DATE
    assert task_run.logger.logged(
        LogLevel.DEBUG, "No changes detected after copier update."
    )
    assert task_run.github_client.pull_request_calls == []


def test_copier_update_skips_when_pull_request_was_not_opened(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._copier._common.get_exec_output_silently",
        lambda command, **kwargs: ExecOutput(exit_code=0, stdout="", stderr=""),
    )

    task_run = run_update_task(tmp_path, pr_opened=False)

    assert task_run.outcome.result == Status.SKIPPED
    assert len(task_run.github_client.pull_request_calls) == 1


def test_copier_update_returns_failure_when_copier_fails(
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

    task_run = run_update_task(tmp_path)

    assert task_run.outcome.result == Status.FAILURE
    assert task_run.outcome.message == "copier failed"
    assert task_run.logger.errors == []
    assert task_run.checkout.add_all_count == 0
    assert task_run.github_client.pull_request_calls == []


def test_copier_update_skips_when_checkout_answers_are_missing(
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

    task_run = run_update_task(tmp_path, write_checkout_answers=False)

    assert task_run.outcome.result == Status.FAILURE
    assert task_run.outcome.message is not None
    assert task_run.outcome.message.startswith("Could not read .copier-answers.yml:")
    assert task_run.logger.errors == []
    assert command_calls == []


def test_copier_update_skips_when_checked_out_answers_changed(
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
        checkout_src_path="https://github.com/attacker/copier-template-python-open-source",
    )

    assert task_run.outcome.result == Status.SKIPPED
    assert (
        task_run.outcome.message
        == ".copier-answers.yml changed between scanning and checkout."
    )
    assert command_calls == []
    assert task_run.logger.warnings == []


def test_copier_update_uses_item_github_server_host(
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
        "--vcs-ref=v1.2.0",
        "--defaults",
        "--trust",
    ]
    assert (
        "http.https://github.example/.extraHeader" in command_calls[0]["env"].values()
    )
    assert "git@github.example:" in command_calls[0]["env"].values()


def test_attempt_mergiraf_solve_logs_debug_when_resolution_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = RecordingCheckout(
        tmp_path,
        RepositoryRef(owner="quantco", name="example", branch="release"),
        changed_files=("pixi.toml", "README.md"),
    )
    logger = RecordingLogger()

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        del command, kwargs
        raise CommandError(
            "mergiraf failed",
            ExecOutput(1, "merge stdout", "merge stderr"),
        )

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._copier._common.get_exec_output_silently",
        fake_exec,
    )

    from quant_ranger._impl.updaters._copier._common import attempt_mergiraf_solve

    attempt_mergiraf_solve(checkout, logger)

    assert logger.debug_messages == [
        "Mergiraf could not resolve merge conflicts in pixi.toml; continuing.",
        "Mergiraf could not resolve merge conflicts in README.md; continuing.",
    ]


def test_run_pixi_lock_if_manifest_changed_skips_without_manifest_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = RecordingCheckout(
        tmp_path,
        RepositoryRef(owner="quantco", name="example", branch="release"),
    )
    logger = RecordingLogger()
    command_calls: list[list[str]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        del kwargs
        command_calls.append(command)
        return ExecOutput(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._copier._common.get_exec_output_silently",
        fake_exec,
    )

    run_pixi_lock_if_manifest_changed(checkout, logger)

    assert command_calls == []
    assert logger.records == []


def test_run_pixi_lock_if_manifest_changed_logs_debug_when_lock_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = RecordingCheckout(
        tmp_path,
        RepositoryRef(owner="quantco", name="example", branch="release"),
        changed_files=("pixi.toml",),
    )
    logger = RecordingLogger()

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        del command, kwargs
        raise CommandError("pixi lock failed", ExecOutput(1, "", "failed"))

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._copier._common.get_exec_output_silently",
        fake_exec,
    )

    run_pixi_lock_if_manifest_changed(checkout, logger)

    assert logger.logged(
        LogLevel.DEBUG,
        "Running `pixi lock` failed. Likely due to merge conflicts in pixi.toml. "
        "Continuing.",
    )


@dataclass
class TaskRun:
    outcome: UpdateOutcome
    checkout: RecordingCheckout
    github_client: FakeGitHubClient
    logger: RecordingLogger


TRUSTED_TEMPLATE_SRC_PATH = (
    "https://github.com/quantco/copier-template-python-open-source"
)
TASK_SITE_CONFIG = SiteConfig(
    copier_trusted_templates={"github.com/quantco/copier-template-python-open-source"}
)


def run_update_task(
    tmp_path: Path,
    *,
    publish_changes: bool = True,
    clean: bool = False,
    pr_opened: bool = True,
    write_checkout_answers: bool = True,
    src_path: str = TRUSTED_TEMPLATE_SRC_PATH,
    checkout_src_path: str | None = None,
    template_owner: str = "quantco",
    template_name: str = "copier-template-python-open-source",
    github_server_host: str = "github.com",
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
        changed_files=("pixi.toml", "README.md"),
        lock_clean=True,
    )
    github_client = FakeGitHubClient(
        pr_opened=pr_opened,
        publish_changes=publish_changes,
        tag_messages={
            (template_owner, template_name, "v1.1.0"): "Hello @octocat",
            (template_owner, template_name, "v1.2.0"): None,
        },
    )
    logger = RecordingLogger()

    outcome = CopierUpdateTask(
        checkout,
        RunContext(
            github_client=cast(GitHubClient, github_client),
            logger=logger,
            site_config=site_config if site_config is not None else TASK_SITE_CONFIG,
        ),
        item=CopierUpdateItem(
            repository_ref=repository_ref,
            template_update=CopierTemplateUpdate(
                template_repository=RepositoryRef(
                    owner=template_owner,
                    name=template_name,
                ),
                sorted_newer_tags=["v1.1.0", "v1.2.0"],
                src_path=src_path,
                github_server_host=github_server_host,
                copier_answers_content=copier_answers_content,
            ),
        ),
        options=UpdateOptions(),
    ).run()

    return TaskRun(outcome, checkout, github_client, logger)
