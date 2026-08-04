import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
import tomlkit
from pydantic import ValidationError
from tomlkit.exceptions import ParseError

from quant_ranger._impl.github import GitHubClient, PullRequestOptions
from quant_ranger._impl.helpers import CommandError, ExecOutput
from quant_ranger._impl.logger import LogLevel, PrefixLogger
from quant_ranger._impl.models import (
    RepositoryRef,
    Schedule,
    Status,
    UpdateResult,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.testing import (
    FakeGitHubClient,
    FakeKeychain,
    RecordingCheckout,
    RecordingLogger,
)
from quant_ranger._impl.updaters import PixiUpdateUpdater
from quant_ranger._impl.updaters._pixi_update import _auth as pixi_auth
from quant_ranger._impl.updaters._pixi_update import _update as pixi_update
from quant_ranger._impl.updaters._pixi_update._update import (
    MAX_PULL_REQUEST_BODY_LENGTH,
    PIXI_UPDATE_TIMEOUT_SECONDS,
    PixiManifest,
    PixiUpdateItem,
    PixiUpdateOptions,
    truncate_pull_request_body,
)
from quant_ranger.site_config import SiteConfig


def parse_pixi_manifest(contents: str) -> PixiManifest:
    try:
        parsed = tomlkit.parse(contents).unwrap()
        return PixiManifest.model_validate(parsed)
    except (ValidationError, ParseError) as error:
        raise ValueError(f"Invalid pixi.toml: {error}") from error


def _pixi_update_updater() -> PixiUpdateUpdater:
    return PixiUpdateUpdater(PixiUpdateOptions())


@pytest.fixture(autouse=True)
def pixi_sandbox_paths(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> dict[str, Path]:
    cache = tmp_path / "rattler-cache"
    auth = tmp_path / ".rattler" / "credentials.json"
    auth.parent.mkdir()
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    if "real_pixi_info" not in request.keywords:
        monkeypatch.setattr(
            "quant_ranger._impl.updaters._pixi_update._update._pixi_info",
            lambda: {
                "cache_dir": str(cache),
                "auth_dir": str(auth),
                "config_locations": [],
            },
        )
    return {"auth": auth, "cache": cache}


def test_parse_manifest_uses_defaults_without_section() -> None:
    manifest = parse_pixi_manifest(
        """
        [project]
        platforms = ["linux-64"]
        """
    )
    config = manifest.tool.update

    assert config.autoupdate_branch_prefix == "pixi-update"
    assert config.autoupdate_commit_message == "chore: Update pixi lockfile"
    assert config.autoupdate_pull_request_labels == ["dependencies"]
    assert config.autoupdate_schedule == "monthly"
    assert config.ignore_environments == []
    assert config.ignore_platforms == []
    assert list(manifest.environments) == ["default"]


def test_parse_manifest_reads_update_section() -> None:
    manifest = parse_pixi_manifest(
        """
        [tool.update]
        autoupdate-branch-prefix = "pixi-lock"
        autoupdate-commit-message = "chore: Bump pixi lock"
        autoupdate-pull-request-labels = ["dependencies", "pixi"]
        autoupdate-schedule = "weekly"
        ignore-environments = ["docs"]
        ignore-platforms = ["win-64"]
        """
    )
    config = manifest.tool.update

    assert config.autoupdate_branch_prefix == "pixi-lock"
    assert config.autoupdate_commit_message == "chore: Bump pixi lock"
    assert config.autoupdate_pull_request_labels == ["dependencies", "pixi"]
    assert config.autoupdate_schedule == Schedule.WEEKLY
    assert config.ignore_environments == ["docs"]
    assert config.ignore_platforms == ["win-64"]


def test_parse_manifest_rejects_invalid_toml() -> None:
    with pytest.raises(ValueError, match="Invalid pixi.toml"):
        parse_pixi_manifest("[")


def test_parse_manifest_rejects_invalid_update_config() -> None:
    with pytest.raises(ValueError, match="Invalid pixi.toml"):
        parse_pixi_manifest(
            """
            [tool.update]
            unknown = "field"
            """
        )


def test_truncate_pull_request_body_leaves_short_body_unchanged() -> None:
    body = "# Updates\n\n- bumped foo from 1.0 to 1.1\n"

    assert truncate_pull_request_body(body) == body


def test_truncate_pull_request_body_leaves_body_at_limit_unchanged() -> None:
    body = "a" * MAX_PULL_REQUEST_BODY_LENGTH

    assert truncate_pull_request_body(body) == body


def test_truncate_pull_request_body_keeps_oversized_body_within_limit() -> None:
    body = "a" * (MAX_PULL_REQUEST_BODY_LENGTH + 1_000)

    assert len(truncate_pull_request_body(body)) <= MAX_PULL_REQUEST_BODY_LENGTH


def test_truncate_pull_request_body_adds_warning_notice() -> None:
    result = truncate_pull_request_body("x" * (MAX_PULL_REQUEST_BODY_LENGTH + 1))

    assert result.startswith("> [!WARNING]")
    assert f"{MAX_PULL_REQUEST_BODY_LENGTH} characters" in result


def test_truncate_pull_request_body_appends_truncation_marker() -> None:
    result = truncate_pull_request_body("x" * (MAX_PULL_REQUEST_BODY_LENGTH + 1))

    assert result.endswith("*... (truncated)*")


def test_truncate_pull_request_body_truncates_at_line_boundary() -> None:
    long_line = "word " * 20_000
    body = f"intact line\n{long_line}"

    result = truncate_pull_request_body(body)

    assert "intact line" in result
    assert "word word" not in result


def test_pixi_update_creates_pull_request_for_nested_lockfile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    project = write_pixi_project(
        tmp_path,
        directory="subproject",
        config="""
        autoupdate-branch-prefix = "pixi-lock"
        autoupdate-commit-message = "chore: Bump pixi lock"
        autoupdate-pull-request-labels = ["dependencies", "pixi"]
        ignore-environments = ["docs"]
        ignore-platforms = ["win-64"]
        """,
        environments=["default", "docs", "lint"],
        platforms=["linux-64", "osx-arm64", "win-64"],
    )
    command_calls: list[dict[str, Any]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        command_calls.append({"command": command, **kwargs})
        if command[0] == "pixi":
            return ExecOutput(exit_code=0, stdout='{"changed": true}', stderr="")
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        fake_exec,
    )
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_exec_output_silently",
        lambda command, **kwargs: ExecOutput(
            exit_code=0, stdout="### Updated packages\n", stderr=""
        ),
    )

    task_run = run_update_task(
        tmp_path,
        path="subproject/pixi.lock",
        branch="release",
        publish_changes=False,
    )

    assert task_run.result.result == Status.UPDATED
    assert task_run.checkout.added_paths == ["subproject/pixi.lock"]
    assert len(command_calls) == 1
    cache_dir = _assert_task_cache(command_calls[0])
    assert command_calls[0] == {
        "command": [
            "pixi",
            "update",
            "--no-progress",
            "--json",
            "--no-install",
            "--manifest-path",
            str(project / "pixi.toml"),
            "-e",
            "default",
            "-e",
            "lint",
            "-p",
            "linux-64",
            "-p",
            "osx-arm64",
        ],
        "cwd": project,
        "env": {
            "PIXI_CACHE_DIR": str(cache_dir),
            "HOME": os.environ["HOME"],
        },
        "read_exec_paths": (
            cache_dir,
            *pixi_update.MACOS_SANDBOX_PATHS.read_exec_paths,
        ),
        "logger": command_calls[0]["logger"],
        "network": True,
        "read_paths": (),
        "redact": (),
        "read_write_paths": (project, cache_dir),
        "timeout": PIXI_UPDATE_TIMEOUT_SECONDS,
        "tempdir": True,
    }
    task_logger = command_calls[0]["logger"]
    assert isinstance(task_logger, PrefixLogger)
    assert task_logger.logger is task_run.logger
    assert task_run.github_client.pull_request_calls == [
        {
            "checkout": task_run.checkout,
            "options": PullRequestOptions(
                title="chore: Bump pixi lock (subproject/pixi.lock)",
                body="### Updated packages",
                source_branch="pixi-lock/subproject/pixi.toml",
                target_branch="release",
                labels=["dependencies", "pixi"],
                quant_ranger_id="pixi-update",
            ),
            "logger": task_logger,
            "publish_changes": False,
        }
    ]


def test_pixi_update_extracts_keychain_credentials_before_sandbox(
    monkeypatch: pytest.MonkeyPatch,
    fake_keychain: FakeKeychain,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    write_pixi_project(
        tmp_path,
        channels=["https://conda.example.com/artifactory/api/conda/internal"],
    )
    auth_file_contents: list[dict[str, Any]] = []
    sandbox_calls: list[dict[str, Any]] = []
    requested_accounts = fake_keychain(
        {"conda.example.com": '{"BearerToken": "secret-token"}\n'}
    )

    def fake_sandbox_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        sandbox_calls.append({"command": command, **kwargs})
        auth_file = Path(kwargs["read_paths"][0])
        assert auth_file.exists()
        auth_file_contents.append(json.loads(auth_file.read_text()))
        return ExecOutput(exit_code=0, stdout="{}", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        fake_sandbox_exec,
    )

    task_run = run_update_task(tmp_path)

    assert task_run.result.result == Status.UP_TO_DATE
    assert requested_accounts == ["conda.example.com"]
    assert auth_file_contents == [
        {"conda.example.com": {"BearerToken": "secret-token"}}
    ]
    cache_dir = _assert_task_cache(sandbox_calls[0])
    assert sandbox_calls[0]["env"] == {
        "RATTLER_AUTH_FILE": str(sandbox_calls[0]["read_paths"][0]),
        "PIXI_CACHE_DIR": str(cache_dir),
        "HOME": os.environ["HOME"],
    }
    assert sandbox_calls[0]["redact"] == ("secret-token",)


def test_pixi_update_reads_keychain_once_for_update_all(
    monkeypatch: pytest.MonkeyPatch,
    fake_keychain: FakeKeychain,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    repository_ref = RepositoryRef(owner="quantco", name="example")
    write_pixi_project(
        tmp_path,
        channels=["https://one.example.com/conda"],
    )
    nested_project = write_pixi_project(
        tmp_path,
        directory="subproject",
        channels=["https://two.example.com/conda"],
    )
    auth_file_contents: list[dict[str, Any]] = []
    sandbox_calls: list[dict[str, Any]] = []
    requested_accounts = fake_keychain(
        {
            "one.example.com": '{"BearerToken": "one.example.com-token"}\n',
            "two.example.com": '{"BearerToken": "two.example.com-token"}\n',
        }
    )

    def fake_sandbox_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        sandbox_calls.append({"command": command, **kwargs})
        auth_file = Path(kwargs["read_paths"][0])
        assert auth_file.exists()
        auth_file_contents.append(json.loads(auth_file.read_text()))
        return ExecOutput(exit_code=0, stdout="{}", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        fake_sandbox_exec,
    )

    results = _pixi_update_updater().update_all(
        [
            PixiUpdateItem(
                repository_ref=repository_ref,
                path="pixi.lock",
                manifest=parse_pixi_manifest((tmp_path / "pixi.toml").read_text()),
            ),
            PixiUpdateItem(
                repository_ref=repository_ref,
                path="subproject/pixi.lock",
                manifest=parse_pixi_manifest(
                    (nested_project / "pixi.toml").read_text()
                ),
            ),
        ],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(
                GitHubClient,
                FakeGitHubClient(
                    checkout=RecordingCheckout(tmp_path, repository_ref),
                ),
            ),
            logger=RecordingLogger(),
        ),
    )

    assert [result.result for result in results] == [
        Status.UP_TO_DATE,
        Status.UP_TO_DATE,
    ]
    # The keychain is queried once for both manifests' hosts combined.
    assert requested_accounts == ["one.example.com", "two.example.com"]
    expected_auth_file_contents = {
        "one.example.com": {"BearerToken": "one.example.com-token"},
        "two.example.com": {"BearerToken": "two.example.com-token"},
    }
    assert auth_file_contents == [
        expected_auth_file_contents,
        expected_auth_file_contents,
    ]
    assert len(sandbox_calls) == 2
    assert sandbox_calls[0]["read_paths"] == sandbox_calls[1]["read_paths"]
    assert (
        sandbox_calls[0]["env"]["RATTLER_AUTH_FILE"]
        == sandbox_calls[1]["env"]["RATTLER_AUTH_FILE"]
    )
    assert _assert_task_cache(sandbox_calls[0]) != _assert_task_cache(sandbox_calls[1])
    assert sandbox_calls[0]["redact"] == (
        "one.example.com-token",
        "two.example.com-token",
    )


@pytest.mark.real_pixi_info
def test_pixi_info_parses_json_object(monkeypatch: pytest.MonkeyPatch) -> None:
    pixi_info_commands: list[list[str]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        del kwargs
        pixi_info_commands.append(command)
        return ExecOutput(
            exit_code=0,
            stdout='{"auth_dir": "/auth/credentials.json", "config_locations": []}',
            stderr="",
        )

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_exec_output_silently",
        fake_exec,
    )

    results = _pixi_update_updater().update_all(
        [],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, FakeGitHubClient()),
            logger=RecordingLogger(),
        ),
    )

    assert results == []
    assert pixi_info_commands == [["pixi", "info", "--json"]]


