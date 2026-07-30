from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import typer

from quant_ranger._impl.artifacts import write_results_file
from quant_ranger._impl.github import (
    GitHubClient,
    GitHubError,
    app_installation_clients,
    resolve_github_app_credentials,
    resolve_github_token,
)
from quant_ranger._impl.helpers import CliError, CommandError, exit_via_sigint
from quant_ranger._impl.logger import Logger
from quant_ranger._impl.models import RepositoryRef, Status
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.site_config import SiteConfig
from quant_ranger._impl.updaters import (
    AnyUpdater,
    CopierMigrationUpdater,
    CopierUpdater,
    CustomUpdater,
    GitHubAppTokenUpdater,
    NodeDependencyCooldownUpdater,
    PixiUpdateUpdater,
    PixiVersionUpdater,
    ZizmorUpdater,
)

from ._helpers import command_signature

BUILTIN_UPDATERS: tuple[type[AnyUpdater], ...] = (
    ZizmorUpdater,
    CopierUpdater,
    CopierMigrationUpdater,
    PixiVersionUpdater,
    PixiUpdateUpdater,
    NodeDependencyCooldownUpdater,
    GitHubAppTokenUpdater,
    CustomUpdater,
)


@dataclass(frozen=True, slots=True)
class UpdateRunOptions:
    raw_repositories: Sequence[str]
    owner: str | None
    all_installed_repositories: bool
    use_gh: bool
    github_api_url: str
    concurrency: int
    publish_changes: bool
    force_push: bool
    results_file: Path | None
    logger: Logger
    site_config: SiteConfig
    show_pr_details: bool = False
    pr_details_diff_lines: int | None = None


def make_update_command(
    updater_type: type[AnyUpdater],
    site_config: SiteConfig,
) -> Callable[..., None]:
    options_type = updater_type.options_type

    def run_update_command(
        context: typer.Context,
        **option_values: object,
    ) -> None:
        run_options = context.obj
        _run_update_with_error_handling(updater_type, option_values, run_options)

    run_update_command.__name__ = updater_type.name
    setattr(
        run_update_command,
        "__signature__",
        command_signature(options_type, site_config=site_config),
    )
    return run_update_command


def _run_update_with_error_handling(
    updater_type: type[AnyUpdater],
    option_values: Mapping[str, object],
    run_options: UpdateRunOptions,
) -> None:
    try:
        if run_options.results_file is not None and issubclass(
            updater_type, CustomUpdater
        ):
            raise CliError(
                "`--results-file` is not supported for custom updaters. Write results yourself instead."
            )

        options = updater_type.options_type.model_validate(option_values)
        updater = updater_type(options)
        _run_update(
            updater=updater,
            raw_repositories=run_options.raw_repositories,
            owner=run_options.owner,
            all_installed_repositories=run_options.all_installed_repositories,
            use_gh=run_options.use_gh,
            github_api_url=run_options.github_api_url,
            concurrency=run_options.concurrency,
            publish_changes=run_options.publish_changes,
            force_push=run_options.force_push,
            show_pr_details=run_options.show_pr_details,
            pr_details_diff_lines=run_options.pr_details_diff_lines,
            logger=run_options.logger,
            results_file=run_options.results_file,
            site_config=run_options.site_config,
        )
    except KeyboardInterrupt:
        exit_via_sigint()
    except CliError as error:
        run_options.logger.error(str(error))
        raise typer.Exit(2) from error


