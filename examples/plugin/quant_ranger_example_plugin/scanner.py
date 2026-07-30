import tomllib
from collections.abc import Sequence
from typing import override

from quant_ranger import RepositoryRef, RunContext, UpdateItem
from quant_ranger.scanners import Scanner


class PythonProjectItem(UpdateItem):
    project_name: str


class PythonProjectScanner(Scanner[PythonProjectItem]):
    @override
    def scan_repository(
        self,
        repository_ref: RepositoryRef,
        context: RunContext,
    ) -> Sequence[PythonProjectItem]:
        content = context.github_client.get_file_content(
            repository_ref,
            "pyproject.toml",
        )
        if content is None:
            context.logger.debug("No pyproject.toml found.")
            return []

        project = tomllib.loads(content).get("project")
        project_name = project.get("name") if isinstance(project, dict) else None
        if not isinstance(project_name, str):
            context.logger.debug("No project name found in pyproject.toml.")
            return []

        return [
            PythonProjectItem(
                repository_ref=repository_ref,
                project_name=project_name,
            )
        ]