@pytest.mark.real_pixi_info
def test_pixi_info_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_exec_output_silently",
        lambda command: ExecOutput(exit_code=0, stdout="not json", stderr=""),
    )

    with pytest.raises(ValueError, match="did not return JSON"):
        _pixi_update_updater().update_all(
            [],
            RunContext(
                site_config=SiteConfig(),
                github_client=cast(GitHubClient, FakeGitHubClient()),
                logger=RecordingLogger(),
            ),
        )


@pytest.mark.real_pixi_info
def test_pixi_info_rejects_non_object_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_exec_output_silently",
        lambda command: ExecOutput(exit_code=0, stdout="[1, 2]", stderr=""),
    )

    with pytest.raises(ValueError, match="returned a non-object value"):
        _pixi_update_updater().update_all(
            [],
            RunContext(
                site_config=SiteConfig(),
                github_client=cast(GitHubClient, FakeGitHubClient()),
                logger=RecordingLogger(),
            ),
        )


def test_pixi_update_allows_reading_pixi_config_locations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    repository_ref = RepositoryRef(owner="quantco", name="example")
    write_pixi_project(tmp_path)
    config_location = tmp_path / ".pixi" / "config.toml"
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update._pixi_info",
        lambda: {"config_locations": [str(config_location)]},
    )
    sandbox_calls: list[dict[str, Any]] = []

    def fake_sandbox_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        sandbox_calls.append({"command": command, **kwargs})
        return ExecOutput(exit_code=0, stdout="{}", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        fake_sandbox_exec,
    )

    results = _pixi_update_updater().update_all(
        [
            PixiUpdateItem(
                repository_ref=repository_ref,
                path="pixi.lock",
                manifest=parse_pixi_manifest((tmp_path / "pixi.toml").read_text()),
            )
        ],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(
                GitHubClient,
                FakeGitHubClient(
                    checkout=RecordingCheckout(tmp_path, repository_ref),
                ),
            ),
            logger=RecordingLogger(),
        ),
    )

    assert [result.result for result in results] == [Status.UP_TO_DATE]
    assert sandbox_calls[0]["read_paths"] == (config_location,)


