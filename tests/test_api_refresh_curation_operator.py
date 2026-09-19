from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.availability.daily_curation import DailyCurationService
from app.availability.daily_curation_operator_view import (
    DailyCurationOperatorViewService,
)
from app.availability.refresh_curation_operator import (
    RefreshCurationOperatorService,
)
from app.availability.repository import SQLiteAvailabilityRepository
from app.availability.verification_queue import VerificationQueueService
from app.availability.verification_review_session import (
    VerificationReviewSessionService,
)
from app.connectors.base import ConnectorError
from app.main import create_app
from app.models.domain import Opportunity
from app.radar.community_digest_preview import CommunityDigestPreviewService
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.source_catalog import load_source_catalog
from app.radar.source_refresh import SourceRefreshService
from app.radar.sources import ConfiguredConnector
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime.now(timezone.utc) - timedelta(minutes=2)


class StaticConnector:
    def __init__(self, opportunities: list[Opportunity]) -> None:
        self.opportunities = opportunities
        self.calls = 0

    async def fetch(self) -> list[Opportunity]:
        self.calls += 1
        return list(self.opportunities)


class FailingConnector:
    async def fetch(self) -> list[Opportunity]:
        raise ConnectorError("DO_NOT_ECHO_UPSTREAM_SECRET")


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
) -> Opportunity:
    source_id = item_id.split(":", 1)[-1]
    return Opportunity(
        id=item_id,
        source=source,
        source_id=source_id,
        source_url=source_url,
        company=f"Company {source_id}",
        title="GIS Analyst",
        description="QGIS geospatial work",
        discovered_at=NOW - timedelta(hours=1),
        published_at=NOW - timedelta(hours=2),
        status="open",
        location="Remote",
        remote_policy="remote",
    )


def _combined_service(
    opportunities,
    availability,
    connectors: list[ConfiguredConnector],
) -> tuple[SourceRefreshService, RefreshCurationOperatorService]:
    catalog = load_source_catalog(Path("config/source_catalog.yaml"))
    extractor = RuleBasedRequirementExtractor(source_catalog=catalog)
    queue = VerificationQueueService(
        opportunity_repository=opportunities,
        availability_repository=availability,
        extractor=extractor,
        source_catalog=catalog,
    )
    review = VerificationReviewSessionService(queue_service=queue)
    digest = CommunityDigestPreviewService(
        opportunity_repository=opportunities,
        extractor=extractor,
        availability_repository=availability,
    )
    daily = DailyCurationService(
        queue_service=queue,
        review_session_service=review,
        digest_preview_service=digest,
    )
    operator = DailyCurationOperatorViewService(
        daily_curation_service=daily,
    )
    refresh = SourceRefreshService(
        opportunity_repository=opportunities,
        availability_repository=availability,
        connectors=connectors,
    )
    combined = RefreshCurationOperatorService(
        source_refresh_service=refresh,
        operator_view_service=operator,
    )
    return refresh, combined


def _app(
    opportunities,
    availability,
    *,
    refresh=None,
    combined=None,
    enable_source_refresh: bool | None = False,
    enable_operator_view: bool = True,
):
    return create_app(
        repository=opportunities,
        availability_repository=availability,
        source_refresh_service=refresh,
        refresh_curation_operator_service=combined,
        enable_source_refresh=enable_source_refresh,
        enable_default_daily_curation_operator_view=enable_operator_view,
        profile=None,
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )


