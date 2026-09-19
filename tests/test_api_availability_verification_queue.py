from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.availability.repository import SQLiteAvailabilityRepository
from app.main import create_app
from app.models.domain import Opportunity
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime.now(timezone.utc)


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
    source_url: str,
    published_at: datetime | None = None,
) -> Opportunity:
    return Opportunity(
        id=item_id,
        source=source,
        source_id=item_id,
        source_url=source_url,
        company=f"Company {item_id}",
        title="GIS Analyst",
        description="QGIS geospatial work",
        discovered_at=NOW - timedelta(hours=1),
        published_at=published_at or NOW - timedelta(hours=2),
        status="open",
        location="Remote",
    )


def _app(opportunities, availability):
    return create_app(
        repository=opportunities,
        availability_repository=availability,
        profile=None,
        enable_default_radar=False,
        enable_default_community_digest_preview=False,
        enable_default_targets=False,
        enable_default_relationships=False,
        enable_availability_verification=False,
    )


def test_queue_endpoint_works_without_profile_or_write_verification_enabled(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    opportunities.upsert(
        _opportunity(
            "workana",
            source="workana",
            source_url="https://workana.com/job/1",
        )
    )
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/availability/verification/queue"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["opportunity_id"] == "workana"
    assert payload["items"][0]["suggested_action"] == "VERIFY_CURRENT_SOURCE"
    assert "career_match" not in response.text
    assert "income_viability" not in response.text


def test_queue_endpoint_surfaces_discovery_only_as_find_official_source(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    opportunities.upsert(
        _opportunity(
            "reddit",
            source="reddit",
            source_url="https://reddit.com/r/gis/comments/example",
        )
    )
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/availability/verification/queue"
        )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["priority_score"] == 100
    assert item["reason_codes"] == [
        "DISCOVERY_ONLY_NEEDS_OFFICIAL_SOURCE"
    ]
    assert item["suggested_action"] == "FIND_OFFICIAL_SOURCE"


def test_queue_endpoint_excludes_verified_closed(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    stored, _ = opportunities.upsert(
        _opportunity(
            "closed",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/closed",
        )
    )
    availability.record_verification(
        stored.id,
        is_open=False,
        observed_at=NOW - timedelta(minutes=10),
        evidence_source="official_company_page",
    )
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/availability/verification/queue"
        )

    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_queue_endpoint_respects_max_items_policy(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    for index in range(3):
        opportunities.upsert(
            _opportunity(
                f"linkedin-{index}",
                source="linkedin",
                source_url=f"https://linkedin.com/jobs/view/{index}",
            )
        )
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/availability/verification/queue",
            json={"max_items": 2},
        )

    assert response.status_code == 200
    assert response.json()["count"] == 2


def test_queue_endpoint_can_be_explicitly_disabled(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = create_app(
        repository=opportunities,
        availability_repository=availability,
        profile=None,
        enable_default_radar=False,
        enable_default_community_digest_preview=False,
        enable_default_verification_queue=False,
        enable_default_targets=False,
        enable_default_relationships=False,
        enable_availability_verification=False,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/availability/verification/queue"
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Availability verification queue unavailable"
    }


def test_invalid_queue_policy_is_rejected_by_request_schema(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/availability/verification/queue",
            json={"max_items": 0},
        )

    assert response.status_code == 422