@pytest.mark.parametrize("config_locations", ["not-a-list", [42]])
def test_pixi_update_fails_on_invalid_config_locations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_locations: Any,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    repository_ref = RepositoryRef(owner="quantco", name="example")
    write_pixi_project(tmp_path)
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update._pixi_info",
        lambda: {"config_locations": config_locations},
    )

    with pytest.raises(
        ValueError,
        match="did not return a list of config_locations",
    ):
        _pixi_update_updater().update_all(
            [
                PixiUpdateItem(
                    repository_ref=repository_ref,
                    path="pixi.lock",
                    manifest=parse_pixi_manifest((tmp_path / "pixi.toml").read_text()),
                )
            ],
            RunContext(
                site_config=SiteConfig(),
                github_client=cast(GitHubClient, FakeGitHubClient()),
                logger=RecordingLogger(),
            ),
        )


def test_pixi_update_home_fails_with_clear_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delenv("HOME", raising=False)
    write_pixi_project(tmp_path)
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        lambda command, **kwargs: pytest.fail("pixi update should not run"),
    )

    task_run = run_update_task(tmp_path)

    assert task_run.result.result == Status.FAILURE
    assert task_run.result.message == (
        "Pixi update requires the HOME environment variable to be set."
    )


def test_pixi_update_warns_for_missing_keychain_hosts_and_continues(
    monkeypatch: pytest.MonkeyPatch,
    fake_keychain: FakeKeychain,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    repository_ref = RepositoryRef(owner="quantco", name="example")
    write_pixi_project(
        tmp_path,
        channels=[
            "https://conda.example.com/artifactory/api/conda/internal",
            "https://repo.prefix.dev/example",
        ],
    )
    auth_file_contents: list[dict[str, Any]] = []
    sandbox_calls: list[dict[str, Any]] = []
    logger = RecordingLogger()
    fake_keychain({"conda.example.com": '{"BearerToken": "secret-token"}\n'})

    def fake_sandbox_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        sandbox_calls.append({"command": command, **kwargs})
        auth_file_contents.append(json.loads(Path(kwargs["read_paths"][0]).read_text()))
        return ExecOutput(exit_code=0, stdout="{}", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        fake_sandbox_exec,
    )

    results = _pixi_update_updater().update_all(
        [
            PixiUpdateItem(
                repository_ref=repository_ref,
                path="pixi.lock",
                manifest=parse_pixi_manifest((tmp_path / "pixi.toml").read_text()),
            )
        ],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(
                GitHubClient,
                FakeGitHubClient(
                    checkout=RecordingCheckout(tmp_path, repository_ref),
                ),
            ),
            logger=logger,
        ),
    )

    assert [result.result for result in results] == [Status.UP_TO_DATE]
    assert auth_file_contents == [
        {"conda.example.com": {"BearerToken": "secret-token"}}
    ]
    assert sandbox_calls[0]["read_paths"]
    assert sandbox_calls[0]["redact"] == ("secret-token",)
    assert logger.warnings == [
        "Could not find Pixi auth credentials for repo.prefix.dev; "
        "continuing without them."
    ]


