import json
import sys
from pathlib import Path
from typing import Any

import pytest

from quant_ranger._impl.helpers import CommandError, ExecOutput
from quant_ranger._impl.logger import LogLevel
from quant_ranger._impl.testing import FakeKeychain, RecordingLogger
from quant_ranger._impl.updaters._pixi_update import _auth as pixi_auth


def test_prepare_sandbox_auth_returns_empty_without_channel_hosts(
    monkeypatch: pytest.MonkeyPatch,
    fake_keychain: FakeKeychain,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    requested_accounts = fake_keychain({})

    assert (
        pixi_auth.prepare_sandbox_auth(
            [],
            RecordingLogger(),
            tempdir=tmp_path,
            pixi_info={},
        )
        == pixi_auth.SandboxAuth()
    )
    assert requested_accounts == []


def test_prepare_sandbox_auth_skips_keychain_outside_macos(
    monkeypatch: pytest.MonkeyPatch,
    fake_keychain: FakeKeychain,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    requested_accounts = fake_keychain({})
    logger = RecordingLogger()

    auth = pixi_auth.prepare_sandbox_auth(
        ["conda.example.com"],
        logger,
        tempdir=tmp_path,
        pixi_info={"auth_dir": str(tmp_path / "missing-credentials.json")},
    )

    assert auth == pixi_auth.SandboxAuth()
    assert requested_accounts == []
    assert logger.logged(LogLevel.DEBUG, "No macOS Keychain available for Pixi auth.")


def test_prepare_sandbox_auth_uses_keychain_credentials(
    monkeypatch: pytest.MonkeyPatch,
    fake_keychain: FakeKeychain,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    logger = RecordingLogger()
    fake_keychain({"*.prefix.dev": '{"BearerToken": "secret-token"}\n'})

    auth = pixi_auth.prepare_sandbox_auth(
        ["repo.prefix.dev", "missing.example.com"],
        logger,
        tempdir=tmp_path,
        pixi_info={},
    )

    auth_file = (tmp_path / "credentials.json").resolve()
    assert auth == pixi_auth.SandboxAuth(
        credential_read_paths=(auth_file,),
        credential_env={"RATTLER_AUTH_FILE": str(auth_file)},
        redact=("secret-token",),
    )
    assert json.loads(auth_file.read_text()) == {
        "*.prefix.dev": {"BearerToken": "secret-token"}
    }
    assert logger.warnings == [
        "Could not find Pixi auth credentials for missing.example.com; "
        "continuing without them."
    ]


def test_prepare_sandbox_auth_uses_rattler_credentials_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    auth_file = (tmp_path / "credentials.json").resolve()
    auth_file.write_text(json.dumps({"*.prefix.dev": {"BearerToken": "token"}}))
    logger = RecordingLogger()

    auth = pixi_auth.prepare_sandbox_auth(
        ["repo.prefix.dev"],
        logger,
        tempdir=tmp_path,
        pixi_info={"auth_dir": str(auth_file)},
    )

    assert auth == pixi_auth.SandboxAuth(
        credential_read_paths=(auth_file,),
        credential_env={"RATTLER_AUTH_FILE": str(auth_file)},
    )
    assert logger.debug_messages == [
        "No macOS Keychain available for Pixi auth.",
        f"Using rattler credentials file for Pixi auth: {auth_file}.",
    ]


def test_read_macos_keychain_credentials_reads_credentials_and_reports_missing_hosts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    logger = RecordingLogger()
    security_calls: list[list[str]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        del kwargs
        security_calls.append(command)
        if command[5] == "with-token.example.com":
            return ExecOutput(
                exit_code=0,
                stdout='{"BearerToken": "secret-token"}\n',
                stderr="",
            )
        return ExecOutput(exit_code=44, stdout="", stderr="not found")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._auth.get_exec_output_silently",
        fake_exec,
    )

    auth = pixi_auth.prepare_sandbox_auth(
        ["with-token.example.com", "without-token.example.com"],
        logger,
        tempdir=tmp_path,
        pixi_info={},
    )

    auth_file = (tmp_path / "credentials.json").resolve()
    assert auth == pixi_auth.SandboxAuth(
        credential_read_paths=(auth_file,),
        credential_env={"RATTLER_AUTH_FILE": str(auth_file)},
        redact=("secret-token",),
    )
    assert json.loads(auth_file.read_text()) == {
        "with-token.example.com": {"BearerToken": "secret-token"}
    }
    assert security_calls == [
        [
            "security",
            "find-generic-password",
            "-s",
            "rattler",
            "-a",
            host,
            "-w",
        ]
        for host in (
            "with-token.example.com",
            "without-token.example.com",
            "*.without-token.example.com",
            "*.example.com",
            "*.com",
        )
    ]
    assert logger.debug_messages == [
        "Using Pixi auth credentials from macOS Keychain for with-token.example.com.",
        "No Pixi auth credentials found in macOS Keychain for without-token.example.com.",
    ]
    assert logger.warnings == [
        "Could not find Pixi auth credentials for without-token.example.com; "
        "continuing without them."
    ]


def test_read_macos_keychain_credentials_supports_wildcard_hosts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    logger = RecordingLogger()
    requested_accounts: list[str] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        del kwargs
        requested_accounts.append(command[5])
        if command[5] == "*.prefix.dev":
            return ExecOutput(
                exit_code=0,
                stdout='{"BearerToken": "wildcard-token"}\n',
                stderr="",
            )
        return ExecOutput(exit_code=44, stdout="", stderr="not found")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._auth.get_exec_output_silently",
        fake_exec,
    )

    auth = pixi_auth.prepare_sandbox_auth(
        ["repo.prefix.dev", "api.prefix.dev"],
        logger,
        tempdir=tmp_path,
        pixi_info={},
    )

    auth_file = (tmp_path / "credentials.json").resolve()
    assert auth == pixi_auth.SandboxAuth(
        credential_read_paths=(auth_file,),
        credential_env={"RATTLER_AUTH_FILE": str(auth_file)},
        redact=("wildcard-token",),
    )
    assert json.loads(auth_file.read_text()) == {
        "*.prefix.dev": {"BearerToken": "wildcard-token"}
    }
    assert requested_accounts == [
        "repo.prefix.dev",
        "*.repo.prefix.dev",
        "*.prefix.dev",
    ]
    assert logger.debug_messages == [
        "Using Pixi auth credentials from macOS Keychain for *.prefix.dev."
    ]


def test_read_macos_keychain_credentials_stops_when_security_command_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    logger = RecordingLogger()

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        raise CommandError(
            "security could not be started",
            ExecOutput(exit_code=127, stdout="", stderr=""),
        )

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._auth.get_exec_output_silently",
        fake_exec,
    )

    auth = pixi_auth.prepare_sandbox_auth(
        ["conda.example.com"],
        logger,
        tempdir=tmp_path,
        pixi_info={"auth_dir": str(tmp_path / "missing-credentials.json")},
    )

    assert auth == pixi_auth.SandboxAuth()
    assert logger.debug_messages[0] == "No macOS Keychain available for Pixi auth."


@pytest.mark.parametrize(
    ("secret", "credential"),
    [
        ("", None),
        ("   \n", None),
        ("plain-token\n", None),
        ('{"BearerToken": "bearer-token"}', {"BearerToken": "bearer-token"}),
        ('{"BearerToken": ""}', {"BearerToken": ""}),
        ('{"OtherKey": "value"}', {"OtherKey": "value"}),
        (
            '{"BasicHTTP": {"username": "", "password": ""}}',
            {"BasicHTTP": {"username": "", "password": ""}},
        ),
        ("{}", {}),
        ("[1, 2]", None),
    ],
)
def test_prepare_sandbox_auth_supports_keychain_secret_shapes(
    secret: str,
    credential: dict[str, Any] | None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        del kwargs
        if command[5] == "repo.example.com":
            return ExecOutput(exit_code=0, stdout=secret, stderr="")
        return ExecOutput(exit_code=44, stdout="", stderr="not found")

    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._auth.get_exec_output_silently",
        fake_exec,
    )

    auth = pixi_auth.prepare_sandbox_auth(
        ["repo.example.com"],
        RecordingLogger(),
        tempdir=tmp_path,
        pixi_info={"auth_dir": str(tmp_path / "missing-credentials.json")},
    )

    auth_file = (tmp_path / "credentials.json").resolve()
    if credential is None:
        assert auth == pixi_auth.SandboxAuth()
    else:
        assert auth.credential_read_paths == (auth_file,)
        assert json.loads(auth_file.read_text()) == {"repo.example.com": credential}


def test_prepare_sandbox_auth_redacts_nested_credential_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    secret = json.dumps(
        {
            "BearerToken": "token",
            "BasicHTTP": {
                "username": "user",
                "password": "password",
            },
            "empty": "",
            "none": None,
        }
    )
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._auth.get_exec_output_silently",
        lambda command, **kwargs: ExecOutput(exit_code=0, stdout=secret, stderr=""),
    )

    auth = pixi_auth.prepare_sandbox_auth(
        ["conda.example.com"],
        RecordingLogger(),
        tempdir=tmp_path,
        pixi_info={},
    )

    assert auth.redact == ("token", "user", "password")


