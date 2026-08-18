import shutil
from importlib import resources
from pathlib import Path

import typer

from quant_ranger._impl.helpers import CliError
from quant_ranger._impl.logger import Logger


def export_frontend(output_directory: Path, logger: Logger) -> None:
    """Copy the packaged static frontend without replacing existing data."""
    assets = resources.files("quant_ranger").joinpath("_frontend")
    if not assets.is_dir():
        raise CliError("This quant-ranger installation has no frontend assets.")

    try:
        output_directory.mkdir(parents=True, exist_ok=True)
        with resources.as_file(assets) as assets_path:
            shutil.copytree(assets_path, output_directory, dirs_exist_ok=True)
    except OSError as error:
        raise CliError(
            f"Failed to export the frontend to {output_directory}: {error}"
        ) from error

    logger.info(f"Wrote the frontend to {output_directory}.")


def make_frontend_app(logger: Logger) -> typer.Typer:
    app = typer.Typer(
        help="Export the packaged static frontend for self-hosting.",
        no_args_is_help=True,
        rich_markup_mode="rich",
    )

    @app.command("export")
    def export(
        output_directory: Path = typer.Option(
            ...,
            "--output-directory",
            "-o",
            help="Directory in which to write the static site.",
        ),
    ) -> None:
        """Write the packaged static frontend to a directory."""
        try:
            export_frontend(output_directory, logger)
        except CliError as error:
            logger.error(str(error))
            raise typer.Exit(2) from error

    return app
