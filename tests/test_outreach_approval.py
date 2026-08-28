from datetime import datetime, timedelta, timezone

import pytest

from app.outreach.approval import ApprovalService, is_active, revoke
from app.outreach.draft import build_draft_snapshot
from app.outreach.hashing import batch_manifest_sha256
from app.outreach.models import ApprovalRequest, DraftAttachment, OutreachEvent
from app.outreach.repository import SQLiteOutreachRepository

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _repo(tmp_path) -> SQLiteOutreachRepository:
    repo = SQLiteOutreachRepository(tmp_path / "outreach.sqlite3")
    repo.initialize()
    for offset, event_type in enumerate(
        ["PACKET_ACCEPTED", "CONTACT_RESOLVED", "OUTREACH_READY", "DRAFT_CREATED"]
    ):
        repo.append_event(
            OutreachEvent(
                event_id=f"event-{offset}",
                opportunity_id="opp-1",
                event_type=event_type,
                occurred_at=NOW + timedelta(seconds=offset),
            )
        )
    return repo


def _draft(*, basis="CREATED_EXACT", body="Hello"):
    return build_draft_snapshot(
        opportunity_id="opp-1",
        brief_sha256_value="a" * 64,
        application_packet_sha256="b" * 64,
        provider_draft_id="draft-1",
        to=["careers@example.test"],
        cc=[],
        bcc=[],
        subject="Application",
        body=body,
        attachments=[DraftAttachment(filename="cv.pdf", sha256="c" * 64, role="CV")],
        cv_sha256="c" * 64,
        content_type="text/plain",
        reply_message_id=None,
        verification_basis=basis,
        now=NOW,
        id_factory=lambda: "snapshot-1",
    )


def test_single_approval_binds_exact_draft_hash(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft()
    request = ApprovalRequest(
        requested_by="user",
        approval_scope="SINGLE",
        draft_sha256=draft.draft_sha256,
    )
    record = ApprovalService(id_factory=lambda: "approval-1").approve(
        draft_snapshot=draft,
        approval_request=request,
        ledger=repo,
        now=NOW + timedelta(seconds=10),
    )
    assert record.draft_sha256 == draft.draft_sha256
    assert record.application_packet_sha256 == draft.application_packet_sha256
    assert repo.get_active_approval(draft.draft_sha256, NOW + timedelta(seconds=11)) is not None


def test_batch_approval_requires_exact_manifest(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft()
    hashes = [draft.draft_sha256, "d" * 64]
    request = ApprovalRequest(
        requested_by="user",
        approval_scope="BATCH",
        draft_sha256=draft.draft_sha256,
        draft_sha256s=hashes,
        batch_manifest_sha256=batch_manifest_sha256(hashes),
    )
    record = ApprovalService(id_factory=lambda: "approval-1").approve(
        draft_snapshot=draft,
        approval_request=request,
        ledger=repo,
        now=NOW + timedelta(seconds=10),
    )
    assert record.batch_manifest_sha256 == batch_manifest_sha256(hashes)

    bad_request = request.model_copy(update={"batch_manifest_sha256": "f" * 64})
    with pytest.raises(ValueError, match="batch manifest"):
        ApprovalService(id_factory=lambda: "approval-2").approve(
            draft_snapshot=draft,
            approval_request=bad_request,
            ledger=repo,
            now=NOW + timedelta(seconds=11),
        )


def test_changed_draft_has_no_active_approval(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft()
    request = ApprovalRequest(
        requested_by="user",
        approval_scope="SINGLE",
        draft_sha256=draft.draft_sha256,
    )
    ApprovalService(id_factory=lambda: "approval-1").approve(
        draft_snapshot=draft,
        approval_request=request,
        ledger=repo,
        now=NOW + timedelta(seconds=10),
    )
    changed = _draft(body="Changed")
    assert changed.draft_sha256 != draft.draft_sha256
    assert repo.get_active_approval(changed.draft_sha256, NOW + timedelta(seconds=11)) is None


def test_revoked_approval_blocks(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft()
    request = ApprovalRequest(
        requested_by="user",
        approval_scope="SINGLE",
        draft_sha256=draft.draft_sha256,
    )
    record = ApprovalService(id_factory=lambda: "approval-1").approve(
        draft_snapshot=draft,
        approval_request=request,
        ledger=repo,
        now=NOW + timedelta(seconds=10),
    )
    revoked = revoke(record, revoked_at=NOW + timedelta(seconds=20))
    assert is_active(revoked, now=NOW + timedelta(seconds=21)) is False


def test_expired_approval_blocks(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft()
    request = ApprovalRequest(
        requested_by="user",
        approval_scope="SINGLE",
        draft_sha256=draft.draft_sha256,
        expires_at=NOW + timedelta(minutes=5),
    )
    record = ApprovalService(id_factory=lambda: "approval-1").approve(
        draft_snapshot=draft,
        approval_request=request,
        ledger=repo,
        now=NOW + timedelta(seconds=10),
    )
    assert is_active(record, now=NOW + timedelta(minutes=6)) is False


def test_approval_never_creates_send_request(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft()
    request = ApprovalRequest(
        requested_by="user",
        approval_scope="SINGLE",
        draft_sha256=draft.draft_sha256,
    )
    ApprovalService(id_factory=lambda: "approval-1").approve(
        draft_snapshot=draft,
        approval_request=request,
        ledger=repo,
        now=NOW + timedelta(seconds=10),
    )
    assert "SEND_REQUESTED" not in [event.event_type for event in repo.list_events("opp-1")]


def test_unverifiable_draft_cannot_be_approved(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft(basis="UNVERIFIABLE")
    request = ApprovalRequest(
        requested_by="user",
        approval_scope="SINGLE",
        draft_sha256=draft.draft_sha256,
    )
    with pytest.raises(ValueError, match="unverifiable"):
        ApprovalService().approve(
            draft_snapshot=draft,
            approval_request=request,
            ledger=repo,
            now=NOW + timedelta(seconds=10),
        )
