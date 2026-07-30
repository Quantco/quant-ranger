import os
import signal
import subprocess
import time
from pathlib import Path
from threading import Barrier, Event
from types import SimpleNamespace
from typing import Any

import pytest

import quant_ranger._impl.helpers as helpers_module
from quant_ranger._impl.helpers import (
    INTERRUPT_WARNING,
    SECOND_INTERRUPT_WARNING,
    CommandError,
    ExecOutput,
    app_tempdir,
    exit_via_sigint,
    get_exec_output_silently,
    map_concurrently,
    pluralize,
    redact_text,
    truncate_lines,
)
from quant_ranger._impl.testing import RecordingLogger


def test_redact_text_replaces_non_empty_secrets() -> None:
    assert redact_text("token=secret and other", ["secret", ""]) == (
        "token=*** and other"
    )


def test_app_tempdir_creates_and_removes_directory() -> None:
    with app_tempdir("quant-ranger-test-") as tmp:
        assert tmp.exists()
        path = tmp / "file.txt"
        path.write_text("hello", encoding="utf-8")

    assert not tmp.exists()


def test_map_concurrently_exits_on_second_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ForcedExitError(Exception):
        pass

    shutdown_calls: list[dict[str, object]] = []

    class InterruptingExecutor:
        def __init__(self, max_workers: int) -> None:
            self.max_workers = max_workers

        def submit(self, fn: Any, *args: Any) -> Any:
            del fn, args
            raise KeyboardInterrupt

        def shutdown(
            self,
            wait: bool = True,
            *,
            cancel_futures: bool = False,
        ) -> None:
            shutdown_calls.append({"wait": wait, "cancel_futures": cancel_futures})
            raise KeyboardInterrupt

    exit_calls = 0

    def fake_exit() -> None:
        nonlocal exit_calls
        exit_calls += 1
        raise ForcedExitError

    monkeypatch.setattr(helpers_module, "ThreadPoolExecutor", InterruptingExecutor)
    monkeypatch.setattr(helpers_module, "exit_via_sigint", fake_exit)
    logger = RecordingLogger()

    with pytest.raises(ForcedExitError):
        map_concurrently(
            lambda item: item,
            [1],
            concurrency=2,
            logger=logger,
            description="Interrupting",
        )

    assert shutdown_calls == [{"wait": True, "cancel_futures": True}]
    assert logger.warnings == [INTERRUPT_WARNING, SECOND_INTERRUPT_WARNING]
    assert exit_calls == 1


def test_exit_via_sigint_restores_default_handler_and_raises_sigint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raised_signals: list[int] = []
    monkeypatch.setattr(signal, "raise_signal", raised_signals.append)
    original_handler = signal.getsignal(signal.SIGINT)

    try:
        exit_via_sigint()

        assert signal.getsignal(signal.SIGINT) is signal.SIG_DFL
        assert raised_signals == [signal.SIGINT]
    finally:
        signal.signal(signal.SIGINT, original_handler)


def test_map_concurrently_propagates_keyboard_interrupt() -> None:
    barrier = Barrier(2)
    interrupted = Event()
    blocked_task_finished = Event()
    logger = RecordingLogger()

    def run_task(item: str) -> None:
        barrier.wait(timeout=5)
        if item == "interrupt":
            interrupted.set()
            raise KeyboardInterrupt
        assert interrupted.wait(timeout=5)
        blocked_task_finished.set()

    with pytest.raises(KeyboardInterrupt):
        map_concurrently(
            run_task,
            ["interrupt", "blocked"],
            concurrency=2,
            logger=logger,
            description="Interrupting",
        )

    assert logger.warnings == [INTERRUPT_WARNING]
    assert blocked_task_finished.is_set()


def test_map_concurrently_cancels_pending_items_when_one_fails() -> None:
    started_items: list[int] = []

    def run_task(item: int) -> None:
        started_items.append(item)
        if item == 0:
            raise RuntimeError("boom")
        time.sleep(0.01)

    with pytest.raises(RuntimeError, match="boom"):
        map_concurrently(
            run_task,
            list(range(100)),
            concurrency=1,
            logger=RecordingLogger(),
            description="Failing",
        )

    # The failure of the first item must cancel the remaining pending items
    # instead of running all of them.
    assert len(started_items) < 100


def test_get_exec_output_silently_returns_captured_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(returncode=0, stdout="stdout", stderr="stderr")

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: fake_run(**kwargs))

    output = get_exec_output_silently(["tool", "arg"], cwd=tmp_path)

    assert output == ExecOutput(exit_code=0, stdout="stdout", stderr="stderr")
    assert calls[0]["cwd"] == tmp_path
    assert calls[0]["env"] == {
        "PATH": os.environ.get("PATH", ""),
    }
    assert calls[0]["input"] is None
    assert calls[0]["capture_output"] is True
    assert calls[0]["check"] is False
    assert calls[0]["text"] is True
    assert calls[0]["timeout"] is None


def test_get_exec_output_silently_passes_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: fake_run(**kwargs))

    get_exec_output_silently(["tool"], input='{"changed": true}')

    assert calls[0]["input"] == '{"changed": true}'


