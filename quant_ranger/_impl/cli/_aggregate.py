import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import typer

from quant_ranger._impl.aggregators import (
    AnyAggregator,
    IncidentIoAlertsAggregator,
    LogFailuresAggregator,
)
from quant_ranger._impl.artifacts import (
    parse_update_results,
    read_results_file,
    resolve_updater_type,
)
from quant_ranger._impl.helpers import CliError, exit_via_sigint
from quant_ranger._impl.logger import Logger
from quant_ranger._impl.models import UpdateItem, UpdateOutput
from quant_ranger._impl.site_config import SiteConfig
from quant_ranger._impl.updaters import AnyUpdater

from ._helpers import command_signature

BUILTIN_AGGREGATORS: tuple[type[AnyAggregator], ...] = (
    LogFailuresAggregator,
    IncidentIoAlertsAggregator,
)


@dataclass(frozen=True, slots=True)
class AggregateRunOptions:
    logger: Logger


def make_aggregate_command(
    aggregator_type: type[AnyAggregator],
    updater_types: Sequence[type[AnyUpdater]],
    site_config: SiteConfig,
) -> Callable[..., None]:
    options_type = aggregator_type.options_type

    def run_aggregate_command(
        context: typer.Context,
        results_file: Path,
        **option_values: object,
    ) -> None:
        run_options = context.obj
        options = options_type.model_validate(option_values)
        aggregator = aggregator_type(options)
        _run_aggregate_with_error_handling(
            aggregator,
            results_file=results_file,
            run_options=run_options,
            updater_types=updater_types,
        )

    run_aggregate_command.__name__ = aggregator_type.name
    # The aggregator's Pydantic options are not visible in the closure
    # signature, so provide the Typer-facing signature explicitly.
    setattr(
        run_aggregate_command,
        "__signature__",
        command_signature(
            options_type,
            _results_file_argument_parameter(),
            site_config=site_config,
        ),
    )
    return run_aggregate_command


def _results_file_argument_parameter() -> inspect.Parameter:
    return inspect.Parameter(
        "results_file",
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        annotation=Path,
        default=typer.Argument(
            ...,
            help="JSON results file written by `quant-ranger update`.",
        ),
    )


def _run_aggregate_with_error_handling(
    aggregator: AnyAggregator,
    *,
    results_file: Path,
    run_options: AggregateRunOptions,
    updater_types: Sequence[type[AnyUpdater]],
) -> None:
    try:
        _run_aggregator_from_results_file(
            aggregator,
            results_file=results_file,
            logger=run_options.logger,
            updater_types=updater_types,
        )
    except KeyboardInterrupt:
        exit_via_sigint()
    except CliError as error:
        run_options.logger.error(str(error))
        raise typer.Exit(2) from error


def _run_aggregator_from_results_file(
    aggregator: AnyAggregator,
    *,
    results_file: Path,
    logger: Logger,
    updater_types: Sequence[type[AnyUpdater]],
) -> None:
    artifact = read_results_file(results_file)
    updater_type = resolve_updater_type(artifact.updater, updater_types)
    results = parse_update_results(
        artifact,
        updater_type=updater_type,
    )
    _check_aggregator_result_compatibility(
        updater_name=artifact.updater,
        item_type=updater_type.item_type,
        output_type=updater_type.output_type,
        aggregator=aggregator,
    )

    logger.info(f'Running aggregator "{aggregator.name}"...')
    aggregator.aggregate(results, logger, artifact)


def _check_aggregator_result_compatibility(
    *,
    updater_name: str,
    item_type: type[UpdateItem],
    output_type: type[UpdateOutput],
    aggregator: AnyAggregator,
) -> None:
    if not issubclass(item_type, aggregator.item_type):
        raise CliError(
            f"Aggregator {aggregator.name!r} expects item type "
            f"{aggregator.item_type.__name__} or a subclass, but updater "
            f"{updater_name!r} produces {item_type.__name__}."
        )
    if not issubclass(output_type, aggregator.output_type):
        raise CliError(
            f"Aggregator {aggregator.name!r} expects output type "
            f"{aggregator.output_type.__name__} or a subclass, but updater "
            f"{updater_name!r} produces {output_type.__name__}."
        )