def test_pixi_update_reads_rattler_credentials_file_without_keychain_token(
    monkeypatch: pytest.MonkeyPatch,
    fake_keychain: FakeKeychain,
    pixi_sandbox_paths: dict[str, Path],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    write_pixi_project(
        tmp_path,
        channels=["https://conda.example.com/artifactory/api/conda/internal"],
    )
    pixi_sandbox_paths["auth"].write_text(
        json.dumps({"conda.example.com": {"BearerToken": "file-token"}})
    )
    sandbox_calls: list[dict[str, Any]] = []
    fake_keychain({})

    def fake_sandbox_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        sandbox_calls.append({"command": command, **kwargs})
        return ExecOutput(exit_code=0, stdout="{}", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        fake_sandbox_exec,
    )

    task_run = run_update_task(tmp_path)

    assert task_run.result.result == Status.UP_TO_DATE
    cache_dir = _assert_task_cache(sandbox_calls[0])
    assert sandbox_calls[0]["env"] == {
        "RATTLER_AUTH_FILE": str(pixi_sandbox_paths["auth"]),
        "PIXI_CACHE_DIR": str(cache_dir),
        "HOME": os.environ["HOME"],
    }
    assert sandbox_calls[0]["read_paths"] == (pixi_sandbox_paths["auth"],)
    assert sandbox_calls[0]["redact"] == ()
    assert task_run.logger.logged(
        LogLevel.DEBUG,
        f"Using rattler credentials file for Pixi auth: {pixi_sandbox_paths['auth']}.",
    )


@pytest.mark.parametrize(
    "host",
    [
        "prefix.dev",
        "repo.wildcard-prefix.dev",
        "otherhost.com",
        "conda.anaconda.org",
    ],
)
def test_pixi_update_accepts_supported_rattler_credentials_file_shapes(
    host: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    auth_file = (tmp_path / "credentials.json").resolve()
    auth_file.write_text(
        json.dumps(
            {
                "prefix.dev": {
                    "BearerToken": "your_token",
                },
                "*.wildcard-prefix.dev": {
                    "BearerToken": "your_wildcard_token",
                },
                "otherhost.com": {
                    "BasicHTTP": {
                        "username": "your_username",
                        "password": "your_password",
                    },
                },
                "conda.anaconda.org": {
                    "CondaToken": "your_token",
                },
            }
        )
    )
    logger = RecordingLogger()

    auth = pixi_auth.prepare_sandbox_auth(
        [host],
        logger,
        tempdir=tmp_path,
        pixi_info={"auth_dir": str(auth_file)},
    )

    assert auth == pixi_auth.SandboxAuth(
        credential_read_paths=(auth_file,),
        credential_env={"RATTLER_AUTH_FILE": str(auth_file)},
    )
    assert logger.warnings == []


def test_parse_manifest_reads_table_channels(
    monkeypatch: pytest.MonkeyPatch,
    fake_keychain: FakeKeychain,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    repository_ref = RepositoryRef(owner="quantco", name="example")
    manifest = parse_pixi_manifest(
        """
        [workspace]
        platforms = ["linux-64"]
        channels = [
          { channel = "https://conda.example.com/artifactory/api/conda/internal", exclude-newer = "0d" },
          { priority = 1 },
          "conda-forge",
        ]

        [feature.cuda]
        channels = [
          "https://cuda.prefix.dev/channel",
          "https://conda.example.com/artifactory/api/conda/duplicate",
        ]

        [feature.docs]
        channels = ["https://docs.prefix.dev/channel"]

        [package]
        name = "example"
        version = "0.1.0"

        [package.build]
        backend = { name = "pixi-build-python", version = "0.*" }
        channels = ["https://build.prefix.dev/channel"]
        """
    )
    requested_accounts = fake_keychain({})
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        lambda command, **kwargs: ExecOutput(exit_code=0, stdout="{}", stderr=""),
    )

    _pixi_update_updater().update_all(
        [
            PixiUpdateItem(
                repository_ref=repository_ref,
                path="pixi.lock",
                manifest=manifest,
            )
        ],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(
                GitHubClient,
                FakeGitHubClient(
                    checkout=RecordingCheckout(tmp_path, repository_ref),
                ),
            ),
            logger=RecordingLogger(),
        ),
    )

    # The keychain fake records every candidate account (host plus wildcard
    # fallbacks); the exact entries are the manifest's channel hosts, deduplicated.
    assert [
        account for account in requested_accounts if not account.startswith("*.")
    ] == [
        "conda.example.com",
        "cuda.prefix.dev",
        "docs.prefix.dev",
        "build.prefix.dev",
    ]


def test_pixi_update_updater_requires_prepared_auth_for_tasks(
    tmp_path: Path,
) -> None:
    repository_ref = RepositoryRef(owner="quantco", name="example")
    write_pixi_project(tmp_path)

    with pytest.raises(RuntimeError, match="auth has not been prepared"):
        _pixi_update_updater().make_task(
            PixiUpdateItem(
                repository_ref=repository_ref,
                path="pixi.lock",
                manifest=parse_pixi_manifest((tmp_path / "pixi.toml").read_text()),
            ),
            RecordingCheckout(tmp_path, repository_ref),
            RunContext(
                site_config=SiteConfig(),
                github_client=cast(GitHubClient, FakeGitHubClient()),
                logger=RecordingLogger(),
            ),
        )


def test_pixi_update_warns_and_continues_without_auth_credentials(
    monkeypatch: pytest.MonkeyPatch,
    fake_keychain: FakeKeychain,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    write_pixi_project(
        tmp_path,
        channels=["https://conda.example.com/artifactory/api/conda/internal"],
    )

    fake_keychain({})
    sandbox_calls: list[dict[str, Any]] = []

    def fake_sandbox_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        sandbox_calls.append({"command": command, **kwargs})
        return ExecOutput(exit_code=0, stdout="{}", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        fake_sandbox_exec,
    )

    task_run = run_update_task(tmp_path)

    assert task_run.result.result == Status.UP_TO_DATE
    _assert_task_cache(sandbox_calls[0])
    assert "RATTLER_AUTH_FILE" not in sandbox_calls[0]["env"]
    assert sandbox_calls[0]["read_paths"] == ()
    assert task_run.logger.logged(
        LogLevel.DEBUG, "No rattler credentials file found at "
    )
    assert task_run.logger.logged(
        LogLevel.WARNING, "Could not find Pixi auth credentials for conda.example.com"
    )


def test_pixi_update_forwards_ssl_cert_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    write_pixi_project(tmp_path)
    cert_target = tmp_path / "ca-bundle.pem"
    cert_target.write_text("certificate")
    cert_link = tmp_path / "cert-link.pem"
    cert_link.symlink_to(cert_target)
    monkeypatch.setenv("SSL_CERT_FILE", str(cert_link))
    sandbox_calls: list[dict[str, Any]] = []

    def fake_sandbox_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        sandbox_calls.append({"command": command, **kwargs})
        return ExecOutput(exit_code=0, stdout="{}", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        fake_sandbox_exec,
    )

    task_run = run_update_task(tmp_path)

    assert task_run.result.result == Status.UP_TO_DATE
    assert sandbox_calls[0]["env"]["SSL_CERT_FILE"] == str(cert_link)
    assert cert_link in sandbox_calls[0]["read_paths"]
    assert cert_target in sandbox_calls[0]["read_paths"]


def test_pixi_update_sandbox_paths_skip_linux_paths_on_macos(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    write_pixi_project(tmp_path)
    sandbox_calls: list[dict[str, Any]] = []

    def fake_sandbox_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        sandbox_calls.append({"command": command, **kwargs})
        return ExecOutput(exit_code=0, stdout="{}", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        fake_sandbox_exec,
    )

    run_update_task(tmp_path)

    cache_dir = Path(sandbox_calls[0]["env"]["PIXI_CACHE_DIR"])
    assert sandbox_calls[0]["read_exec_paths"] == (
        cache_dir,
        Path("/bin"),
        Path("/usr/bin"),
    )
    assert sandbox_calls[0]["read_paths"] == ()


def test_pixi_update_sandbox_paths_include_linux_paths_on_linux(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    write_pixi_project(tmp_path)
    sandbox_calls: list[dict[str, Any]] = []

    def fake_sandbox_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        sandbox_calls.append({"command": command, **kwargs})
        return ExecOutput(exit_code=0, stdout="{}", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        fake_sandbox_exec,
    )

    run_update_task(tmp_path)

    cache_dir = Path(sandbox_calls[0]["env"]["PIXI_CACHE_DIR"])
    assert sandbox_calls[0]["read_exec_paths"] == (
        cache_dir,
        Path("/bin"),
        Path("/usr/bin"),
        Path("/lib"),
        Path("/lib64"),
        Path("/usr/lib"),
        Path("/usr/lib64"),
    )
    assert sandbox_calls[0]["read_paths"] == (
        Path("/etc/ld.so.cache"),
        Path("/etc/resolv.conf"),
        Path("/etc/hosts"),
        Path("/dev/urandom"),
        Path("/dev/random"),
        Path("/etc/ssl"),
        Path("/etc/pki"),
        Path("/var/lib/ca-certificates"),
        Path("/etc/ca-certificates"),
    )
    assert Path("/dev/null") in sandbox_calls[0]["read_write_paths"]


def test_pixi_update_sandbox_paths_fail_on_unknown_platform(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd")
    write_pixi_project(tmp_path)

    task_run = run_update_task(tmp_path)

    assert task_run.result.result == Status.FAILURE
    assert task_run.result.message == (
        "Pixi update sandboxing is not supported on 'freebsd'."
    )


def test_pixi_update_creates_root_pull_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    write_pixi_project(
        tmp_path,
        config='autoupdate-commit-message = "chore: Bump pixi lock"',
    )

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        del kwargs
        return ExecOutput(exit_code=0, stdout='{"changed": true}', stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        fake_exec,
    )
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_exec_output_silently",
        lambda command, **kwargs: ExecOutput(
            exit_code=0, stdout="### Updated packages\n", stderr=""
        ),
    )

    task_run = run_update_task(tmp_path)

    assert task_run.result.result == Status.UPDATED
    assert task_run.github_client.pull_request_calls[0]["options"].title == (
        "chore: Bump pixi lock"
    )


def test_pixi_update_truncates_oversized_pull_request_body(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    write_pixi_project(tmp_path)
    updates = "### Updated packages\n" + ("a" * MAX_PULL_REQUEST_BODY_LENGTH)

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        lambda command, **kwargs: ExecOutput(
            exit_code=0, stdout='{"changed": true}', stderr=""
        ),
    )
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_exec_output_silently",
        lambda command, **kwargs: ExecOutput(exit_code=0, stdout=updates, stderr=""),
    )

    task_run = run_update_task(tmp_path)

    options = cast(
        PullRequestOptions,
        task_run.github_client.pull_request_calls[0]["options"],
    )
    assert options.body.startswith("> [!WARNING]")
    assert len(options.body) <= MAX_PULL_REQUEST_BODY_LENGTH
    assert options.body.endswith("*... (truncated)*")


def test_pixi_update_skips_when_pull_request_was_not_created(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    write_pixi_project(tmp_path)

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        del kwargs
        return ExecOutput(exit_code=0, stdout='{"changed": true}', stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        fake_exec,
    )
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_exec_output_silently",
        lambda command, **kwargs: ExecOutput(
            exit_code=0, stdout="### Updated packages\n", stderr=""
        ),
    )

    task_run = run_update_task(
        tmp_path, github_client=FakeGitHubClient(pr_opened=False)
    )

    assert task_run.result.result == Status.SKIPPED
    assert task_run.checkout.added_paths == ["pixi.lock"]


def test_pixi_update_returns_up_to_date_without_pull_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    write_pixi_project(tmp_path)
    command_calls: list[list[str]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        del kwargs
        command_calls.append(command)
        return ExecOutput(exit_code=0, stdout="{}", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        fake_exec,
    )

    task_run = run_update_task(tmp_path)

    assert task_run.result.result == Status.UP_TO_DATE
    assert command_calls == [
        [
            "pixi",
            "update",
            "--no-progress",
            "--json",
            "--no-install",
            "--manifest-path",
            str(tmp_path / "pixi.toml"),
        ]
    ]
    assert task_run.checkout.added_paths == []
    assert task_run.github_client.pull_request_calls == []


def test_pixi_update_fails_when_pixi_update_command_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    write_pixi_project(tmp_path)

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        del kwargs
        output = ExecOutput(exit_code=1, stdout="", stderr="something went wrong")
        raise CommandError("pixi update failed", output)

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        fake_exec,
    )

    task_run = run_update_task(tmp_path)

    assert task_run.result.result == Status.FAILURE
    assert task_run.result.message == "pixi update failed"
    assert task_run.logger.errors == [
        "[quantco/example@main pixi.lock] failure: pixi update failed"
    ]
    assert task_run.checkout.added_paths == []
    assert task_run.github_client.pull_request_calls == []


def test_pixi_update_includes_default_environment_when_not_declared(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    write_pixi_project(
        tmp_path,
        config='ignore-environments = ["docs"]',
        environments=["docs", "lint"],
    )
    pixi_command: list[str] | None = None

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        nonlocal pixi_command
        del kwargs
        pixi_command = command
        return ExecOutput(exit_code=0, stdout="{}", stderr="")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        fake_exec,
    )

    task_run = run_update_task(tmp_path)

    assert task_run.result.result == Status.UP_TO_DATE
    assert pixi_command is not None
    assert pixi_command[-4:] == ["-e", "default", "-e", "lint"]


def test_pixi_update_rejects_platform_ignores_without_platform_section(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "pixi.toml").write_text(
        """
        [tool.update]
        ignore-platforms = ["win-64"]
        """
    )
    (tmp_path / "pixi.lock").write_text("")
    command_calls: list[list[str]] = []
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        lambda command, **kwargs: command_calls.append(command),
    )

    task_run = run_update_task(tmp_path)

    assert task_run.result.result == Status.FAILURE
    assert task_run.result.message is not None
    assert "either [project] or [workspace]" in task_run.result.message
    assert command_calls == []


def test_pixi_lockfile_scanner_emits_item_for_each_lockfile() -> None:
    repository = RepositoryRef(owner="quantco", name="with-lockfiles", branch="main")
    logger = RecordingLogger()

    items = _pixi_update_updater().scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(
                GitHubClient,
                FakeGitHubClient(
                    files={
                        "quantco/with-lockfiles": [
                            "pixi.lock",
                            "subproject/pixi.lock",
                        ],
                    },
                    file_contents={
                        "pixi.toml": """
                        [project]
                        platforms = ["linux-64"]
                        """,
                        "subproject/pixi.toml": """
                        [project]
                        platforms = ["osx-arm64"]

                        [tool.update]
                        autoupdate-commit-message = "chore: Bump nested lock"
                        """,
                    },
                ),
            ),
            logger=logger,
        ),
    )

    assert [
        (item.repository_ref, item.path.as_posix()) for item in items.update_items
    ] == [
        (repository, "pixi.lock"),
        (repository, "subproject/pixi.lock"),
    ]
    assert items.update_items[1].manifest.tool.update.autoupdate_commit_message == (
        "chore: Bump nested lock"
    )
    assert logger.logged(LogLevel.INFO, "Generated 2 update items.")


