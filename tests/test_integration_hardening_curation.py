from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.availability.daily_curation import (
    DailyCurationPolicy,
    DailyCurationService,
)
from app.availability.daily_curation_operator_view import (
    DailyCurationOperatorViewOptions,
    DailyCurationOperatorViewService,
)
from app.availability.repository import SQLiteAvailabilityRepository
from app.availability.verification_queue import (
    VerificationQueuePolicy,
    VerificationQueueService,
)
from app.availability.verification_review_session import (
    VerificationReviewSessionService,
)
from app.models.domain import Opportunity
from app.radar.community_digest_preview import CommunityDigestPreviewService
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.source_catalog import load_source_catalog
from app.radar.source_refresh import _normalize_source_names
from app.repositories.opportunities import SQLiteOpportunityRepository
from app.services.ingestion import ingest


NOW = datetime(2026, 9, 19, 1, 0, tzinfo=timezone.utc)


class StaticConnector:
    def __init__(self, items: list[Opportunity]) -> None:
        self.items = items

    async def fetch(self) -> list[Opportunity]:
        return list(self.items)


def _opportunity(
    item_id: str,
    *,
    source: str = "linkedin",
    source_url: str | None = None,
    discovered_at: datetime | None = None,
    published_at: datetime | None = None,
) -> Opportunity:
    return Opportunity(
        id=item_id,
        source=source,
        source_id=item_id,
        source_url=source_url or f"https://linkedin.com/jobs/view/{item_id}",
        company=f"Company {item_id}",
        title=f"GIS Analyst {item_id}",
        description="QGIS geospatial work",
        discovered_at=discovered_at or NOW - timedelta(hours=1),
        published_at=published_at or NOW - timedelta(hours=2),
        status="open",
        location="Remote",
        remote_policy="remote",
    )


def _services(tmp_path):
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
    return daily, queue, opportunities, availability


def test_daily_curation_uses_queue_lookback_for_digest_candidates(
    tmp_path,
) -> None:
    daily, _, opportunities, _ = _services(tmp_path)
    opportunities.upsert(
        _opportunity(
            "old-linkedin",
            discovered_at=NOW - timedelta(days=45),
            published_at=NOW - timedelta(days=45),
        )
    )

    run = daily.run(
        now=NOW,
        policy=DailyCurationPolicy(
            queue_policy=VerificationQueuePolicy(
                candidate_lookback_days=30,
            )
        ),
    )

    assert run.held.total_count == 0
    assert run.publishable.digest.count == 0


def test_daily_curation_fails_closed_if_queue_changes_during_digest(
    tmp_path,
    monkeypatch,
) -> None:
    daily, queue, opportunities, _ = _services(tmp_path)
    opportunities.upsert(
        _opportunity(
            "linkedin",
            published_at=NOW - timedelta(hours=1),
        )
    )
    original_build = queue.build
    calls = 0

    def changing_build(*, now, policy=None):
        nonlocal calls
        calls += 1
        result = original_build(now=now, policy=policy)
        if calls >= 3:
            return result.model_copy(
                update={"inspected_count": result.inspected_count + 1}
            )
        return result

    monkeypatch.setattr(queue, "build", changing_build)

    with pytest.raises(
        RuntimeError,
        match="curation snapshot changed during digest projection",
    ):
        daily.run(now=NOW)


def test_operator_view_hides_structured_held_reasons_when_disabled(
    tmp_path,
) -> None:
    daily, _, opportunities, _ = _services(tmp_path)
    opportunities.upsert(_opportunity("linkedin"))
    service = DailyCurationOperatorViewService(
        daily_curation_service=daily,
    )

    view = service.build(
        now=NOW,
        view_options=DailyCurationOperatorViewOptions(
            include_held_details=False,
        ),
    )

    assert view.held.total_count == 1
    assert view.held.reason_counts == {}


def test_plain_operator_view_includes_next_draft_endpoint(tmp_path) -> None:
    daily, _, opportunities, _ = _services(tmp_path)
    opportunities.upsert(_opportunity("linkedin"))
    service = DailyCurationOperatorViewService(
        daily_curation_service=daily,
    )

    view = service.build(
        now=NOW,
        view_options=DailyCurationOperatorViewOptions(
            format="plain",
            include_checklists=False,
        ),
    )

    assert "Draft endpoint: /api/v1/availability/verification/draft" in (
        view.rendered_view
    )


def test_source_refresh_rejects_surrounding_source_whitespace() -> None:
    with pytest.raises(
        ValueError,
        match="source names must not contain surrounding whitespace",
    ):
        _normalize_source_names([" remotive "])


@pytest.mark.asyncio
async def test_ingest_clips_future_discovery_to_explicit_snapshot_time(
    tmp_path,
) -> None:
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()
    future_item = _opportunity(
        "future-discovery",
        source="greenhouse",
        source_url="https://boards.greenhouse.io/acme/jobs/1",
        discovered_at=NOW + timedelta(minutes=5),
        published_at=NOW - timedelta(hours=1),
    )

    result = await ingest(
        StaticConnector([future_item]),
        opportunities,
        availability_repository=availability,
        observed_at=NOW,
    )

    stored = opportunities.get("future-discovery")
    assert result.created == 1
    assert stored is not None
    assert stored.discovered_at == NOW
    assert availability.get("future-discovery").last_seen_at == NOW
