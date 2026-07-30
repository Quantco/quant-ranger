from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import replace
from typing import Any, ClassVar, get_args, get_origin

from quant_ranger._impl.git import RepositoryCheckout
from quant_ranger._impl.helpers import (
    app_tempdir,
    map_concurrently,
    pluralize,
    truncate_lines,
)
from quant_ranger._impl.logger import PrefixLogger, progress
from quant_ranger._impl.models import (
    Status,
    UpdateItem,
    UpdateItemTypeMixin,
    UpdateOptions,
    UpdateOutcome,
    UpdateOutput,
    UpdateOutputTypeMixin,
    UpdateResult,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.scanners import Scanner


class UpdateTask[
    ItemT: UpdateItem,
    OutputT: UpdateOutput = UpdateOutput,
    OptionsT: UpdateOptions = UpdateOptions,
](ABC):
    """A checkout-bound update task."""

    def __init__(
        self,
        checkout: RepositoryCheckout,
        context: RunContext,
        *,
        item: ItemT,
        options: OptionsT,
    ) -> None:
        self.checkout = checkout
        self.context = context
        self.item = item
        self.options = options

    @abstractmethod
    def run(self) -> UpdateOutcome[OutputT]:
        """Run the update task and return its outcome.

        Implementations may raise for unexpected update failures. `update_all` will
        report those exceptions as `Status.FAILURE` for this item and continue with
        the next item.
        """


class Updater[
    ItemT: UpdateItem,
    OutputT: UpdateOutput = UpdateOutput,
    OptionsT: UpdateOptions = UpdateOptions,
](UpdateItemTypeMixin, UpdateOutputTypeMixin, ABC):
    """Base class for code-based updaters."""

    name: ClassVar[str]
    description: ClassVar[str] = ""
    scanner: Scanner[ItemT]
    options_type: ClassVar[type[UpdateOptions]] = UpdateOptions
    task_type: type[UpdateTask[ItemT, OutputT, OptionsT]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "options_type" not in cls.__dict__:
            setattr(
                cls,
                "options_type",
                _infer_update_options_type(cls),
            )

    def __init__(self, options: OptionsT) -> None:
        self.options: OptionsT = options

    def make_task(
        self,
        item: ItemT,
        checkout: RepositoryCheckout,
        context: RunContext,
    ) -> UpdateTask[ItemT, OutputT, OptionsT]:
        """Create the checkout-bound task for one update item.

        The default implementation assumes ``task_type`` can be constructed with
        the standard ``UpdateTask`` keyword arguments. Updaters with custom task
        constructors must override this method and keep that construction in sync.
        """
        return self.task_type(
            checkout=checkout,
            context=context,
            item=item,
            options=self.options,
        )

    def _update(
        self,
        item: ItemT,
        context: RunContext,
    ) -> UpdateOutcome[OutputT]:
        """Materialize repository and run updater for a single item."""
        with app_tempdir(f"quant-ranger-{self.name}-") as checkout_path:
            checkout = context.github_client.clone_repository(
                item.repository_ref,
                directory=checkout_path,
            )

            task = self.make_task(item, checkout, context)
            return task.run()

    def update_all(
        self,
        update_items: Iterable[ItemT],
        context: RunContext,
        *,
        concurrency: int = 1,
    ) -> list[UpdateResult[OutputT, ItemT]]:
        """Materialize repositories and run this updater for already-scanned items."""
        update_items = list(update_items)
        results: list[UpdateResult[OutputT, ItemT]] = []

        context.logger.info(f"Running {pluralize(len(update_items), 'update item')}...")
        assert concurrency >= 1
        if concurrency == 1:
            for item in progress(
                update_items,
                logger=context.logger,
                description="Updating repositories",
                total=len(update_items),
            ):
                results.append(self._run_item(item, context))
        else:
            results = map_concurrently(
                lambda item: self._run_item(item, context),
                update_items,
                concurrency=concurrency,
                logger=context.logger,
                description="Updating repositories",
            )

        return results

    def _run_item(
        self,
        item: ItemT,
        context: RunContext,
    ) -> UpdateResult[OutputT, ItemT]:
        """Run one update item and convert unexpected errors to failure results."""
        item_context = replace(
            context,
            logger=PrefixLogger(f"{item.log_prefix()} ", context.logger),
        )

        unexpected_error: Exception | None = None
        try:
            outcome = self._update(item, item_context)
        except Exception as error:
            unexpected_error = error
            outcome = UpdateOutcome[OutputT].from_exception(
                error,
                result=Status.FAILURE,
            )

        outcome_summary = outcome.result.value
        if outcome.message:
            outcome_summary = f"{outcome_summary}: {outcome.message}"
        if outcome.result == Status.FAILURE:
            if unexpected_error is not None:
                item_context.logger.exception(outcome_summary, unexpected_error)
            else:
                if outcome.details:
                    # Handled failure details (e.g. command output) are capped to
                    # keep the log readable.
                    details = truncate_lines(outcome.details, max_lines=10)
                    outcome_summary = f"{outcome_summary}\n{details}"
                item_context.logger.error(outcome_summary)
        else:
            item_context.logger.info(outcome_summary)
        return UpdateResult.from_outcome(
            outcome,
            item=item,
        )


type AnyUpdater = Updater[Any, Any, Any]


def _infer_update_options_type(cls: type[Any]) -> type[UpdateOptions]:
    updater_base = next(
        (base for base in cls.__orig_bases__ if _is_updater_base(base)),
        None,
    )
    if updater_base is None:
        msg = f"{cls.__name__} must inherit from Updater[...] or set options_type."
        raise TypeError(msg)

    options_type = get_args(updater_base)[2]
    if not isinstance(options_type, type) or not issubclass(
        options_type, UpdateOptions
    ):
        msg = f"{cls.__name__} options type must be a subclass of UpdateOptions."
        raise TypeError(msg)
    return options_type


def _is_updater_base(base: Any) -> bool:
    origin = get_origin(base)
    return isinstance(origin, type) and issubclass(origin, Updater)