def test_pixi_lockfile_scanner_returns_no_items_without_lockfiles() -> None:
    repository = RepositoryRef(owner="quantco", name="without-lockfiles", branch="main")
    logger = RecordingLogger()

    items = _pixi_update_updater().scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(
                GitHubClient,
                FakeGitHubClient(files={"quantco/without-lockfiles": []}),
            ),
            logger=logger,
        ),
    )

    assert items.update_items == ()
    assert logger.logged(LogLevel.INFO, "Generated 0 update items.")


def test_pixi_lockfile_scanner_filters_schedule_mismatches() -> None:
    repository = RepositoryRef(owner="quantco", name="with-lockfiles", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        files={
            "quantco/with-lockfiles": [
                "pixi.lock",
                "subproject/pixi.lock",
            ],
        },
        file_contents={
            "pixi.toml": """
            [tool.update]
            autoupdate-schedule = "monthly"
            """,
            "subproject/pixi.toml": """
            [tool.update]
            autoupdate-schedule = "weekly"
            """,
        },
    )

    items = PixiUpdateUpdater(
        PixiUpdateOptions(schedule=Schedule.WEEKLY)
    ).scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert [
        (item.repository_ref, item.path.as_posix()) for item in items.update_items
    ] == [(repository, "subproject/pixi.lock")]
    assert items.update_items[0].manifest.tool.update.autoupdate_schedule == (
        Schedule.WEEKLY
    )
    assert github_client.file_content_calls == [
        (repository, "pixi.toml"),
        (repository, "subproject/pixi.toml"),
    ]
    assert logger.logged(
        LogLevel.DEBUG,
        "[quantco/with-lockfiles@main] Skipping pixi.lock: configured schedule "
        "is monthly; current scheduled run is weekly.",
    )


