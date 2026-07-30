from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from textwrap import dedent
from typing import Any, cast

import pytest

from quant_ranger._impl.github import GitHubClient, PullRequestOptions
from quant_ranger._impl.logger import LogLevel
from quant_ranger._impl.models import (
    RepositoryRef,
    Status,
    UpdateItem,
    UpdateOutcome,
)
from quant_ranger._impl.runtime import RunContext
from quant_ranger._impl.testing import (
    FakeGitHubClient,
    RecordingCheckout,
    RecordingLogger,
)
from quant_ranger._impl.updaters._node_dependency_cooldown import (
    NodeDependencyCooldownOptions,
    NodeDependencyCooldownTask,
    set_bun_minimum_release_age,
    set_bun_minimum_release_age_excludes,
    set_npm_minimum_release_age,
    set_npm_minimum_release_age_excludes,
    set_pnpm_block_exotic_subdeps,
    set_pnpm_minimum_release_age,
    set_pnpm_minimum_release_age_excludes,
)
from quant_ranger.site_config import DEFAULT_PULL_REQUEST_TEMPLATES, SiteConfig

BUN_EXCLUDES = ("@example/config", "@example/ui")
PNPM_NPM_EXCLUDES = ("@example/*", "example-package")


@pytest.mark.parametrize(
    ("updater", "setting_line"),
    [
        (
            partial(set_bun_minimum_release_age, minimum_release_age_days=7),
            "minimumReleaseAge = 604800",
        ),
        (
            partial(set_bun_minimum_release_age_excludes, excludes=BUN_EXCLUDES),
            'minimumReleaseAgeExcludes = ["@example/config", "@example/ui"]',
        ),
    ],
)
def test_set_bun_install_setting_inserts_in_supported_locations(
    updater: Callable[[str], str | None],
    setting_line: str,
) -> None:
    assert updater("") == f"[install]\n{setting_line}\n"
    assert updater("[install]\nlockfile = true\n") == (
        f"[install]\n{setting_line}\nlockfile = true\n"
    )
    assert updater('[bundle]\nentrypoints = ["./index.ts"]\n') == (
        f'[bundle]\nentrypoints = ["./index.ts"]\n\n[install]\n{setting_line}\n'
    )
    assert updater("[install]") == f"[install]\n{setting_line}\n"


@pytest.mark.parametrize("age", [604800, 1000000])
def test_set_bun_minimum_release_age_returns_none_when_already_set(age: int) -> None:
    content = f"[install]\nminimumReleaseAge = {age}\n"
    assert set_bun_minimum_release_age(content, minimum_release_age_days=7) is None


@pytest.mark.parametrize(
    "excludes",
    [
        '["@example/config", "@example/ui"]',
        '["@example/config", "@example/ui", "@other/pkg"]',
    ],
)
def test_set_bun_minimum_release_age_excludes_returns_none_when_already_set(
    excludes: str,
) -> None:
    content = f"[install]\nminimumReleaseAgeExcludes = {excludes}\n"
    assert set_bun_minimum_release_age_excludes(content, excludes=BUN_EXCLUDES) is None


def test_set_bun_minimum_release_age_bumps_age_and_preserves_context() -> None:
    content = dedent(
        """
        [install]
        exact = true
        minimumReleaseAge   =   100
        minimumReleaseAgeExcludes = ["@example/config", "@example/ui"]

        lockfile = true
        """
    ).lstrip()

    assert (
        set_bun_minimum_release_age(content, minimum_release_age_days=7)
        == dedent(
            """
        [install]
        exact = true
        minimumReleaseAge = 604800
        minimumReleaseAgeExcludes = ["@example/config", "@example/ui"]

        lockfile = true
        """
        ).lstrip()
    )


def test_set_bun_minimum_release_age_ignores_malformed_excludes() -> None:
    content = (
        '[install]\nminimumReleaseAge = 100\nminimumReleaseAgeExcludes = "@custom/*"\n'
    )
    assert set_bun_minimum_release_age(content, minimum_release_age_days=7) == (
        "[install]\n"
        "minimumReleaseAge = 604800\n"
        'minimumReleaseAgeExcludes = "@custom/*"\n'
    )