def _run_update(
    *,
    updater: AnyUpdater,
    raw_repositories: Sequence[str],
    owner: str | None,
    all_installed_repositories: bool,
    use_gh: bool,
    github_api_url: str,
    concurrency: int,
    publish_changes: bool,
    force_push: bool,
    show_pr_details: bool = False,
    pr_details_diff_lines: int | None = None,
    logger: Logger,
    results_file: Path | None = None,
    site_config: SiteConfig,
) -> None:
    explicit_repositories = _parse_repository_arguments(
        raw_repositories,
        default_owner=owner,
    )
    if not explicit_repositories and owner is None and not all_installed_repositories:
        raise CliError(
            "`--owner`, `--repository owner/repo`, or "
            "`--all-installed-repositories` is required."
        )
    if force_push and not explicit_repositories:
        raise CliError(
            "`--force-push` requires explicit repositories via `--repository`."
        )

    contexts = _make_run_contexts(
        use_gh=use_gh,
        github_api_url=github_api_url,
        publish_changes=publish_changes,
        force_push=force_push,
        show_pr_details=show_pr_details,
        pr_details_diff_lines=pr_details_diff_lines,
        logger=logger,
        site_config=site_config,
    )

    repositories_by_context: list[tuple[RunContext, list[RepositoryRef]]] = []
    try:
        for context in contexts:
            client = context.github_client
            installation_owner = client.installation_owner
            if explicit_repositories:
                # Installation clients can only see their own owner (user/organization),
                # so restrict explicit repository checks to that installation.
                candidates = explicit_repositories
                if installation_owner is not None:
                    candidates = [
                        repository
                        for repository in candidates
                        if repository.owner.lower() == installation_owner.lower()
                    ]
                repositories = [
                    repository
                    for repository in candidates
                    if client.check_ref_exists(repository)
                ]
                if not repositories:
                    continue
            elif all_installed_repositories:
                repositories = client.installed_repositories()
            else:
                assert owner is not None
                if installation_owner is not None:
                    if installation_owner.lower() != owner.lower():
                        continue
                    repositories = client.installed_repositories()
                else:
                    repositories = client.active_repositories(owner)
            repositories_by_context.append((context, repositories))
    except GitHubError as error:
        raise CliError(str(error)) from error

    processed_explicit_repositories = {
        repository
        for _, repositories in repositories_by_context
        for repository in repositories
    }
    unprocessed_repositories = [
        repository
        for repository in explicit_repositories
        if repository not in processed_explicit_repositories
    ]
    if unprocessed_repositories:
        subject = (
            "Repository or branch"
            if len(unprocessed_repositories) == 1
            else "Repositories or branches"
        )
        verb = "was" if len(unprocessed_repositories) == 1 else "were"
        names = ", ".join(
            repository.display_name for repository in unprocessed_repositories
        )
        raise CliError(f"{subject} {verb} not found or inaccessible: {names}.")

    if (
        not explicit_repositories
        and not all_installed_repositories
        and not repositories_by_context
    ):
        raise CliError(f"No GitHub App installation found for owner {owner!r}.")

    repository_count = sum(
        len(repositories) for _, repositories in repositories_by_context
    )
    mode = "write mode" if publish_changes else "dry run"
    logger.info(
        f'Running updater "{updater.name}" '
        f"for {repository_count} repositories ({mode})..."
    )

    results = []
    scan_failures = []
    for context, repositories in repositories_by_context:
        scan_output = updater.scanner.scan_all(
            repositories,
            context,
            concurrency=concurrency,
        )
        scan_failures.extend(scan_output.scan_failures)
        results.extend(
            updater.update_all(
                scan_output.update_items,
                context,
                concurrency=concurrency,
            )
        )

    skipped = sum(result.result == Status.SKIPPED for result in results)
    updated = sum(result.result == Status.UPDATED for result in results)
    up_to_date = sum(result.result == Status.UP_TO_DATE for result in results)
    failed = sum(result.result == Status.FAILURE for result in results)
    scan_failed = len(scan_failures)
    logger.info(
        "Update finished: "
        f"{skipped} skipped, "
        f"{updated} updated, "
        f"{up_to_date} up-to-date, "
        f"{failed} failed, "
        f"{scan_failed} failed during scanning."
    )

    if results_file is not None:
        write_results_file(
            results_file,
            updater=updater,
            results=results,
            scan_failures=scan_failures,
        )
        logger.info(f"Wrote updater results to {results_file}.")


def _make_run_contexts(
    *,
    use_gh: bool,
    github_api_url: str,
    publish_changes: bool,
    force_push: bool = False,
    show_pr_details: bool = False,
    pr_details_diff_lines: int | None = None,
    logger: Logger,
    site_config: SiteConfig,
) -> list[RunContext]:
    app_credentials = None
    if not use_gh:
        try:
            app_credentials = resolve_github_app_credentials()
        except GitHubError as error:
            raise CliError(str(error)) from error

    if app_credentials is not None:
        try:
            clients = app_installation_clients(
                app_credentials,
                logger=logger,
                api_url=github_api_url,
                publish_changes=publish_changes,
                force_push=force_push,
                show_pr_details=show_pr_details,
                pr_details_diff_lines=pr_details_diff_lines,
                fallback_commit_author=site_config.fallback_commit_author,
            )
        except GitHubError as error:
            raise CliError(str(error)) from error
        return [
            RunContext(
                github_client=client,
                # The client logger is prefixed with the installation owner;
                # reuse it so all per-installation logging is distinguishable.
                logger=client.logger,
                site_config=site_config,
            )
            for client in clients
        ]

    try:
        token = resolve_github_token(use_gh=use_gh)
    except CommandError as error:
        raise CliError(
            f"Failed to resolve GitHub token: Exit code {error.output.exit_code}"
        ) from error

    if token is None:
        raise CliError(
            "GitHub authentication is required. Pass --gh to use `gh auth token`, "
            "set GH_APP_CLIENT_ID and GH_APP_PRIVATE_KEY, or set GH_TOKEN or "
            "GITHUB_TOKEN."
        )

    return [
        RunContext(
            github_client=GitHubClient(
                token_or_installation=token,
                logger=logger,
                api_url=github_api_url,
                publish_changes=publish_changes,
                force_push=force_push,
                show_pr_details=show_pr_details,
                pr_details_diff_lines=pr_details_diff_lines,
                fallback_commit_author=site_config.fallback_commit_author,
            ),
            logger=logger,
            site_config=site_config,
        )
    ]


def _parse_repository_arguments(
    raw_repositories: Sequence[str],
    *,
    default_owner: str | None,
) -> list[RepositoryRef]:
    repositories: list[RepositoryRef] = []
    for raw_spec in raw_repositories:
        for spec in (part.strip() for part in raw_spec.split(",")):
            if not spec:
                continue
            try:
                parsed = RepositoryRef.parse(
                    spec,
                    default_owner=default_owner,
                    default_branch=None,
                )
            except ValueError as error:
                raise CliError(str(error)) from error
            repositories.append(parsed)
    return repositories
