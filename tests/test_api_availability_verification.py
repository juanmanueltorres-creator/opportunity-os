from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.availability.repository import SQLiteAvailabilityRepository
from app.main import create_app
from app.models.domain import Opportunity
from app.repositories.opportunities import SQLiteOpportunityRepository


def _repositories(tmp_path):
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()
    stored, _ = opportunities.upsert(
        Opportunity(
            id="opp-1",
            source="manual",
            source_id="opp-1",
            source_url="https://company.example/jobs/opp-1",
            company="Example Co",
            title="GIS Analyst",
            description="QGIS role",
            discovered_at=datetime.now(timezone.utc) - timedelta(days=1),
            published_at=datetime.now(timezone.utc) - timedelta(days=2),
            status="open",
        )
    )
    return opportunities, availability, stored


def _evidence(now: datetime, *, decision: str = "OPEN") -> dict[str, object]:
    return {
        "opportunity_id": "opp-1",
        "decision": decision,
        "observed_at": now.isoformat(),
        "evidence_kind": "OFFICIAL_COMPANY_PAGE",
        "evidence_source": "careers.example.com",
        "source_url": "https://careers.example.com/jobs/opp-1",
        "note": "Application page reviewed manually",
    }


def _app(
    opportunities,
    availability,
    *,
    enabled: bool,
):
    return create_app(
        repository=opportunities,
        availability_repository=availability,
        profile=None,
        enable_default_radar=False,
        enable_default_community_digest_preview=False,
        enable_default_targets=False,
        enable_default_relationships=False,
        enable_availability_verification=enabled,
    )


def test_verification_api_is_disabled_by_default_write_policy(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        "OPPORTUNITY_AVAILABILITY_VERIFICATION_ENABLED",
        raising=False,
    )
    opportunities, availability, _ = _repositories(tmp_path)
    app = create_app(
        repository=opportunities,
        availability_repository=availability,
        profile=None,
        enable_default_radar=False,
        enable_default_community_digest_preview=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )
    now = datetime.now(timezone.utc)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/availability/verification/preview",
            json=_evidence(now),
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Availability verification unavailable"
    }


def test_enabled_preview_is_read_only(tmp_path) -> None:
    opportunities, availability, _ = _repositories(tmp_path)
    app = _app(opportunities, availability, enabled=True)
    now = datetime.now(timezone.utc)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/availability/verification/preview",
            json=_evidence(now),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "READY"
    assert payload["current_state"] == "UNVERIFIED"
    assert payload["proposed_state"] == "VERIFIED_OPEN"
    assert payload["external_actions"] == []
    assert availability.list_observations("opp-1") == []


def test_enabled_confirm_records_exact_preview_once(tmp_path) -> None:
    opportunities, availability, _ = _repositories(tmp_path)
    app = _app(opportunities, availability, enabled=True)
    now = datetime.now(timezone.utc)
    evidence = _evidence(now)

    with TestClient(app) as client:
        preview = client.post(
            "/api/v1/availability/verification/preview",
            json=evidence,
        ).json()
        confirm = client.post(
            "/api/v1/availability/verification/confirm",
            json={
                "evidence": evidence,
                "preview_sha256": preview["preview_sha256"],
                "confirmed_by": "operator",
                "confirmed_at": now.isoformat(),
            },
        )
        retry = client.post(
            "/api/v1/availability/verification/confirm",
            json={
                "evidence": evidence,
                "preview_sha256": preview["preview_sha256"],
                "confirmed_by": "second_operator",
                "confirmed_at": (
                    now + timedelta(seconds=1)
                ).isoformat(),
            },
        )

    assert confirm.status_code == 200
    assert confirm.json()["status"] == "RECORDED"
    assert retry.status_code == 200
    assert retry.json()["status"] == "ALREADY_RECORDED"
    assert (
        retry.json()["receipt"]["receipt_id"]
        == confirm.json()["receipt"]["receipt_id"]
    )
    assert retry.json()["receipt"]["confirmed_by"] == "operator"
    assert len(availability.list_observations("opp-1")) == 1


def test_stale_preview_is_blocked_after_concurrent_sighting(tmp_path) -> None:
    opportunities, availability, _ = _repositories(tmp_path)
    app = _app(opportunities, availability, enabled=True)
    now = datetime.now(timezone.utc)
    evidence = _evidence(now)

    with TestClient(app) as client:
        preview = client.post(
            "/api/v1/availability/verification/preview",
            json=evidence,
        ).json()
        availability.record_seen(
            "opp-1",
            observed_at=now + timedelta(seconds=1),
            evidence_source="aggregator",
            source_url="https://aggregator.example/jobs/1",
        )
        response = client.post(
            "/api/v1/availability/verification/confirm",
            json={
                "evidence": evidence,
                "preview_sha256": preview["preview_sha256"],
                "confirmed_by": "operator",
                "confirmed_at": (
                    now + timedelta(seconds=2)
                ).isoformat(),
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "BLOCKED_STALE_PREVIEW",
        "receipt": None,
        "errors": ["stale_preview"],
    }


def test_verified_closed_workflow_does_not_mutate_base_opportunity_status(tmp_path) -> None:
    opportunities, availability, stored = _repositories(tmp_path)
    app = _app(opportunities, availability, enabled=True)
    now = datetime.now(timezone.utc)
    evidence = _evidence(now, decision="CLOSED")

    with TestClient(app) as client:
        preview = client.post(
            "/api/v1/availability/verification/preview",
            json=evidence,
        ).json()
        response = client.post(
            "/api/v1/availability/verification/confirm",
            json={
                "evidence": evidence,
                "preview_sha256": preview["preview_sha256"],
                "confirmed_by": "operator",
                "confirmed_at": now.isoformat(),
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "RECORDED"
    assert availability.get(stored.id).availability_state == "VERIFIED_CLOSED"
    assert opportunities.get(stored.id).status == "open"


def test_invalid_evidence_url_is_rejected_before_service(tmp_path) -> None:
    opportunities, availability, _ = _repositories(tmp_path)
    app = _app(opportunities, availability, enabled=True)
    now = datetime.now(timezone.utc)
    evidence = _evidence(now)
    evidence["source_url"] = "file:///tmp/fake"

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/availability/verification/preview",
            json=evidence,
        )

    assert response.status_code == 422


def test_missing_opportunity_returns_typed_blocked_preview(tmp_path) -> None:
    opportunities, availability, _ = _repositories(tmp_path)
    app = _app(opportunities, availability, enabled=True)
    now = datetime.now(timezone.utc)
    evidence = _evidence(now)
    evidence["opportunity_id"] = "missing"

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/availability/verification/preview",
            json=evidence,
        )

    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED"
    assert response.json()["errors"] == ["opportunity_not_found"]