def test_prepare_sandbox_auth_falls_back_to_home_credentials_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("RATTLER_AUTH_FILE", raising=False)
    logger = RecordingLogger()

    auth = pixi_auth.prepare_sandbox_auth(
        ["host-that-has-no-credentials.example.com"],
        logger,
        tempdir=tmp_path,
        pixi_info={},
    )

    home_auth_file = (Path.home() / ".rattler" / "credentials.json").resolve()
    assert auth == pixi_auth.SandboxAuth()
    assert logger.warnings == [
        "Could not find Pixi auth credentials for "
        "host-that-has-no-credentials.example.com in macOS Keychain or "
        f"{home_auth_file}."
    ]


def test_prepare_sandbox_auth_prefers_auth_file_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    auth_file = (tmp_path / "custom-auth.json").resolve()
    auth_file.write_text(json.dumps({"conda.example.com": {"BearerToken": "token"}}))
    monkeypatch.setenv("RATTLER_AUTH_FILE", str(auth_file))

    auth = pixi_auth.prepare_sandbox_auth(
        ["conda.example.com"],
        RecordingLogger(),
        tempdir=tmp_path,
        pixi_info={"auth_dir": "/ignored"},
    )

    assert auth == pixi_auth.SandboxAuth(
        credential_read_paths=(auth_file,),
        credential_env={"RATTLER_AUTH_FILE": str(auth_file)},
    )