def test_set_bun_minimum_release_age_excludes_adds_missing_entries() -> None:
    content = (
        "[install]\n"
        "minimumReleaseAge = 604800\n"
        'minimumReleaseAgeExcludes = ["@example/config"]\n'
    )
    assert set_bun_minimum_release_age_excludes(content, excludes=BUN_EXCLUDES) == (
        "[install]\n"
        "minimumReleaseAge = 604800\n"
        'minimumReleaseAgeExcludes = ["@example/config", "@example/ui"]\n'
    )


def test_set_bun_minimum_release_age_excludes_inserts_only_missing_key() -> None:
    content = "[install]\nminimumReleaseAge = 604800\nlockfile = true\n"
    assert set_bun_minimum_release_age_excludes(content, excludes=BUN_EXCLUDES) == (
        "[install]\n"
        'minimumReleaseAgeExcludes = ["@example/config", "@example/ui"]\n'
        "minimumReleaseAge = 604800\n"
        "lockfile = true\n"
    )


def test_set_bun_minimum_release_age_excludes_ignores_malformed_age() -> None:
    content = '[install]\nminimumReleaseAge = "not-a-number"\n'
    assert set_bun_minimum_release_age_excludes(content, excludes=BUN_EXCLUDES) == (
        "[install]\n"
        'minimumReleaseAgeExcludes = ["@example/config", "@example/ui"]\n'
        'minimumReleaseAge = "not-a-number"\n'
    )


def test_bun_excludes_guard_requires_secure_install_age(tmp_path: Path) -> None:
    (tmp_path / "bun.lock").write_text("")
    (tmp_path / "bunfig.toml").write_text(
        dedent(
            """
            [other]
            minimumReleaseAge = 1

            [install]
            minimumReleaseAge = 1
            """
        ).lstrip()
    )

    run_update_task(tmp_path, bun_minimum_release_age_excludes=BUN_EXCLUDES)

    # The [other] section confuses the age update, so the install age stays
    # insecure and no exclusions may be added.
    updated_config = (tmp_path / "bunfig.toml").read_text()
    assert "minimumReleaseAgeExcludes" not in updated_config


@pytest.mark.parametrize(
    "updater",
    [
        partial(set_bun_minimum_release_age, minimum_release_age_days=7),
        partial(set_bun_minimum_release_age_excludes, excludes=BUN_EXCLUDES),
    ],
)
@pytest.mark.parametrize(
    "content",
    [
        "install = { cache = '~/.bun/install/cache' }\n",
        "install.cache = '~/.bun/install/cache'\n",
        "[install.scopes]\n'@myorg' = { token = 'abc' }\n",
        "[install] # bun install settings\nlockfile = true\n",
        "[ install ]\nlockfile = true\n",
    ],
)
def test_set_bun_install_setting_rejects_unsafe_section_forms(
    updater: Callable[[str], str | None],
    content: str,
) -> None:
    with pytest.raises(ValueError, match="cannot safely edit"):
        updater(content)


@pytest.mark.parametrize(
    "content",
    [
        "install = { minimumReleaseAge = 100 }\n",
        "install.minimumReleaseAge = 100\n",
    ],
)
def test_set_bun_minimum_release_age_rejects_unsafe_forms(content: str) -> None:
    with pytest.raises(ValueError, match="cannot safely edit"):
        set_bun_minimum_release_age(content, minimum_release_age_days=7)


@pytest.mark.parametrize(
    "content",
    [
        "install = { minimumReleaseAgeExcludes = [] }\n",
        "install.minimumReleaseAgeExcludes = []\n",
    ],
)
def test_set_bun_minimum_release_age_excludes_rejects_unsafe_forms(
    content: str,
) -> None:
    with pytest.raises(ValueError, match="cannot safely edit"):
        set_bun_minimum_release_age_excludes(content, excludes=BUN_EXCLUDES)


@pytest.mark.parametrize("value", ['"not-a-list"', '["@example/pkg", 42]'])
def test_set_bun_minimum_release_age_excludes_rejects_non_string_list_entries(
    value: str,
) -> None:
    content = f"[install]\nminimumReleaseAgeExcludes = {value}\n"
    with pytest.raises(ValueError, match="cannot safely edit"):
        set_bun_minimum_release_age_excludes(content, excludes=BUN_EXCLUDES)


