from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.availability.repository import SQLiteAvailabilityRepository
from app.availability.verification_queue import (
    VerificationQueuePolicy,
    VerificationQueueService,
)
from app.availability.verification_review_session import (
    VerificationReviewSessionPolicy,
    VerificationReviewSessionService,
)
from app.models.domain import Opportunity
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.source_catalog import load_source_catalog
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime(2026, 9, 18, 21, 0, tzinfo=timezone.utc)


def _service(tmp_path):
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()
    catalog = load_source_catalog(Path("config/source_catalog.yaml"))
    queue = VerificationQueueService(
        opportunity_repository=opportunities,
        availability_repository=availability,
        extractor=RuleBasedRequirementExtractor(source_catalog=catalog),
        source_catalog=catalog,
    )
    return (
        VerificationReviewSessionService(queue_service=queue),
        opportunities,
        availability,
    )


def _opportunity(
    item_id: str,
    *,
    source: str,
    source_url: str,
    description: str = "QGIS geospatial work",
    published_at: datetime | None = NOW - timedelta(hours=2),
) -> Opportunity:
    return Opportunity(
        id=item_id,
        source=source,
        source_id=item_id,
        source_url=source_url,
        company=f"Company {item_id}",
        title=f"GIS Analyst {item_id}",
        description=description,
        discovered_at=NOW - timedelta(hours=1),
        published_at=published_at,
        status="open",
        location="Remote",
    )


def test_session_projects_top_queue_items_into_review_cards(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
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

    session = service.build(
        now=NOW,
        policy=VerificationReviewSessionPolicy(batch_size=2),
    )

    assert session.count == 2
    assert [card.opportunity_id for card in session.cards] == [
        "reddit",
        "workana",
    ]
    assert session.cards[0].rank == 1
    assert session.cards[0].suggested_action == "FIND_OFFICIAL_SOURCE"
    assert session.cards[1].rank == 2
    assert session.cards[1].suggested_action == "VERIFY_CURRENT_SOURCE"


def test_discovery_only_card_requires_official_source_search(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "reddit",
            source="reddit",
            source_url="https://reddit.com/r/gis/comments/example",
        )
    )

    session = service.build(now=NOW)
    card = session.cards[0]

    assert card.checklist == [
        "LOCATE_OFFICIAL_SOURCE",
        "MATCH_ROLE_IDENTITY",
        "CONFIRM_APPLICATION_ACTIONABLE",
        "CAPTURE_EVIDENCE_URL",
    ]
    assert card.acceptable_evidence_kinds == [
        "OFFICIAL_COMPANY_PAGE",
        "DIRECT_ATS",
    ]


def test_fast_market_card_accepts_direct_platform_evidence(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "workana",
            source="workana",
            source_url="https://workana.com/job/1",
        )
    )

    card = service.build(now=NOW).cards[0]

    assert "DIRECT_PLATFORM" in card.acceptable_evidence_kinds
    assert "CONFIRM_LISTING_LOADS" in card.checklist
    assert "CONFIRM_APPLICATION_ACTIONABLE" in card.checklist


def test_near_deadline_card_adds_deadline_check(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "deadline",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/deadline",
            description="QGIS role. Deadline: 19/09/2026",
        )
    )

    card = service.build(now=NOW).cards[0]

    assert "CONFIRM_DEADLINE" in card.checklist
    assert card.application_deadline is not None


def test_stale_verification_card_requests_reverification(tmp_path) -> None:
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

    card = service.build(now=NOW).cards[0]

    assert card.suggested_action == "REVERIFY_CURRENT_SOURCE"
    assert "CONFIRM_STILL_OPEN" in card.checklist
    assert card.last_verified_at == NOW - timedelta(days=8)


def test_session_is_read_only(tmp_path) -> None:
    service, repository, availability = _service(tmp_path)
    stored, _ = repository.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )
    before = availability.list_observations(stored.id)

    session = service.build(now=NOW)

    after = availability.list_observations(stored.id)
    assert session.count == 1
    assert before == after == []
    assert all(card.external_actions == [] for card in session.cards)


def test_session_does_not_expose_confirm_endpoint_or_auto_evidence_payload(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )

    card = service.build(now=NOW).cards[0]
    payload = card.model_dump()

    assert card.verification_preview_endpoint.endswith("/preview")
    assert "confirm" not in card.verification_preview_endpoint
    assert "decision" not in payload
    assert "confirmed_by" not in payload
    assert "confirmed_at" not in payload


def test_batch_size_limits_work_session_without_reordering_queue(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    for index in range(8):
        repository.upsert(
            _opportunity(
                f"linkedin-{index}",
                source="linkedin",
                source_url=f"https://linkedin.com/jobs/view/{index}",
            )
        )

    session = service.build(
        now=NOW,
        policy=VerificationReviewSessionPolicy(batch_size=5),
    )

    assert session.count == 5
    assert [card.rank for card in session.cards] == [1, 2, 3, 4, 5]


def test_session_id_is_deterministic_for_same_snapshot(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )

    left = service.build(now=NOW)
    right = service.build(now=NOW)

    assert left.session_id == right.session_id
    assert left.model_dump() == right.model_dump()


def test_session_id_changes_when_review_snapshot_changes(tmp_path) -> None:
    service, repository, availability = _service(tmp_path)
    stored, _ = repository.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )
    before = service.build(now=NOW)

    availability.record_seen(
        stored.id,
        observed_at=NOW,
        evidence_source="linkedin",
        source_url=stored.source_url,
    )
    after = service.build(now=NOW)

    assert before.session_id != after.session_id
    assert before.cards[0].last_seen_at is None
    assert after.cards[0].last_seen_at == NOW


def test_custom_queue_policy_flows_into_session(tmp_path) -> None:
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
        observed_at=NOW - timedelta(days=3),
        evidence_source="official_company_page",
    )

    default_session = service.build(now=NOW)
    custom_session = service.build(
        now=NOW,
        policy=VerificationReviewSessionPolicy(
            batch_size=5,
            queue_policy=VerificationQueuePolicy(
                standard_reverify_after_days=2,
            ),
        ),
    )

    assert default_session.count == 0
    assert custom_session.count == 1


def test_invalid_batch_size_fails_closed() -> None:
    with pytest.raises(ValueError, match="batch_size must be within 1..20"):
        VerificationReviewSessionPolicy(batch_size=0)
