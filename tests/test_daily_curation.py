from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.availability.daily_curation import (
    DailyCurationPolicy,
    DailyCurationService,
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
from app.radar.community_digest import CommunityDigestPolicy
from app.radar.community_digest_preview import CommunityDigestPreviewService
from app.radar.community_digest_renderer import CommunityDigestRenderOptions
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.source_catalog import load_source_catalog
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime(2026, 9, 18, 22, 30, tzinfo=timezone.utc)


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
    return (
        DailyCurationService(
            queue_service=queue,
            review_session_service=review,
            digest_preview_service=digest,
        ),
        opportunities,
        availability,
    )


def _opportunity(
    item_id: str,
    *,
    source: str,
    source_url: str,
    title: str | None = None,
    published_at: datetime | None = NOW - timedelta(hours=2),
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
        published_at=published_at,
        status="open",
        location="Remote",
        remote_policy="remote",
    )


def test_daily_run_partitions_review_publishable_and_held(tmp_path) -> None:
    service, repository, availability = _services(tmp_path)

    repository.upsert(
        _opportunity(
            "reddit",
            source="reddit",
            source_url="https://reddit.com/r/gis/comments/example",
        )
    )
    repository.upsert(
        _opportunity(
            "linkedin-unverified",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/unverified",
        )
    )
    repository.upsert(
        _opportunity(
            "greenhouse",
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/1",
        )
    )
    verified, _ = repository.upsert(
        _opportunity(
            "linkedin-verified",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/verified",
        )
    )
    availability.record_verification(
        verified.id,
        is_open=True,
        observed_at=NOW - timedelta(days=1),
        evidence_source="official_company_page",
    )

    run = service.run(
        now=NOW,
        policy=DailyCurationPolicy(review_batch_size=2),
    )

    assert [card.opportunity_id for card in run.review.cards] == [
        "reddit",
        "linkedin-unverified",
    ]
    held_ids = [item.opportunity_id for item in run.held.items]
    assert "reddit" in held_ids
    assert "linkedin-unverified" in held_ids

    publishable_ids = [
        item.opportunity_id
        for item in run.publishable.digest.items
    ]
    assert "greenhouse" in publishable_ids
    assert "linkedin-verified" in publishable_ids
    assert "reddit" not in publishable_ids
    assert "linkedin-unverified" not in publishable_ids


def test_unverified_fast_market_is_held_not_publishable(tmp_path) -> None:
    service, repository, _ = _services(tmp_path)
    repository.upsert(
        _opportunity(
            "workana",
            source="workana",
            source_url="https://workana.com/job/1",
        )
    )

    run = service.run(now=NOW)

    assert run.held.total_count == 1
    assert run.held.items[0].opportunity_id == "workana"
    assert run.publishable.digest.count == 0


def test_recent_verified_fast_market_can_be_publishable(tmp_path) -> None:
    service, repository, availability = _services(tmp_path)
    stored, _ = repository.upsert(
        _opportunity(
            "workana",
            source="workana",
            source_url="https://workana.com/job/1",
        )
    )
    availability.record_verification(
        stored.id,
        is_open=True,
        observed_at=NOW - timedelta(hours=6),
        evidence_source="workana",
    )

    run = service.run(now=NOW)

    assert run.held.total_count == 0
    assert run.publishable.digest.count == 1
    assert run.publishable.digest.items[0].opportunity_id == stored.id


def test_stale_verified_open_returns_to_held_and_review(tmp_path) -> None:
    service, repository, availability = _services(tmp_path)
    stored, _ = repository.upsert(
        _opportunity(
            "linkedin-stale",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/stale",
        )
    )
    availability.record_verification(
        stored.id,
        is_open=True,
        observed_at=NOW - timedelta(days=8),
        evidence_source="official_company_page",
    )

    run = service.run(now=NOW)

    assert run.review.cards[0].opportunity_id == stored.id
    assert run.review.cards[0].suggested_action == "REVERIFY_CURRENT_SOURCE"
    assert run.held.items[0].opportunity_id == stored.id
    assert run.publishable.digest.count == 0


def test_publishable_selection_backfills_after_held_source_item(tmp_path) -> None:
    service, repository, availability = _services(tmp_path)
    held, _ = repository.upsert(
        _opportunity(
            "linkedin-held",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/held",
            published_at=NOW - timedelta(minutes=20),
        )
    )
    publishable, _ = repository.upsert(
        _opportunity(
            "linkedin-publishable",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/publishable",
            title="QGIS Mapping Specialist",
            published_at=NOW - timedelta(minutes=30),
        )
    )
    availability.record_verification(
        publishable.id,
        is_open=True,
        observed_at=NOW - timedelta(hours=1),
        evidence_source="official_company_page",
    )

    run = service.run(
        now=NOW,
        policy=DailyCurationPolicy(
            digest_policy=CommunityDigestPolicy(
                max_items=1,
                max_per_source=1,
            )
        ),
    )

    assert held.id in {
        item.opportunity_id for item in run.held.items
    }
    assert run.publishable.digest.count == 1
    assert run.publishable.digest.items[0].opportunity_id == publishable.id


def test_held_display_limit_does_not_weaken_publishable_exclusion(tmp_path) -> None:
    service, repository, _ = _services(tmp_path)
    for index in range(4):
        repository.upsert(
            _opportunity(
                f"linkedin-{index}",
                source="linkedin",
                source_url=f"https://linkedin.com/jobs/view/{index}",
            )
        )

    run = service.run(
        now=NOW,
        policy=DailyCurationPolicy(
            review_batch_size=2,
            held_items_limit=1,
        ),
    )

    assert run.held.total_count == 4
    assert run.held.shown_count == 1
    assert run.held.omitted_count == 3
    assert run.publishable.digest.count == 0


def test_daily_run_is_read_only(tmp_path) -> None:
    service, repository, availability = _services(tmp_path)
    stored, _ = repository.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )
    before = availability.list_observations(stored.id)

    run = service.run(now=NOW)

    after = availability.list_observations(stored.id)
    assert run.external_actions == []
    assert before == after == []