def test_pixi_lockfile_scanner_skips_never_without_schedule_filter() -> None:
    repository = RepositoryRef(owner="quantco", name="with-lockfiles", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        files={
            "quantco/with-lockfiles": [
                "pixi.lock",
                "subproject/pixi.lock",
            ],
        },
        file_contents={
            "pixi.toml": """
            [tool.update]
            autoupdate-schedule = "never"
            """,
            "subproject/pixi.toml": """
            [tool.update]
            autoupdate-schedule = "weekly"
            """,
        },
    )

    items = PixiUpdateUpdater(PixiUpdateOptions()).scanner.scan_all(
        [repository],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )

    assert [
        (item.repository_ref, item.path.as_posix()) for item in items.update_items
    ] == [(repository, "subproject/pixi.lock")]
    assert logger.logged(
        LogLevel.DEBUG,
        "[quantco/with-lockfiles@main] Skipping pixi.lock: configured schedule "
        "is never.",
    )


def test_pixi_lockfile_scanner_skips_missing_manifest() -> None:
    repository = RepositoryRef(owner="quantco", name="with-lockfile", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        files={"quantco/with-lockfile": ["pixi.lock"]},
    )

    items = _pixi_update_updater().scanner.scan_all(
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
        "[quantco/with-lockfile@main] Skipping pixi.lock: no pixi.toml found.",
    )