@pytest.mark.parametrize(
    "updater",
    [
        partial(set_bun_minimum_release_age, minimum_release_age_days=7),
        partial(set_bun_minimum_release_age_excludes, excludes=BUN_EXCLUDES),
    ],
)
@pytest.mark.parametrize("content", ["[", "install = 'bad'\n"])
def test_set_bun_install_setting_rejects_invalid_toml(
    updater: Callable[[str], str | None],
    content: str,
) -> None:
    with pytest.raises(ValueError):
        updater(content)


def test_set_bun_minimum_release_age_excludes_serializes_quotes_and_deduplicates() -> (
    None
):
    assert (
        set_bun_minimum_release_age_excludes(
            "", excludes=('package-"quoted"', 'package-"quoted"')
        )
        == '[install]\nminimumReleaseAgeExcludes = ["package-\\"quoted\\""]\n'
    )


@pytest.mark.parametrize(
    "setter",
    [
        set_bun_minimum_release_age_excludes,
        set_pnpm_minimum_release_age_excludes,
        set_npm_minimum_release_age_excludes,
    ],
)
def test_set_minimum_release_age_excludes_returns_none_for_empty_configuration(
    setter: Callable[..., str | None],
) -> None:
    assert setter("[", excludes=()) is None


@pytest.mark.parametrize("exclude", ["", "   ", "two\nlines", "carriage\rreturn"])
def test_set_minimum_release_age_excludes_rejects_invalid_values(
    exclude: str,
) -> None:
    with pytest.raises(ValueError, match="non-empty single-line"):
        set_bun_minimum_release_age_excludes("", excludes=(exclude,))


def test_minimum_release_age_setters_use_configured_days() -> None:
    assert (
        set_bun_minimum_release_age("", minimum_release_age_days=2)
        == "[install]\nminimumReleaseAge = 172800\n"
    )
    assert (
        set_pnpm_minimum_release_age("", minimum_release_age_days=2)
        == "minimumReleaseAge: 2880\n"
    )
    assert (
        set_npm_minimum_release_age("", minimum_release_age_days=2)
        == "min-release-age=2\n"
    )


def test_set_pnpm_minimum_release_age_adds_appends_and_bumps() -> None:
    assert (
        set_pnpm_minimum_release_age("", minimum_release_age_days=7)
        == "minimumReleaseAge: 10080\n"
    )
    assert (
        set_pnpm_minimum_release_age(
            "packages:\n  - packages/*", minimum_release_age_days=7
        )
        == "packages:\n  - packages/*\nminimumReleaseAge: 10080\n"
    )
    assert (
        set_pnpm_minimum_release_age(
            "minimumReleaseAge:   60\n", minimum_release_age_days=7
        )
        == "minimumReleaseAge: 10080\n"
    )
    assert (
        set_pnpm_minimum_release_age(
            'minimumReleaseAge: "20000"\n', minimum_release_age_days=7
        )
        == "minimumReleaseAge: 10080\n"
    )
    assert (
        set_pnpm_minimum_release_age(
            "minimumReleaseAge: soon\n", minimum_release_age_days=7
        )
        == "minimumReleaseAge: 10080\n"
    )


@pytest.mark.parametrize(
    "content",
    [
        "minimumReleaseAge: 10080\n",
        "minimumReleaseAge: 20000\n",
    ],
)
def test_set_pnpm_minimum_release_age_returns_none_when_already_set(
    content: str,
) -> None:
    assert set_pnpm_minimum_release_age(content, minimum_release_age_days=7) is None


@pytest.mark.parametrize("content", ["[", "- packages/*\n"])
def test_set_pnpm_minimum_release_age_rejects_invalid_yaml(content: str) -> None:
    with pytest.raises(ValueError, match="Invalid pnpm-workspace.yaml"):
        set_pnpm_minimum_release_age(content, minimum_release_age_days=7)


def test_set_pnpm_minimum_release_age_rejects_unsafe_key_form() -> None:
    with pytest.raises(ValueError, match="cannot safely edit"):
        set_pnpm_minimum_release_age(
            '"minimumReleaseAge": 60\n', minimum_release_age_days=7
        )


