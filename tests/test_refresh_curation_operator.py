from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

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
from app.models.domain import Opportunity
from app.radar.community_digest_preview import CommunityDigestPreviewService
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.source_catalog import load_source_catalog
from app.radar.source_refresh import SourceRefreshService
from app.radar.sources import ConfiguredConnector
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime(2026, 9, 19, 1, 30, tzinfo=timezone.utc)


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


def _opportunity(
    item_id: str,
    *,
    source: str,
    source_url: str,
    title: str = "GIS Analyst",
) -> Opportunity:
    source_id = item_id.split(":", 1)[-1]
    return Opportunity(
        id=item_id,
        source=source,
        source_id=source_id,
        source_url=source_url,
        company=f"Company {source_id}",
        title=title,
        description="QGIS geospatial work",
        discovered_at=NOW - timedelta(hours=1),
        published_at=NOW - timedelta(hours=2),
        status="open",
        location="Remote",
        remote_policy="remote",
    )


def _service(tmp_path, connectors: list[ConfiguredConnector]):
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()

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
    return (
        RefreshCurationOperatorService(
            source_refresh_service=refresh,
            operator_view_service=operator,
        ),
        opportunities,
        availability,
    )


@pytest.mark.asyncio
async def test_refresh_happens_before_curation_and_official_ats_is_publishable(
    tmp_path,
) -> None:
    greenhouse = StaticConnector(
        [
            _opportunity(
                "greenhouse:1",
                source="greenhouse",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ]
    )
    service, opportunities, availability = _service(
        tmp_path,
        [
            ConfiguredConnector(
                name="greenhouse:acme",
                connector=greenhouse,
            )
        ],
    )

    assert opportunities.list() == []

    run = await service.run(now=NOW)

    assert run.source_refresh.created_count == 1
    assert run.source_refresh.seen_recorded_count == 1
    assert run.operator_view.publishable_count == 1
    assert run.operator_view.held_count == 0
    assert run.operator_view.review_count == 0
    assert "greenhouse:1" in run.operator_view.publishable.rendered_digest
    state = availability.get("greenhouse:1")
    assert state is not None
    assert state.last_seen_at == NOW
    assert run.generated_at == NOW
    assert run.operator_view.generated_at == NOW


@pytest.mark.asyncio
async def test_platform_job_board_refresh_enters_held_review_not_publishable(
    tmp_path,
) -> None:
    remotive = StaticConnector(
        [
            _opportunity(
                "remotive:1",
                source="remotive",
                source_url="https://remotive.com/jobs/1",
            )
        ]
    )
    service, _, _ = _service(
        tmp_path,
        [ConfiguredConnector(name="remotive", connector=remotive)],
    )

    run = await service.run(now=NOW)

    assert run.source_refresh.created_count == 1
    assert run.operator_view.review_count == 1
    assert run.operator_view.held_count == 1
    assert run.operator_view.publishable_count == 0
    assert run.operator_view.review_items[0].opportunity_id == "remotive:1"
    assert run.operator_view.review_items[0].next_action == (
        "Verificar fuente actual"
    )


@pytest.mark.asyncio
async def test_partial_source_failure_still_runs_curation_and_surfaces_failure(
    tmp_path,
) -> None:
    greenhouse = StaticConnector(
        [
            _opportunity(
                "greenhouse:1",
                source="greenhouse",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ]
    )
    service, _, _ = _service(
        tmp_path,
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

    run = await service.run(now=NOW)

    assert run.partial_source_failure is True
    assert run.source_refresh.ok_count == 1
    assert run.source_refresh.error_count == 1
    assert run.operator_view.publishable_count == 1
    assert "DO_NOT_ECHO_UPSTREAM_SECRET" not in run.model_dump_json()


@pytest.mark.asyncio
async def test_all_source_failures_still_project_existing_stored_state(
    tmp_path,
) -> None:
    service, opportunities, _ = _service(
        tmp_path,
        [
            ConfiguredConnector(
                name="greenhouse:broken",
                connector=FailingConnector(),
            )
        ],
    )
    opportunities.upsert(
        _opportunity(
            "greenhouse:stored",
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/stored",
        )
    )

    run = await service.run(now=NOW)

    assert run.partial_source_failure is True
    assert run.source_refresh.ok_count == 0
    assert run.source_refresh.error_count == 1
    assert run.operator_view.publishable_count == 1
    assert "greenhouse:stored" in run.operator_view.publishable.rendered_digest


@pytest.mark.asyncio
async def test_exact_source_subset_controls_reads_before_curation(tmp_path) -> None:
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
    service, opportunities, _ = _service(
        tmp_path,
        [
            ConfiguredConnector(name="remotive", connector=remotive),
            ConfiguredConnector(
                name="greenhouse:acme",
                connector=greenhouse,
            ),
        ],
    )

    run = await service.run(
        now=NOW,
        source_names=["greenhouse:acme"],
    )

    assert run.external_reads == ["greenhouse:acme"]
    assert remotive.calls == 0
    assert greenhouse.calls == 1
    assert opportunities.get("remotive:1") is None
    assert opportunities.get("greenhouse:1") is not None
    assert run.operator_view.publishable_count == 1


@pytest.mark.asyncio
async def test_invalid_source_subset_fails_before_curation(tmp_path) -> None:
    service, opportunities, _ = _service(tmp_path, [])

    with pytest.raises(
        ValueError,
        match="requested source is not configured",
    ):
        await service.run(
            now=NOW,
            source_names=["unknown"],
        )

    assert opportunities.list() == []


@pytest.mark.asyncio
async def test_refresh_curation_run_exposes_reads_but_no_downstream_actions(
    tmp_path,
) -> None:
    greenhouse = StaticConnector(
        [
            _opportunity(
                "greenhouse:1",
                source="greenhouse",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ]
    )
    service, _, _ = _service(
        tmp_path,
        [
            ConfiguredConnector(
                name="greenhouse:acme",
                connector=greenhouse,
            )
        ],
    )

    run = await service.run(now=NOW)

    assert run.external_reads == ["greenhouse:acme"]
    assert run.external_actions == []
    assert run.source_refresh.external_actions == []
    assert run.operator_view.external_actions == []


@pytest.mark.asyncio
async def test_refresh_curation_run_id_changes_with_refresh_outcome(tmp_path) -> None:
    greenhouse = StaticConnector(
        [
            _opportunity(
                "greenhouse:1",
                source="greenhouse",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ]
    )
    service, _, _ = _service(
        tmp_path,
        [
            ConfiguredConnector(
                name="greenhouse:acme",
                connector=greenhouse,
            )
        ],
    )

    first = await service.run(now=NOW)
    second = await service.run(now=NOW)

    assert first.source_refresh.created_count == 1
    assert second.source_refresh.created_count == 0
    assert second.source_refresh.existing_count == 1
    assert first.run_id != second.run_id


@pytest.mark.asyncio
async def test_refresh_curation_requires_timezone_aware_now(tmp_path) -> None:
    service, _, _ = _service(tmp_path, [])

    with pytest.raises(ValueError, match="now must be timezone-aware"):
        await service.run(
            now=datetime(2026, 9, 19, 1, 30),
        )
