from importlib.metadata import EntryPoint, entry_points
from typing import ClassVar, Protocol

from quant_ranger._impl.aggregators import Aggregator, AnyAggregator
from quant_ranger._impl.helpers import CliError
from quant_ranger._impl.logger import Logger
from quant_ranger._impl.site_config import SiteConfig
from quant_ranger._impl.updaters import AnyUpdater, Updater

_UPDATER_ENTRY_POINT_GROUP = "quant_ranger.updaters"
_AGGREGATOR_ENTRY_POINT_GROUP = "quant_ranger.aggregators"
_SITE_CONFIG_ENTRY_POINT_GROUP = "quant_ranger.site_config"


class _NamedCommand(Protocol):
    name: ClassVar[str]


def available_updater_types(
    *,
    builtin_types: tuple[type[AnyUpdater], ...],
    logger: Logger,
    load_plugins: bool = True,
) -> tuple[type[AnyUpdater], ...]:
    _check_unique_builtin_names(builtin_types)
    if not load_plugins:
        return builtin_types

    logger.debug("Loading updater plugins:")
    plugin_types = _discover_plugin_types(
        group=_UPDATER_ENTRY_POINT_GROUP,
        base_type=Updater,
        taken_names={builtin_type.name for builtin_type in builtin_types},
        logger=logger,
    )
    return (*builtin_types, *plugin_types)


def available_aggregator_types(
    *,
    builtin_types: tuple[type[AnyAggregator], ...],
    logger: Logger,
    load_plugins: bool = True,
) -> tuple[type[AnyAggregator], ...]:
    _check_unique_builtin_names(builtin_types)
    if not load_plugins:
        return builtin_types

    logger.debug("Loading aggregator plugins:")
    plugin_types = _discover_plugin_types(
        group=_AGGREGATOR_ENTRY_POINT_GROUP,
        base_type=Aggregator,
        taken_names={builtin_type.name for builtin_type in builtin_types},
        logger=logger,
    )
    return (*builtin_types, *plugin_types)


def load_site_config(
    *,
    logger: Logger,
    load_plugins: bool = True,
) -> SiteConfig:
    if not load_plugins:
        return SiteConfig()

    site_config_entry_points = entry_points(group=_SITE_CONFIG_ENTRY_POINT_GROUP)
    if len(site_config_entry_points) > 1:
        # Sorted so the error message is deterministic.
        names = ", ".join(
            f"{entry_point.name!r} ({entry_point.value!r})"
            for entry_point in sorted(
                site_config_entry_points,
                key=lambda entry_point: entry_point.name,
            )
        )
        raise CliError(
            f"Multiple site config plugins are installed: {names}. Install exactly one."
        )
    if not site_config_entry_points:
        return SiteConfig()

    (entry_point,) = site_config_entry_points
    try:
        value = entry_point.load()
    except (SystemExit, Exception) as error:
        raise CliError(
            f"Site config plugin {entry_point.name!r} ({entry_point.value!r}) "
            f"failed to load: {error}."
        ) from error

    if not isinstance(value, SiteConfig):
        raise CliError(
            f"Site config plugin {entry_point.name!r} ({entry_point.value!r}) "
            f"must load a SiteConfig instance, got {value!r}."
        )

    package = entry_point.module.partition(".")[0]
    logger.debug(f"Loaded site config {entry_point.name!r} ({package}).")
    return value


def _check_unique_builtin_names(builtin_types: tuple[type[_NamedCommand], ...]) -> None:
    seen_types: dict[str, type[_NamedCommand]] = {}
    for builtin_type in builtin_types:
        if builtin_type.name in seen_types:
            msg = (
                f"Duplicate builtin command name {builtin_type.name!r}: "
                f"{seen_types[builtin_type.name].__name__} and "
                f"{builtin_type.__name__}."
            )
            raise ValueError(msg)
        seen_types[builtin_type.name] = builtin_type


def _discover_plugin_types[T: _NamedCommand](
    *,
    group: str,
    base_type: type[T],
    taken_names: set[str],
    logger: Logger,
) -> tuple[type[T], ...]:
    discovered_types: list[type[T]] = []
    sorted_entry_points = sorted(
        entry_points(group=group),
        key=lambda entry_point: entry_point.name,
    )
    for entry_point in sorted_entry_points:
        try:
            value = entry_point.load()
        # SystemExit is not an Exception: a plugin calling sys.exit() at
        # import time must not kill the CLI.
        except (SystemExit, Exception) as error:
            _report_plugin_error(
                logger,
                entry_point,
                f"failed to load: {error}",
            )
            continue

        if not isinstance(value, type) or not issubclass(value, base_type):
            _report_plugin_error(
                logger,
                entry_point,
                f"must load a subclass of {base_type.__name__}, got {value!r}",
            )
            continue

        if not isinstance(getattr(value, "name", None), str):
            _report_plugin_error(
                logger,
                entry_point,
                f"must define a `name` string class attribute, got {value!r}",
            )
            continue

        if value.name in taken_names:
            _report_plugin_error(
                logger,
                entry_point,
                f"command name {value.name!r} duplicates an existing command",
            )
            continue

        taken_names.add(value.name)
        discovered_types.append(value)
        package = value.__module__.partition(".")[0]
        logger.debug(f"  {value.name} ({package})")
    return tuple(discovered_types)


def _report_plugin_error(
    logger: Logger,
    entry_point: EntryPoint,
    reason: str,
) -> None:
    logger.warning(
        f"Skipping plugin entry point {entry_point.name!r} "
        f"from group {entry_point.group!r} ({entry_point.value!r}): {reason}."
    )