def test_set_pnpm_minimum_release_age_preserves_surrounding_keys() -> None:
    content = dedent(
        """
        packages:
          - "packages/*"
        minimumReleaseAge: 60
        onlyBuiltDependencies:
          - esbuild
        """
    ).lstrip()

    assert (
        set_pnpm_minimum_release_age(content, minimum_release_age_days=7)
        == dedent(
            """
        packages:
          - "packages/*"
        minimumReleaseAge: 10080
        onlyBuiltDependencies:
          - esbuild
        """
        ).lstrip()
    )


def test_set_pnpm_block_exotic_subdeps_adds_appends_and_updates() -> None:
    assert set_pnpm_block_exotic_subdeps("") == "blockExoticSubdeps: true\n"
    assert (
        set_pnpm_block_exotic_subdeps("minimumReleaseAge: 10080\n")
        == "minimumReleaseAge: 10080\nblockExoticSubdeps: true\n"
    )
    assert (
        set_pnpm_block_exotic_subdeps("blockExoticSubdeps:   false\n")
        == "blockExoticSubdeps: true\n"
    )
    assert (
        set_pnpm_block_exotic_subdeps('blockExoticSubdeps: "true"\n')
        == "blockExoticSubdeps: true\n"
    )
    assert (
        set_pnpm_block_exotic_subdeps("blockExoticSubdeps: maybe\n")
        == "blockExoticSubdeps: true\n"
    )


def test_set_pnpm_block_exotic_subdeps_returns_none_when_true() -> None:
    assert set_pnpm_block_exotic_subdeps("blockExoticSubdeps: true\n") is None


def test_set_pnpm_block_exotic_subdeps_rejects_unsafe_key_form() -> None:
    with pytest.raises(ValueError, match="cannot safely edit"):
        set_pnpm_block_exotic_subdeps('"blockExoticSubdeps": false\n')


def test_set_pnpm_minimum_release_age_excludes_adds_list_to_empty_file() -> None:
    assert (
        set_pnpm_minimum_release_age_excludes("", excludes=PNPM_NPM_EXCLUDES)
        == 'minimumReleaseAgeExclude:\n- "@example/*"\n- "example-package"\n'
    )


def test_set_pnpm_minimum_release_age_excludes_appends_to_existing_content() -> None:
    content = "minimumReleaseAge: 10080\n"
    assert (
        set_pnpm_minimum_release_age_excludes(content, excludes=("@example/*",))
        == 'minimumReleaseAge: 10080\nminimumReleaseAgeExclude:\n- "@example/*"\n'
    )


def test_set_pnpm_minimum_release_age_excludes_adds_entries_to_existing_list() -> None:
    content = dedent(
        """
        minimumReleaseAgeExclude:
          - '@other/pkg'
        """
    ).lstrip()

    result = set_pnpm_minimum_release_age_excludes(content, excludes=PNPM_NPM_EXCLUDES)
    assert result is not None
    assert '- "@example/*"\n' in result
    assert '- "example-package"\n' in result
    assert "- '@other/pkg'\n" in result


def test_set_pnpm_minimum_release_age_excludes_returns_none_when_entries_exist() -> (
    None
):
    content = dedent(
        """
        minimumReleaseAgeExclude:
          - '@example/*'
          - example-package
        """
    ).lstrip()
    assert (
        set_pnpm_minimum_release_age_excludes(content, excludes=PNPM_NPM_EXCLUDES)
        is None
    )


def test_set_pnpm_minimum_release_age_excludes_returns_none_when_entry_among_others() -> (
    None
):
    content = dedent(
        """
        minimumReleaseAgeExclude:
          - '@other/pkg'
          - '@example/*'
          - some-package
        """
    ).lstrip()
    assert (
        set_pnpm_minimum_release_age_excludes(content, excludes=("@example/*",)) is None
    )


def test_set_pnpm_minimum_release_age_excludes_preserves_comments_when_appending() -> (
    None
):
    content = dedent(
        """
        # managed by quant-ranger
        minimumReleaseAgeExclude:
          - '@other/pkg'  # keep this
        # end of list
        blockExoticSubdeps: true
        """
    ).lstrip()

    result = set_pnpm_minimum_release_age_excludes(content, excludes=("@example/*",))
    assert (
        result
        == dedent(
            """
        # managed by quant-ranger
        minimumReleaseAgeExclude:
          - '@other/pkg'  # keep this
          - "@example/*"
        # end of list
        blockExoticSubdeps: true
        """
        ).lstrip()
    )


