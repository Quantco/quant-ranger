import importlib.util
import uuid
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType
from typing import Annotated, Any, ClassVar, override

import typer

from quant_ranger._impl.helpers import CliError
from quant_ranger._impl.models import (
    UpdateItem,
    UpdateOptions,
    UpdateOutput,
    UpdateResult,
)
from quant_ranger._impl.runtime import RunContext

from ._base import Updater

CUSTOM_UPDATER_MODULE_PREFIX = "quant_ranger_custom_updater_"
UPDATER_EXPORT_NAME = "updater"


class CustomFileUpdater[
    ItemT: UpdateItem,
    OutputT: UpdateOutput = UpdateOutput,
](Updater[ItemT, OutputT, UpdateOptions]):
    """Base class for custom updaters loaded from Python files."""

    item_type: ClassVar[type[UpdateItem]] = UpdateItem
    output_type: ClassVar[type[UpdateOutput]] = UpdateOutput
    options_type: ClassVar[type[UpdateOptions]] = UpdateOptions

    def __init_subclass__(cls, **kwargs: Any) -> None:
        if cls.__dict__.get("options_type", UpdateOptions) is not UpdateOptions:
            msg = (
                f"{cls.__name__} cannot define custom options; custom file "
                "updaters use UpdateOptions."
            )
            raise TypeError(msg)
        cls.options_type = UpdateOptions
        super().__init_subclass__(**kwargs)

    def __init__(self) -> None:
        super().__init__(UpdateOptions())


class CustomUpdaterOptions(UpdateOptions):
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            "-p",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help=(
                "Trusted Python file to import and execute without a sandbox. "
                "It must export `updater`, a `CustomFileUpdater` instance."
            ),
        ),
    ]


class CustomUpdater(Updater[UpdateItem, UpdateOutput, CustomUpdaterOptions]):
    name = "custom"
    description = (
        "Run a trusted Python updater. Imports a file that exports a "
        "`CustomFileUpdater` instance named `updater`."
    )

    @override
    def __init__(self, options: CustomUpdaterOptions) -> None:
        super().__init__(options)
        self._loaded_updater = _load_updater_from_path(options.path)
        # Keep the CLI-visible command as `custom`, but scan with the loaded updater.
        self.scanner = self._loaded_updater.scanner

    @override
    def update_all(
        self,
        update_items: Iterable[UpdateItem],
        context: RunContext,
        *,
        concurrency: int = 1,
    ) -> list[UpdateResult]:
        return self._loaded_updater.update_all(
            update_items,
            context,
            concurrency=concurrency,
        )


def _load_updater_from_path(path: Path) -> CustomFileUpdater[Any, Any]:
    if not path.is_file():
        msg = f"Custom updater path is not a file: {path}"
        raise CliError(msg)

    module = _load_module(path)
    if not hasattr(module, UPDATER_EXPORT_NAME):
        msg = (
            "Custom updater files must define `updater = ...` with a "
            "CustomFileUpdater instance."
        )
        raise CliError(msg)

    value = getattr(module, UPDATER_EXPORT_NAME)
    if isinstance(value, CustomFileUpdater):
        return value

    msg = (
        f"Custom updater export `{UPDATER_EXPORT_NAME}` must be a "
        "CustomFileUpdater instance."
    )
    raise CliError(msg)


def _load_module(path: Path) -> ModuleType:
    module_name = f"{CUSTOM_UPDATER_MODULE_PREFIX}{uuid.uuid7().hex}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        msg = f"Could not import custom updater file: {path}"
        raise CliError(msg)

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
