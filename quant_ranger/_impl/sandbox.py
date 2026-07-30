import os
import shlex
import shutil
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from pathlib import Path

from quant_ranger._impl.helpers import (
    CommandError,
    ExecOutput,
    app_tempdir,
    get_exec_output_silently,
    proxy_env,
)
from quant_ranger._impl.logger import Logger


def get_sandboxed_exec_output_silently(
    command: Sequence[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
    input: str | None = None,
    timeout: float | None = None,
    ignore_return_code: bool = False,
    logger: Logger | None = None,
    redact: Sequence[str] = (),
    sandbox_executable: str | os.PathLike[str] = "rattler-sandbox",
    read_paths: Sequence[str | os.PathLike[str]] = (),
    read_write_paths: Sequence[str | os.PathLike[str]] = (),
    read_exec_paths: Sequence[str | os.PathLike[str]] = (),
    network: bool = False,
    tempdir: bool = False,
) -> ExecOutput:
    """Run a command quietly through ``rattler-sandbox``.

    The command runs from ``cwd`` or, if omitted, the current process
    directory. That directory is readable inside the sandbox; pass it via
    ``read_write_paths`` if the command needs to modify it. With ``tempdir=True``
    the command gets a fresh temporary directory that is read/write inside the
    sandbox and exported as ``TMPDIR``. Read/execute access is also granted to
    the resolved command executable. Environment overrides are applied inside
    the sandbox with ``/usr/bin/env`` because ``rattler-sandbox`` does not
    forward them.
    """
    if not command:
        raise ValueError("command must not be empty")

    effective_cwd = Path(cwd).resolve() if cwd is not None else Path.cwd()
    resolved_command = _resolve_command(command, cwd=effective_cwd)
    executable_dir = Path(resolved_command[0]).parent
    with ExitStack() as stack:
        # Proxy variables must be injected into the sandboxed command itself;
        # the sandboxer process environment is not forwarded.
        env = {**proxy_env(), **(env or {})} or None
        if tempdir:
            temp_path = stack.enter_context(
                app_tempdir(prefix="quant-ranger-tmp-")
            ).resolve()
            env = {"TMPDIR": str(temp_path), **(env or {})}
            read_write_paths = (*read_write_paths, temp_path)
        if env is not None:
            # Mind that the environment variables are still visible via /proc/<pid>/cmdline
            resolved_command = _apply_sandbox_env(resolved_command, env)
        sandbox_command = _rattler_sandbox_command(
            resolved_command,
            cwd=effective_cwd,
            env=env,
            sandbox_executable=sandbox_executable,
            read_paths=read_paths,
            read_write_paths=read_write_paths,
            read_exec_paths=(*read_exec_paths, executable_dir),
            network=network,
        )
        return get_exec_output_silently(
            sandbox_command,
            cwd=effective_cwd,
            # Caller env is injected via /usr/bin/env inside the sandbox; the
            # sandboxer process itself must not see it (it may carry secrets).
            env={},
            input=input,
            timeout=timeout,
            ignore_return_code=ignore_return_code,
            logger=logger,
            redact=redact,
        )


def _rattler_sandbox_command(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None,
    sandbox_executable: str | os.PathLike[str],
    read_paths: Sequence[str | os.PathLike[str]],
    read_write_paths: Sequence[str | os.PathLike[str]],
    read_exec_paths: Sequence[str | os.PathLike[str]],
    network: bool,
) -> list[str]:
    sandbox_command = [str(sandbox_executable)]

    for path in _unique_resolved_paths(read_write_paths):
        sandbox_command.extend(["--fs-write-and-read", path])
    for path in _unique_resolved_paths((cwd, *read_paths)):
        sandbox_command.extend(["--fs-read", path])
    for path in _unique_resolved_paths((*read_exec_paths, "/usr/bin/env")):
        sandbox_command.extend(["--fs-exec-and-read", path])

    if network:
        sandbox_command.append("--network")

    return [*sandbox_command, "--", *command]


def _apply_sandbox_env(
    command: Sequence[str],
    env: Mapping[str, str],
) -> list[str]:
    env_executable = Path("/usr/bin/env")
    if not env_executable.exists():
        output = ExecOutput(
            exit_code=127,
            stdout="",
            stderr="No such file or directory: /usr/bin/env",
        )
        raise CommandError("Command /usr/bin/env could not be resolved.", output)

    return [
        str(env_executable),
        *(f"{key}={value}" for key, value in env.items()),
        *command,
    ]


def _resolve_command(
    command: Sequence[str],
    *,
    cwd: Path,
) -> list[str]:
    executable = _resolve_command_executable(command[0], cwd=cwd)
    if executable is None:
        output = ExecOutput(
            exit_code=127,
            stdout="",
            stderr=f"No such file or directory: {command[0]}",
        )
        raise CommandError(
            f"Command {shlex.quote(command[0])} could not be resolved.",
            output,
        )
    return [str(executable), *command[1:]]


def _resolve_command_executable(
    executable: str,
    *,
    cwd: Path,
) -> Path | None:
    executable_path = Path(executable)
    if executable_path.is_absolute():
        resolved = executable_path.resolve()
        return resolved if resolved.exists() else None
    if os.sep in executable or (os.altsep is not None and os.altsep in executable):
        resolved = (cwd / executable_path).resolve()
        return resolved if resolved.exists() else None

    resolved = shutil.which(executable)
    return Path(resolved).resolve() if resolved is not None else None


def _unique_resolved_paths(
    paths: Sequence[str | os.PathLike[str]],
) -> tuple[str, ...]:
    unique_paths: list[str] = []
    seen: set[str] = set()
    for path in paths:
        # Do not resolve symlinks; the sandbox needs access to resolve them in case sandboxed programs use them
        resolved = os.path.abspath(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(resolved)
    return tuple(unique_paths)
