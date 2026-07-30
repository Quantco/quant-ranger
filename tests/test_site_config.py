from dataclasses import replace

import pytest
from pydantic import ValidationError

from quant_ranger.site_config import SiteConfig


def test_copier_migration_lowercases_templates() -> None:
    migration = replace(
        SiteConfig().copier_migrations["example"],
        templates=frozenset({"GitHub.Example/QuantCo/Copier-Template"}),
    )

    assert migration.templates == frozenset({"github.example/quantco/copier-template"})


def test_copier_migration_rejects_malformed_templates() -> None:
    with pytest.raises(ValueError, match="expected 'host/owner/name'"):
        replace(
            SiteConfig().copier_migrations["example"],
            templates=frozenset({"quantco/copier-template"}),
        )


def test_site_config_lowercases_trusted_templates() -> None:
    site_config = SiteConfig(
        copier_trusted_templates={"GitHub.Example/quantco/Copier-Template"}
    )

    assert site_config.copier_trusted_templates == frozenset(
        {"github.example/quantco/copier-template"}
    )


@pytest.mark.parametrize(
    "template",
    [
        "quantco/copier-template",
        "github.example/quantco/copier-template/extra",
        "https://github.example/quantco/copier-template",
        "github.example/quantco/copier template",
    ],
)
def test_site_config_rejects_malformed_trusted_templates(template: str) -> None:
    with pytest.raises(ValidationError, match="expected 'host/owner/name'"):
        SiteConfig(copier_trusted_templates={template})
