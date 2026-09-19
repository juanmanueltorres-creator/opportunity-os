from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.availability.repository import SQLiteAvailabilityRepository
from app.curation.repository import SQLiteCurationLedgerRepository
from app.curation.service import CurationLedgerService
from app.main import create_app
from app.models.domain import Opportunity
from app.radar.source_refresh import SourceRefreshService
from app.radar.sources import ConfiguredConnector
from app.repositories.opportunities import SQLiteOpportunityRepository


class StaticConnector:
    def __init__(self, opportunities: list[Opportunity]) -> None:
        self.opportunities = opportunities

    async def fetch(self) -> list[Opportunity]:
        return list(self.opportunities)


def _repositories(tmp_path):
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()
    return opportunities, availability


def _greenhouse_opportunity() -> Opportunity:
    now = datetime.now(timezone.utc)
    return Opportunity(
        id="greenhouse:1",
        source="greenhouse",
        source_id="1",
        source_url="https://boards.greenhouse.io/acme/jobs/1",
        company="Acme",
        title="GIS Analyst",
        description="QGIS geospatial work",
        discovered_at=now - timedelta(minutes=5),
        published_at=now - timedelta(hours=1),
        status="open",
        location="Remote",
        remote_policy="remote",
    )


def _remotive_opportunity() -> Opportunity:
    now = datetime.now(timezone.utc)
    return Opportunity(
        id="remotive:1",
        source="remotive",
        source_id="1",
        source_url="https://remotive.com/jobs/1",
        company="Remote Co",
        title="GIS Analyst",
        description="QGIS geospatial work",
        discovered_at=now - timedelta(minutes=5),
        published_at=now - timedelta(hours=1),
        status="open",
        location="Remote",
        remote_policy="remote",
    )


def _app(
    opportunities,
    availability,
    items: list[Opportunity],
    *,
    ledger_enabled: bool = True,
):
    refresh = SourceRefreshService(
        opportunity_repository=opportunities,
        availability_repository=availability,
        connectors=[
            ConfiguredConnector(
                name="source:test",
                connector=StaticConnector(items),
            )
        ],
    )
    return create_app(
        repository=opportunities,
        availability_repository=availability,
        source_refresh_service=refresh,
        enable_source_refresh=False,
        enable_default_curation_ledger=ledger_enabled,
        profile=None,
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )


def test_api_records_run_confirms_publication_and_suppresses_next_digest(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        [_greenhouse_opportunity()],
    )

    with TestClient(app) as client:
        run_response = client.post(
            "/api/v1/curation/daily/refresh-view"
        )
        assert run_response.status_code == 200
        run = run_response.json()
        assert run["operator_view"]["publishable_count"] == 1
        publishable_ids = run["operator_view"]["publishable"][
            "opportunity_ids"
        ]
        assert publishable_ids == ["greenhouse:1"]

        record_response = client.post(
            "/api/v1/curation/ledger/runs",
            json=run,
        )
        assert record_response.status_code == 200
        record = record_response.json()
        assert record["status"] == "NEW"
        assert record["record"]["publishable_opportunity_ids"] == [
            "greenhouse:1"
        ]

        preview_response = client.post(
            "/api/v1/curation/publication/preview",
            json={
                "run_id": run["run_id"],
                "digest_id": run["operator_view"]["publishable"]["digest_id"],
                "opportunity_ids": publishable_ids,
                "channel": "WHATSAPP",
            },
        )
        assert preview_response.status_code == 200
        preview = preview_response.json()
        assert preview["status"] == "READY"

        confirmed_at = datetime.now(timezone.utc)
        confirm_response = client.post(
            "/api/v1/curation/publication/confirm",
            json={
                "preview": preview,
                "confirmed_by": "operator",
                "confirmed_at": confirmed_at.isoformat(),
                "note": "Published manually",
            },
        )
        assert confirm_response.status_code == 200
        confirmation = confirm_response.json()
        assert confirmation["status"] == "RECORDED"
        assert confirmation["checkpoint"]["opportunity_ids"] == [
            "greenhouse:1"
        ]

        next_view_response = client.post(
            "/api/v1/curation/daily/view"
        )
        assert next_view_response.status_code == 200
        next_view = next_view_response.json()

    assert next_view["publishable_count"] == 0
    assert next_view["held_count"] == 0
    assert next_view["publishable"]["opportunity_ids"] == []


