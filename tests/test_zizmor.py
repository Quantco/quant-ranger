from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from quant_ranger._impl.github import GitHubClient, PullRequestOptions
from quant_ranger._impl.helpers import CommandError, ExecOutput
from quant_ranger._impl.logger import LogLevel
from quant_ranger._impl.models import RepositoryRef, Status, UpdateItem, UpdateOptions
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.testing import (
    FakeGitHubClient,
    RecordingCheckout,
    RecordingLogger,
)
from quant_ranger._impl.updaters._zizmor import ZizmorUpdateTask
from quant_ranger.site_config import DEFAULT_PULL_REQUEST_TEMPLATES, SiteConfig


def test_zizmor_skips_repositories_without_auditable_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        raise CommandError(
            "Command failed",
            ExecOutput(
                exit_code=3,
                stdout="",
                stderr=(
                    "fatal: no audit was performed\n"
                    "error: no inputs collected\n"
                    "collection yielded no auditable inputs\n"
                ),
            ),
        )

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._zizmor.get_exec_output_silently",
        fake_exec,
    )
    checkout = RecordingCheckout(tmp_path)
    logger = RecordingLogger()

    result = ZizmorUpdateTask(
        checkout,
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, FakeGitHubClient()),
            logger=logger,
        ),
        item=UpdateItem(
            repository_ref=RepositoryRef(
                owner="quantco",
                name="example",
                branch="main",
            )
        ),
        options=UpdateOptions(),
    ).run()

    assert result.result == Status.SKIPPED
    assert result.message == "No auditable zizmor inputs found."
    assert logger.debug_messages == [
        "Running zizmor to fix GitHub Actions findings.",
        "No auditable GitHub Actions workflow, action, or Dependabot config found.",
    ]
    assert logger.errors == []
    assert not checkout.clean_checked


def test_zizmor_reports_failure_when_command_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        raise CommandError(
            "zizmor failed",
            ExecOutput(exit_code=2, stdout="finding", stderr="traceback"),
        )

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._zizmor.get_exec_output_silently",
        fake_exec,
    )
    checkout = RecordingCheckout(tmp_path)
    logger = RecordingLogger()

    result = ZizmorUpdateTask(
        checkout,
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, FakeGitHubClient()),
            logger=logger,
        ),
        item=UpdateItem(
            repository_ref=RepositoryRef(
                owner="quantco",
                name="example",
                branch="main",
            )
        ),
        options=UpdateOptions(),
    ).run()

    assert result.result == Status.FAILURE
    assert result.message == "zizmor failed"
    assert logger.errors == []
    assert not checkout.clean_checked


def test_zizmor_returns_up_to_date_when_no_changes_are_made(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        return ExecOutput(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._zizmor.get_exec_output_silently",
        fake_exec,
    )
    checkout = RecordingCheckout(tmp_path, clean=True)
    logger = RecordingLogger()
    github_client = FakeGitHubClient()

    result = ZizmorUpdateTask(
        checkout,
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
        item=UpdateItem(
            repository_ref=RepositoryRef(
                owner="quantco",
                name="example",
                branch="main",
            )
        ),
        options=UpdateOptions(),
    ).run()

    assert result.result == Status.UP_TO_DATE
    assert checkout.clean_checked
    assert not checkout.added
    assert github_client.pull_request_calls == []
    assert logger.logged(
        LogLevel.DEBUG, "No changes detected. All findings are already resolved."
    )


def test_zizmor_creates_pull_request_for_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        return ExecOutput(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._zizmor.get_exec_output_silently",
        fake_exec,
    )
    checkout = RecordingCheckout(tmp_path, clean=False)
    logger = RecordingLogger()
    github_client = FakeGitHubClient(pr_opened=True, publish_changes=False)
    pull_request_template = replace(
        DEFAULT_PULL_REQUEST_TEMPLATES.zizmor,
        branch_prefix="zizmor-updater",
    )

    result = ZizmorUpdateTask(
        checkout,
        RunContext(
            site_config=SiteConfig(
                pull_request_templates=replace(
                    DEFAULT_PULL_REQUEST_TEMPLATES,
                    zizmor=pull_request_template,
                )
            ),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
        item=UpdateItem(
            repository_ref=RepositoryRef(
                owner="quantco",
                name="example",
                branch="main",
            )
        ),
        options=UpdateOptions(),
    ).run()

    assert result.result == Status.UPDATED
    assert checkout.added
    assert len(github_client.pull_request_calls) == 1
    call = github_client.pull_request_calls[0]
    assert call["checkout"] is checkout
    assert call["options"] == PullRequestOptions(
        title=pull_request_template.title,
        body=pull_request_template.body,
        source_branch="zizmor-updater",
        quant_ranger_id="zizmor",
    )
    assert "dependabot-cooldown" in call["options"].body
    assert call["logger"] is logger
    assert call["publish_changes"] is False


@pytest.mark.parametrize(
    ("api_url", "expected_gh_host"),
    [
        ("https://api.github.com", None),
        ("https://api.example.ghe.com", "example.ghe.com"),
        ("https://github.example.com/api/v3", "github.example.com"),
        ("https://api.internal.corp/api/v3", "api.internal.corp"),
    ],
)
def test_zizmor_sets_gh_host_for_github_enterprise(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    api_url: str,
    expected_gh_host: str | None,
) -> None:
    environments: list[dict[str, str]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        environments.append(kwargs["env"])
        return ExecOutput(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._zizmor.get_exec_output_silently",
        fake_exec,
    )
    checkout = RecordingCheckout(tmp_path, clean=True)

    result = ZizmorUpdateTask(
        checkout,
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, FakeGitHubClient(api_url=api_url)),
            logger=RecordingLogger(),
        ),
        item=UpdateItem(
            repository_ref=RepositoryRef(
                owner="quantco",
                name="example",
                branch="main",
            )
        ),
        options=UpdateOptions(),
    ).run()

    assert result.result == Status.UP_TO_DATE
    assert len(environments) == 1
    assert environments[0].get("GH_HOST") == expected_gh_host


def test_zizmor_skips_when_pull_request_has_manual_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        return ExecOutput(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._zizmor.get_exec_output_silently",
        fake_exec,
    )
    checkout = RecordingCheckout(tmp_path, clean=False)
    github_client = FakeGitHubClient(pr_opened=False)

    result = ZizmorUpdateTask(
        checkout,
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=RecordingLogger(),
        ),
        item=UpdateItem(
            repository_ref=RepositoryRef(
                owner="quantco",
                name="example",
                branch="main",
            )
        ),
        options=UpdateOptions(),
    ).run()

    assert result.result == Status.SKIPPED
    assert checkout.added
    assert len(github_client.pull_request_calls) == 1
