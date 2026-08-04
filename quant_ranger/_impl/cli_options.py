from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

import typer
from typer.models import ArgumentInfo, OptionInfo

from quant_ranger._impl.models import Schedule
from quant_ranger._impl.site_config import SiteConfig


@dataclass(frozen=True, slots=True)
class SiteConfigParameter:
    """Resolve Typer parameter metadata from the loaded site configuration.

    Place this marker in an ``Annotated`` options-model field where a static
    ``typer.Option`` or ``typer.Argument`` would normally go. The CLI resolves
    the factory while constructing the command and leaves ordinary static
    parameter annotations unchanged. Factories must use annotation-style
    metadata such as ``typer.Option("--name")`` or ``typer.Argument()``.
    """

    factory: Callable[[SiteConfig], OptionInfo | ArgumentInfo]

    def resolve(self, site_config: SiteConfig) -> OptionInfo | ArgumentInfo:
        parameter: object = self.factory(site_config)
        if not isinstance(parameter, OptionInfo | ArgumentInfo):
            raise TypeError(
                "SiteConfigParameter factory must return typer.Option() or "
                f"typer.Argument(), got {parameter!r}."
            )
        return parameter


ScheduleOption = Annotated[
    Schedule | None,
    typer.Option(
        "--schedule",
        help=(
            "Filter to update configurations whose schedule matches this value. "
            "Omit to include every cadence. Configurations set to `never` are "
            "always excluded."
        ),
    ),
]
