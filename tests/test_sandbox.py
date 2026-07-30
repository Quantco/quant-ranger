import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from quant_ranger._impl.helpers import CommandError, ExecOutput
from quant_ranger._impl.sandbox import get_sandboxed_exec_output_silently


def test_get_sandboxed_exec_output_silently_wraps_rattler_sandbox(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    read_path = tmp_path / "read"
    write_path = tmp_path / "write"
    exec_path = tmp_path / "exec"
    tool_dir = tmp_path / "bin"
    for path in (repo, read_path, write_path, exec_path, tool_dir):
        path.mkdir(parents=True)

    tool = tool_dir / "tool"
    tool.write_text("", encoding="utf-8")
    tool.chmod(0o755)

    captured_command: list[str] | None = None
    captured_kwargs: dict[str, Any] | None = None

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        nonlocal captured_command, captured_kwargs
        captured_command = command
        captured_kwargs = kwargs
        return SimpleNamespace(returncode=0, stdout="stdout", stderr="")

    monkeypatch.setenv("PATH", str(tool_dir))
    monkeypatch.setattr("subprocess.run", fake_run)

    output = get_sandboxed_exec_output_silently(
        ["tool", "arg"],
        cwd=repo,
        read_paths=[read_path],
        read_write_paths=[write_path],
        read_exec_paths=[exec_path],
        sandbox_executable="/tools/rattler-sandbox",
        network=True,
        timeout=12,
    )

    assert output == ExecOutput(exit_code=0, stdout="stdout", stderr="")
    assert captured_command is not None
    assert captured_kwargs is not None
    assert captured_command[0] == "/tools/rattler-sandbox"
    assert captured_command[-3:] == ["--", str(tool.resolve()), "arg"]
    assert "--network" in captured_command
    assert captured_kwargs["cwd"] == repo.resolve()
    assert captured_kwargs["timeout"] == 12

    write_values = _flag_values(captured_command, "--fs-write-and-read")
    read_values = _flag_values(captured_command, "--fs-read")
    exec_values = _flag_values(captured_command, "--fs-exec-and-read")

    assert write_values == [str(write_path.resolve())]
    assert read_values == [str(repo.resolve()), str(read_path.resolve())]
    assert exec_values == [
        str(exec_path.resolve()),
        str(tool_dir.resolve()),
        _env_path(),
    ]


def test_get_sandboxed_exec_output_silently_passes_env_inside_sandbox(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool_dir = tmp_path / "bin"
    tool_dir.mkdir()
    tool = tool_dir / "tool"
    tool.write_text("", encoding="utf-8")
    tool.chmod(0o755)
    captured_command: list[str] | None = None

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        nonlocal captured_command
        captured_command = command
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setenv("PATH", str(tool_dir))
    monkeypatch.setattr("subprocess.run", fake_run)

    get_sandboxed_exec_output_silently(
        ["tool", "arg"],
        cwd=tmp_path,
        env={"CUSTOM": "value"},
    )

    assert captured_command is not None
    separator = captured_command.index("--")
    assert captured_command[separator + 1 : separator + 5] == [
        "/usr/bin/env",
        "CUSTOM=value",
        str(tool.resolve()),
        "arg",
    ]
    assert _flag_values(captured_command, "--fs-write-and-read") == []
    assert _flag_values(captured_command, "--fs-read") == [str(tmp_path.resolve())]
    assert _flag_values(captured_command, "--fs-exec-and-read") == [
        str(tool_dir.resolve()),
        _env_path(),
    ]


def test_get_sandboxed_exec_output_silently_forwards_proxy_inside_sandbox(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool_dir = tmp_path / "bin"
    tool_dir.mkdir()
    tool = tool_dir / "tool"
    tool.write_text("", encoding="utf-8")
    tool.chmod(0o755)
    captured_command: list[str] | None = None

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        nonlocal captured_command
        captured_command = command
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setenv("PATH", str(tool_dir))
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.setattr("subprocess.run", fake_run)

    get_sandboxed_exec_output_silently(
        ["tool", "arg"],
        cwd=tmp_path,
        env={"CUSTOM": "value"},
    )

    assert captured_command is not None
    separator = captured_command.index("--")
    assert captured_command[separator + 1 : separator + 6] == [
        "/usr/bin/env",
        "HTTPS_PROXY=http://proxy.example:8080",
        "CUSTOM=value",
        str(tool.resolve()),
        "arg",
    ]


def test_get_sandboxed_exec_output_silently_creates_fresh_tempdir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool_dir = tmp_path / "bin"
    tool_dir.mkdir()
    tool = tool_dir / "tool"
    tool.write_text("", encoding="utf-8")
    tool.chmod(0o755)
    captured_command: list[str] | None = None

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        nonlocal captured_command
        captured_command = command
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setenv("PATH", str(tool_dir))
    monkeypatch.setattr("subprocess.run", fake_run)

    get_sandboxed_exec_output_silently(["tool"], cwd=tmp_path, tempdir=True)

    assert captured_command is not None
    tempdir = _sandbox_tmpdir(captured_command)
    assert "quant-ranger-tmp-" in tempdir
    assert _flag_values(captured_command, "--fs-write-and-read") == [tempdir]
    assert _flag_values(captured_command, "--fs-read") == [str(tmp_path.resolve())]
    assert _flag_values(captured_command, "--fs-exec-and-read") == [
        str(tool_dir.resolve()),
        _env_path(),
    ]
    assert not Path(tempdir).exists()


def test_get_sandboxed_exec_output_silently_resolves_absolute_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = tmp_path / "bin" / "tool"
    tool.parent.mkdir()
    tool.write_text("", encoding="utf-8")
    tool.chmod(0o755)
    captured_command: list[str] | None = None

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        nonlocal captured_command
        captured_command = command
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    get_sandboxed_exec_output_silently([str(tool)], cwd=tmp_path)

    assert captured_command is not None
    assert captured_command[-1] == str(tool.resolve())
    assert _flag_values(captured_command, "--fs-write-and-read") == []
    assert _flag_values(captured_command, "--fs-read") == [str(tmp_path.resolve())]
    assert _flag_values(captured_command, "--fs-exec-and-read") == [
        str(tool.parent.resolve()),
        _env_path(),
    ]


def test_get_sandboxed_exec_output_silently_resolves_command_relative_to_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = tmp_path / "bin" / "tool"
    tool.parent.mkdir()
    tool.write_text("", encoding="utf-8")
    tool.chmod(0o755)
    captured_command: list[str] | None = None

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        nonlocal captured_command
        captured_command = command
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    get_sandboxed_exec_output_silently([f".{os.sep}bin{os.sep}tool"], cwd=tmp_path)

    assert captured_command is not None
    assert captured_command[-1] == str(tool.resolve())
    assert _flag_values(captured_command, "--fs-write-and-read") == []
    assert _flag_values(captured_command, "--fs-read") == [str(tmp_path.resolve())]
    assert _flag_values(captured_command, "--fs-exec-and-read") == [
        str(tool.parent.resolve()),
        _env_path(),
    ]


def test_get_sandboxed_exec_output_silently_deduplicates_sandbox_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool_dir = tmp_path / "bin"
    tool_dir.mkdir()
    tool = tool_dir / "tool"
    tool.write_text("", encoding="utf-8")
    tool.chmod(0o755)
    write_path = tmp_path / "write"
    write_path.mkdir()
    captured_command: list[str] | None = None

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        nonlocal captured_command
        captured_command = command
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setenv("PATH", str(tool_dir))
    monkeypatch.setattr("subprocess.run", fake_run)

    get_sandboxed_exec_output_silently(
        ["tool"],
        cwd=tmp_path,
        read_write_paths=[write_path, write_path],
    )

    assert captured_command is not None
    assert _flag_values(captured_command, "--fs-write-and-read") == [
        str(write_path.resolve())
    ]
    assert _flag_values(captured_command, "--fs-read") == [str(tmp_path.resolve())]
    assert _flag_values(captured_command, "--fs-exec-and-read") == [
        str(tool_dir.resolve()),
        _env_path(),
    ]


def test_get_sandboxed_exec_output_silently_requires_env_executable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = tmp_path / "tool"
    tool.write_text("", encoding="utf-8")
    tool.chmod(0o755)
    original_exists = Path.exists

    def fake_exists(self: Path, **kwargs: Any) -> bool:
        if str(self) == "/usr/bin/env":
            return False
        return original_exists(self, **kwargs)

    monkeypatch.setattr(Path, "exists", fake_exists)

    with pytest.raises(CommandError, match="/usr/bin/env could not be resolved"):
        get_sandboxed_exec_output_silently(
            [str(tool)],
            cwd=tmp_path,
            env={"CUSTOM": "value"},
        )


def test_get_sandboxed_exec_output_silently_requires_command() -> None:
    with pytest.raises(ValueError, match="command must not be empty"):
        get_sandboxed_exec_output_silently([])


def test_get_sandboxed_exec_output_silently_reports_unresolved_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))

    with pytest.raises(CommandError) as error_info:
        get_sandboxed_exec_output_silently(["missing-tool"], cwd=tmp_path)

    assert error_info.value.output == ExecOutput(
        exit_code=127,
        stdout="",
        stderr="No such file or directory: missing-tool",
    )
    assert "could not be resolved" in str(error_info.value)


def _flag_values(command: list[str], flag: str) -> list[str]:
    return [
        value
        for option, value in zip(command, command[1:], strict=False)
        if option == flag
    ]


def _sandbox_tmpdir(command: list[str]) -> str:
    separator = command.index("--")
    env_index = command.index("/usr/bin/env", separator + 1)
    return command[env_index + 1].removeprefix("TMPDIR=")


def _env_path() -> str:
    return str(Path("/usr/bin/env").resolve())
