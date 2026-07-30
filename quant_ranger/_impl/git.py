from collections.abc import Iterable, Sequence
from pathlib import Path

from quant_ranger._impl.helpers import ExecOutput, get_exec_output_silently
from quant_ranger._impl.logger import Logger
from quant_ranger._impl.models import RepositoryRef

QUANT_RANGER_TRAILER = "Quant-Ranger"


class RepositoryCheckout:
    """Git operations for a local checkout of a repository ref."""

    def __init__(
        self,
        path: str | Path,
        repository_ref: RepositoryRef,
    ) -> None:
        self.absolute_path = Path(path).resolve()
        self.repository_ref = repository_ref

    def get_name(self) -> str:
        return self.repository_ref.name

    def git_exec(
        self,
        args: Sequence[str],
        logger: Logger | None = None,
        *,
        config: Sequence[str] = (),
        redact: Sequence[str] = (),
    ) -> ExecOutput:
        return get_exec_output_silently(
            ["git", *git_config_args(config), *args],
            cwd=self.absolute_path,
            logger=logger,
            redact=redact,
        )

    def add_all(self) -> None:
        self.git_exec(["add", "-A"])

    def add(self, path: str | Path) -> None:
        self.git_exec(["add", str(path)])

    def checkout_branch(self, branch: str, logger: Logger) -> None:
        self.git_exec(["checkout", "-B", branch], logger)

    def commit_with_author(
        self,
        message: str,
        *,
        author_name: str,
        author_email: str,
        user_name: str,
        user_email: str,
        quant_ranger_id: str,
        logger: Logger,
    ) -> None:
        self.git_exec(
            [
                "commit",
                "-m",
                message,
                "--trailer",
                f"{QUANT_RANGER_TRAILER}: {quant_ranger_id}",
            ],
            logger,
            config=[
                f"user.name={user_name}",
                f"user.email={user_email}",
                f"author.name={author_name}",
                f"author.email={author_email}",
            ],
        )

    def is_clean(self) -> bool:
        output = self.git_exec(["status", "--porcelain"])
        return output.stdout == ""

    def changed_files(
        self,
        logger: Logger | None = None,
        *,
        staged: bool = False,
        path: str | Path | None = None,
    ) -> list[str]:
        args = ["diff"]
        if staged:
            args.append("--cached")
        args.append("--name-only")
        if path is not None:
            args.extend(["--", str(path)])

        output = self.git_exec(args, logger).stdout
        return [line for line in output.splitlines() if line]

    def head_commit_files(self, logger: Logger | None = None) -> list[str]:
        output = self.git_exec(["show", "--format=", "--name-only", "HEAD"], logger)
        return [line for line in output.stdout.splitlines() if line]

    def head_commit_diff(self) -> str:
        return self.git_exec(["show", "--format=", "HEAD"]).stdout

    def force_push_branch(
        self,
        source_branch: str,
        logger: Logger,
        *,
        config: Sequence[str] = (),
        redact: Sequence[str] = (),
    ) -> None:
        self.git_exec(
            ["push", "--force", "--set-upstream", "origin", source_branch],
            logger,
            config=config,
            redact=redact,
        )


def git_config_args(config: Iterable[str]) -> list[str]:
    return [arg for entry in config for arg in ("-c", entry)]