def test_get_exec_output_silently_passes_explicit_env_with_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_env: dict[str, str] | None = None

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        nonlocal captured_env
        captured_env = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    get_exec_output_silently(["tool"], env={"CUSTOM": "value"})

    assert captured_env is not None
    assert captured_env == {
        "CUSTOM": "value",
        "PATH": os.environ.get("PATH", ""),
    }


def test_get_exec_output_silently_forwards_proxy_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_env: dict[str, str] | None = None

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        nonlocal captured_env
        captured_env = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("NO_PROXY", "github.example")
    monkeypatch.setenv("http_proxy", "http://lower.example:8080")

    get_exec_output_silently(["tool"], env={"CUSTOM": "value"})

    assert captured_env == {
        "CUSTOM": "value",
        "HTTPS_PROXY": "http://proxy.example:8080",
        "NO_PROXY": "github.example",
        "http_proxy": "http://lower.example:8080",
        "PATH": os.environ.get("PATH", ""),
    }


def test_get_exec_output_silently_prefers_explicit_env_over_proxy_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_env: dict[str, str] | None = None

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        nonlocal captured_env
        captured_env = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setenv("HTTPS_PROXY", "http://ambient.example:8080")

    get_exec_output_silently(["tool"], env={"HTTPS_PROXY": "http://explicit.example"})

    assert captured_env == {
        "HTTPS_PROXY": "http://explicit.example",
        "PATH": os.environ.get("PATH", ""),
    }


def test_get_exec_output_silently_logs_debug_output_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=0,
            stdout="stdout secret\n",
            stderr="stderr secret\n",
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    logger = RecordingLogger()

    get_exec_output_silently(["tool", "secret"], logger=logger, redact=["secret"])

    assert logger.debug_messages == [
        "Command tool *** exited with code 0."
        "\nstdout:\n-------\nstdout ***"
        "\nstderr:\n-------\nstderr ***"
    ]


def test_get_exec_output_silently_raises_command_error_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=2,
            stdout="stdout secret\n",
            stderr="stderr secret\n",
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(CommandError) as error_info:
        get_exec_output_silently(["tool", "secret"], redact=["secret"])

    assert error_info.value.output == ExecOutput(
        exit_code=2,
        stdout="stdout secret\n",
        stderr="stderr secret\n",
    )
    assert str(error_info.value) == "Command tool *** exited with code 2."
    assert error_info.value.details == (
        "stdout:\n-------\nstdout ***\nstderr:\n-------\nstderr ***"
    )


def test_get_exec_output_silently_can_ignore_return_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(returncode=2, stdout="stdout", stderr="stderr")

    monkeypatch.setattr("subprocess.run", fake_run)

    output = get_exec_output_silently(["tool"], ignore_return_code=True)

    assert output == ExecOutput(exit_code=2, stdout="stdout", stderr="stderr")


@pytest.mark.parametrize(
    "returncode",
    [
        -int(signal.SIGINT),
        128 + int(signal.SIGINT),
    ],
)
@pytest.mark.parametrize("ignore_return_code", [False, True])
def test_get_exec_output_silently_propagates_sigint_return_code(
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    ignore_return_code: bool,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(returncode=returncode, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(KeyboardInterrupt):
        get_exec_output_silently(["tool"], ignore_return_code=ignore_return_code)


def test_get_exec_output_silently_wraps_os_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        raise OSError("missing executable")

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(CommandError) as error_info:
        get_exec_output_silently(["missing-tool"])

    assert error_info.value.output.exit_code == 127
    assert "could not be started" in str(error_info.value)
    assert "missing executable" in str(error_info.value)


def test_get_exec_output_silently_wraps_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        raise subprocess.TimeoutExpired(
            command,
            kwargs["timeout"],
            output=b"partial stdout",
            stderr=b"partial stderr",
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(CommandError) as error_info:
        get_exec_output_silently(["slow-tool"], timeout=60)

    assert error_info.value.output == ExecOutput(
        exit_code=124,
        stdout="partial stdout",
        stderr="partial stderr",
    )
    assert str(error_info.value) == "Command slow-tool timed out after 60 seconds."


def test_get_exec_output_silently_wraps_timeout_without_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(CommandError) as error_info:
        get_exec_output_silently(["slow-tool"], timeout=60)

    assert error_info.value.output == ExecOutput(
        exit_code=124,
        stdout="",
        stderr="",
    )


def test_pluralize_selects_noun_form_by_count() -> None:
    assert pluralize(1, "file") == "1 file"
    assert pluralize(0, "file") == "0 files"
    assert pluralize(2, "file") == "2 files"
    assert pluralize(1, "repository", "repositories") == "1 repository"
    assert pluralize(2, "repository", "repositories") == "2 repositories"


def test_truncate_lines_keeps_short_text_unchanged() -> None:
    text = "\n".join(f"line {index}" for index in range(10))

    assert truncate_lines(text, max_lines=10) == text


def test_truncate_lines_elides_middle_lines() -> None:
    text = "\n".join(f"line {index}" for index in range(20))

    truncated = truncate_lines(text, max_lines=10)

    lines = truncated.splitlines()
    assert lines[:5] == [f"line {index}" for index in range(5)]
    assert lines[5] == "[... 10 lines truncated ...]"
    assert lines[6:] == [f"line {index}" for index in range(15, 20)]
