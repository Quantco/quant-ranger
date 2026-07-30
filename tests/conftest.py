import os
import sys

import pytest

from quant_ranger._impl.testing import FakeKeychain, FakeKeychainExec

# Typer bakes terminal detection into a module-level constant when
# `typer.rich_utils` is first imported, so fixture-time monkeypatching is too
# late for it. Disable terminal rendering before test modules import typer;
# GitHub runners would otherwise force ANSI codes through GITHUB_ACTIONS.
assert "typer" not in sys.modules, "typer must not be imported before conftest"
os.environ["_TYPER_FORCE_DISABLE_TERMINAL"] = "1"


@pytest.fixture(autouse=True)
def _plain_console_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep rich consoles created during tests free of ANSI codes regardless of the
    caller's environment, so assertions on console output are deterministic.

    These are the only variables rich consults at runtime for terminal detection.
    """
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("TTY_COMPATIBLE", raising=False)


@pytest.fixture(autouse=True)
def _no_ambient_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove proxy variables so subprocess environments asserted in tests do not depend
    on the caller's environment."""
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)


@pytest.fixture
def fake_keychain(monkeypatch: pytest.MonkeyPatch) -> FakeKeychain:
    """Fake the macOS `security` command used for Pixi keychain auth.

    Call the fixture with an account → secret mapping; unknown accounts report "not
    found". Returns a list that records the requested accounts.
    """

    def install(secrets: dict[str, str]) -> list[str]:
        fake_exec = FakeKeychainExec(secrets)
        monkeypatch.setattr(
            "quant_ranger._impl.updaters._pixi_update._auth.get_exec_output_silently",
            fake_exec,
        )
        return fake_exec.requested_accounts

    return install