def test_set_pnpm_minimum_release_age_excludes_preserves_comments_when_creating_key() -> (
    None
):
    content = dedent(
        """
        # managed by quant-ranger
        minimumReleaseAge: 10080
        """
    ).lstrip()

    result = set_pnpm_minimum_release_age_excludes(content, excludes=("@example/*",))
    assert (
        result
        == dedent(
            """
        # managed by quant-ranger
        minimumReleaseAge: 10080
        minimumReleaseAgeExclude:
        - "@example/*"
        """
        ).lstrip()
    )


def test_set_pnpm_minimum_release_age_excludes_rejects_non_list_form() -> None:
    content = "minimumReleaseAgeExclude: '@example/*'\n"
    with pytest.raises(ValueError, match="cannot safely edit"):
        set_pnpm_minimum_release_age_excludes(content, excludes=PNPM_NPM_EXCLUDES)


def test_set_pnpm_minimum_release_age_excludes_rejects_inline_list_form() -> None:
    content = "minimumReleaseAgeExclude: ['@other/pkg']\n"
    with pytest.raises(ValueError, match="cannot safely edit"):
        set_pnpm_minimum_release_age_excludes(content, excludes=PNPM_NPM_EXCLUDES)


def test_set_npm_minimum_release_age_adds_appends_and_bumps() -> None:
    assert (
        set_npm_minimum_release_age("", minimum_release_age_days=7)
        == "min-release-age=7\n"
    )
    assert (
        set_npm_minimum_release_age(
            "registry=https://registry.npmjs.org/", minimum_release_age_days=7
        )
        == "registry=https://registry.npmjs.org/\nmin-release-age=7\n"
    )
    assert set_npm_minimum_release_age(
        "min-release-age=3\n", minimum_release_age_days=7
    ) == ("min-release-age=7\n")


@pytest.mark.parametrize(
    "content",
    [
        "min-release-age=soon\n",
        "min-release-age=7.5\n",
    ],
)
def test_set_npm_minimum_release_age_rejects_invalid_value(content: str) -> None:
    with pytest.raises(ValueError, match="invalid form"):
        set_npm_minimum_release_age(content, minimum_release_age_days=7)


@pytest.mark.parametrize(
    "content",
    [
        "min-release-age=7\n",
        "min-release-age = 14\n",
        "  min-release-age=7\n",
    ],
)
def test_set_npm_minimum_release_age_returns_none_when_already_set(
    content: str,
) -> None:
    assert set_npm_minimum_release_age(content, minimum_release_age_days=7) is None


def test_set_npm_minimum_release_age_preserves_surrounding_lines() -> None:
    content = dedent(
        """
        package-lock=false
        min-release-age = 1
        legacy-peer-deps=true
        """
    ).lstrip()

    assert (
        set_npm_minimum_release_age(content, minimum_release_age_days=7)
        == dedent(
            """
        package-lock=false
        min-release-age=7
        legacy-peer-deps=true
        """
        ).lstrip()
    )


def test_set_npm_minimum_release_age_excludes_adds_to_empty_file() -> None:
    assert (
        set_npm_minimum_release_age_excludes("", excludes=PNPM_NPM_EXCLUDES)
        == "min-release-age-exclude[]=@example/*\n"
        "min-release-age-exclude[]=example-package\n"
    )


def test_set_npm_minimum_release_age_excludes_appends_to_existing_content() -> None:
    assert (
        set_npm_minimum_release_age_excludes(
            "min-release-age=7\n", excludes=("@example/*",)
        )
        == "min-release-age=7\nmin-release-age-exclude[]=@example/*\n"
    )


def test_set_npm_minimum_release_age_excludes_returns_none_when_already_set() -> None:
    assert (
        set_npm_minimum_release_age_excludes(
            "min-release-age-exclude[]=@example/*\n", excludes=("@example/*",)
        )
        is None
    )


def test_set_npm_minimum_release_age_excludes_returns_none_when_entry_among_others() -> (
    None
):
    content = (
        "min-release-age-exclude[]=@other/*\nmin-release-age-exclude[]=@example/*\n"
    )
    assert (
        set_npm_minimum_release_age_excludes(content, excludes=("@example/*",)) is None
    )


