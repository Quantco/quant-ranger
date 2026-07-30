import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer

from quant_ranger import __version__
from quant_ranger._impl.helpers import CliError
from quant_ranger._impl.logger import ConsoleLogger, Logger

from .._plugins import (
    available_aggregator_types,
    available_updater_types,
    load_site_config,
)
from ._aggregate import (
    BUILTIN_AGGREGATORS,
    AggregateRunOptions,
    make_aggregate_command,
)
from ._update import BUILTIN_UPDATERS, UpdateRunOptions, make_update_command

PROGRAM_NAME = "quant-ranger"
DEBUG_WARNING = "Debug logging may include sensitive subprocess stdout or stderr."
ROOT_USER_WARNING = (
    "Running quant-ranger as root is unsafe: birdcage sandboxing is not secure "
    "when the process has root privileges. Re-run as an unprivileged user."
)


RepositoryOption = Annotated[
    list[str] | None,
    typer.Option(
        "--repository",
        "-r",
        help=(
            "Repository to process. Repeat this option or use comma-separated "
            "values. Accepts repo, owner/repo, and either form with @branch."
        ),
    ),
]
GhOption = Annotated[
    bool,
    typer.Option(
        "--gh",
        help=(
            "Use `gh auth token` for GitHub authentication. Takes precedence over "
            "GitHub App credentials, GH_TOKEN, and GITHUB_TOKEN."
        ),
    ),
]
GitHubApiUrlOption = Annotated[
    str,
    typer.Option(
        "--github-api-url",
        help="GitHub API base URL.",
    ),
]
OwnerOption = Annotated[
    str | None,
    typer.Option(
        "--owner",
        help=(
            "Owner for bare repository names. When --repository is omitted, "
            "discover active, non-empty repositories for this owner."
        ),
    ),
]
DebugOption = Annotated[
    bool,
    typer.Option(
        "--debug",
        "-d",
        help=(
            "Enable verbose diagnostic logging. This may include sensitive "
            "subprocess stdout or stderr."
        ),
    ),
]
ConcurrencyOption = Annotated[
    int,
    typer.Option(
        "--jobs",
        "-j",
        min=1,
        help="Number of scanner and updater tasks to run concurrently.",
    ),
]
PublishChangesOption = Annotated[
    bool,
    typer.Option(
        "--publish-changes",
        help=(
            "Push managed branches and create or update pull requests. Without "
            "this, quant-ranger does not push or modify pull requests."
        ),
    ),
]
ForcePushOption = Annotated[
    bool,
    typer.Option(
        "--force-push",
        help=(
            "Allow overwriting managed pull request branches that contain "
            "manual changes. Requires --repository and does not enable "
            "publishing."
        ),
    ),
]
ResultsFileOption = Annotated[
    Path | None,
    typer.Option(
        "--results-file",
        help=(
            "Write task results and scan failures to a JSON artifact for "
            "`aggregate`. Unsupported by `custom`."
        ),
    ),
]
PrDetailsOption = Annotated[
    bool,
    typer.Option(
        "--pr-details",
        help="Show pull request details, including the full diff.",
    ),
]
PrDetailsDiffLinesOption = Annotated[
    int | None,
    typer.Option(
        "--pr-details-diff-lines",
        min=1,
        help="Trim pull request detail diffs and enable --pr-details.",
    ),
]
AllInstalledRepositoriesOption = Annotated[
    bool,
    typer.Option(
        "--all-installed-repositories",
        help=(
            "Process all repositories this GitHub App has access to, across all "
            "installations. This option can only be used with GitHub App "
            "credentials and cannot be combined with --owner or --repository."
        ),
    ),
]


