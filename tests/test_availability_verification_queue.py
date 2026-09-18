from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.availability.repository import SQLiteAvailabilityRepository
from app.models.domain import Opportunity
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.source_catalog import load_source_catalog
from app.availability.verification_queue import (
    VerificationQueuePolicy,
    VerificationQueueService,
)
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc)


def _service(tmp_path):
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()
    catalog = load_source_catalog(Path("config/source_catalog.yaml"))
    extractor = RuleBasedRequirementExtractor(source_catalog=catalog)
    return (
        VerificationQueueService(
            opportunity_repository=opportunities,
            availability_repository=availability,
            extractor=extractor,
            source_catalog=catalog,
        ),
        opportunities,
        availability,
    )


def _opportunity(
    item_id: str,
    *,
    source: str,
    source_url: str,
    title: str = "GIS Analyst",
    description: str = "QGIS geospatial work",
    published_at: datetime | None = NOW - timedelta(hours=2),
    status: str = "open",
) -> Opportunity:
    return Opportunity(
        id=item_id,
        source=source,
        source_id=item_id,
        source_url=source_url,
        company=f"Company {item_id}",
        title=title,
        description=description,
        discovered_at=NOW - timedelta(hours=1),
        published_at=published_at,
        status=status,
        location="Remote",
    )


def test_discovery_only_signal_is_highest_priority_and_requires_official_source(
    tmp_path,
) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "reddit",
            source="reddit",
            source_url="https://reddit.com/r/gis/comments/example",
        )
    )

    queue = service.build(now=NOW)

    assert queue.count == 1
    item = queue.items[0]
    assert item.priority_score == 100
    assert item.reason_codes == ["DISCOVERY_ONLY_NEEDS_OFFICIAL_SOURCE"]
    assert item.suggested_action == "FIND_OFFICIAL_SOURCE"


def test_fast_market_unverified_is_prioritized_above_regular_board(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
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
            source_url="https://linkedin.com/jobs/view/2",
        )
    )

    queue = service.build(now=NOW)

    assert [item.opportunity_id for item in queue.items] == [
        "workana",
        "linkedin",
    ]
    assert queue.items[0].priority_score == 90
    assert queue.items[1].priority_score == 80


def test_direct_official_source_not_requiring_verification_stays_out(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "greenhouse",
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/1",
        )
    )

    queue = service.build(now=NOW)

    assert queue.count == 0


def test_verified_closed_never_enters_review_queue(tmp_path) -> None:
    service, repository, availability = _service(tmp_path)
    stored, _ = repository.upsert(
        _opportunity(
            "closed",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/closed",
        )
    )
    availability.record_verification(
        stored.id,
        is_open=False,
        observed_at=NOW - timedelta(hours=1),
        evidence_source="official_company_page",
    )

    queue = service.build(now=NOW)

    assert queue.count == 0


def test_recent_verified_open_stays_out_until_reverification_window(tmp_path) -> None:
    service, repository, availability = _service(tmp_path)
    stored, _ = repository.upsert(
        _opportunity(
            "recent",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/recent",
        )
    )
    availability.record_verification(
        stored.id,
        is_open=True,
        observed_at=NOW - timedelta(days=2),
        evidence_source="official_company_page",
    )

    queue = service.build(now=NOW)

    assert queue.count == 0


def test_stale_verified_open_enters_reverification_queue(tmp_path) -> None:
    service, repository, availability = _service(tmp_path)
    stored, _ = repository.upsert(
        _opportunity(
            "stale",
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

    queue = service.build(now=NOW)

    assert queue.count == 1
    assert queue.items[0].reason_codes == ["VERIFICATION_STALE"]
    assert queue.items[0].suggested_action == "REVERIFY_CURRENT_SOURCE"
    assert queue.items[0].priority_score == 70


def test_fast_market_reverification_window_is_shorter(tmp_path) -> None:
    service, repository, availability = _service(tmp_path)
    stored, _ = repository.upsert(
        _opportunity(
            "fast-stale",
            source="workana",
            source_url="https://workana.com/job/fast-stale",
            published_at=NOW - timedelta(days=3),
        )
    )
    availability.record_verification(
        stored.id,
        is_open=True,
        observed_at=NOW - timedelta(days=3),
        evidence_source="workana",
    )

    queue = service.build(now=NOW)

    assert queue.count == 1
    assert queue.items[0].reason_codes == ["VERIFICATION_STALE"]


def test_old_fast_market_project_is_not_worth_verification_work(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "old-fast",
            source="workana",
            source_url="https://workana.com/job/old",
            published_at=NOW - timedelta(days=20),
        )
    )

    queue = service.build(now=NOW)

    assert queue.count == 0


def test_expired_deadline_is_not_queued(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "expired",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/expired",
            description="QGIS role. Deadline: 17/09/2026",
        )
    )

    queue = service.build(now=NOW)

    assert queue.count == 0


def test_near_deadline_unverified_gets_deadline_priority(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "deadline",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/deadline",
            description="QGIS role. Deadline: 19/09/2026",
        )
    )

    queue = service.build(now=NOW)

    assert queue.count == 1
    assert queue.items[0].priority_score == 95
    assert "DEADLINE_SOON_UNVERIFIED" in queue.items[0].reason_codes
    assert "SOURCE_REQUIRES_VERIFICATION" in queue.items[0].reason_codes


def test_queue_is_profile_independent_and_contains_no_personal_fit_fields(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "profile-free",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/profile-free",
        )
    )

    queue = service.build(now=NOW)
    payload = queue.model_dump()

    assert queue.count == 1
    assert "career_match" not in str(payload)
    assert "income_viability" not in str(payload)
    assert "tier" not in str(payload)


def test_queue_limit_never_promotes_non_reviewable_items(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    for index in range(3):
        repository.upsert(
            _opportunity(
                f"linkedin-{index}",
                source="linkedin",
                source_url=f"https://linkedin.com/jobs/view/{index}",
            )
        )
    repository.upsert(
        _opportunity(
            "official",
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/official",
        )
    )

    queue = service.build(
        now=NOW,
        policy=VerificationQueuePolicy(max_items=2),
    )

    assert queue.count == 2
    assert all(
        item.source_key == "linkedin"
        for item in queue.items
    )


def test_unknown_source_fails_conservatively_into_verification_queue(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "unknown",
            source="mystery-board",
            source_url="https://jobs.unknown.example/role/1",
        )
    )

    queue = service.build(now=NOW)

    assert queue.count == 1
    assert queue.items[0].source_key is None
    assert queue.items[0].reason_codes == ["SOURCE_REQUIRES_VERIFICATION"]
    assert queue.items[0].priority_score == 80


def test_direct_official_near_deadline_does_not_create_manual_review_work(
    tmp_path,
) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "official-deadline",
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/2",
            description="QGIS role. Deadline: 19/09/2026",
        )
    )

    queue = service.build(now=NOW)

    assert queue.count == 0
