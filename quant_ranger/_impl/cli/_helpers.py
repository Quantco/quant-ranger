"""Helpers for Typer commands generated from tool option models.

Updater and aggregator subcommands are registered from Python classes, and their
CLI options live on Pydantic models instead of normal function parameters. The
actual command closures therefore accept ``typer.Context`` plus
``**option_values`` at runtime, while Typer still needs a regular
``inspect.Signature`` to build the command-line interface.
"""

import inspect
from typing import Annotated, get_args, get_origin, get_type_hints

import typer
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from quant_ranger._impl.cli_options import SiteConfigParameter
from quant_ranger._impl.site_config import SiteConfig


def _context_parameter() -> inspect.Parameter:
    # Typer injects this object so generated commands can read callback state
    # such as the logger and update/aggregate run options from ``context.obj``.
    return inspect.Parameter(
        "context",
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        annotation=typer.Context,
    )


def _field_default(
    field: FieldInfo,
) -> object:
    # Required Pydantic fields become required CLI options. Optional fields
    # keep their model defaults so Typer displays and applies them normally.
    if field.is_required():
        return inspect.Parameter.empty
    return field.get_default(call_default_factory=True)


def _resolve_site_config_annotation(
    type_hint: object,
    site_config: SiteConfig,
) -> object:
    if get_origin(type_hint) is not Annotated:
        return type_hint

    base_type, *metadata = get_args(type_hint)
    if not any(isinstance(item, SiteConfigParameter) for item in metadata):
        return type_hint

    resolved_metadata = tuple(
        item.resolve(site_config) if isinstance(item, SiteConfigParameter) else item
        for item in metadata
    )
    return Annotated[base_type, *resolved_metadata]


def _model_parameters(
    options_type: type[BaseModel],
    site_config: SiteConfig,
) -> list[inspect.Parameter]:
    # Preserve ``Annotated[..., typer.Option(...)]`` metadata from option models;
    # Typer reads those annotations from the synthetic signature.
    type_hints = get_type_hints(options_type, include_extras=True)
    return [
        inspect.Parameter(
            name,
            inspect.Parameter.KEYWORD_ONLY,
            annotation=_resolve_site_config_annotation(
                type_hints[name],
                site_config,
            ),
            default=_field_default(field),
        )
        for name, field in options_type.model_fields.items()
    ]


def command_signature(
    options_type: type[BaseModel],
    *parameters: inspect.Parameter,
    site_config: SiteConfig,
) -> inspect.Signature:
    # The closure's real signature is
    # ``(context, **option_values)``, but Typer sees this synthetic signature.
    # It calls the closure with ``context``, any explicit command parameters
    # such as ``results_file``, and keyword values for each option-model field.
    return inspect.Signature(
        [
            _context_parameter(),
            *parameters,
            *_model_parameters(options_type, site_config),
        ]
    )
