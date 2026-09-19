from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.availability.repository import SQLiteAvailabilityRepository
from app.availability.review_evidence_draft import (
    ReviewEvidenceDraftRequest,
    ReviewEvidenceDraftService,
)
from app.availability.verification_queue import VerificationQueueService
from app.availability.verification_review_session import (
    VerificationReviewSessionService,
)
from app.availability.verification_service import AvailabilityVerificationService
from app.models.domain import Opportunity
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.source_catalog import load_source_catalog
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime(2026, 9, 18, 22, 0, tzinfo=timezone.utc)


def _services(tmp_path):
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
    review = VerificationReviewSessionService(queue_service=queue)
    verification = AvailabilityVerificationService(
        opportunity_repository=opportunities,
        availability_repository=availability,
    )
    draft = ReviewEvidenceDraftService(
        opportunity_repository=opportunities,
        availability_repository=availability,
        verification_service=verification,
    )
    return draft, review, opportunities, availability


def _opportunity(
    item_id: str,
    *,
    source: str = "linkedin",
    source_url: str | None = None,
) -> Opportunity:
    return Opportunity(
        id=item_id,
        source=source,
        source_id=item_id,
        source_url=source_url or f"https://linkedin.com/jobs/view/{item_id}",
        company=f"Company {item_id}",
        title=f"GIS Analyst {item_id}",
        description="QGIS geospatial work",
        discovered_at=NOW - timedelta(hours=1),
        published_at=NOW - timedelta(hours=2),
        status="open",
        location="Remote",
    )


def _card(review, *, now=NOW):
    session = review.build(now=now)
    assert session.cards
    return session.cards[0]


def test_draft_builds_verification_evidence_and_preview_without_writing(tmp_path) -> None:
    draft, review, opportunities, availability = _services(tmp_path)
    stored, _ = opportunities.upsert(_opportunity("linkedin"))
    card = _card(review)
    before = availability.list_observations(stored.id)

    result = draft.build(
        ReviewEvidenceDraftRequest(
            card=card,
            decision="OPEN",
            observed_at=NOW - timedelta(minutes=5),
            evidence_kind="OFFICIAL_COMPANY_PAGE",
            evidence_source="careers.example.com",
            source_url="https://careers.example.com/jobs/linkedin",
            note="Application form visible",
        ),
        now=NOW,
    )

    after = availability.list_observations(stored.id)
    assert result.status == "READY"
    assert result.evidence is not None
    assert result.evidence.decision == "OPEN"
    assert result.evidence.source_url == (
        "https://careers.example.com/jobs/linkedin"
    )
    assert result.verification_preview is not None
    assert result.verification_preview.status == "READY"
    assert result.verification_preview.proposed_state == "VERIFIED_OPEN"
    assert before == after == []
    assert result.external_actions == []


def test_draft_never_infers_decision_from_review_card(tmp_path) -> None:
    draft, review, opportunities, _ = _services(tmp_path)
    opportunities.upsert(_opportunity("linkedin"))
    card = _card(review)

    result = draft.build(
        ReviewEvidenceDraftRequest(
            card=card,
            decision="CLOSED",
            observed_at=NOW - timedelta(minutes=5),
            evidence_kind="MANUAL_REVIEW",
            evidence_source="operator.review",
            source_url="https://linkedin.com/jobs/view/linkedin",
            note="Listing says applications are closed",
        ),
        now=NOW,
    )

    assert result.status == "READY"
    assert result.evidence is not None
    assert result.evidence.decision == "CLOSED"
    assert result.verification_preview is not None
    assert result.verification_preview.proposed_state == "VERIFIED_CLOSED"


def test_discovery_only_card_rejects_direct_platform_evidence(tmp_path) -> None:
    draft, review, opportunities, availability = _services(tmp_path)
    opportunities.upsert(
        _opportunity(
            "reddit",
            source="reddit",
            source_url="https://reddit.com/r/gis/comments/example",
        )
    )
    card = _card(review)

    result = draft.build(
        ReviewEvidenceDraftRequest(
            card=card,
            decision="OPEN",
            observed_at=NOW - timedelta(minutes=5),
            evidence_kind="DIRECT_PLATFORM",
            evidence_source="reddit",
            source_url="https://reddit.com/r/gis/comments/example",
        ),
        now=NOW,
    )

    assert result.status == "BLOCKED_EVIDENCE_KIND"
    assert result.errors == ["evidence_kind_not_allowed_for_review_card"]
    assert result.evidence is None
    assert result.verification_preview is None
    assert availability.list_observations("reddit") == []


def test_discovery_only_card_accepts_official_source_found_during_review(
    tmp_path,
) -> None:
    draft, review, opportunities, _ = _services(tmp_path)
    opportunities.upsert(
        _opportunity(
            "reddit",
            source="reddit",
            source_url="https://reddit.com/r/gis/comments/example",
        )
    )
    card = _card(review)

    result = draft.build(
        ReviewEvidenceDraftRequest(
            card=card,
            decision="OPEN",
            observed_at=NOW - timedelta(minutes=5),
            evidence_kind="OFFICIAL_COMPANY_PAGE",
            evidence_source="company.example",
            source_url="https://company.example/careers/gis",
        ),
        now=NOW,
    )

    assert result.status == "READY"
    assert result.evidence is not None
    assert result.evidence.source_url == "https://company.example/careers/gis"