def test_pixi_lockfile_scanner_skips_invalid_manifest() -> None:
    repository = RepositoryRef(owner="quantco", name="with-lockfile", branch="main")
    logger = RecordingLogger()
    github_client = FakeGitHubClient(
        files={"quantco/with-lockfile": ["pixi.lock"]},
        file_contents={
            "pixi.toml": """
            [tool.update]
            unknown = "field"
            """,
        },
    )

    items = _pixi_update_updater().scanner.scan_all(
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
        LogLevel.ERROR,
        "[quantco/with-lockfile@main] Skipping pixi.lock: could not parse pixi manifest:",
    )


def test_pixi_update_updater_does_not_read_remote_manifest_without_schedule(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_ref = RepositoryRef(owner="quantco", name="example")
    write_pixi_project(tmp_path)
    github_client = FakeGitHubClient(
        checkout=RecordingCheckout(tmp_path, repository_ref),
    )
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_sandboxed_exec_output_silently",
        lambda command, **kwargs: ExecOutput(exit_code=0, stdout="{}", stderr=""),
    )

    results = _pixi_update_updater().update_all(
        [
            PixiUpdateItem(
                repository_ref=repository_ref,
                path="pixi.lock",
                manifest=parse_pixi_manifest((tmp_path / "pixi.toml").read_text()),
            )
        ],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=RecordingLogger(),
        ),
    )

    assert [result.result for result in results] == [Status.UP_TO_DATE]
    assert github_client.file_content_calls == []
    assert github_client.clone_calls == [repository_ref]


