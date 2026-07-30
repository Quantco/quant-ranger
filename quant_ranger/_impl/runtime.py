from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from quant_ranger._impl.logger import ConsoleLogger, Logger

if TYPE_CHECKING:
    from quant_ranger._impl.github import GitHubClient
    from quant_ranger._impl.site_config import SiteConfig


@dataclass(slots=True)
class RunContext:
    """Runtime dependencies shared across scanner and updater operations."""

    github_client: GitHubClient
    site_config: SiteConfig
    logger: Logger = field(default_factory=ConsoleLogger)
