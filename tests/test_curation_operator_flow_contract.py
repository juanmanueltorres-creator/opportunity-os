from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.availability.repository import SQLiteAvailabilityRepository
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


def _opportunity(item_id: str) -> Opportunity:
    now = datetime.now(timezone.utc)
    source_id = item_id.split(":", 1)[1]
    return Opportunity(
        id=item_id,
        source="greenhouse",
        source_id=source_id,
        source_url=f"https://boards.greenhouse.io/acme/jobs/{source_id}",
        company="Acme",
        title=f"GIS Analyst {source_id}",
        description="QGIS geospatial work",
        discovered_at=now - timedelta(minutes=5),
        published_at=now - timedelta(hours=1),
        status="open",
        location="Remote",
        remote_policy="remote",
    )


def _app(tmp_path):
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()
    refresh = SourceRefreshService(
        opportunity_repository=opportunities,
        availability_repository=availability,
        connectors=[
            ConfiguredConnector(
                name="source:test",
                connector=StaticConnector(
                    [_opportunity("greenhouse:1"), _opportunity("greenhouse:2")]
                ),
            )
        ],
    )
    return create_app(
        repository=opportunities,
        availability_repository=availability,
        source_refresh_service=refresh,
        enable_source_refresh=False,
        enable_default_curation_ledger=True,
        profile=None,
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )


def _record_run(client: TestClient, run: dict) -> None:
    response = client.post("/api/v1/curation/ledger/runs", json=run)
    assert response.status_code == 200
    assert response.json()["status"] == "NEW"


def _checkpoint(
    client: TestClient,
    *,
    run: dict,
    opportunity_ids: list[str],
) -> None:
    preview_response = client.post(
        "/api/v1/curation/publication/preview",
        json={
            "run_id": run["run_id"],
            "digest_id": run["operator_view"]["publishable"]["digest_id"],
            "opportunity_ids": opportunity_ids,
            "channel": "WHATSAPP",
        },
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["status"] == "READY"

    confirm_response = client.post(
        "/api/v1/curation/publication/confirm",
        json={
            "preview": preview,
            "confirmed_by": "operator",
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "note": "Operator flow contract",
        },
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "RECORDED"


def test_operator_flow_contract_end_to_end(tmp_path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as client:
        first_response = client.post("/api/v1/curation/daily/refresh-view")
        assert first_response.status_code == 200
        first = first_response.json()
        assert set(
            first["operator_view"]["publishable"]["opportunity_ids"]
        ) == {"greenhouse:1", "greenhouse:2"}
        _record_run(client, first)

        baseline = client.get(
            "/api/v1/curation/operator/overview?format=plain"
        ).json()
        assert baseline["status"] == "BASELINE_ONLY"
        assert baseline["current_run"]["run_id"] == first["run_id"]
        assert baseline["publication_coverage"]["status"] == "NONE_CHECKPOINTED"
        assert set(baseline["uncheckpointed_publishable_ids"]) == {
            "greenhouse:1",
            "greenhouse:2",
        }

        _checkpoint(
            client,
            run=first,
            opportunity_ids=["greenhouse:1"],
        )

        partial = client.get(
            "/api/v1/curation/operator/overview?format=plain"
        ).json()
        assert partial["publication_coverage"]["status"] == "PARTIAL"
        assert partial["publication_coverage"]["checkpointed_opportunity_ids"] == [
            "greenhouse:1"
        ]
        assert partial["uncheckpointed_publishable_ids"] == ["greenhouse:2"]

        second_response = client.post("/api/v1/curation/daily/refresh-view")
        assert second_response.status_code == 200
        second = second_response.json()
        assert second["operator_view"]["publishable"]["opportunity_ids"] == [
            "greenhouse:2"
        ]
        _record_run(client, second)

        ready = client.get(
            "/api/v1/curation/operator/overview?format=plain"
        ).json()
        assert ready["status"] == "READY"
        assert ready["current_run"]["run_id"] == second["run_id"]
        assert ready["delta"]["previous_run"]["run_id"] == first["run_id"]
        assert ready["delta"]["exited_publishable_ids"] == ["greenhouse:1"]
        assert ready["publication_coverage"]["status"] == "NONE_CHECKPOINTED"
        assert ready["publication_coverage"]["checkpointed_opportunity_ids"] == []
        assert ready["uncheckpointed_publishable_ids"] == ["greenhouse:2"]

        _checkpoint(
            client,
            run=second,
            opportunity_ids=["greenhouse:2"],
        )

        complete = client.get(
            "/api/v1/curation/operator/overview?format=plain"
        ).json()
        assert complete["status"] == "READY"
        assert complete["publication_coverage"]["status"] == "COMPLETE"
        assert complete["publication_coverage"]["checkpointed_opportunity_ids"] == [
            "greenhouse:2"
        ]
        assert complete["uncheckpointed_publishable_ids"] == []

        final_view_response = client.post("/api/v1/curation/daily/view")
        assert final_view_response.status_code == 200
        final_view = final_view_response.json()
        assert final_view["publishable"]["opportunity_ids"] == []
        assert final_view["publishable_count"] == 0

    for snapshot in (baseline, partial, ready, complete):
        assert snapshot["external_actions"] == []
        assert snapshot["delta"]["external_actions"] == []
        assert snapshot["change_brief"]["external_actions"] == []
        assert snapshot["publication_coverage"]["external_actions"] == []
