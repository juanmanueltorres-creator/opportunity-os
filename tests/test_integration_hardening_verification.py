from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.availability.repository import SQLiteAvailabilityRepository
from app.availability.review_evidence_draft import (
    ReviewEvidenceDraftRequest,
    ReviewEvidenceDraftService,
)
from app.availability.verification_models import (
    VerificationConfirmRequest,
    VerificationEvidence,
)
from app.availability.verification_queue import VerificationQueueService
from app.availability.verification_review_session import (
    VerificationReviewSessionService,
)
from app.availability.verification_service import AvailabilityVerificationService
from app.models.domain import Opportunity
from app.radar.community_digest_preview import CommunityDigestPreviewService
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.source_catalog import load_source_catalog
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc)


def _opportunity(
    item_id: str,
    *,
    source: str = "workana",
    source_url: str | None = None,
    description: str = "QGIS geospatial work",
) -> Opportunity:
    return Opportunity(
        id=item_id,
        source=source,
        source_id=item_id,
        source_url=source_url or f"https://workana.com/job/{item_id}",
        company=f"Company {item_id}",
        title=f"GIS Analyst {item_id}",
        description=description,
        discovered_at=NOW - timedelta(hours=1),
        published_at=NOW - timedelta(hours=2),
        status="open",
        location="Remote",
        remote_policy="remote",
    )


def _repositories(tmp_path):
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()
    return opportunities, availability


def test_availability_get_many_projects_multiple_ids_in_bulk(tmp_path) -> None:
    _, availability = _repositories(tmp_path)
    availability.record_seen(
        "opp-1",
        observed_at=NOW - timedelta(hours=2),
        evidence_source="source-a",
    )
    availability.record_verification(
        "opp-2",
        is_open=False,
        observed_at=NOW - timedelta(hours=1),
        evidence_source="official",
    )

    states = availability.get_many(
        ["opp-1", "opp-2", "missing", "opp-1"]
    )

    assert set(states) == {"opp-1", "opp-2"}
    assert states["opp-1"].availability_state == "UNVERIFIED"
    assert states["opp-2"].availability_state == "VERIFIED_CLOSED"


def test_digest_preview_uses_bulk_availability_projection(
    tmp_path,
    monkeypatch,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    stored, _ = opportunities.upsert(_opportunity("bulk"))
    availability.record_seen(
        stored.id,
        observed_at=NOW,
        evidence_source="workana",
    )
    extractor = RuleBasedRequirementExtractor(
        source_catalog=load_source_catalog(Path("config/source_catalog.yaml"))
    )
    service = CommunityDigestPreviewService(
        opportunity_repository=opportunities,
        extractor=extractor,
        availability_repository=availability,
    )

    def fail_single_get(_: str):
        raise AssertionError("preview must not perform N availability get calls")

    monkeypatch.setattr(availability, "get", fail_single_get)

    preview = service.preview(now=NOW)

    assert preview.candidate_count == 1


@pytest.mark.parametrize(
    "source_url",
    ["https://", "https://not a url", "file:///tmp/fake"],
)
def test_verification_evidence_rejects_incomplete_http_urls(
    source_url: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="source_url must use http or https",
    ):
        VerificationEvidence(
            opportunity_id="opp-1",
            decision="OPEN",
            observed_at=NOW,
            evidence_kind="OFFICIAL_COMPANY_PAGE",
            evidence_source="manual.review",
            source_url=source_url,
        )


def test_confirmation_receipt_reports_post_append_projected_state(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    opportunities.upsert(
        _opportunity(
            "opp-1",
            source="manual",
            source_url="https://company.example/jobs/opp-1",
        )
    )
    availability.record_verification(
        "opp-1",
        is_open=False,
        observed_at=NOW,
        evidence_source="official.newer",
        source_url="https://company.example/jobs/opp-1",
    )
    service = AvailabilityVerificationService(
        opportunity_repository=opportunities,
        availability_repository=availability,
    )
    older_open = VerificationEvidence(
        opportunity_id="opp-1",
        decision="OPEN",
        observed_at=NOW - timedelta(days=1),
        evidence_kind="OFFICIAL_COMPANY_PAGE",
        evidence_source="official.older",
        source_url="https://company.example/jobs/opp-1",
    )
    preview = service.preview(older_open)

    result = service.confirm(
        VerificationConfirmRequest(
            evidence=older_open,
            preview_sha256=preview.preview_sha256,
            confirmed_by="operator",
            confirmed_at=NOW + timedelta(minutes=1),
        ),
        processed_at=NOW + timedelta(minutes=1),
    )

    assert result.status == "RECORDED"
    assert result.receipt is not None
    assert result.receipt.resulting_state == "VERIFIED_CLOSED"
    assert availability.get("opp-1").availability_state == "VERIFIED_CLOSED"


def test_deadline_bearing_fast_market_item_keeps_fast_market_reason(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    opportunities.upsert(
        _opportunity(
            "deadline-market",
            source="workana",
            source_url="https://workana.com/job/deadline-market",
            description="QGIS mapping. Deadline: 19/09/2026",
        )
    )
    catalog = load_source_catalog(Path("config/source_catalog.yaml"))
    queue = VerificationQueueService(
        opportunity_repository=opportunities,
        availability_repository=availability,
        extractor=RuleBasedRequirementExtractor(source_catalog=catalog),
        source_catalog=catalog,
    )

    result = queue.build(now=NOW)

    item = next(
        item
        for item in result.items
        if item.opportunity_id == "deadline-market"
    )
    assert item.freshness_policy == "deadline_sensitive"
    assert "FAST_MARKET_UNVERIFIED" in item.reason_codes


def test_review_card_signature_blocks_client_side_policy_tampering(
    tmp_path,
) -> None:
    opportunities, availability = _repositories(tmp_path)
    opportunities.upsert(
        _opportunity(
            "reddit",
            source="reddit",
            source_url="https://reddit.com/r/gis/comments/example",
        )
    )
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
    card = review.build(now=NOW).cards[0]
    tampered = card.model_copy(
        update={
            "title": "Different role",
            "acceptable_evidence_kinds": ["DIRECT_PLATFORM"],
        }
    )

    result = draft.build(
        ReviewEvidenceDraftRequest(
            card=tampered,
            decision="OPEN",
            observed_at=NOW,
            evidence_kind="DIRECT_PLATFORM",
            evidence_source="operator.review",
            source_url="https://reddit.com/r/gis/comments/example",
        ),
        now=NOW,
    )

    assert result.status == "BLOCKED_STALE_CARD"
    assert result.errors == ["review_card_hash_mismatch"]