def test_daily_run_id_is_deterministic_for_same_snapshot(tmp_path) -> None:
    service, repository, _ = _services(tmp_path)
    repository.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )

    left = service.run(now=NOW)
    right = service.run(now=NOW)

    assert left.run_id == right.run_id
    assert left.model_dump() == right.model_dump()


def test_daily_run_uses_same_queue_order_for_review_prefix(tmp_path) -> None:
    service, repository, _ = _services(tmp_path)
    repository.upsert(
        _opportunity(
            "reddit",
            source="reddit",
            source_url="https://reddit.com/r/gis/comments/example",
        )
    )
    repository.upsert(
        _opportunity(
            "workana",
            source="workana",
            source_url="https://workana.com/job/1",
        )
    )
    repository.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )

    run = service.run(
        now=NOW,
        policy=DailyCurationPolicy(review_batch_size=2),
    )

    assert [
        card.opportunity_id for card in run.review.cards
    ] == [
        item.opportunity_id for item in run.held.items[:2]
    ]


def test_daily_run_propagates_digest_render_options(tmp_path) -> None:
    service, repository, _ = _services(tmp_path)
    repository.upsert(
        _opportunity(
            "greenhouse",
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/1",
        )
    )

    run = service.run(
        now=NOW,
        render_options=CommunityDigestRenderOptions(
            title="Curación diaria",
            format="markdown",
            include_intro=False,
            include_footer=False,
        ),
    )

    assert run.publishable.format == "markdown"
    assert run.publishable.rendered_text.startswith("# 🚀 Curación diaria")


def test_custom_queue_policy_controls_reverification_hold(tmp_path) -> None:
    service, repository, availability = _services(tmp_path)
    stored, _ = repository.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )
    availability.record_verification(
        stored.id,
        is_open=True,
        observed_at=NOW - timedelta(days=3),
        evidence_source="official_company_page",
    )

    default_run = service.run(now=NOW)
    strict_run = service.run(
        now=NOW,
        policy=DailyCurationPolicy(
            queue_policy=VerificationQueuePolicy(
                standard_reverify_after_days=2,
            ),
        ),
    )

    assert default_run.held.total_count == 0
    assert default_run.publishable.digest.count == 1
    assert strict_run.held.total_count == 1
    assert strict_run.publishable.digest.count == 0
