from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.outreach.hashing import batch_manifest_sha256, draft_sha256
from app.outreach.models import (
    ApprovalRecord,
    ContactResolution,
    DraftAttachment,
    DraftSnapshot,
    OutreachEvent,
    OutreachPreparationResult,
    SendAuthorizationResult,
)

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _draft(
    provider_draft_id: str,
    *,
    created_at: datetime = NOW,
    filename: str = "Alex_Example_CV.pdf",
    recipient: str = "careers@example.test",
    subject: str = "Application — GIS Developer",
) -> DraftSnapshot:
    return DraftSnapshot(
        draft_snapshot_id="snap-1",
        opportunity_id="opp-1",
        brief_sha256="a" * 64,
        application_packet_sha256="b" * 64,
        provider="gmail",
        provider_draft_id=provider_draft_id,
        to=[recipient],
        subject=subject,
        body_canonical="Hello\n\nAttached is my CV.",
        attachments=[
            DraftAttachment(filename=filename, sha256="c" * 64, role="CV")
        ],
        cv_sha256="c" * 64,
        content_type="text/plain",
        verification_basis="CREATED_EXACT",
        created_at=created_at,
        verified_at=created_at,
        draft_sha256="0" * 64,
    )


def test_provider_id_and_time_do_not_change_semantic_draft_hash() -> None:
    left = _draft("draft-a")
    right = _draft("draft-b", created_at=NOW + timedelta(minutes=5))
    assert draft_sha256(left) == draft_sha256(right)


def test_attachment_filename_changes_semantic_draft_hash() -> None:
    left = _draft("draft-a", filename="Alex_Example_CV.pdf")
    right = _draft("draft-a", filename="wrong-name.pdf")
    assert draft_sha256(left) != draft_sha256(right)


def test_recipient_changes_semantic_draft_hash() -> None:
    left = _draft("draft-a", recipient="careers@example.test")
    right = _draft("draft-a", recipient="talent@example.test")
    assert draft_sha256(left) != draft_sha256(right)


def test_actionable_email_resolution_cannot_be_unverified() -> None:
    with pytest.raises(ValueError, match="actionable email"):
        ContactResolution(
            opportunity_id="opp-1",
            channel="PUBLISHED_VACANCY_EMAIL",
            email="careers@example.test",
            organization="Example Labs",
            source_kind="VACANCY",
            source_ref="https://example.test/jobs/1",
            confidence=1.0,
            verification_status="UNVERIFIED",
            resolution_reason="fixture",
            resolved_at=NOW,
            resolver_version="contact-v1",
        )


def test_batch_manifest_is_order_independent_and_deduplicated() -> None:
    left = batch_manifest_sha256(["b" * 64, "a" * 64, "a" * 64])
    right = batch_manifest_sha256(["a" * 64, "b" * 64])
    assert left == right


def test_draft_requires_exactly_one_matching_cv_attachment() -> None:
    with pytest.raises(ValueError, match="exactly one CV"):
        DraftSnapshot(
            draft_snapshot_id="snap-1",
            opportunity_id="opp-1",
            brief_sha256="a" * 64,
            application_packet_sha256="b" * 64,
            provider_draft_id="draft-a",
            to=["careers@example.test"],
            subject="Application",
            body_canonical="Hello",
            attachments=[
                DraftAttachment(filename="notes.txt", sha256="d" * 64, role="OTHER")
            ],
            cv_sha256="c" * 64,
            content_type="text/plain",
            verification_basis="CREATED_EXACT",
            draft_sha256="0" * 64,
            created_at=NOW,
            verified_at=NOW,
        )

    with pytest.raises(ValueError, match="CV attachment hash"):
        DraftSnapshot(
            draft_snapshot_id="snap-1",
            opportunity_id="opp-1",
            brief_sha256="a" * 64,
            application_packet_sha256="b" * 64,
            provider_draft_id="draft-a",
            to=["careers@example.test"],
            subject="Application",
            body_canonical="Hello",
            attachments=[
                DraftAttachment(filename="cv.pdf", sha256="d" * 64, role="CV")
            ],
            cv_sha256="c" * 64,
            content_type="text/plain",
            verification_basis="CREATED_EXACT",
            draft_sha256="0" * 64,
            created_at=NOW,
            verified_at=NOW,
        )


def test_outreach_models_reject_naive_timestamps_and_extra_fields() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        OutreachEvent(
            event_id="event-1",
            opportunity_id="opp-1",
            event_type="PACKET_ACCEPTED",
            occurred_at=datetime(2026, 8, 28, 12, 0),
        )

    with pytest.raises(ValidationError):
        DraftAttachment(
            filename="cv.pdf",
            sha256="c" * 64,
            role="CV",
            unknown="forbidden",
        )


def test_batch_approval_requires_manifest_and_single_forbids_it() -> None:
    common = dict(
        approval_id="approval-1",
        opportunity_id="opp-1",
        draft_sha256="d" * 64,
        application_packet_sha256="p" * 64,
        approved_by="user",
        approved_at=NOW,
    )
    with pytest.raises(ValueError, match="batch approval"):
        ApprovalRecord(approval_scope="BATCH", **common)

    with pytest.raises(ValueError, match="single approval"):
        ApprovalRecord(
            approval_scope="SINGLE",
            batch_manifest_sha256="m" * 64,
            **common,
        )


def test_outreach_preparation_and_send_authorization_states_are_consistent() -> None:
    with pytest.raises(ValueError, match="OUTREACH_READY requires brief"):
        OutreachPreparationResult(status="OUTREACH_READY")

    with pytest.raises(ValueError, match="idempotency key"):
        SendAuthorizationResult(status="AUTHORIZED", authorized=True)

    blocked = SendAuthorizationResult(
        status="BLOCKED",
        authorized=False,
        error_code="approval_missing",
    )
    assert blocked.error_code == "approval_missing"
