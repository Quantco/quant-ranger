from typing import Any, cast

import pytest

from quant_ranger._impl.models import (
    UpdateItem,
    UpdateOutput,
)
from quant_ranger.aggregators import (
    Aggregator,
)


def test_aggregator_requires_generic_base_when_inferring_options_type() -> None:
    with pytest.raises(
        TypeError,
        match=r"BareAggregator must inherit from Aggregator\[\.\.\.\] or set options_type.",
    ):

        class BareAggregator(Aggregator):
            pass


def test_aggregator_rejects_invalid_options_type() -> None:
    invalid_base = cast(Any, Aggregator)[UpdateItem, UpdateOutput, str]

    with pytest.raises(
        TypeError,
        match="BadOptionsAggregator options type must be a subclass of AggregatorOptions.",
    ):

        class BadOptionsAggregator(invalid_base):
            pass