def write_pixi_project(
    tmp_path: Path,
    *,
    directory: str = ".",
    config: str = "",
    channels: list[str] | None = None,
    environments: list[str] | None = None,
    platforms: list[str] | None = None,
) -> Path:
    project = tmp_path if directory == "." else tmp_path / directory
    project.mkdir(parents=True, exist_ok=True)
    channels = channels or []
    environments = environments or []
    platforms = platforms or ["linux-64"]

    channel_list = ", ".join(f'"{channel}"' for channel in channels)
    channel_line = f"channels = [{channel_list}]" if channels else ""
    environment_sections = "\n".join(
        f"[environments.{environment}]\n" for environment in environments
    )
    platform_list = ", ".join(f'"{platform}"' for platform in platforms)
    (project / "pixi.toml").write_text(
        f"""
        [project]
        platforms = [{platform_list}]
        {channel_line}

        [tool.update]
        {config.strip()}

        {environment_sections}
        """
    )
    (project / "pixi.lock").write_text("")
    return project


def _assert_task_cache(call: dict[str, Any]) -> Path:
    cache_dir = Path(call["env"]["PIXI_CACHE_DIR"])

    assert call["timeout"] == PIXI_UPDATE_TIMEOUT_SECONDS
    assert call["env"]["HOME"] == os.environ["HOME"]
    assert call["read_exec_paths"] == (
        cache_dir,
        *pixi_update.MACOS_SANDBOX_PATHS.read_exec_paths,
    )
    assert cache_dir in call["read_write_paths"]
    return cache_dir


@dataclass
class TaskRun:
    result: UpdateResult
    checkout: RecordingCheckout
    github_client: FakeGitHubClient
    logger: RecordingLogger


def run_update_task(
    tmp_path: Path,
    *,
    path: str = "pixi.lock",
    branch: str | None = "main",
    publish_changes: bool = True,
    schedule: Schedule | None = None,
    github_client: FakeGitHubClient | None = None,
) -> TaskRun:
    repository_ref = RepositoryRef(owner="quantco", name="example", branch=branch)
    checkout = RecordingCheckout(tmp_path, repository_ref)
    github_client = github_client or FakeGitHubClient()
    github_client.publish_changes = publish_changes
    github_client.checkout = checkout
    logger = RecordingLogger()
    manifest_path = tmp_path / Path(path).parent / "pixi.toml"
    manifest = parse_pixi_manifest(manifest_path.read_text())

    results = PixiUpdateUpdater(PixiUpdateOptions(schedule=schedule)).update_all(
        [
            PixiUpdateItem(
                repository_ref=repository_ref,
                path=path,
                manifest=manifest,
            )
        ],
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
    )
    (result,) = results
    return TaskRun(result, checkout, github_client, logger)
