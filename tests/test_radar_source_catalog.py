from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest


def _module():
    return import_module("app.radar.source_catalog")


def test_public_source_catalog_loads_and_resolves_observed_channels() -> None:
    module = _module()
    catalog = module.load_source_catalog(Path("config/source_catalog.yaml"))

    assert catalog.version == "source-catalog-v1"

    workana = catalog.resolve("workana.com")
    assert workana is not None
    assert workana.key == "workana"
    assert workana.category == "FREELANCE_MARKETPLACE"
    assert workana.authority == "DIRECT_PLATFORM"
    assert workana.default_channel_tags == ["freelance", "project"]

    geo_careers = catalog.resolve("GEO-CAREERS.COM")
    assert geo_careers is not None
    assert geo_careers.category == "NICHE_JOB_BOARD"

    reddit = catalog.resolve("reddit")
    assert reddit is not None
    assert reddit.authority == "DISCOVERY_ONLY"
    assert reddit.publishable is False
    assert reddit.verification_required is True


def test_unknown_source_is_not_inferred_from_partial_text() -> None:
    module = _module()
    catalog = module.load_source_catalog(Path("config/source_catalog.yaml"))

    assert catalog.resolve("unknown-board") is None
    assert catalog.resolve("workana-scrape") is None
    assert catalog.resolve("") is None


def test_discovery_only_source_cannot_be_marked_publishable() -> None:
    module = _module()

    with pytest.raises(ValueError):
        module.SourceCatalogEntry.model_validate(
            {
                "key": "community",
                "category": "COMMUNITY_SIGNAL",
                "authority": "DISCOVERY_ONLY",
                "freshness_mode": "DISCOVERED_AT_ONLY",
                "default_channel_tags": ["community"],
                "publishable": True,
                "verification_required": True,
            }
        )


def test_discovery_only_source_must_require_verification() -> None:
    module = _module()

    with pytest.raises(ValueError):
        module.SourceCatalogEntry.model_validate(
            {
                "key": "community",
                "category": "COMMUNITY_SIGNAL",
                "authority": "DISCOVERY_ONLY",
                "freshness_mode": "DISCOVERED_AT_ONLY",
                "default_channel_tags": ["community"],
                "publishable": False,
                "verification_required": False,
            }
        )


def test_registry_rejects_alias_collision_between_sources() -> None:
    module = _module()

    with pytest.raises(ValueError):
        module.SourceCatalog.model_validate(
            {
                "version": "test-v1",
                "sources": [
                    {
                        "key": "first",
                        "aliases": ["shared.example"],
                        "category": "JOB_BOARD",
                        "authority": "DIRECT_PLATFORM",
                        "freshness_mode": "DELAYED_TIMESTAMP",
                        "publishable": True,
                        "verification_required": True,
                    },
                    {
                        "key": "second",
                        "aliases": ["shared.example"],
                        "category": "JOB_BOARD",
                        "authority": "DIRECT_PLATFORM",
                        "freshness_mode": "DELAYED_TIMESTAMP",
                        "publishable": True,
                        "verification_required": True,
                    },
                ],
            }
        )


def test_invalid_catalog_error_does_not_echo_payload(tmp_path) -> None:
    module = _module()
    marker = "DO_NOT_ECHO_PRIVATE_MARKER"
    path = tmp_path / "source_catalog.yaml"
    path.write_text(
        f"""
version: source-catalog-v1
sources:
  - key: workana
    category: FREELANCE_MARKETPLACE
    authority: DIRECT_PLATFORM
    freshness_mode: DIRECT_TIMESTAMP
    publishable: true
    verification_required: true
    secret: {marker}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as excinfo:
        module.load_source_catalog(path)

    assert str(excinfo.value) == f"Invalid source catalog: {path}"
    assert marker not in str(excinfo.value)


def test_source_key_is_a_normalized_slug() -> None:
    module = _module()

    with pytest.raises(ValueError):
        module.SourceCatalogEntry.model_validate(
            {
                "key": "Workana.com",
                "category": "FREELANCE_MARKETPLACE",
                "authority": "DIRECT_PLATFORM",
                "freshness_mode": "DIRECT_TIMESTAMP",
                "publishable": True,
                "verification_required": True,
            }
        )