@pytest.mark.parametrize("contents", ["not json", "[1, 2]"])
def test_prepare_sandbox_auth_rejects_invalid_credentials_file(
    contents: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    auth_file = tmp_path / "credentials.json"
    auth_file.write_text(contents)

    with pytest.raises(ValueError, match="Invalid rattler credentials file"):
        pixi_auth.prepare_sandbox_auth(
            ["conda.example.com"],
            RecordingLogger(),
            tempdir=tmp_path,
            pixi_info={"auth_dir": str(auth_file)},
        )


def test_prepare_sandbox_auth_matches_exact_credentials_file_hosts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    auth_file = (tmp_path / "credentials.json").resolve()
    auth_file.write_text(
        json.dumps(
            {
                "conda.example.com": {"BearerToken": "token"},
                "other.example.com": {"BearerToken": "token"},
            }
        )
    )
    logger = RecordingLogger()

    auth = pixi_auth.prepare_sandbox_auth(
        ["conda.example.com", "missing.example.com"],
        logger,
        tempdir=tmp_path,
        pixi_info={"auth_dir": str(auth_file)},
    )

    assert auth == pixi_auth.SandboxAuth(
        credential_read_paths=(auth_file,),
        credential_env={"RATTLER_AUTH_FILE": str(auth_file)},
    )
    assert logger.warnings == [
        "Could not find Pixi auth credentials for missing.example.com; "
        "continuing without them."
    ]


def test_prepare_sandbox_auth_matches_wildcard_credentials_file_hosts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    auth_file = (tmp_path / "credentials.json").resolve()
    auth_file.write_text(
        json.dumps(
            {
                "*.repo.prefix.dev": {"BearerToken": "deeper-token"},
                "*.prefix.dev": {"BearerToken": "token"},
                "*.example.com": {"BearerToken": "example-token"},
                "*.com": {"BearerToken": "broad-token"},
            }
        )
    )
    logger = RecordingLogger()

    auth = pixi_auth.prepare_sandbox_auth(
        [
            "repo.prefix.dev",
            "prefix.dev",
            "conda.example.com",
            "service.example.com",
        ],
        logger,
        tempdir=tmp_path,
        pixi_info={"auth_dir": str(auth_file)},
    )

    assert auth == pixi_auth.SandboxAuth(
        credential_read_paths=(auth_file,),
        credential_env={"RATTLER_AUTH_FILE": str(auth_file)},
    )
    assert logger.warnings == []