def test_set_npm_minimum_release_age_excludes_adds_when_other_entries_exist() -> None:
    content = "min-release-age-exclude[]=@other/*\n"
    assert (
        set_npm_minimum_release_age_excludes(
            content, excludes=("@example/*", "@example/*")
        )
        == "min-release-age-exclude[]=@other/*\n"
        "min-release-age-exclude[]=@example/*\n"
    )


def test_set_npm_minimum_release_age_excludes_normalizes_whitespace() -> None:
    updated = set_npm_minimum_release_age_excludes("", excludes=(" @example/* ",))

    assert updated == "min-release-age-exclude[]=@example/*\n"
    assert (
        set_npm_minimum_release_age_excludes(updated, excludes=(" @example/* ",))
        is None
    )


def test_node_dependency_cooldown_creates_pull_request_for_supported_lockfiles(
    tmp_path: Path,
) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "package-lock.json").write_text("{}")
    (tmp_path / "package-lock.json").write_text("{}")
    (tmp_path / ".npmrc").write_text("min-release-age=1\n")

    bun_project = tmp_path / "tools"
    bun_project.mkdir()
    (bun_project / "bun.lock").write_text("")
    (bun_project / "bunfig.toml").write_text("[install]\nlockfile = true\n")

    pnpm_project = tmp_path / "packages" / "app"
    pnpm_project.mkdir(parents=True)
    (pnpm_project / "pnpm-lock.yaml").write_text("")
    pull_request_template = replace(
        DEFAULT_PULL_REQUEST_TEMPLATES.node_dependency_cooldown,
        branch_prefix="harden-node-supply-chain",
    )

    task_run = run_update_task(
        tmp_path,
        branch="release",
        publish_changes=False,
        minimum_release_age_days=3,
        bun_minimum_release_age_excludes=BUN_EXCLUDES,
        minimum_release_age_excludes=PNPM_NPM_EXCLUDES,
        site_config=SiteConfig(
            pull_request_templates=replace(
                DEFAULT_PULL_REQUEST_TEMPLATES,
                node_dependency_cooldown=pull_request_template,
            )
        ),
    )

    assert task_run.outcome.result == Status.UPDATED
    assert (tmp_path / ".npmrc").read_text() == (
        "min-release-age=3\n"
        "min-release-age-exclude[]=@example/*\n"
        "min-release-age-exclude[]=example-package\n"
    )
    assert (bun_project / "bunfig.toml").read_text() == (
        "[install]\n"
        "minimumReleaseAge = 259200\n"
        'minimumReleaseAgeExcludes = ["@example/config", "@example/ui"]\n'
        "lockfile = true\n"
    )
    assert (pnpm_project / "pnpm-workspace.yaml").read_text() == (
        "minimumReleaseAge: 4320\n"
        'minimumReleaseAgeExclude:\n- "@example/*"\n- "example-package"\n'
        "blockExoticSubdeps: true\n"
    )
    assert task_run.checkout.added_paths == [
        "tools/bunfig.toml",
        "tools/bunfig.toml",
        "packages/app/pnpm-workspace.yaml",
        "packages/app/pnpm-workspace.yaml",
        "packages/app/pnpm-workspace.yaml",
        ".npmrc",
        ".npmrc",
    ]
    assert task_run.github_client.pull_request_calls == [
        {
            "checkout": task_run.checkout,
            "options": PullRequestOptions(
                title=pull_request_template.title,
                body=pull_request_template.body,
                source_branch="harden-node-supply-chain",
                target_branch="release",
                quant_ranger_id="node-dependency-cooldown",
            ),
            "logger": task_run.logger,
            "publish_changes": False,
        }
    ]


def test_node_dependency_cooldown_adds_no_exclusions_by_default(
    tmp_path: Path,
) -> None:
    (tmp_path / "package-lock.json").write_text("{}")
    (tmp_path / "bun.lock").write_text("")
    (tmp_path / "pnpm-lock.yaml").write_text("")

    task_run = run_update_task(tmp_path)

    assert task_run.outcome.result == Status.UPDATED
    assert (tmp_path / ".npmrc").read_text() == "min-release-age=7\n"
    assert (tmp_path / "bunfig.toml").read_text() == (
        "[install]\nminimumReleaseAge = 604800\n"
    )
    assert (tmp_path / "pnpm-workspace.yaml").read_text() == (
        "minimumReleaseAge: 10080\nblockExoticSubdeps: true\n"
    )
    assert task_run.checkout.added_paths == [
        "bunfig.toml",
        "pnpm-workspace.yaml",
        "pnpm-workspace.yaml",
        ".npmrc",
    ]
    assert (
        task_run.github_client.pull_request_calls[0]["options"].body
        == SiteConfig().pull_request_templates.node_dependency_cooldown.body
    )


