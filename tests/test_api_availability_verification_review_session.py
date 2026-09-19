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
    description: str = "QGIS geospatial work",
) -> Opportunity:
    return Opportunity(
        id=item_id,
        source=source,
        source_id=item_id,
        source_url=source_url,
        company=f"Company {item_id}",
        title=f"GIS Analyst {item_id}",
        description=description,
        discovered_at=NOW - timedelta(hours=1),
        published_at=NOW - timedelta(hours=2),
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


def test_review_session_endpoint_builds_top_batch_without_write_authority(
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
            "/api/v1/availability/verification/session",
            json={"batch_size": 2},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [card["opportunity_id"] for card in payload["cards"]] == [
        "reddit",
        "workana",
    ]
    assert payload["cards"][0]["suggested_action"] == "FIND_OFFICIAL_SOURCE"
    assert payload["cards"][1]["suggested_action"] == "VERIFY_CURRENT_SOURCE"
    assert all(card["external_actions"] == [] for card in payload["cards"])
    assert availability.list_observations("reddit") == []
    assert availability.list_observations("workana") == []


def test_review_session_endpoint_returns_review_checklist_and_evidence_kinds(
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
            "/api/v1/availability/verification/session"
        )

    assert response.status_code == 200
    card = response.json()["cards"][0]
    assert card["checklist"] == [
        "LOCATE_OFFICIAL_SOURCE",
        "MATCH_ROLE_IDENTITY",
        "CONFIRM_APPLICATION_ACTIONABLE",
        "CAPTURE_EVIDENCE_URL",
    ]
    assert card["acceptable_evidence_kinds"] == [
        "OFFICIAL_COMPANY_PAGE",
        "DIRECT_ATS",
    ]
    assert card["verification_preview_endpoint"] == (
        "/api/v1/availability/verification/preview"
    )
    assert "confirm" not in card["verification_preview_endpoint"]


def test_review_session_endpoint_respects_batch_size(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    for index in range(8):
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
            "/api/v1/availability/verification/session",
            json={"batch_size": 5},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 5
    assert [card["rank"] for card in payload["cards"]] == [1, 2, 3, 4, 5]


def test_review_session_endpoint_is_profile_independent(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    opportunities.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/availability/verification/session"
        )

    assert response.status_code == 200
    assert "career_match" not in response.text
    assert "income_viability" not in response.text
    assert "selected_intent" not in response.text


def test_review_session_endpoint_can_be_disabled_independently(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = create_app(
        repository=opportunities,
        availability_repository=availability,
        profile=None,
        enable_default_radar=False,
        enable_default_community_digest_preview=False,
        enable_default_verification_review_session=False,
        enable_default_targets=False,
        enable_default_relationships=False,
        enable_availability_verification=False,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/availability/verification/session"
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Availability verification review session unavailable"
    }


def test_disabling_queue_also_leaves_default_review_session_unavailable(
    tmp_path,
) -> None:
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
            "/api/v1/availability/verification/session"
        )

    assert response.status_code == 503


def test_invalid_review_session_batch_size_is_rejected_by_schema(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/availability/verification/session",
            json={"batch_size": 0},
        )

    assert response.status_code == 422
