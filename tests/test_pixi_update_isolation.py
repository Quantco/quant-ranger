"""Run `PixiUpdateTask` with the real `rattler-sandbox` and a scripted `pixi`."""

import os
import shlex
from pathlib import Path
from typing import cast

import pytest

from quant_ranger._impl.git import RepositoryCheckout
from quant_ranger._impl.github import GitHubClient
from quant_ranger._impl.helpers import (
    CommandError,
    ExecOutput,
    get_exec_output_silently,
)
from quant_ranger._impl.models import RepositoryRef, Status
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.sandbox import get_sandboxed_exec_output_silently
from quant_ranger._impl.testing import FakeGitHubClient, RecordingLogger
from quant_ranger._impl.updaters._pixi_update._auth import SandboxAuth
from quant_ranger._impl.updaters._pixi_update._update import (
    PixiManifest,
    PixiUpdateItem,
    PixiUpdateOptions,
    PixiUpdateTask,
    _pixi_update_sandbox_paths,
)
from quant_ranger.site_config import SiteConfig

LOCKFILE_CONTENT = "version: 6\n"


@pytest.fixture(autouse=True)
def require_sandbox(tmp_path: Path) -> None:
    probe = tmp_path / "probe"
    probe.mkdir()
    sandbox_paths = _pixi_update_sandbox_paths()
    try:
        get_sandboxed_exec_output_silently(
            ["/bin/sh", "-c", ":"],
            cwd=probe,
            read_paths=sandbox_paths.read_paths,
            read_exec_paths=sandbox_paths.read_exec_paths,
        )
    except CommandError as error:
        pytest.skip(f"rattler-sandbox cannot run here: {error}")


# Plant a git hook and record whether the original checkout is accessible.
PIXI_SCRIPT = """#!/bin/sh
set -e
PATH=/usr/bin:/bin
mkdir -p .git/hooks
echo '#!/bin/sh' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
echo {lockfile} > pixi.lock
if ls {checkout} >/dev/null 2>&1; then
    echo "checkout-readable: yes" >> pixi.lock
else
    echo "checkout-readable: no" >> pixi.lock
fi
if echo written > {checkout}/written 2>/dev/null; then
    echo "checkout-writable: yes" >> pixi.lock
else
    echo "checkout-writable: no" >> pixi.lock
fi
echo '{{"changed": true}}'
"""


def test_sandboxed_writes_do_not_reach_checkout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout_path = tmp_path / "checkout"
    _init_repository(checkout_path)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pixi = bin_dir / "pixi"
    pixi.write_text(
        PIXI_SCRIPT.format(
            checkout=shlex.quote(str(checkout_path.resolve())),
            lockfile=shlex.quote(LOCKFILE_CONTENT.strip()),
        )
    )
    pixi.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(
        "quant_ranger._impl.updaters._pixi_update._update.get_exec_output_silently",
        lambda command, **kwargs: ExecOutput(exit_code=0, stdout="", stderr=""),
    )

    repository_ref = RepositoryRef(owner="quantco", name="example", branch="main")
    before = _snapshot(checkout_path)
    task = PixiUpdateTask(
        RepositoryCheckout(checkout_path, repository_ref),
        RunContext(
            site_config=SiteConfig(),
            github_client=cast(GitHubClient, FakeGitHubClient()),
            logger=RecordingLogger(),
        ),
        item=PixiUpdateItem(
            repository_ref=repository_ref,
            path="pixi.lock",
            manifest=PixiManifest.model_validate(
                {"workspace": {"platforms": ["linux-64"]}}
            ),
        ),
        options=PixiUpdateOptions(),
        auth=SandboxAuth(),
        config_locations=(),
    )

    outcome = task.run()

    assert outcome.result == Status.UPDATED
    assert (checkout_path / "pixi.lock").read_text() == (
        f"{LOCKFILE_CONTENT}checkout-readable: no\ncheckout-writable: no\n"
    )
    # Besides the lockfile, only staging it may change the checkout: the index and
    # the lockfile's blob object.
    assert _git(checkout_path, "diff", "--cached", "--name-only") == "pixi.lock"
    blob = _git(checkout_path, "hash-object", "pixi.lock")
    staged_paths = {
        "pixi.lock",
        ".git/index",
        f".git/objects/{blob[:2]}",
        f".git/objects/{blob[:2]}/{blob[2:]}",
    }
    after = _snapshot(checkout_path)
    assert {path: after[path] for path in after.keys() - staged_paths} == {
        path: before[path] for path in before.keys() - staged_paths
    }


def _init_repository(path: Path) -> None:
    path.mkdir()
    (path / "pixi.toml").write_text('[workspace]\nplatforms = ["linux-64"]\n')
    (path / "pixi.lock").write_text("version: 5\n")
    for args in (
        ["init", "--quiet", "--initial-branch", "main"],
        ["add", "pixi.toml", "pixi.lock"],
        [
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--quiet",
            "--no-verify",
            "-m",
            "Initial commit",
        ],
    ):
        get_exec_output_silently(["git", *args], cwd=path)


def _git(path: Path, *args: str) -> str:
    return get_exec_output_silently(["git", *args], cwd=path).stdout.strip()


def _snapshot(root: Path) -> dict[str, bytes | str]:
    """Map every path below `root` to its content, symlink target or mode."""
    snapshot: dict[str, bytes | str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        mode = oct(path.lstat().st_mode)
        if path.is_symlink():
            snapshot[relative] = f"symlink:{path.readlink()}"
        elif path.is_dir():
            snapshot[relative] = f"directory:{mode}"
        else:
            snapshot[relative] = path.read_bytes() + mode.encode()
    return snapshot