def make_app(
    *,
    startup_logger: Logger | None = None,
    load_plugins: bool = True,
) -> typer.Typer:
    """Build the quant-ranger CLI app with all updater and aggregator commands.

    Plugin commands are discovered from entry points unless `load_plugins` is
    False. The startup logger only reports plugin loading; it defaults to a
    non-debug console logger.
    """
    startup_logger = startup_logger if startup_logger is not None else ConsoleLogger()
    try:
        site_config = load_site_config(
            logger=startup_logger,
            load_plugins=load_plugins,
        )
    except CliError as error:
        startup_logger.error(str(error))
        raise SystemExit(2) from error

    app = typer.Typer(
        help="Run repository maintenance and process results.",
        rich_markup_mode="rich",
    )
    update_app = typer.Typer(
        help=(
            "Run repository update tasks. Runs are dry by default. Pass "
            "--publish-changes to push branches and create or update pull requests."
        ),
        no_args_is_help=True,
        rich_markup_mode="rich",
    )
    aggregate_app = typer.Typer(
        help=(
            "Process update results. Run an aggregator over a JSON artifact "
            "written by `quant-ranger update`."
        ),
        no_args_is_help=True,
        rich_markup_mode="rich",
    )
    app.add_typer(update_app, name="update")
    app.add_typer(aggregate_app, name="aggregate")

    @app.callback(invoke_without_command=True)
    def root(
        context: typer.Context,
        _version: Annotated[
            bool,
            typer.Option(
                "--version",
                callback=_version_callback,
                is_eager=True,
                help="Show program's version number and exit.",
            ),
        ] = False,
    ) -> None:
        if context.invoked_subcommand is None:
            typer.echo(context.get_help())
            raise typer.Exit()

    @update_app.callback()
    def update(
        context: typer.Context,
        repositories: RepositoryOption = None,
        # Do not turn a missing site default into Typer's required-option
        # sentinel: Click would reject the command before
        # --all-installed-repositories could satisfy the requirement.
        owner: OwnerOption = site_config.default_owner,
        all_installed_repositories: AllInstalledRepositoriesOption = False,
        gh: GhOption = False,
        github_api_url: GitHubApiUrlOption = site_config.default_github_api_url,
        concurrency: ConcurrencyOption = 1,
        debug: DebugOption = False,
        publish_changes: PublishChangesOption = False,
        force_push: ForcePushOption = False,
        results_file: ResultsFileOption = None,
        pr_details: PrDetailsOption = False,
        pr_details_diff_lines: PrDetailsDiffLinesOption = None,
    ) -> None:
        owner_source = context.get_parameter_source("owner")
        if (
            all_installed_repositories
            and owner_source is not None
            and owner_source.name == "COMMANDLINE"
        ):
            raise typer.BadParameter(
                "`--owner` and `--all-installed-repositories` cannot be used together."
            )
        if repositories is not None and all_installed_repositories:
            raise typer.BadParameter(
                "`--repository` and `--all-installed-repositories` cannot be used together."
            )
        context.obj = UpdateRunOptions(
            raw_repositories=repositories or [],
            owner=owner,
            all_installed_repositories=all_installed_repositories,
            use_gh=gh,
            github_api_url=github_api_url,
            concurrency=concurrency,
            publish_changes=publish_changes,
            force_push=force_push,
            results_file=results_file,
            show_pr_details=pr_details or pr_details_diff_lines is not None,
            pr_details_diff_lines=pr_details_diff_lines,
            logger=_make_logger(debug),
            site_config=site_config,
        )

    @aggregate_app.callback()
    def aggregate(
        context: typer.Context,
        debug: DebugOption = False,
    ) -> None:
        context.obj = AggregateRunOptions(
            logger=_make_logger(debug),
        )

    updater_types = available_updater_types(
        builtin_types=BUILTIN_UPDATERS,
        logger=startup_logger,
        load_plugins=load_plugins,
    )
    aggregator_types = available_aggregator_types(
        builtin_types=BUILTIN_AGGREGATORS,
        logger=startup_logger,
        load_plugins=load_plugins,
    )
    for updater_type in updater_types:
        update_app.command(
            updater_type.name,
            help=updater_type.description,
            rich_help_panel=_plugin_help_panel(updater_type, BUILTIN_UPDATERS),
        )(make_update_command(updater_type, site_config))
    for aggregator_type in aggregator_types:
        aggregate_app.command(
            aggregator_type.name,
            help=aggregator_type.description,
            rich_help_panel=_plugin_help_panel(aggregator_type, BUILTIN_AGGREGATORS),
        )(make_aggregate_command(aggregator_type, updater_types, site_config))

    return app


def _plugin_help_panel(
    command_type: type,
    builtin_types: Sequence[type],
) -> str | None:
    """Group plugin commands into a help panel named after their package.

    Builtin commands stay in the default panel.
    """
    if command_type in builtin_types:
        return None
    package = command_type.__module__.partition(".")[0]
    return f"Plugin commands ({package})"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"{PROGRAM_NAME} {__version__}")
        raise typer.Exit()


def _make_logger(debug: bool) -> ConsoleLogger:
    logger = ConsoleLogger(debug=debug)
    if debug:
        logger.warning(DEBUG_WARNING)
    return logger


def _is_root_user() -> bool:
    get_effective_user_id = getattr(os, "geteuid", None)
    return get_effective_user_id is not None and get_effective_user_id() == 0


def _debug_in_argv(arguments: Sequence[str]) -> bool:
    for argument in arguments:
        if argument == "--":
            return False
        if argument in {"--debug", "-d"}:
            return True
    return False


def main() -> None:
    if _is_root_user():
        typer.secho(
            f"warning: {ROOT_USER_WARNING}",
            fg=typer.colors.YELLOW,
            err=True,
        )
    # Commands must be registered before Typer parses arguments, so debug
    # plugin logging can only be enabled via a plain argv scan.
    debug = _debug_in_argv(sys.argv)
    logger = ConsoleLogger(debug=debug)
    try:
        app = make_app(startup_logger=logger)
        app()
    except Exception as error:
        logger.exception("Unexpected error", error)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
