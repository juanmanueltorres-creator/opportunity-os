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
    daily_enabled: bool = True,
    queue_enabled: bool = True,
    digest_enabled: bool = True,
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
        enable_default_verification_queue=queue_enabled,
        enable_default_community_digest_preview=digest_enabled,
    )


def test_daily_curation_endpoint_returns_review_publishable_and_held(tmp_path) -> None:
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
            "linkedin-held",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/held",
        )
    )
    opportunities.upsert(
        _opportunity(
            "greenhouse",
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/1",
        )
    )
    verified, _ = opportunities.upsert(
        _opportunity(
            "linkedin-verified",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/verified",
        )
    )
    availability.record_verification(
        verified.id,
        is_open=True,
        observed_at=NOW - timedelta(hours=2),
        evidence_source="official_company_page",
    )
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily",
            json={"review_batch_size": 2},
        )

    assert response.status_code == 200
    payload = response.json()
    assert [card["opportunity_id"] for card in payload["review"]["cards"]] == [
        "reddit",
        "linkedin-held",
    ]
    held_ids = {
        item["opportunity_id"]
        for item in payload["held"]["items"]
    }
    publishable_ids = {
        item["opportunity_id"]
        for item in payload["publishable"]["digest"]["items"]
    }
    assert {"reddit", "linkedin-held"}.issubset(held_ids)
    assert {"greenhouse", "linkedin-verified"}.issubset(publishable_ids)
    assert held_ids.isdisjoint(publishable_ids)
    assert payload["external_actions"] == []


def test_daily_curation_works_without_profile_or_verification_write_authority(
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
        response = client.post("/api/v1/curation/daily")

    assert response.status_code == 200
    assert response.json()["publishable"]["digest"]["count"] == 1
    assert "career_match" not in response.text
    assert "income_viability" not in response.text


def test_daily_curation_excludes_entire_held_backlog_not_only_visible_slice(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    for index in range(4):
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
            "/api/v1/curation/daily",
            json={
                "review_batch_size": 2,
                "held_items_limit": 1,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["held"]["total_count"] == 4
    assert payload["held"]["shown_count"] == 1
    assert payload["held"]["omitted_count"] == 3
    assert payload["publishable"]["digest"]["count"] == 0


def test_daily_curation_propagates_markdown_render_options(tmp_path) -> None:
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
        response = client.post(
            "/api/v1/curation/daily",
            json={
                "format": "markdown",
                "title": "Curación diaria",
                "include_intro": False,
                "include_footer": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["publishable"]["format"] == "markdown"
    assert payload["publishable"]["rendered_text"].startswith(
        "# 🚀 Curación diaria"
    )


def test_daily_curation_is_read_only(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    stored, _ = opportunities.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )
    before = availability.list_observations(stored.id)
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post("/api/v1/curation/daily")

    assert response.status_code == 200
    after = availability.list_observations(stored.id)
    assert before == after == []


def test_daily_curation_can_be_disabled_independently(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        daily_enabled=False,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/curation/daily")

    assert response.status_code == 503
    assert response.json() == {"detail": "Daily curation unavailable"}


def test_disabling_queue_leaves_default_daily_curation_unavailable(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        queue_enabled=False,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/curation/daily")

    assert response.status_code == 503


def test_disabling_digest_leaves_default_daily_curation_unavailable(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        digest_enabled=False,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/curation/daily")

    assert response.status_code == 503


def test_invalid_daily_curation_timezone_maps_to_public_safe_422(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily",
            json={"timezone_name": "SECRET/INVALID_ZONE"},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid daily curation options"
    }
    assert "SECRET/INVALID_ZONE" not in response.text


def test_invalid_daily_curation_bounds_are_rejected_by_schema(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(opportunities, availability)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily",
            json={"review_batch_size": 0},
        )

    assert response.status_code == 422