def test_api_publication_preview_rejects_review_only_item(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        [_remotive_opportunity()],
    )

    with TestClient(app) as client:
        run = client.post(
            "/api/v1/curation/daily/refresh-view"
        ).json()
        assert run["operator_view"]["review_count"] == 1
        assert run["operator_view"]["publishable_count"] == 0

        record = client.post(
            "/api/v1/curation/ledger/runs",
            json=run,
        )
        assert record.status_code == 200

        preview = client.post(
            "/api/v1/curation/publication/preview",
            json={
                "run_id": run["run_id"],
                "digest_id": run["operator_view"]["publishable"]["digest_id"],
                "opportunity_ids": ["remotive:1"],
                "channel": "WHATSAPP",
            },
        )

    assert preview.status_code == 200
    payload = preview.json()
    assert payload["status"] == "BLOCKED"
    assert payload["errors"] == [
        "opportunity_not_in_recorded_publishable_digest"
    ]


def test_api_duplicate_run_record_is_idempotent(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        [_greenhouse_opportunity()],
    )

    with TestClient(app) as client:
        run = client.post(
            "/api/v1/curation/daily/refresh-view"
        ).json()
        first = client.post(
            "/api/v1/curation/ledger/runs",
            json=run,
        )
        second = client.post(
            "/api/v1/curation/ledger/runs",
            json=run,
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "NEW"
    assert second.json()["status"] == "IDENTICAL"
    assert (
        first.json()["record"]["recorded_at"]
        == second.json()["record"]["recorded_at"]
    )


def test_api_repeated_publication_preview_is_blocked(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        [_greenhouse_opportunity()],
    )

    with TestClient(app) as client:
        run = client.post(
            "/api/v1/curation/daily/refresh-view"
        ).json()
        client.post("/api/v1/curation/ledger/runs", json=run)
        evidence = {
            "run_id": run["run_id"],
            "digest_id": run["operator_view"]["publishable"]["digest_id"],
            "opportunity_ids": ["greenhouse:1"],
            "channel": "WHATSAPP",
        }
        preview = client.post(
            "/api/v1/curation/publication/preview",
            json=evidence,
        ).json()
        confirm = client.post(
            "/api/v1/curation/publication/confirm",
            json={
                "preview": preview,
                "confirmed_by": "operator",
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        repeated = client.post(
            "/api/v1/curation/publication/preview",
            json=evidence,
        )

    assert confirm.status_code == 200
    assert confirm.json()["status"] == "RECORDED"
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "BLOCKED"
    assert repeated.json()["errors"] == ["opportunity_already_published"]


def test_curation_ledger_can_be_disabled(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        [_greenhouse_opportunity()],
        ledger_enabled=False,
    )

    with TestClient(app) as client:
        run = client.post(
            "/api/v1/curation/daily/refresh-view"
        ).json()
        response = client.post(
            "/api/v1/curation/ledger/runs",
            json=run,
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Curation ledger unavailable"}


def test_invalid_publication_cooldown_is_rejected_by_schema(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        [],
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily/view",
            json={"publication_cooldown_days": 0},
        )

    assert response.status_code == 422


def test_api_tampered_run_snapshot_is_blocked(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        [_greenhouse_opportunity()],
    )

    with TestClient(app) as client:
        run = client.post(
            "/api/v1/curation/daily/refresh-view"
        ).json()
        run["partial_source_failure"] = True
        response = client.post(
            "/api/v1/curation/ledger/runs",
            json=run,
        )

    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED"
    assert response.json()["errors"] == [
        "run_partial_failure_snapshot_mismatch"
    ]


def test_api_exact_publication_confirm_retry_is_idempotent(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        [_greenhouse_opportunity()],
    )

    with TestClient(app) as client:
        run = client.post(
            "/api/v1/curation/daily/refresh-view"
        ).json()
        client.post("/api/v1/curation/ledger/runs", json=run)
        preview = client.post(
            "/api/v1/curation/publication/preview",
            json={
                "run_id": run["run_id"],
                "digest_id": run["operator_view"]["publishable"]["digest_id"],
                "opportunity_ids": ["greenhouse:1"],
                "channel": "WHATSAPP",
            },
        ).json()
        request = {
            "preview": preview,
            "confirmed_by": "operator",
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "note": "Posted manually",
        }
        first = client.post(
            "/api/v1/curation/publication/confirm",
            json=request,
        )
        second = client.post(
            "/api/v1/curation/publication/confirm",
            json=request,
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "RECORDED"
    assert second.json()["status"] == "ALREADY_RECORDED"
    assert (
        first.json()["checkpoint"]["checkpoint_id"]
        == second.json()["checkpoint"]["checkpoint_id"]
    )


def test_injected_ledger_service_requires_repository_for_default_daily_curation(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    custom_repository = SQLiteCurationLedgerRepository(
        tmp_path / "custom-ledger.db"
    )
    custom_service = CurationLedgerService(repository=custom_repository)

    with pytest.raises(
        ValueError,
        match="curation_ledger_repository is required",
    ):
        create_app(
            repository=opportunities,
            availability_repository=availability,
            curation_ledger_service=custom_service,
            enable_source_refresh=False,
            profile=None,
            enable_default_radar=False,
            enable_default_targets=False,
            enable_default_relationships=False,
        )


def test_api_curation_history_reports_recorded_run_and_publication(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        [_greenhouse_opportunity()],
    )

    with TestClient(app) as client:
        run = client.post(
            "/api/v1/curation/daily/refresh-view"
        ).json()
        record = client.post(
            "/api/v1/curation/ledger/runs",
            json=run,
        )
        assert record.status_code == 200

        preview = client.post(
            "/api/v1/curation/publication/preview",
            json={
                "run_id": run["run_id"],
                "digest_id": run["operator_view"]["publishable"]["digest_id"],
                "opportunity_ids": ["greenhouse:1"],
                "channel": "WHATSAPP",
            },
        ).json()
        confirm = client.post(
            "/api/v1/curation/publication/confirm",
            json={
                "preview": preview,
                "confirmed_by": "operator",
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        assert confirm.status_code == 200
        assert confirm.json()["status"] == "RECORDED"

        history = client.get("/api/v1/curation/history?limit=5")

    assert history.status_code == 200
    payload = history.json()
    assert payload["limit"] == 5
    assert payload["count"] == 1
    item = payload["items"][0]
    assert item["run_id"] == run["run_id"]
    assert item["new_opportunity_count"] == 1
    assert item["published_opportunity_ids"] == ["greenhouse:1"]
    assert item["publication_checkpoint_count"] == 1
    assert item["publication_channels"] == ["WHATSAPP"]
    assert payload["external_actions"] == []


def test_api_curation_history_validates_limit_and_ledger_availability(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    enabled_app = _app(opportunities, availability, [])
    disabled_app = _app(
        opportunities,
        availability,
        [],
        ledger_enabled=False,
    )

    with TestClient(enabled_app) as client:
        invalid = client.get("/api/v1/curation/history?limit=0")
    with TestClient(disabled_app) as client:
        unavailable = client.get("/api/v1/curation/history")

    assert invalid.status_code == 422
    assert unavailable.status_code == 503
    assert unavailable.json() == {"detail": "Curation ledger unavailable"}


def test_api_latest_curation_delta_compares_two_recorded_runs(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        [_greenhouse_opportunity()],
    )

    with TestClient(app) as client:
        first = client.post(
            "/api/v1/curation/daily/refresh-view"
        ).json()
        assert client.post(
            "/api/v1/curation/ledger/runs",
            json=first,
        ).status_code == 200
        preview = client.post(
            "/api/v1/curation/publication/preview",
            json={
                "run_id": first["run_id"],
                "digest_id": first["operator_view"]["publishable"]["digest_id"],
                "opportunity_ids": ["greenhouse:1"],
                "channel": "WHATSAPP",
            },
        ).json()
        confirmation = client.post(
            "/api/v1/curation/publication/confirm",
            json={
                "preview": preview,
                "confirmed_by": "operator",
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        assert confirmation.json()["status"] == "RECORDED"

        second = client.post(
            "/api/v1/curation/daily/refresh-view"
        ).json()
        assert client.post(
            "/api/v1/curation/ledger/runs",
            json=second,
        ).status_code == 200

        response = client.get("/api/v1/curation/history/delta")

    assert response.status_code == 200
    delta = response.json()
    assert delta["status"] == "READY"
    assert delta["current_run"]["run_id"] == second["run_id"]
    assert delta["previous_run"]["run_id"] == first["run_id"]
    assert delta["exited_publishable_ids"] == ["greenhouse:1"]
    assert delta["published_only_in_previous_run_ids"] == ["greenhouse:1"]
    assert delta["external_actions"] == []


def test_api_latest_curation_delta_requires_ledger(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    app = _app(
        opportunities,
        availability,
        [],
        ledger_enabled=False,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/curation/history/delta")

    assert response.status_code == 503
    assert response.json() == {"detail": "Curation ledger unavailable"}
