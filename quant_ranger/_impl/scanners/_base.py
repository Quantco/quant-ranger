from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from quant_ranger._impl.helpers import map_concurrently, pluralize
from quant_ranger._impl.logger import PrefixLogger, progress
from quant_ranger._impl.models import (
    RepositoryRef,
    ScanFailure,
    UpdateItem,
    UpdateItemTypeMixin,
)
from quant_ranger._impl.runtime import RunContext


@dataclass(frozen=True, slots=True)
class ScanResult[ItemT: UpdateItem]:
    """Items and failures produced by a scanner run."""

    update_items: tuple[ItemT, ...] = ()
    scan_failures: tuple[ScanFailure, ...] = ()


class Scanner[ItemT: UpdateItem](UpdateItemTypeMixin, ABC):
    """Base class for code-based scanners that generate update items."""

    def scan_all(
        self,
        repository_refs: Iterable[RepositoryRef],
        context: RunContext,
        *,
        concurrency: int = 1,
    ) -> ScanResult[ItemT]:
        repository_refs = list(repository_refs)
        update_items: list[ItemT] = []
        scan_failures: list[ScanFailure] = []
        total = len(repository_refs)
        context.logger.info(f"Scanning {total} repositories...")

        assert concurrency >= 1
        if concurrency == 1:
            scanned = (
                self._try_scan_repository(repository_ref, context)
                for repository_ref in progress(
                    repository_refs,
                    logger=context.logger,
                    description="Scanning repositories",
                    total=total,
                )
            )
        else:
            scanned = map_concurrently(
                lambda repository_ref: self._try_scan_repository(
                    repository_ref, context
                ),
                repository_refs,
                concurrency=concurrency,
                logger=context.logger,
                description="Scanning repositories",
            )
        for result in scanned:
            update_items.extend(result.update_items)
            scan_failures.extend(result.scan_failures)

        suffix = (
            f"; {pluralize(len(scan_failures), 'repository', 'repositories')} "
            "failed during scanning"
            if scan_failures
            else ""
        )
        context.logger.info(
            f"Generated {pluralize(len(update_items), 'update item')}{suffix}."
        )
        return ScanResult(
            update_items=tuple(update_items),
            scan_failures=tuple(scan_failures),
        )

    @abstractmethod
    def scan_repository(
        self,
        repository_ref: RepositoryRef,
        context: RunContext,
    ) -> Sequence[ItemT]:
        """Return update items for a repository, or an empty list to skip it.

        Return an empty list when the repository is out of scope for this updater; raise
        when the repository should be scanned but cannot be. Exceptions are captured as
        scan failures for the affected repository while scanning continues for the
        remaining repositories.
        """

    def _try_scan_repository(
        self,
        repository_ref: RepositoryRef,
        context: RunContext,
    ) -> ScanResult[ItemT]:
        """Scan one repository and convert exceptions to scan failures."""
        repository_context = replace(
            context,
            logger=PrefixLogger(f"[{repository_ref.display_name}] ", context.logger),
        )
        try:
            return ScanResult(
                update_items=tuple(
                    self.scan_repository(repository_ref, repository_context)
                )
            )
        except Exception as error:
            scan_failure = ScanFailure.from_exception(
                error,
                repository_ref=repository_ref,
            )
            # Tracebacks are stored in the scan failure for artifacts but not
            # logged to keep failures easy to spot in the log.
            repository_context.logger.error(
                f"Skipping repository: {scan_failure.message}"
            )
            return ScanResult(scan_failures=(scan_failure,))
