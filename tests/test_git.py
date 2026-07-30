from pathlib import Path
from typing import Any

import pytest

from quant_ranger._impl.git import RepositoryCheckout, git_config_args
from quant_ranger._impl.helpers import ExecOutput
from quant_ranger._impl.models import RepositoryRef
from quant_ranger._impl.testing import RecordingLogger


def test_git_config_args_flattens_config_entries() -> None:
    assert git_config_args(["a=b", "c=d"]) == ["-c", "a=b", "-c", "c=d"]


def test_repository_checkout_resolves_path(tmp_path: Path) -> None:
    checkout = RepositoryCheckout(
        tmp_path / "checkout",
        RepositoryRef(owner="quantco", name="example"),
    )

    assert checkout.absolute_path == (tmp_path / "checkout").resolve()
    assert checkout.get_name() == "example"


def test_git_exec_adds_git_config_and_checkout_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        calls.append({"command": command, **kwargs})
        return ExecOutput(exit_code=0, stdout="ok", stderr="")

    monkeypatch.setattr("quant_ranger._impl.git.get_exec_output_silently", fake_exec)
    checkout = RepositoryCheckout(
        tmp_path,
        RepositoryRef(owner="quantco", name="example"),
    )

    output = checkout.git_exec(
        ["status"],
        config=["user.name=octocat"],
        redact=["secret"],
    )

    assert output.stdout == "ok"
    assert calls == [
        {
            "command": ["git", "-c", "user.name=octocat", "status"],
            "cwd": Path(tmp_path).resolve(),
            "logger": None,
            "redact": ["secret"],
        }
    ]


def test_repository_checkout_helpers_build_expected_git_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        calls.append(command)
        if command[-2:] == ["status", "--porcelain"]:
            return ExecOutput(exit_code=0, stdout="", stderr="")
        if command[-4:] == ["diff", "--name-only", "--", "pixi.toml"]:
            return ExecOutput(exit_code=0, stdout="pixi.toml\n", stderr="")
        if command[-3:] == ["diff", "--cached", "--name-only"]:
            return ExecOutput(exit_code=0, stdout="file\n\nother-file\n", stderr="")
        if command[-2:] == ["diff", "--name-only"]:
            return ExecOutput(exit_code=0, stdout="pixi.toml\n", stderr="")
        if command[-4:] == ["show", "--format=", "--name-only", "HEAD"]:
            return ExecOutput(exit_code=0, stdout="file\n\nother-file\n", stderr="")
        if command[-3:] == ["show", "--format=", "HEAD"]:
            return ExecOutput(exit_code=0, stdout="diff output\n", stderr="")
        return ExecOutput(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr("quant_ranger._impl.git.get_exec_output_silently", fake_exec)
    checkout = RepositoryCheckout(
        tmp_path,
        RepositoryRef(owner="quantco", name="example"),
    )

    checkout.add_all()
    checkout.add("pixi.toml")
    checkout.checkout_branch("update-branch", logger=RecordingLogger())
    checkout.commit_with_author(
        "chore: update",
        author_name="octocat",
        author_email="1+octocat@users.noreply.github.com",
        user_name="example-ranger[bot]",
        user_email="1+example-ranger[bot]@users.noreply.github.com",
        quant_ranger_id="zizmor",
        logger=RecordingLogger(),
    )
    assert checkout.is_clean()
    assert checkout.changed_files() == ["pixi.toml"]
    assert checkout.changed_files(path="pixi.toml") == ["pixi.toml"]
    assert checkout.changed_files(staged=True) == ["file", "other-file"]
    assert checkout.head_commit_files() == ["file", "other-file"]
    assert checkout.head_commit_diff() == "diff output\n"
    checkout.force_push_branch(
        "update-branch",
        logger=RecordingLogger(),
        config=["http.extraHeader=AUTHORIZATION: basic secret"],
        redact=["secret"],
    )

    assert calls == [
        ["git", "add", "-A"],
        ["git", "add", "pixi.toml"],
        ["git", "checkout", "-B", "update-branch"],
        [
            "git",
            "-c",
            "user.name=example-ranger[bot]",
            "-c",
            "user.email=1+example-ranger[bot]@users.noreply.github.com",
            "-c",
            "author.name=octocat",
            "-c",
            "author.email=1+octocat@users.noreply.github.com",
            "commit",
            "-m",
            "chore: update",
            "--trailer",
            "Quant-Ranger: zizmor",
        ],
        ["git", "status", "--porcelain"],
        ["git", "diff", "--name-only"],
        ["git", "diff", "--name-only", "--", "pixi.toml"],
        ["git", "diff", "--cached", "--name-only"],
        ["git", "show", "--format=", "--name-only", "HEAD"],
        ["git", "show", "--format=", "HEAD"],
        [
            "git",
            "-c",
            "http.extraHeader=AUTHORIZATION: basic secret",
            "push",
            "--force",
            "--set-upstream",
            "origin",
            "update-branch",
        ],
    ]


def test_repository_checkout_detects_dirty_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_exec(command: list[str], **kwargs: Any) -> ExecOutput:
        return ExecOutput(exit_code=0, stdout=" M file.py\n", stderr="")

    monkeypatch.setattr("quant_ranger._impl.git.get_exec_output_silently", fake_exec)
    checkout = RepositoryCheckout(
        tmp_path,
        RepositoryRef(owner="quantco", name="example"),
    )

    assert not checkout.is_clean()
