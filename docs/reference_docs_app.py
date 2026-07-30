import argparse
import re
import subprocess
import sys
from pathlib import Path

from griffe import Module, load
from griffe2md import ConfigDict, render_object_docs

from quant_ranger._impl.cli._app import make_app

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DIR = Path(__file__).parent / "contents" / "reference"
CLI_OUTPUT_PATH = REFERENCE_DIR / "cli.md"
PYTHON_OUTPUT_PATH = REFERENCE_DIR / "python-api.md"
OUTPUT_PATHS = (CLI_OUTPUT_PATH, PYTHON_OUTPUT_PATH)

CLI_PAGE_PREFIX = """---
custom_edit_url: null
hide_table_of_contents: true
---

import TOCInline from '@theme/TOCInline';
"""
CLI_GENERATED_NOTE = """:::note[Built-in commands]

This page lists built-in commands. Installed plugins may add commands, and site
configuration may change runtime defaults.

:::"""
CLI_INLINE_TOC = """**Commands on this page**

<TOCInline toc={toc} minHeadingLevel={2} maxHeadingLevel={3} />"""
PYTHON_PAGE_PREFIX = """---
custom_edit_url: null
hide_table_of_contents: true
---

import TOCInline from '@theme/TOCInline';

# Python API reference

Public interfaces for writing plugins and integrating quant-ranger with
other Python code. See
[Installable plugins](../plugins/installable-plugins.md) for a
complete implementation.

**Modules on this page**

<TOCInline toc={toc} minHeadingLevel={2} maxHeadingLevel={2} />
"""
PYTHON_MODULES = (
    "quant_ranger",
    "quant_ranger.scanners",
    "quant_ranger.updaters",
    "quant_ranger.aggregators",
    "quant_ranger.site_config",
)
PYTHON_RENDER_CONFIG: ConfigDict = {
    "annotations_path": "brief",
    "docstring_section_style": "list",
    "filters": ["!^_"],
    "group_by_category": False,
    "heading_level": 2,
    "inherited_members": False,
    "line_length": 88,
    "members_order": "source",
    "merge_init_into_class": True,
    "separate_signature": True,
    "show_bases": True,
    "show_category_heading": True,
    "show_if_no_docstring": True,
    "show_object_full_path": False,
    "show_root_full_path": True,
    "show_root_heading": True,
    "show_root_members_full_path": False,
    "show_signature": True,
    "show_signature_annotations": True,
    "show_submodules": False,
    "signature_crossrefs": False,
    "summary": True,
}
ANCHOR_LINK_RE = re.compile(r"\[([^\n]+?)\]\(#[^)]+\)")
HEADING_BACKTICKS_RE = re.compile(r"^(#{1,6}) `(.+?)`$", re.MULTILINE)

# Keep generated docs independent of installed plugins and deployment defaults.
app = make_app(load_plugins=False)


def _add_cli_page_metadata(generated: str) -> str:
    heading, separator, body = generated.partition("\n")
    if heading != "# CLI reference" or not separator:
        msg = "Generated CLI reference has an unexpected heading."
        raise RuntimeError(msg)
    return (
        f"{CLI_PAGE_PREFIX}\n{heading}\n\n{CLI_GENERATED_NOTE}\n\n"
        f"{CLI_INLINE_TOC}\n\n{body.lstrip()}"
    )


def _generate_cli_reference(output_path: Path) -> None:
    subprocess.run(
        [
            "typer",
            "--app",
            "app",
            str(Path(__file__).resolve()),
            "utils",
            "docs",
            "--name",
            "quant-ranger",
            "--title",
            "CLI reference",
            "--output",
            str(output_path),
        ],
        check=True,
        # `typer` reports the output path, which is noise next to the pixi task
        # header and misleading when only checking for staleness.
        stdout=subprocess.DEVNULL,
    )
    generated = output_path.read_text(encoding="utf-8")
    output_path.write_text(_add_cli_page_metadata(generated), encoding="utf-8")


def _get_module(package: Module, module_name: str) -> Module:
    if module_name == package.path:
        return package

    member = package.get_member(module_name.removeprefix(f"{package.path}."))
    if not isinstance(member, Module):
        msg = f"{module_name} is not a module."
        raise TypeError(msg)
    return member


def _render_python_module(module: Module) -> str:
    if module.exports is None:
        msg = f"{module.path} does not define __all__."
        raise RuntimeError(msg)

    config: ConfigDict = {
        **PYTHON_RENDER_CONFIG,
        "members": [
            str(name) for name in module.exports if not str(name).startswith("_")
        ],
    }
    rendered = render_object_docs(module, config, format_md=True)
    rendered = HEADING_BACKTICKS_RE.sub(r"\1 \2", rendered)
    return ANCHOR_LINK_RE.sub(r"\1", rendered).strip()


def _generate_python_reference(output_path: Path) -> None:
    package = load(
        "quant_ranger",
        submodules=True,
        search_paths=[PROJECT_ROOT],
        resolve_aliases=True,
    )
    if not isinstance(package, Module):
        msg = "quant_ranger is not a module."
        raise TypeError(msg)

    modules = [_get_module(package, module_name) for module_name in PYTHON_MODULES]
    rendered = "\n\n".join(_render_python_module(module) for module in modules)
    output_path.write_text(
        f"{PYTHON_PAGE_PREFIX}\n{rendered}\n",
        encoding="utf-8",
    )


STALE_MESSAGE = """\
The committed reference pages were out of date:

{paths}

They are generated from the CLI definition and the public Python API, so a
change to either has to be regenerated and committed alongside it. The pages
above have just been regenerated for you -- stage them together with your source
change:

    git add {paths_arg}

To regenerate them yourself at any point, run `pixi run -e docs docs-reference`."""


def _check() -> int:
    # Regenerate in place rather than into a scratch directory, so the check
    # runs the exact same code path as `docs-reference` and cannot disagree with
    # it. Git then tells us whether that changed anything.
    _generate()
    changed = subprocess.run(
        ["git", "diff", "--name-only", "--", *(str(path) for path in OUTPUT_PATHS)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.split()
    if not changed:
        return 0

    print(
        STALE_MESSAGE.format(
            paths="\n".join(f"  {path}" for path in changed),
            paths_arg=" ".join(changed),
        ),
        file=sys.stderr,
    )
    return 1


def _generate() -> None:
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    _generate_cli_reference(CLI_OUTPUT_PATH)
    _generate_python_reference(PYTHON_OUTPUT_PATH)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed reference pages differ from generated ones.",
    )
    if parser.parse_args().check:
        return _check()

    _generate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