def test_combined_endpoint_refreshes_before_building_operator_view(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    greenhouse = StaticConnector(
        [
            _opportunity(
                "greenhouse:1",
                source="greenhouse",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ]
    )
    refresh, combined = _combined_service(
        opportunities,
        availability,
        [
            ConfiguredConnector(
                name="greenhouse:acme",
                connector=greenhouse,
            )
        ],
    )
    app = _app(
        opportunities,
        availability,
        refresh=refresh,
        combined=combined,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily/refresh-view"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_refresh"]["created_count"] == 1
    assert payload["operator_view"]["publishable_count"] == 1
    assert payload["operator_view"]["held_count"] == 0
    assert payload["external_reads"] == ["greenhouse:acme"]
    assert payload["external_actions"] == []
    assert availability.get("greenhouse:1") is not None


def test_combined_endpoint_routes_unverified_platform_item_to_review(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    remotive = StaticConnector(
        [
            _opportunity(
                "remotive:1",
                source="remotive",
                source_url="https://remotive.com/jobs/1",
            )
        ]
    )
    refresh, combined = _combined_service(
        opportunities,
        availability,
        [ConfiguredConnector(name="remotive", connector=remotive)],
    )
    app = _app(
        opportunities,
        availability,
        refresh=refresh,
        combined=combined,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily/refresh-view"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["operator_view"]["review_count"] == 1
    assert payload["operator_view"]["held_count"] == 1
    assert payload["operator_view"]["publishable_count"] == 0
    assert payload["operator_view"]["review_items"][0]["opportunity_id"] == (
        "remotive:1"
    )


def test_combined_endpoint_surfaces_partial_failure_and_keeps_curation(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    greenhouse = StaticConnector(
        [
            _opportunity(
                "greenhouse:1",
                source="greenhouse",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ]
    )
    refresh, combined = _combined_service(
        opportunities,
        availability,
        [
            ConfiguredConnector(
                name="greenhouse:acme",
                connector=greenhouse,
            ),
            ConfiguredConnector(
                name="lever:broken",
                connector=FailingConnector(),
            ),
        ],
    )
    app = _app(
        opportunities,
        availability,
        refresh=refresh,
        combined=combined,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily/refresh-view"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["partial_source_failure"] is True
    assert payload["source_refresh"]["error_count"] == 1
    assert payload["operator_view"]["publishable_count"] == 1
    assert "DO_NOT_ECHO_UPSTREAM_SECRET" not in response.text


def test_combined_endpoint_supports_exact_source_subset(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    remotive = StaticConnector(
        [
            _opportunity(
                "remotive:1",
                source="remotive",
                source_url="https://remotive.com/jobs/1",
            )
        ]
    )
    greenhouse = StaticConnector(
        [
            _opportunity(
                "greenhouse:1",
                source="greenhouse",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ]
    )
    refresh, combined = _combined_service(
        opportunities,
        availability,
        [
            ConfiguredConnector(name="remotive", connector=remotive),
            ConfiguredConnector(
                name="greenhouse:acme",
                connector=greenhouse,
            ),
        ],
    )
    app = _app(
        opportunities,
        availability,
        refresh=refresh,
        combined=combined,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily/refresh-view",
            json={"sources": ["greenhouse:acme"]},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["external_reads"] == ["greenhouse:acme"]
    assert remotive.calls == 0
    assert greenhouse.calls == 1
    assert payload["operator_view"]["publishable_count"] == 1


def test_combined_endpoint_propagates_operator_render_options(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    greenhouse = StaticConnector(
        [
            _opportunity(
                "greenhouse:1",
                source="greenhouse",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ]
    )
    refresh, combined = _combined_service(
        opportunities,
        availability,
        [
            ConfiguredConnector(
                name="greenhouse:acme",
                connector=greenhouse,
            )
        ],
    )
    app = _app(
        opportunities,
        availability,
        refresh=refresh,
        combined=combined,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily/refresh-view",
            json={
                "view_title": "Ronda de hoy",
                "view_format": "plain",
                "format": "markdown",
                "title": "Digest de hoy",
                "include_intro": False,
                "include_footer": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["operator_view"]["title"] == "Ronda de hoy"
    assert payload["operator_view"]["format"] == "plain"
    assert payload["operator_view"]["rendered_view"].startswith("Ronda de hoy")
    assert payload["operator_view"]["publishable"]["format"] == "markdown"


def test_combined_endpoint_is_unavailable_when_source_refresh_is_disabled(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPPORTUNITY_SOURCE_REFRESH_ENABLED", raising=False)
    opportunities, availability = _repositories(tmp_path)
    app = create_app(
        repository=opportunities,
        availability_repository=availability,
        profile=None,
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily/refresh-view"
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Refresh curation operator run unavailable"
    }


def test_combined_endpoint_is_unavailable_without_operator_view(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    refresh, _ = _combined_service(opportunities, availability, [])
    app = _app(
        opportunities,
        availability,
        refresh=refresh,
        combined=None,
        enable_operator_view=False,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily/refresh-view"
        )

    assert response.status_code == 503


def test_combined_endpoint_invalid_source_is_public_safe_422(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    refresh, combined = _combined_service(opportunities, availability, [])
    app = _app(
        opportunities,
        availability,
        refresh=refresh,
        combined=combined,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily/refresh-view",
            json={"sources": ["PRIVATE_UNKNOWN_SOURCE"]},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid refresh curation operator options"
    }
    assert "PRIVATE_UNKNOWN_SOURCE" not in response.text


def test_combined_endpoint_requires_no_candidate_profile(tmp_path) -> None:
    opportunities, availability = _repositories(tmp_path)
    refresh, combined = _combined_service(opportunities, availability, [])
    app = _app(
        opportunities,
        availability,
        refresh=refresh,
        combined=combined,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/curation/daily/refresh-view"
        )

    assert response.status_code == 200
    assert "career_match" not in response.text
    assert "income_viability" not in response.text