def test_node_dependency_cooldown_default_preserves_existing_exclusions(
    tmp_path: Path,
) -> None:
    (tmp_path / "package-lock.json").write_text("{}")
    (tmp_path / ".npmrc").write_text(
        "min-release-age=1\nmin-release-age-exclude[]=@custom/*\n"
    )
    (tmp_path / "bun.lock").write_text("")
    (tmp_path / "bunfig.toml").write_text(
        '[install]\nminimumReleaseAge = 1\nminimumReleaseAgeExcludes = "@custom/*"\n'
    )
    (tmp_path / "pnpm-lock.yaml").write_text("")
    (tmp_path / "pnpm-workspace.yaml").write_text(
        "minimumReleaseAge: 1\n"
        "minimumReleaseAgeExclude: '@custom/*'\n"
        "blockExoticSubdeps: true\n"
    )

    task_run = run_update_task(tmp_path)

    assert task_run.outcome.result == Status.UPDATED
    assert (tmp_path / ".npmrc").read_text() == (
        "min-release-age=7\nmin-release-age-exclude[]=@custom/*\n"
    )
    assert (tmp_path / "bunfig.toml").read_text() == (
        "[install]\n"
        "minimumReleaseAge = 604800\n"
        'minimumReleaseAgeExcludes = "@custom/*"\n'
    )
    assert (tmp_path / "pnpm-workspace.yaml").read_text() == (
        "minimumReleaseAge: 10080\n"
        "minimumReleaseAgeExclude: '@custom/*'\n"
        "blockExoticSubdeps: true\n"
    )
    assert task_run.checkout.added_paths == [
        "bunfig.toml",
        "pnpm-workspace.yaml",
        ".npmrc",
    ]
    assert task_run.logger.warnings == []


def test_node_dependency_cooldown_updates_bun_age_when_excludes_are_invalid(
    tmp_path: Path,
) -> None:
    (tmp_path / "bun.lock").write_text("")
    (tmp_path / "bunfig.toml").write_text(
        '[install]\nminimumReleaseAge = 1\nminimumReleaseAgeExcludes = "@custom/*"\n'
    )

    task_run = run_update_task(
        tmp_path, bun_minimum_release_age_excludes=("@example/config",)
    )

    assert task_run.outcome.result == Status.UPDATED
    assert (tmp_path / "bunfig.toml").read_text() == (
        "[install]\n"
        "minimumReleaseAge = 604800\n"
        'minimumReleaseAgeExcludes = "@custom/*"\n'
    )
    assert task_run.checkout.added_paths == ["bunfig.toml"]
    assert len(task_run.logger.warnings) == 1
    assert task_run.logger.logged(LogLevel.WARNING, "minimumReleaseAgeExcludes")


def test_node_dependency_cooldown_does_not_exempt_packages_when_bun_age_is_unsafe(
    tmp_path: Path,
) -> None:
    (tmp_path / "bun.lock").write_text("")
    original = '[install]\n"minimumReleaseAge" = 100\n'
    (tmp_path / "bunfig.toml").write_text(original)

    task_run = run_update_task(
        tmp_path, bun_minimum_release_age_excludes=("@example/config",)
    )

    assert task_run.outcome.result == Status.UP_TO_DATE
    assert (tmp_path / "bunfig.toml").read_text() == original
    assert task_run.checkout.added_paths == []
    assert task_run.github_client.pull_request_calls == []
    assert len(task_run.logger.warnings) == 1
    assert task_run.logger.logged(LogLevel.WARNING, "minimumReleaseAge")


