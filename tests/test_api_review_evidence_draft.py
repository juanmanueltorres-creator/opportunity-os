from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.availability.repository import SQLiteAvailabilityRepository
from app.main import create_app
from app.models.domain import Opportunity
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime.now(timezone.utc) - timedelta(minutes=2)


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
    source: str = "linkedin",
    source_url: str | None = None,
) -> Opportunity:
    return Opportunity(
        id=item_id,
        source=source,
        source_id=item_id,
        source_url=source_url or f"https://linkedin.com/jobs/view/{item_id}",
        company=f"Company {item_id}",
        title=f"GIS Analyst {item_id}",
        description="QGIS geospatial work",
        discovered_at=NOW - timedelta(hours=1),
        published_at=NOW - timedelta(hours=2),
        status="open",
        location="Remote",
    )


def _app(
    opportunities,
    availability,
    *,
    draft_enabled: bool = True,
):
    return create_app(
        repository=opportunities,
        availability_repository=availability,
        profile=None,
        enable_default_radar=False,
        enable_default_community_digest_preview=False,
        enable_default_targets=False,
        enable_default_relationships=False,
        enable_availability_verification=False,
        enable_default_review_evidence_draft=draft_enabled,
    )


def _session_card(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/availability/verification/session",
        json={"batch_size": 5},
    )
    assert response.status_code == 200
    cards = response.json()["cards"]
    assert cards
    return cards[0]


def test_draft_endpoint_works_with_write_verification_disabled(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    opportunities.upsert(_opportunity("linkedin"))
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        card = _session_card(client)
        response = client.post(
            "/api/v1/availability/verification/draft",
            json={
                "card": card,
                "decision": "OPEN",
                "observed_at": NOW.isoformat(),
                "evidence_kind": "OFFICIAL_COMPANY_PAGE",
                "evidence_source": "careers.example.com",
                "source_url": "https://careers.example.com/jobs/linkedin",
                "note": "Application form visible",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "READY"
    assert payload["evidence"]["decision"] == "OPEN"
    assert payload["verification_preview"]["status"] == "READY"
    assert payload["verification_preview"]["proposed_state"] == "VERIFIED_OPEN"
    assert payload["external_actions"] == []
    assert availability.list_observations("linkedin") == []


def test_draft_endpoint_preserves_human_closed_decision(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    opportunities.upsert(_opportunity("linkedin"))
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        card = _session_card(client)
        response = client.post(
            "/api/v1/availability/verification/draft",
            json={
                "card": card,
                "decision": "CLOSED",
                "observed_at": NOW.isoformat(),
                "evidence_kind": "MANUAL_REVIEW",
                "evidence_source": "operator.review",
                "source_url": "https://linkedin.com/jobs/view/linkedin",
                "note": "Applications closed",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "READY"
    assert payload["evidence"]["decision"] == "CLOSED"
    assert payload["verification_preview"]["proposed_state"] == "VERIFIED_CLOSED"
    assert availability.list_observations("linkedin") == []


def test_draft_endpoint_blocks_evidence_kind_not_allowed_by_card(tmp_path) -> None:
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
        card = _session_card(client)
        response = client.post(
            "/api/v1/availability/verification/draft",
            json={
                "card": card,
                "decision": "OPEN",
                "observed_at": NOW.isoformat(),
                "evidence_kind": "DIRECT_PLATFORM",
                "evidence_source": "reddit",
                "source_url": "https://reddit.com/r/gis/comments/example",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "BLOCKED_EVIDENCE_KIND"
    assert payload["evidence"] is None
    assert payload["verification_preview"] is None
    assert availability.list_observations("reddit") == []


def test_draft_endpoint_blocks_stale_card_after_new_sighting(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    stored, _ = opportunities.upsert(_opportunity("linkedin"))
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        card = _session_card(client)
        availability.record_seen(
            stored.id,
            observed_at=NOW + timedelta(seconds=30),
            evidence_source="linkedin",
            source_url=stored.source_url,
        )
        response = client.post(
            "/api/v1/availability/verification/draft",
            json={
                "card": card,
                "decision": "OPEN",
                "observed_at": NOW.isoformat(),
                "evidence_kind": "MANUAL_REVIEW",
                "evidence_source": "operator.review",
                "source_url": stored.source_url,
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED_STALE_CARD"


def test_draft_endpoint_rejects_tampered_card_snapshot(tmp_path) -> None:
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
        card = _session_card(client)
        card["acceptable_evidence_kinds"].append("DIRECT_PLATFORM")
        response = client.post(
            "/api/v1/availability/verification/draft",
            json={
                "card": card,
                "decision": "OPEN",
                "observed_at": NOW.isoformat(),
                "evidence_kind": "DIRECT_PLATFORM",
                "evidence_source": "reddit",
                "source_url": "https://reddit.com/r/gis/comments/example",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED_STALE_CARD"
    assert response.json()["errors"] == ["review_card_hash_mismatch"]


def test_draft_endpoint_can_be_disabled_independently(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(opportunities, availability, draft_enabled=False)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/availability/verification/draft",
            json={
                "card": {
                    "rank": 1,
                    "card_sha256": "0" * 64,
                    "opportunity_id": "missing",
                    "title": "Missing",
                    "company": "Missing",
                    "review_url": "https://example.com",
                    "source_key": None,
                    "source_category": None,
                    "availability_state": "UNVERIFIED",
                    "last_seen_at": None,
                    "priority_score": 80,
                    "reason_codes": ["SOURCE_REQUIRES_VERIFICATION"],
                    "suggested_action": "VERIFY_CURRENT_SOURCE",
                    "checklist": ["CONFIRM_LISTING_LOADS"],
                    "acceptable_evidence_kinds": ["MANUAL_REVIEW"],
                    "application_deadline": None,
                    "last_verified_at": None,
                    "verification_preview_endpoint": (
                        "/api/v1/availability/verification/preview"
                    ),
                    "external_actions": [],
                },
                "decision": "OPEN",
                "observed_at": NOW.isoformat(),
                "evidence_kind": "MANUAL_REVIEW",
                "evidence_source": "operator.review",
                "source_url": "https://example.com",
            },
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Review evidence draft unavailable"
    }


def test_draft_endpoint_rejects_non_http_evidence_url(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    opportunities.upsert(_opportunity("linkedin"))
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        card = _session_card(client)
        response = client.post(
            "/api/v1/availability/verification/draft",
            json={
                "card": card,
                "decision": "OPEN",
                "observed_at": NOW.isoformat(),
                "evidence_kind": "MANUAL_REVIEW",
                "evidence_source": "operator.review",
                "source_url": "file:///tmp/fake",
            },
        )

    assert response.status_code == 422
