from collections.abc import Sequence
from typing import override

from quant_ranger._impl.models import RepositoryRef, UpdateItem
from quant_ranger._impl.runtime import RunContext

from ._base import Scanner


class RepositoriesScanner(Scanner[UpdateItem]):
    """Scanner that emits one root update item per repository."""

    @override
    def scan_repository(
        self,
        repository_ref: RepositoryRef,
        context: RunContext,
    ) -> Sequence[UpdateItem]:
        return [UpdateItem(repository_ref=repository_ref)]