def test_availability_change_after_review_blocks_stale_card(tmp_path) -> None:
    draft, review, opportunities, availability = _services(tmp_path)
    stored, _ = opportunities.upsert(_opportunity("linkedin"))
    card = _card(review)
    availability.record_seen(
        stored.id,
        observed_at=NOW - timedelta(minutes=1),
        evidence_source="linkedin",
        source_url=stored.source_url,
    )

    result = draft.build(
        ReviewEvidenceDraftRequest(
            card=card,
            decision="OPEN",
            observed_at=NOW - timedelta(minutes=2),
            evidence_kind="MANUAL_REVIEW",
            evidence_source="operator.review",
            source_url=stored.source_url,
        ),
        now=NOW,
    )

    assert result.status == "BLOCKED_STALE_CARD"
    assert result.errors == ["review_card_availability_changed"]


def test_tampered_review_card_hash_is_rejected(tmp_path) -> None:
    draft, review, opportunities, _ = _services(tmp_path)
    opportunities.upsert(
        _opportunity(
            "reddit",
            source="reddit",
            source_url="https://reddit.com/r/gis/comments/example",
        )
    )
    original = _card(review)
    tampered = original.model_copy(
        update={
            "acceptable_evidence_kinds": [
                *original.acceptable_evidence_kinds,
                "DIRECT_PLATFORM",
            ]
        }
    )

    result = draft.build(
        ReviewEvidenceDraftRequest(
            card=tampered,
            decision="OPEN",
            observed_at=NOW - timedelta(minutes=5),
            evidence_kind="DIRECT_PLATFORM",
            evidence_source="reddit",
            source_url="https://reddit.com/r/gis/comments/example",
        ),
        now=NOW,
    )

    assert result.status == "BLOCKED_STALE_CARD"
    assert result.errors == ["review_card_hash_mismatch"]


def test_future_observation_is_blocked_without_preview(tmp_path) -> None:
    draft, review, opportunities, _ = _services(tmp_path)
    opportunities.upsert(_opportunity("linkedin"))
    card = _card(review)

    result = draft.build(
        ReviewEvidenceDraftRequest(
            card=card,
            decision="OPEN",
            observed_at=NOW + timedelta(minutes=1),
            evidence_kind="MANUAL_REVIEW",
            evidence_source="operator.review",
            source_url="https://linkedin.com/jobs/view/linkedin",
        ),
        now=NOW,
    )

    assert result.status == "BLOCKED_FUTURE_OBSERVATION"
    assert result.errors == ["evidence_observed_at_in_future"]
    assert result.verification_preview is None


def test_missing_opportunity_is_blocked(tmp_path) -> None:
    draft, review, opportunities, _ = _services(tmp_path)
    stored, _ = opportunities.upsert(_opportunity("linkedin"))
    card = _card(review)
    with opportunities._connect() as conn:
        conn.execute("DELETE FROM opportunities WHERE id = ?", (stored.id,))

    result = draft.build(
        ReviewEvidenceDraftRequest(
            card=card,
            decision="OPEN",
            observed_at=NOW - timedelta(minutes=5),
            evidence_kind="MANUAL_REVIEW",
            evidence_source="operator.review",
            source_url=stored.source_url,
        ),
        now=NOW,
    )

    assert result.status == "BLOCKED_NOT_FOUND"
    assert result.errors == ["opportunity_not_found"]


def test_draft_id_is_deterministic_for_same_card_evidence_and_preview(tmp_path) -> None:
    draft, review, opportunities, _ = _services(tmp_path)
    opportunities.upsert(_opportunity("linkedin"))
    card = _card(review)
    request = ReviewEvidenceDraftRequest(
        card=card,
        decision="OPEN",
        observed_at=NOW - timedelta(minutes=5),
        evidence_kind="MANUAL_REVIEW",
        evidence_source="operator.review",
        source_url="https://linkedin.com/jobs/view/linkedin",
        note="Still accepting applications",
    )

    left = draft.build(request, now=NOW)
    right = draft.build(request, now=NOW)

    assert left.status == right.status == "READY"
    assert left.draft_id == right.draft_id
    assert left.model_dump() == right.model_dump()


def test_review_card_hash_binds_displayed_role_identity(tmp_path) -> None:
    draft, review, opportunities, _ = _services(tmp_path)
    opportunities.upsert(_opportunity("linkedin"))
    original = _card(review)
    tampered = original.model_copy(update={"title": "Different role"})

    result = draft.build(
        ReviewEvidenceDraftRequest(
            card=tampered,
            decision="OPEN",
            observed_at=NOW - timedelta(minutes=5),
            evidence_kind="MANUAL_REVIEW",
            evidence_source="operator.review",
            source_url=original.review_url,
        ),
        now=NOW,
    )

    assert result.status == "BLOCKED_STALE_CARD"
    assert result.errors == ["review_card_hash_mismatch"]


def test_evidence_draft_rejects_http_url_without_valid_host() -> None:
    import pytest

    with pytest.raises(
        ValueError,
        match="source_url must use http or https with a valid host",
    ):
        ReviewEvidenceDraftRequest(
            card=_dummy_card_for_url_validation(),
            decision="OPEN",
            observed_at=NOW,
            evidence_kind="MANUAL_REVIEW",
            evidence_source="operator.review",
            source_url="https://not a url",
        )


def _dummy_card_for_url_validation():
    from app.availability.verification_review_session import VerificationReviewCard

    return VerificationReviewCard(
        rank=1,
        card_sha256="0" * 64,
        opportunity_id="url-check",
        title="GIS Analyst",
        company="Example",
        review_url="https://example.com/job",
        availability_state="UNVERIFIED",
        priority_score=80,
        reason_codes=["SOURCE_REQUIRES_VERIFICATION"],
        suggested_action="VERIFY_CURRENT_SOURCE",
        checklist=["CONFIRM_LISTING_LOADS"],
        acceptable_evidence_kinds=["MANUAL_REVIEW"],
        external_actions=[],
    )
