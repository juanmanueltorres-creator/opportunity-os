from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module

import httpx
import pytest

NOW = datetime(2026, 8, 28, 20, 30, tzinfo=timezone.utc)


def _module():
    return import_module("app.radar.sources")


def test_source_registry_loads_strict_fictional_yaml(tmp_path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
sources:
  - type: remotive
    enabled: true
  - type: greenhouse
    enabled: true
    company_name: Example GIS Co
    board_token: example-gis
  - type: lever
    enabled: false
    company_name: Example Data Co
    site: example-data
  - type: ashby
    enabled: false
    company_name: Example AI Co
    board_name: example-ai
""".strip(),
        encoding="utf-8",
    )

    registry = _module().load_source_config(path)

    assert [source.type for source in registry.sources] == [
        "remotive",
        "greenhouse",
        "lever",
        "ashby",
    ]
    assert [source.enabled for source in registry.sources] == [True, True, False, False]


def test_unknown_source_field_is_rejected_without_echoing_yaml(tmp_path) -> None:
    path = tmp_path / "sources.yaml"
    secret_marker = "DO_NOT_ECHO_SECRET_MARKER"
    path.write_text(
        f"""
sources:
  - type: remotive
    enabled: true
    password: {secret_marker}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as excinfo:
        _module().load_source_config(path)

    assert str(excinfo.value) == f"Invalid source registry: {path}"
    assert secret_marker not in str(excinfo.value)


def test_unknown_source_type_is_rejected(tmp_path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
sources:
  - type: mystery_board
    enabled: true
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid source registry"):
        _module().load_source_config(path)


def test_connector_factory_builds_enabled_sources_against_existing_constructors() -> None:
    module = _module()
    registry = module.SourceRegistry.model_validate(
        {
            "sources": [
                {"type": "remotive", "enabled": True},
                {
                    "type": "greenhouse",
                    "enabled": True,
                    "company_name": "Example GIS Co",
                    "board_token": "example-gis",
                },
                {
                    "type": "lever",
                    "enabled": True,
                    "company_name": "Example Data Co",
                    "site": "example-data",
                },
                {
                    "type": "ashby",
                    "enabled": True,
                    "company_name": "Example AI Co",
                    "board_name": "example-ai",
                },
            ]
        }
    )

    client = httpx.AsyncClient()
    try:
        configured = module.build_connectors(registry, client, timeout_seconds=7.5)
    finally:
        import asyncio

        asyncio.run(client.aclose())

    assert [item.name for item in configured] == [
        "remotive",
        "greenhouse:example-gis",
        "lever:example-data",
        "ashby:example-ai",
    ]
    assert [type(item.connector).__name__ for item in configured] == [
        "RemotiveConnector",
        "GreenhouseConnector",
        "LeverConnector",
        "AshbyConnector",
    ]
    assert all(item.connector.timeout_seconds == 7.5 for item in configured)


def test_disabled_sources_are_not_built() -> None:
    module = _module()
    registry = module.SourceRegistry.model_validate(
        {
            "sources": [
                {"type": "remotive", "enabled": False},
                {
                    "type": "greenhouse",
                    "enabled": True,
                    "company_name": "Example GIS Co",
                    "board_token": "example-gis",
                },
            ]
        }
    )
    client = httpx.AsyncClient()
    try:
        configured = module.build_connectors(registry, client, timeout_seconds=5.0)
    finally:
        import asyncio

        asyncio.run(client.aclose())

    assert [item.name for item in configured] == ["greenhouse:example-gis"]


def test_manual_opportunity_conversion_is_deterministic_and_preserves_supplied_facts() -> None:
    module = _module()
    manual = module.ManualOpportunityInput(
        source="community-board",
        source_url="https://example.com/jobs/geo-analyst",
        title="Geo Analyst",
        company="Example Cooperative",
        raw_description="Work with QGIS and territorial data.",
        location="Cordoba, Argentina",
        published_at=datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc),
        application_deadline=datetime(2026, 9, 5, 23, 59, tzinfo=timezone.utc),
    )

    first = manual.to_opportunity(NOW)
    second = manual.to_opportunity(NOW)

    assert first == second
    assert first.id.startswith("community-board:manual-")
    assert first.source == "community-board"
    assert first.source_url == "https://example.com/jobs/geo-analyst"
    assert first.company == "Example Cooperative"
    assert first.location == "Cordoba, Argentina"
    assert first.published_at == datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc)
    assert "2026-09-05" in first.description


def test_manual_opportunity_rejects_naive_dates() -> None:
    module = _module()

    with pytest.raises(ValueError):
        module.ManualOpportunityInput(
            source="manual",
            source_url="https://example.com/jobs/1",
            title="Role",
            company="Example Co",
            raw_description="Description",
            published_at=datetime(2026, 8, 27, 15, 0),
        )
