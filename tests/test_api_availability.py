from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.availability.repository import SQLiteAvailabilityRepository
from app.main import create_app
from app.models.domain import Opportunity
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime(2026, 9, 18, 18, 30, tzinfo=timezone.utc)


def _repositories(tmp_path):
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()
    return opportunities, availability


def _opportunity() -> Opportunity:
    return Opportunity(
        id="opp-1",
        source="workana",
        source_id="1",
        source_url="https://workana.com/job/1",
        company="Example Client",
        title="GIS Mapping Project",
        description="QGIS project",
        discovered_at=NOW,
    )


def test_availability_endpoint_returns_current_projection(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    stored, _ = opportunities.upsert(_opportunity())
    availability.record_seen(
        stored.id,
        observed_at=NOW,
        evidence_source="workana",
        source_url=stored.source_url,
    )

    app = create_app(
        repository=opportunities,
        availability_repository=availability,
        enable_default_radar=False,
        enable_default_community_digest_preview=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )

    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/opportunities/{stored.id}/availability"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["opportunity_id"] == stored.id
    assert payload["availability_state"] == "UNVERIFIED"
    assert payload["observation_count"] == 1
    assert payload["last_verified_at"] is None


def test_availability_endpoint_does_not_fabricate_history(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    stored, _ = opportunities.upsert(_opportunity())

    app = create_app(
        repository=opportunities,
        availability_repository=availability,
        enable_default_radar=False,
        enable_default_community_digest_preview=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )

    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/opportunities/{stored.id}/availability"
        )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Availability history not found"
    }


def test_availability_endpoint_preserves_opportunity_not_found_boundary(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = create_app(
        repository=opportunities,
        availability_repository=availability,
        enable_default_radar=False,
        enable_default_community_digest_preview=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/opportunities/missing/availability"
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Opportunity not found"}
