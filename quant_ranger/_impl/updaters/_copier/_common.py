import re
from collections.abc import Iterable, Sequence
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from quant_ranger._impl.git import RepositoryCheckout
from quant_ranger._impl.github import git_basic_auth
from quant_ranger._impl.helpers import CommandError, get_exec_output_silently
from quant_ranger._impl.logger import Logger
from quant_ranger._impl.models import RepositoryRef

COPIER_ANSWERS_FILE = ".copier-answers.yml"


def _trusted_template_src_paths(templates: Iterable[str]) -> frozenset[str]:
    src_paths: set[str] = set()
    for template in templates:
        template_host, repository = template.lower().split("/", maxsplit=1)

        src_paths.update(
            {
                f"https://{template_host}/{repository}",
                f"https://{template_host}/{repository}.git",
                f"git@{template_host}:{repository}.git",
            }
        )
        if template_host == "github.com":
            src_paths.add(f"gh:{repository}")

    return frozenset(src_paths)


_GH_REPO_PATTERN = re.compile(
    r"^gh:(?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)
_HTTP_REPO_PATTERN = re.compile(
    r"^(?:https://)?(?P<host>[^/]+)/(?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)
_SSH_REPO_PATTERN = re.compile(
    r"^[^@]+@(?P<host>[^:]+):(?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?$",
    re.IGNORECASE,
)


class CopierAnswers(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    commit: str = Field(alias="_commit")
    src_path: str = Field(alias="_src_path")


def parse_copier_answers(content: str) -> CopierAnswers:
    try:
        parsed: object = yaml.safe_load(content)
        return CopierAnswers.model_validate(parsed)
    except (yaml.YAMLError, ValidationError) as error:
        raise ValueError(f"could not parse {COPIER_ANSWERS_FILE}: {error}") from error


def _parse_template_repository(src_path: str) -> tuple[str, RepositoryRef]:
    """Parse a template src_path into its GitHub host and repository.

    Raises ValueError for src_paths in unsupported formats.
    """
    match = _GH_REPO_PATTERN.match(src_path)
    if match is not None:
        return "github.com", RepositoryRef(
            owner=match.group("owner"),
            name=match.group("name"),
        )

    for pattern in (_HTTP_REPO_PATTERN, _SSH_REPO_PATTERN):
        match = pattern.match(src_path)
        if match is not None:
            return match.group("host").lower(), RepositoryRef(
                owner=match.group("owner"),
                name=match.group("name"),
            )
    msg = f"invalid or unsupported template URL in {COPIER_ANSWERS_FILE}: {src_path}"
    raise ValueError(msg)


def parse_template_repository_for_host(
    src_path: str,
    github_server_host: str,
) -> RepositoryRef:
    """To protect against SSRF, we only accept template src_paths that originate from
    the same GitHub host as the repository being updated.

    Raises ValueError for src_paths that do not match that host.
    """
    template_host, template_repository = _parse_template_repository(src_path)
    if template_host != github_server_host.lower():
        msg = (
            f"template URL in {COPIER_ANSWERS_FILE} points to {template_host} "
            f"instead of {github_server_host}: {src_path}"
        )
        raise ValueError(msg)
    return template_repository


def github_server_host_from_repository_url(repository_url: str) -> str:
    hostname = urlsplit(repository_url).hostname
    if hostname is None:
        msg = f"Could not determine GitHub host from repository URL: {repository_url}"
        raise ValueError(msg)
    return hostname.lower()


def is_trusted_template(
    src_path: str,
    trusted_templates: Iterable[str],
) -> bool:
    """Whether a template's update tasks may run with ``--trust``.

    ``--trust`` lets the template execute arbitrary code with the runner's
    GitHub token in its environment. Since copier updates may require trusted
    template hooks, we only run templates whose full ``_src_path`` string is on
    the ``trusted_templates`` allowlist of ``host/owner/name`` entries. We do a
    case-insensitive match against the full URL to protect against
    manipulations that might point to another repository.
    """
    return src_path.lower() in _trusted_template_src_paths(trusted_templates)


def untrusted_template_message(repository_ref: RepositoryRef, src_path: str) -> str:
    return (
        f"Copier template in {repository_ref.display_name} is not in "
        f"quant-ranger's trusted-template allowlist: {COPIER_ANSWERS_FILE}: "
        f"{src_path}. Copier will run without --trust."
    )


def make_copier_git_env(
    checkout: RepositoryCheckout,
    token: str,
    github_server_host: str,
) -> dict[str, str]:
    server_url = f"https://{github_server_host}"
    basic_auth = git_basic_auth(token)
    ssh_url = f"git@{github_server_host}"
    index = 0

    env: dict[str, str] = {}
    env[f"GIT_CONFIG_KEY_{index}"] = f"http.{server_url}/.extraHeader"
    env[f"GIT_CONFIG_VALUE_{index}"] = f"AUTHORIZATION: basic {basic_auth}"
    index += 1
    env[f"GIT_CONFIG_KEY_{index}"] = f"url.{server_url}/.insteadOf"
    env[f"GIT_CONFIG_VALUE_{index}"] = f"{ssh_url}:"
    index += 1
    env[f"GIT_CONFIG_KEY_{index}"] = "safe.directory"
    env[f"GIT_CONFIG_VALUE_{index}"] = str(checkout.absolute_path)
    index += 1
    env[f"GIT_CONFIG_KEY_{index}"] = "merge.conflictStyle"
    env[f"GIT_CONFIG_VALUE_{index}"] = "diff3"
    index += 1
    env["GIT_CONFIG_COUNT"] = str(index)

    # Copier will create some temporary commits during the update procedure.
    # These commits will never appear anywhere. However we still need to supply
    # names and email addresses as otherwise git will refuse to create them.
    env["GIT_AUTHOR_NAME"] = "copier[bot]"
    env["GIT_AUTHOR_EMAIL"] = "noreply@example.com"
    env["GIT_COMMITTER_NAME"] = "GitHub"
    env["GIT_COMMITTER_EMAIL"] = "noreply@github.com"

    return env


def run_copier_command(
    command: Sequence[str],
    checkout: RepositoryCheckout,
    logger: Logger,
    *,
    token: str,
    github_server_host: str,
) -> None:
    get_exec_output_silently(
        command,
        cwd=checkout.absolute_path,
        env=make_copier_git_env(
            checkout,
            token,
            github_server_host,
        ),
        logger=logger,
        redact=[token, git_basic_auth(token)],
    )


def attempt_mergiraf_solve(checkout: RepositoryCheckout, logger: Logger) -> None:
    for filename in checkout.changed_files(logger):
        try:
            get_exec_output_silently(
                ["mergiraf", "solve", "--keep-backup=false", filename],
                cwd=checkout.absolute_path,
                logger=logger,
            )
            logger.debug(f"Mergiraf resolved merge conflicts in {filename}.")
        except CommandError:
            logger.debug(
                f"Mergiraf could not resolve merge conflicts in {filename}; continuing."
            )


def run_pixi_lock_if_manifest_changed(
    checkout: RepositoryCheckout,
    logger: Logger,
) -> None:
    if not checkout.changed_files(logger, path="pixi.toml"):
        return

    logger.debug("pixi.toml was modified, running pixi lock to update the lock file.")
    try:
        get_exec_output_silently(
            ["pixi", "lock"],
            cwd=checkout.absolute_path,
            logger=logger,
        )
    except CommandError:
        logger.debug(
            "Running `pixi lock` failed. Likely due to merge conflicts in pixi.toml. "
            "Continuing."
        )