def test_node_dependency_cooldown_returns_up_to_date_when_configs_are_current(
    tmp_path: Path,
) -> None:
    (tmp_path / "package-lock.json").write_text("{}")
    (tmp_path / ".npmrc").write_text(
        "min-release-age=7\n"
        "min-release-age-exclude[]=@example/*\n"
        "min-release-age-exclude[]=example-package\n"
    )
    (tmp_path / "bun.lock").write_text("")
    (tmp_path / "bunfig.toml").write_text(
        "[install]\n"
        "minimumReleaseAge = 604800\n"
        'minimumReleaseAgeExcludes = ["@example/config", "@example/ui"]\n'
    )
    (tmp_path / "pnpm-lock.yaml").write_text("")
    (tmp_path / "pnpm-workspace.yaml").write_text(
        "minimumReleaseAge: 10080\n"
        'minimumReleaseAgeExclude:\n- "@example/*"\n- "example-package"\n'
        "blockExoticSubdeps: true\n"
    )

    task_run = run_update_task(
        tmp_path,
        bun_minimum_release_age_excludes=BUN_EXCLUDES,
        minimum_release_age_excludes=PNPM_NPM_EXCLUDES,
    )

    assert task_run.outcome.result == Status.UP_TO_DATE
    assert task_run.checkout.added_paths == []
    assert task_run.checkout.clean_checked
    assert task_run.github_client.pull_request_calls == []
    assert task_run.logger.logged(
        LogLevel.DEBUG, "No changes needed; minimumReleaseAge already set."
    )


def test_node_dependency_cooldown_skips_bad_configs(tmp_path: Path) -> None:
    (tmp_path / "bun.lock").write_text("")
    (tmp_path / "bunfig.toml").write_text("install = { minimumReleaseAge = 100 }\n")

    task_run = run_update_task(
        tmp_path, bun_minimum_release_age_excludes=("@example/config",)
    )

    assert task_run.outcome.result == Status.UP_TO_DATE
    assert task_run.checkout.added_paths == []
    assert len(task_run.logger.warnings) == 2
    assert task_run.logger.logged(LogLevel.WARNING, "Could not update bunfig.toml")
    assert task_run.logger.logged(LogLevel.WARNING, "cannot safely edit")


def test_node_dependency_cooldown_fails_on_read_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "package-lock.json").write_text("{}")
    (tmp_path / ".npmrc").write_text("min-release-age=1\n")
    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.name == ".npmrc":
            raise OSError("permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    with pytest.raises(RuntimeError, match="Could not read .npmrc"):
        run_update_task(tmp_path)


def test_node_dependency_cooldown_skips_when_pull_request_is_not_created(
    tmp_path: Path,
) -> None:
    (tmp_path / "package-lock.json").write_text("{}")

    task_run = run_update_task(
        tmp_path,
        github_client=FakeGitHubClient(pr_opened=False),
    )

    assert task_run.outcome.result == Status.SKIPPED
    assert task_run.checkout.added_paths == [".npmrc"]
    assert task_run.github_client.pull_request_calls


@dataclass
class TaskRun:
    outcome: UpdateOutcome
    checkout: RecordingCheckout
    github_client: FakeGitHubClient
    logger: RecordingLogger


def run_update_task(
    tmp_path: Path,
    *,
    branch: str | None = "main",
    publish_changes: bool = True,
    minimum_release_age_days: int = 7,
    bun_minimum_release_age_excludes: Sequence[str] = (),
    minimum_release_age_excludes: Sequence[str] = (),
    github_client: FakeGitHubClient | None = None,
    site_config: SiteConfig | None = None,
) -> TaskRun:
    repository_ref = RepositoryRef(owner="octo-org", name="example", branch=branch)
    checkout = RecordingCheckout(tmp_path, repository_ref)
    github_client = github_client or FakeGitHubClient()
    github_client.publish_changes = publish_changes
    logger = RecordingLogger()

    outcome = NodeDependencyCooldownTask(
        checkout,
        RunContext(
            site_config=site_config or SiteConfig(),
            github_client=cast(GitHubClient, github_client),
            logger=logger,
        ),
        item=UpdateItem(repository_ref=repository_ref),
        options=NodeDependencyCooldownOptions(
            minimum_release_age_days=minimum_release_age_days,
            bun_minimum_release_age_excludes=list(bun_minimum_release_age_excludes),
            minimum_release_age_excludes=list(minimum_release_age_excludes),
        ),
    ).run()

    return TaskRun(outcome, checkout, github_client, logger)
