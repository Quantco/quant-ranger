from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, ClassVar, get_args, get_origin

from pydantic import BaseModel, ConfigDict

from quant_ranger._impl.logger import Logger
from quant_ranger._impl.models import (
    ScanFailure,
    UpdateItem,
    UpdateItemTypeMixin,
    UpdateOutput,
    UpdateOutputTypeMixin,
    UpdateResult,
)


class AggregatorOptions(BaseModel):
    """Typed CLI/runtime options for an aggregator."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Aggregator[
    ItemT: UpdateItem = UpdateItem,
    OutputT: UpdateOutput = UpdateOutput,
    OptionsT: AggregatorOptions = AggregatorOptions,
](UpdateItemTypeMixin, UpdateOutputTypeMixin, ABC):
    """Post-process the structured results of an updater run."""

    name: ClassVar[str]
    description: ClassVar[str] = ""
    options_type: ClassVar[type[AggregatorOptions]] = AggregatorOptions

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "options_type" not in cls.__dict__:
            setattr(
                cls,
                "options_type",
                _infer_aggregator_options_type(cls),
            )

    def __init__(self, options: OptionsT) -> None:
        self.options: OptionsT = options

    @abstractmethod
    def aggregate(
        self,
        results: Sequence[UpdateResult[OutputT, ItemT]],
        logger: Logger,
        scan_failures: Sequence[ScanFailure],
        updater_name: str,
    ) -> None:
        """Consume all updater results after the update run completes."""


type AnyAggregator = Aggregator[Any, Any, Any]


def _infer_aggregator_options_type(cls: type[Any]) -> type[AggregatorOptions]:
    aggregator_base = next(
        (base for base in cls.__orig_bases__ if _is_aggregator_base(base)),
        None,
    )
    if aggregator_base is None:
        msg = f"{cls.__name__} must inherit from Aggregator[...] or set options_type."
        raise TypeError(msg)

    options_type = get_args(aggregator_base)[2]
    if not isinstance(options_type, type) or not issubclass(
        options_type,
        AggregatorOptions,
    ):
        msg = f"{cls.__name__} options type must be a subclass of AggregatorOptions."
        raise TypeError(msg)
    return options_type


def _is_aggregator_base(base: Any) -> bool:
    origin = get_origin(base)
    return isinstance(origin, type) and issubclass(origin, Aggregator)
