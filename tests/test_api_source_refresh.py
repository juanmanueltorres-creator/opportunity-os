from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.availability.repository import SQLiteAvailabilityRepository
from app.connectors.base import ConnectorError
from app.main import create_app
from app.models.domain import Opportunity
from app.radar.source_refresh import SourceRefreshService
from app.radar.sources import ConfiguredConnector
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime.now(timezone.utc) - timedelta(minutes=2)


class StaticConnector:
    def __init__(self, opportunities: list[Opportunity]) -> None:
        self.opportunities = opportunities
        self.calls = 0

    async def fetch(self) -> list[Opportunity]:
        self.calls += 1
        return list(self.opportunities)


class FailingConnector:
    async def fetch(self) -> list[Opportunity]:
        raise ConnectorError("DO_NOT_ECHO_UPSTREAM_SECRET")


def _repositories(tmp_path):
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()
    return opportunities, availability


def _opportunity(
    item_id: str,
    *,
    source: str,
) -> Opportunity:
    source_id = item_id.split(":", 1)[-1]
    return Opportunity(
        id=item_id,
        source=source,
        source_id=source_id,
        source_url=f"https://example.com/{source}/{source_id}",
        company=f"Company {source_id}",
        title="GIS Analyst",
        description="QGIS geospatial work",
        discovered_at=NOW - timedelta(hours=1),
        published_at=NOW - timedelta(days=1),
        status="open",
        location="Remote",
        remote_policy="remote",
    )


def _service(
    opportunities,
    availability,
    connectors: list[ConfiguredConnector],
) -> SourceRefreshService:
    return SourceRefreshService(
        opportunity_repository=opportunities,
        availability_repository=availability,
        connectors=connectors,
    )


def _app(
    opportunities,
    availability,
    *,
    service: SourceRefreshService | None = None,
    enabled: bool | None = False,
):
    return create_app(
        repository=opportunities,
        availability_repository=availability,
        source_refresh_service=service,
        enable_source_refresh=enabled,
        profile=None,
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )


def test_source_refresh_api_is_disabled_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPPORTUNITY_SOURCE_REFRESH_ENABLED", raising=False)
    opportunities, availability = _repositories(tmp_path)
    app = create_app(
        repository=opportunities,
        availability_repository=availability,
        profile=None,
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/sources/refresh")

    assert response.status_code == 503
    assert response.json() == {"detail": "Source refresh unavailable"}


def test_injected_source_refresh_service_is_explicit_opt_in(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    connector = StaticConnector(
        [_opportunity("remotive:1", source="remotive")]
    )
    service = _service(
        opportunities,
        availability,
        [ConfiguredConnector(name="remotive", connector=connector)],
    )
    app = _app(
        opportunities,
        availability,
        service=service,
        enabled=False,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/sources/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["created_count"] == 1
    assert payload["seen_recorded_count"] == 1
    assert payload["closure_inference"] is False
    assert payload["external_reads"] == ["remotive"]
    assert payload["external_actions"] == []
    assert availability.get("remotive:1") is not None


def test_source_refresh_api_can_run_exact_source_subset(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    remotive = StaticConnector(
        [_opportunity("remotive:1", source="remotive")]
    )
    greenhouse = StaticConnector(
        [_opportunity("greenhouse:1", source="greenhouse")]
    )
    service = _service(
        opportunities,
        availability,
        [
            ConfiguredConnector(name="remotive", connector=remotive),
            ConfiguredConnector(
                name="greenhouse:example",
                connector=greenhouse,
            ),
        ],
    )
    app = _app(opportunities, availability, service=service)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/sources/refresh",
            json={"sources": ["greenhouse:example"]},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested_sources"] == ["greenhouse:example"]
    assert payload["external_reads"] == ["greenhouse:example"]
    assert remotive.calls == 0
    assert greenhouse.calls == 1


def test_source_refresh_api_returns_partial_failure_diagnostics_safely(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    good = StaticConnector(
        [_opportunity("remotive:1", source="remotive")]
    )
    service = _service(
        opportunities,
        availability,
        [
            ConfiguredConnector(name="remotive", connector=good),
            ConfiguredConnector(
                name="lever:broken",
                connector=FailingConnector(),
            ),
        ],
    )
    app = _app(opportunities, availability, service=service)

    with TestClient(app) as client:
        response = client.post("/api/v1/sources/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok_count"] == 1
    assert payload["error_count"] == 1
    failed = next(
        item
        for item in payload["diagnostics"]
        if item["source"] == "lever:broken"
    )
    assert failed["message"] == "Source unavailable"
    assert "DO_NOT_ECHO_UPSTREAM_SECRET" not in response.text


def test_unknown_source_is_public_safe_422_and_does_not_fetch(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    connector = StaticConnector(
        [_opportunity("remotive:1", source="remotive")]
    )
    service = _service(
        opportunities,
        availability,
        [ConfiguredConnector(name="remotive", connector=connector)],
    )
    app = _app(opportunities, availability, service=service)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/sources/refresh",
            json={"sources": ["PRIVATE_UNKNOWN_SOURCE"]},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid source refresh options"
    }
    assert "PRIVATE_UNKNOWN_SOURCE" not in response.text
    assert connector.calls == 0
    assert opportunities.list() == []


def test_empty_source_subset_is_rejected_by_request_schema(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    service = _service(opportunities, availability, [])
    app = _app(opportunities, availability, service=service)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/sources/refresh",
            json={"sources": []},
        )

    assert response.status_code == 422


def test_env_enabled_refresh_with_empty_registry_is_available(
    tmp_path,
    monkeypatch,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    source_config = tmp_path / "sources.yaml"
    source_config.write_text("sources: []\n", encoding="utf-8")
    monkeypatch.setenv("OPPORTUNITY_SOURCE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("OPPORTUNITY_SOURCES_PATH", str(source_config))

    app = create_app(
        repository=opportunities,
        availability_repository=availability,
        profile=None,
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/sources/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured_sources"] == []
    assert payload["source_count"] == 0
    assert payload["external_reads"] == []
