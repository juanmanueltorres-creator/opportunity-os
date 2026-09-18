from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.domain import Opportunity
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime.now(timezone.utc)


def _repository(tmp_path) -> SQLiteOpportunityRepository:
    repository = SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()
    return repository


def _opportunity(item_id: str) -> Opportunity:
    return Opportunity(
        id=item_id,
        source="workana",
        source_id=item_id,
        source_url=f"https://workana.com/job/{item_id}?utm_source=chatgpt.com",
        company="Example Client",
        title="GIS Forest Mapping",
        description="QGIS remote sensing project",
        discovered_at=NOW - timedelta(hours=1),
        published_at=NOW - timedelta(hours=2),
        status="open",
        location="Argentina",
        remote_policy="remote",
    )


def test_preview_endpoint_works_without_candidate_profile(tmp_path) -> None:
    repository = _repository(tmp_path)
    repository.upsert(_opportunity("forest-map"))
    app = create_app(
        repository=repository,
        profile=None,
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/community/digest/preview",
            json={
                "timezone_name": "America/Argentina/Cordoba",
                "max_items": 5,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate_count"] == 1
    assert payload["digest"]["count"] == 1
    assert payload["format"] == "whatsapp"
    assert "GIS Forest Mapping" in payload["rendered_text"]
    assert "utm_source" not in payload["rendered_text"]
    assert "chatgpt" not in payload["rendered_text"].casefold()
    assert payload["digest"]["items"][0]["source_url"] == (
        "https://workana.com/job/forest-map"
    )


def test_preview_endpoint_can_return_markdown_with_custom_title(tmp_path) -> None:
    repository = _repository(tmp_path)
    repository.upsert(_opportunity("markdown"))
    app = create_app(
        repository=repository,
        profile=None,
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/community/digest/preview",
            json={
                "format": "markdown",
                "title": "Radar comunitario",
                "include_intro": False,
                "include_footer": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "markdown"
    assert payload["rendered_text"].startswith("# 🚀 Radar comunitario")


def test_preview_endpoint_is_available_with_empty_repository(tmp_path) -> None:
    app = create_app(
        repository=_repository(tmp_path),
        profile=None,
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/community/digest/preview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate_count"] == 0
    assert payload["digest"]["count"] == 0
    assert "No hay oportunidades suficientemente verificadas" in payload["rendered_text"]


def test_preview_endpoint_returns_503_when_feature_is_disabled(tmp_path) -> None:
    app = create_app(
        repository=_repository(tmp_path),
        profile=None,
        enable_default_radar=False,
        enable_default_community_digest_preview=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/community/digest/preview")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Community digest preview unavailable"
    }


def test_invalid_timezone_maps_to_public_safe_422(tmp_path) -> None:
    app = create_app(
        repository=_repository(tmp_path),
        profile=None,
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/community/digest/preview",
            json={"timezone_name": "SECRET/DO_NOT_ECHO_INVALID_ZONE"},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid community digest preview options"
    }
    assert "DO_NOT_ECHO_INVALID_ZONE" not in response.text


def test_invalid_policy_bound_is_rejected_by_request_schema(tmp_path) -> None:
    app = create_app(
        repository=_repository(tmp_path),
        profile=None,
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/community/digest/preview",
            json={"max_items": 0},
        )

    assert response.status_code == 422
