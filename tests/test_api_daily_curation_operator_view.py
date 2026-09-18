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
    source: str,
    source_url: str,
    title: str | None = None,
) -> Opportunity:
    return Opportunity(
        id=item_id,
        source=source,
        source_id=item_id,
        source_url=source_url,
        company=f"Company {item_id}",
        title=title or f"GIS Analyst {item_id}",
        description="QGIS geospatial work",
        discovered_at=NOW - timedelta(hours=1),
        published_at=NOW - timedelta(hours=2),
        status="open",
        location="Remote",
        remote_policy="remote",
    )


def _app(
    opportunities,
    availability,
    *,
    view_enabled: bool = True,
    daily_enabled: bool = True,
):
    return create_app(
        repository=opportunities,
        availability_repository=availability,
        profile=None,
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
        enable_availability_verification=False,
        enable_default_daily_curation=daily_enabled,
        enable_default_daily_curation_operator_view=view_enabled,
    )


def test_operator_view_endpoint_returns_human_view_and_structured_cards(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    opportunities.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )
    opportunities.upsert(
        _opportunity(
            "greenhouse",
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/1",
        )
    )
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily/view",
            json={"view_title": "Ronda operativa"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Ronda operativa"
    assert payload["review_count"] == 1
    assert payload["publishable_count"] == 1
    assert payload["held_count"] == 1
    assert payload["review_items"][0]["opportunity_id"] == "linkedin"
    assert payload["review_items"][0]["card"]["opportunity_id"] == "linkedin"
    assert payload["review_items"][0]["card_sha256"] == (
        payload["review_items"][0]["card"]["card_sha256"]
    )
    assert payload["review_items"][0]["next_endpoint"] == (
        "/api/v1/availability/verification/draft"
    )
    assert payload["external_actions"] == []
    assert "# Ronda operativa" in payload["rendered_view"]


def test_operator_view_endpoint_works_without_profile_or_write_authority(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    opportunities.upsert(
        _opportunity(
            "greenhouse",
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/1",
        )
    )
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post("/api/v1/curation/daily/view")

    assert response.status_code == 200
    assert response.json()["publishable_count"] == 1
    assert "career_match" not in response.text
    assert "income_viability" not in response.text
    assert "confirmed_by" not in response.text


def test_operator_view_endpoint_supports_plain_without_checklists(tmp_path) -> None:
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
            "/api/v1/curation/daily/view",
            json={
                "view_format": "plain",
                "include_review_checklists": False,
                "include_held_details": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "plain"
    assert payload["review_items"][0]["checklist"] == []
    assert "REVIEW AHORA" in payload["rendered_view"]
    assert "[ ]" not in payload["rendered_view"]


def test_operator_view_endpoint_embeds_publishable_digest(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    opportunities.upsert(
        _opportunity(
            "greenhouse",
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/1",
            title="GIS Developer",
        )
    )
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily/view",
            json={
                "format": "markdown",
                "title": "Digest listo",
                "include_intro": False,
                "include_footer": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["publishable"]["count"] == 1
    assert "GIS Developer" in payload["publishable"]["rendered_digest"]
    assert "GIS Developer" in payload["rendered_view"]


def test_operator_view_endpoint_can_be_disabled_independently(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        view_enabled=False,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/curation/daily/view")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Daily curation operator view unavailable"
    }


def test_disabling_daily_curation_also_disables_default_operator_view(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        daily_enabled=False,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/curation/daily/view")

    assert response.status_code == 503


def test_invalid_operator_view_title_maps_to_public_safe_422(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily/view",
            json={"view_title": "   "},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid daily curation operator view options"
    }


def test_invalid_view_format_is_rejected_by_request_schema(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily/view",
            json={"view_format": "html"},
        )

    assert response.status_code == 422
