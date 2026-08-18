import warnings as _warnings
from importlib import metadata as _metadata

from quant_ranger._impl.artifacts import UpdateResultsArtifact
from quant_ranger._impl.git import RepositoryCheckout
from quant_ranger._impl.github import GitHubClient, GitHubError, PullRequestOptions
from quant_ranger._impl.helpers import (
    CommandError,
    ExecOutput,
    get_exec_output_silently,
)
from quant_ranger._impl.logger import Logger
from quant_ranger._impl.models import (
    Diagnostics,
    PathUpdateItem,
    RepositoryRef,
    ScanFailure,
    Schedule,
    ScheduledPathUpdateItem,
    ScheduledUpdateItem,
    Status,
    UpdateItem,
    UpdateOptions,
    UpdateOutcome,
    UpdateOutput,
    UpdateResult,
)
from quant_ranger._impl.runtime import RunContext

__all__ = [
    "CommandError",
    "Diagnostics",
    "ExecOutput",
    "GitHubClient",
    "GitHubError",
    "Logger",
    "PathUpdateItem",
    "PullRequestOptions",
    "RepositoryCheckout",
    "RepositoryRef",
    "RunContext",
    "ScanFailure",
    "Schedule",
    "ScheduledPathUpdateItem",
    "ScheduledUpdateItem",
    "Status",
    "UpdateItem",
    "UpdateOptions",
    "UpdateOutcome",
    "UpdateOutput",
    "UpdateResult",
    "UpdateResultsArtifact",
    "__version__",
    "get_exec_output_silently",
]

try:
    __version__ = _metadata.version(__name__)
except _metadata.PackageNotFoundError as e:  # pragma: no cover
    _warnings.warn(f"Could not determine version of {__name__}\n{e!s}", stacklevel=2)
    __version__ = "unknown"
