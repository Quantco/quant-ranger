import logging
import sys
import threading
from collections.abc import Iterable, Iterator
from enum import StrEnum
from typing import Protocol, TextIO

from rich.console import Console, RenderableType
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.text import Text


class LogLevel(StrEnum):
    """Levels at which a `Logger` can emit messages."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Logger(Protocol):
    """Small logging interface shared by CLI helpers and updaters."""

    console: Console
    show_progress: bool

    def info(self, message: str) -> None: ...

    def info_panel(
        self,
        title: str,
        content: RenderableType,
    ) -> None: ...

    def debug(self, message: str) -> None: ...

    def warning(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...

    def exception(self, message: str, error: BaseException) -> None: ...


class ConsoleLogger:
    """Logger that writes human-readable progress to a stream."""

    console: Console
    show_progress: bool

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        force_terminal: bool | None = None,
        debug: bool = False,
    ) -> None:
        self.stream = stream or sys.stderr
        self.console = Console(file=self.stream, force_terminal=force_terminal)
        self.show_progress = self.console.is_terminal
        self._lock = threading.RLock()
        self._logger = logging.Logger(
            "quant-ranger",
            level=logging.DEBUG if debug else logging.INFO,
        )
        handler = RichHandler(
            console=self.console,
            markup=False,
            rich_tracebacks=True,
            show_path=False,
            show_time=False,
        )
        self._logger.addHandler(handler)

    def info(self, message: str) -> None:
        self._logger.info(message)

    def info_panel(
        self,
        title: str,
        content: RenderableType,
    ) -> None:
        with self._lock:
            self.console.print(
                Panel(
                    content,
                    title=Text(f"info: {title}"),
                )
            )

    def debug(self, message: str) -> None:
        self._logger.debug(message)

    def warning(self, message: str) -> None:
        self._logger.warning(message)

    def error(self, message: str) -> None:
        self._logger.error(message)

    def exception(self, message: str, error: BaseException) -> None:
        self._logger.error(
            message,
            exc_info=error,
        )


class PrefixLogger:
    """Logger that adds a prefix to each message."""

    console: Console
    show_progress: bool

    def __init__(self, prefix: str, logger: Logger) -> None:
        self.prefix = prefix
        self.logger = logger
        self.console = logger.console
        self.show_progress = logger.show_progress

    def info(self, message: str) -> None:
        self.logger.info(f"{self.prefix}{message}")

    def info_panel(
        self,
        title: str,
        content: RenderableType,
    ) -> None:
        self.logger.info_panel(
            f"{self.prefix}{title}",
            content,
        )

    def debug(self, message: str) -> None:
        self.logger.debug(f"{self.prefix}{message}")

    def warning(self, message: str) -> None:
        self.logger.warning(f"{self.prefix}{message}")

    def error(self, message: str) -> None:
        self.logger.error(f"{self.prefix}{message}")

    def exception(self, message: str, error: BaseException) -> None:
        self.logger.exception(f"{self.prefix}{message}", error)


def progress[T](
    values: Iterable[T],
    *,
    logger: Logger,
    description: str,
    total: int | None = None,
) -> Iterator[T]:
    if not logger.show_progress:
        yield from values
        return

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("elapsed:"),
        TimeElapsedColumn(),
        TextColumn("rem:"),
        TimeRemainingColumn(),
        console=logger.console,
    ) as rich_progress:
        task_id = rich_progress.add_task(description, total=total)
        for value in values:
            yield value
            rich_progress.advance(task_id)
