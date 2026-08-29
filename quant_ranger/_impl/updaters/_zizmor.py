from importlib.resources import as_file, files
from typing import override
from urllib.parse import urlsplit

from quant_ranger._impl.github import PullRequestOptions, github_web_url
from quant_ranger._impl.helpers import CommandError, get_exec_output_silently
from quant_ranger._impl.models import Status, UpdateItem, UpdateOutcome
from quant_ranger._impl.scanners import RepositoriesScanner

from ._base import Updater, UpdateTask

ZIZMOR_CONFIG_RESOURCE = files("quant_ranger._impl.updaters").joinpath("zizmor.yml")
NO_INPUTS_COLLECTED_MARKERS = (
    "no inputs collected",
    "collection yielded no auditable inputs",
)


class ZizmorUpdateTask(UpdateTask[UpdateItem]):
    @override
    def run(self) -> UpdateOutcome:
        github_client = self.context.github_client
        logger = self.context.logger

        logger.debug("Running zizmor to fix GitHub Actions findings.")
        env = {"GH_TOKEN": github_client.token}
        enterprise_host = _github_enterprise_host(github_client.api_url)
        if enterprise_host is not None:
            env["GH_HOST"] = enterprise_host
        try:
            with as_file(ZIZMOR_CONFIG_RESOURCE) as config_path:
                get_exec_output_silently(
                    [
                        "zizmor",
                        "--config",
                        str(config_path),
                        "--fix=all",
                        "--no-exit-codes",
                        ".",
                    ],
                    cwd=self.checkout.absolute_path,
                    env=env,
                    logger=logger,
                    redact=[github_client.token],
                )
        except CommandError as error:
            if _is_no_inputs_collected_error(error):
                logger.debug(
                    "No auditable GitHub Actions workflow, action, or Dependabot "
                    "config found."
                )
                return UpdateOutcome(
                    result=Status.SKIPPED,
                    message="No auditable zizmor inputs found.",
                )
            return UpdateOutcome(
                result=Status.FAILURE,
                message=str(error),
                details=error.details,
            )
        if self.checkout.is_clean():
            logger.debug("No changes detected. All findings are already resolved.")
            return UpdateOutcome(result=Status.UP_TO_DATE)

        self.checkout.add_all()
        pull_request_template = self.context.site_config.pull_request_templates.zizmor
        pr_opened = github_client.create_pull_request(
            self.checkout,
            PullRequestOptions(
                title=pull_request_template.title,
                body=pull_request_template.body,
                source_branch=pull_request_template.branch_prefix,
                quant_ranger_id=ZizmorUpdater.name,
            ),
            logger,
        )

        if not pr_opened:
            return UpdateOutcome(result=Status.SKIPPED)

        return UpdateOutcome(result=Status.UPDATED)


class ZizmorUpdater(Updater[UpdateItem]):
    name = "zizmor"
    description = (
        "Fix configured zizmor findings. Applies the packaged automatic fixes "
        "to GitHub Actions and Dependabot configuration."
    )
    scanner = RepositoriesScanner()
    task_type = ZizmorUpdateTask


def _github_enterprise_host(api_url: str) -> str | None:
    """Extract the GitHub Enterprise host from an API URL.

    Returns `None` for github.com, where zizmor needs no host configuration.
    """
    hostname = (urlsplit(github_web_url(api_url)).hostname or "").lower()
    if hostname in ("", "github.com"):
        return None
    return hostname


def _is_no_inputs_collected_error(error: CommandError) -> bool:
    output = f"{error.output.stdout}\n{error.output.stderr}".lower()
    return any(marker in output for marker in NO_INPUTS_COLLECTED_MARKERS)
