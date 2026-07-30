import os
import shlex
import signal
import subprocess
import tempfile
from collections.abc import Callable, Generator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from quant_ranger._impl.logger import Logger, progress

INTERRUPT_WARNING = (
    "Ctrl+C received; cancelling pending tasks and waiting for running tasks "
    "to finish. Press Ctrl+C again to exit immediately."
)
SECOND_INTERRUPT_WARNING = "Second Ctrl+C received; exiting immediately."

# subprocess.run reports signal termination as the negative signal number;
# shells and wrapper scripts report it as 128 + the signal number.
_SIGINT_EXIT_CODES = frozenset({-int(signal.SIGINT), 128 + int(signal.SIGINT)})


def exit_via_sigint() -> None:
    """Terminate the process by re-raising SIGINT with the default handler.

    Unlike exiting with code 130, the parent process observes a genuine signal death
    (shells still report it as exit code 130).
    """
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.raise_signal(signal.SIGINT)


def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    """Return `count` and the fitting noun form, e.g. `1 file` / `2 files`."""
    noun = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {noun}"


def truncate_lines(text: str, *, max_lines: int) -> str:
    """Keep the first and last lines of `text`, eliding the middle beyond
    `max_lines`."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    head_count = max_lines // 2
    tail_count = max_lines - head_count
    elided = len(lines) - head_count - tail_count
    return "\n".join(
        [
            *lines[:head_count],
            f"[... {pluralize(elided, 'line')} truncated ...]",
            *lines[-tail_count:],
        ]
    )


@dataclass(frozen=True, slots=True)
class ExecOutput:
    """Captured command result."""

    exit_code: int
    stdout: str
    stderr: str


class CommandError(RuntimeError):
    """Raised when a command exits unsuccessfully.

    The exception message is a one-line summary; the captured command output is
    formatted in `details`.
    """

    def __init__(
        self,
        message: str,
        output: ExecOutput,
        details: str | None = None,
    ) -> None:
        super().__init__(message)
        self.output = output
        self.details = details


class CliError(Exception):
    """Error that should be presented to a CLI user without a traceback."""


@contextmanager
def app_tempdir(prefix: str = "quant-ranger-") -> Generator[Path]:
    with tempfile.TemporaryDirectory(prefix=prefix) as tmp:
        yield Path(tmp)


def map_concurrently[ItemT, ResultT](
    fn: Callable[[ItemT], ResultT],
    items: Sequence[ItemT],
    *,
    concurrency: int,
    logger: Logger,
    description: str,
) -> list[ResultT]:
    """Run `fn` over `items` in a thread pool, collecting results in completion order as
    a progress bar advances.

    On Ctrl+C, pending items are cancelled and running ones are awaited before the
    `KeyboardInterrupt` propagates. A second Ctrl+C terminates the process immediately
    via SIGINT, skipping cleanup handlers such as temporary directory removal.
    """
    executor = ThreadPoolExecutor(max_workers=concurrency)
    shutdown_started = False
    try:
        results: list[ResultT] = []
        futures = [executor.submit(fn, item) for item in items]
        for future in progress(
            as_completed(futures),
            logger=logger,
            description=description,
            total=len(items),
        ):
            results.append(future.result())
        return results
    except KeyboardInterrupt:
        shutdown_started = True
        try:
            logger.warning(INTERRUPT_WARNING)
            executor.shutdown(wait=True, cancel_futures=True)
        except KeyboardInterrupt:
            logger.warning(SECOND_INTERRUPT_WARNING)
            exit_via_sigint()
        raise
    finally:
        # Cancelling pending futures only matters when an item raised; on
        # success all futures are already done.
        if not shutdown_started:
            executor.shutdown(wait=True, cancel_futures=True)


def redact_text(text: str, secrets: Sequence[str] = ()) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "***")
    return redacted


def _command_for_display(command: Sequence[str], secrets: Sequence[str]) -> str:
    return redact_text(shlex.join(command), secrets)


# Some clients use HTTP proxies; we need to forward the matching environment variables,
# otherwise we will not reach any external resources.
_PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)


def proxy_env() -> dict[str, str]:
    """Return the proxy-related environment variables set for this process."""
    return {
        name: value
        for name in _PROXY_ENV_VARS
        if (value := os.environ.get(name)) is not None
    }


def get_exec_output_silently(
    command: Sequence[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
    input: str | None = None,
    timeout: float | None = None,
    ignore_return_code: bool = False,
    logger: Logger | None = None,
    redact: Sequence[str] = (),
) -> ExecOutput:
    """Run a command quietly unless it fails or debug logging is enabled.

    The command runs with a minimal environment: `PATH` and the proxy variables
    are inherited from the current process (unless overridden via `env`), plus
    whatever `env` contains.
    """
    env = {**proxy_env(), **(env or {})}
    if "PATH" not in env:
        env["PATH"] = os.environ.get("PATH", "")
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=env,
            input=input,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        output = ExecOutput(
            exit_code=124,
            stdout=_timeout_output_to_text(error.stdout),
            stderr=_timeout_output_to_text(error.stderr),
        )
        display = _command_for_display(command, redact)
        timeout_display = f"{error.timeout:g}"
        msg = f"Command {display} timed out after {timeout_display} seconds."
        raise CommandError(
            msg, output, _command_output_details(output, redact=redact)
        ) from error
    except OSError as error:
        output = ExecOutput(exit_code=127, stdout="", stderr=str(error))
        display = _command_for_display(command, redact)
        msg = f"Command {display} could not be started: {error}"
        raise CommandError(msg, output) from error

    output = ExecOutput(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )

    if output.exit_code in _SIGINT_EXIT_CODES:
        raise KeyboardInterrupt

    display = _command_for_display(command, redact)
    msg = f"Command {display} exited with code {output.exit_code}."
    details = _command_output_details(output, redact=redact)

    failed = output.exit_code != 0 and not ignore_return_code
    if failed:
        raise CommandError(msg, output, details)

    if logger is not None:
        logger.debug(msg if details is None else f"{msg}\n{details}")

    return output


def _command_output_details(
    output: ExecOutput,
    *,
    redact: Sequence[str],
) -> str | None:
    stdout = redact_text(output.stdout.rstrip(), redact)
    stderr = redact_text(output.stderr.rstrip(), redact)
    sections: list[str] = []
    if stdout:
        sections.append(f"stdout:\n-------\n{stdout}")
    if stderr:
        sections.append(f"stderr:\n-------\n{stderr}")
    return "\n".join(sections) or None


def _timeout_output_to_text(output: bytes | None) -> str:
    if output is None:
        return ""
    return output.decode(errors="replace")
