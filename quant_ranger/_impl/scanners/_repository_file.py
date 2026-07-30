from collections.abc import Sequence
from re import Pattern
from typing import override

from quant_ranger._impl.models import RepositoryRef, UpdateItem
from quant_ranger._impl.runtime import RunContext

from ._base import Scanner


class RepositoryFileScanner(Scanner[UpdateItem]):
    """Scanner that emits one repository item when matching files exist."""

    def __init__(
        self,
        *,
        filename_pattern: str | Pattern[str],
        missing_message: str | None = None,
    ) -> None:
        """Create a scanner for repository-level items.

        ``missing_message`` is logged when the repository contains no matching
        files.
        """
        self.filename_pattern = filename_pattern
        self.missing_message = missing_message

    @override
    def scan_repository(
        self,
        repository_ref: RepositoryRef,
        context: RunContext,
    ) -> Sequence[UpdateItem]:
        files = context.github_client.find_files_by_name(
            repository_ref,
            self.filename_pattern,
        )
        if not files:
            if self.missing_message is not None:
                context.logger.debug(f"{self.missing_message}.")
            return []

        return [UpdateItem(repository_ref=repository_ref)]
