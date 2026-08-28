from datetime import datetime, timedelta, timezone

import pytest

from app.outreach.draft import build_draft_snapshot
from app.outreach.models import (
    ApprovalRecord,
    ContactResolution,
    DraftAttachment,
    OutreachEvent,
    OutreachPolicy,
    SendReceipt,
)
from app.outreach.repository import SQLiteOutreachRepository
from app.outreach.send import (
    SendGate,
    create_send_request,
    mark_send_attempted,
    record_send_failure,
    record_successful_send,
)

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _draft(*, body="Hello", basis="CREATED_EXACT", provider_id="draft-1"):
    return build_draft_snapshot(
        opportunity_id="opp-1",
        brief_sha256_value="a" * 64,
        application_packet_sha256="b" * 64,
        provider_draft_id=provider_id,
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
        id_factory=lambda: f"snapshot-{provider_id}",
    )


def _approval(draft, *, approval_id="approval-1", expires_at=None):
    return ApprovalRecord(
        approval_id=approval_id,
        opportunity_id="opp-1",
        draft_sha256=draft.draft_sha256,
        application_packet_sha256=draft.application_packet_sha256,
        approved_by="user",
        approval_scope="SINGLE",
        approved_at=NOW,
        expires_at=expires_at,
    )


def _contact():
    return ContactResolution(
        opportunity_id="opp-1",
        selected_candidate_id="published-1",
        channel="PUBLISHED_VACANCY_EMAIL",
        email="careers@example.test",
        organization="Example Labs",
        source_kind="VACANCY",
        source_ref="https://example.test/jobs/1",
        confidence=1.0,
        verification_status="VERIFIED_DIRECT",
        resolution_reason="published email",
        resolved_at=NOW,
        resolver_version="contact-v1",
    )


def _repo(tmp_path):
    repo = SQLiteOutreachRepository(tmp_path / "outreach.sqlite3")
    repo.initialize()
    return repo


def _seed_to_approved(repo, approval):
    chain = [
        "PACKET_ACCEPTED",
        "CONTACT_RESOLVED",
        "OUTREACH_READY",
        "DRAFT_CREATED",
        "APPROVED",
    ]
    for offset, event_type in enumerate(chain):
        repo.append_event(
            OutreachEvent(
                event_id=f"seed-{event_type.lower()}",
                opportunity_id="opp-1",
                event_type=event_type,
                entity_key=(approval.approval_id if event_type == "APPROVED" else None),
                occurred_at=NOW + timedelta(seconds=offset),
            )
        )


def _request(draft, approval, *, request_id="request-1"):
    return create_send_request(
        opportunity_id="opp-1",
        draft_sha256=draft.draft_sha256,
        approval_id=approval.approval_id,
        requested_by="user",
        now=NOW + timedelta(seconds=10),
        id_factory=lambda: request_id,
    )


def _register_request(repo, request):
    repo.save_send_request(request)
    repo.append_event(
        OutreachEvent(
            event_id=f"send-request:{request.request_id}",
            opportunity_id=request.opportunity_id,
            event_type="SEND_REQUESTED",
            entity_key=request.request_id,
            occurred_at=request.requested_at,
        )
    )


def _gate(repo, draft, approval, request):
    return SendGate().validate(
        draft_snapshot=draft,
        approval_record=approval,
        send_request=request,
        contact_resolution=_contact(),
        ledger=repo,
        policy=OutreachPolicy(),
        now=NOW + timedelta(seconds=20),
    )


def test_valid_approval_without_send_request_blocks(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft()
    approval = _approval(draft)
    result = _gate(repo, draft, approval, None)
    assert result.authorized is False
    assert result.error_code == "send_request_missing"


def test_send_request_for_different_draft_hash_blocks(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft()
    approval = _approval(draft)
    request = _request(draft, approval).model_copy(update={"draft_sha256": "f" * 64})
    result = _gate(repo, draft, approval, request)
    assert result.error_code == "send_request_invalid"


def test_send_request_for_different_approval_blocks(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft()
    approval = _approval(draft)
    request = _request(draft, approval).model_copy(update={"approval_id": "approval-other"})
    result = _gate(repo, draft, approval, request)
    assert result.error_code == "send_request_invalid"


def test_unverifiable_draft_blocks(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft(basis="UNVERIFIABLE")
    approval = _approval(draft)
    request = _request(draft, approval)
    result = _gate(repo, draft, approval, request)
    assert result.error_code == "draft_unverifiable"


def test_expired_approval_blocks(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft()
    approval = _approval(draft, expires_at=NOW + timedelta(seconds=5))
    request = _request(draft, approval)
    result = _gate(repo, draft, approval, request)
    assert result.error_code == "approval_expired"


@pytest.mark.parametrize(
    ("to", "cc", "bcc"),
    [
        (["careers@example.test", "other@example.test"], [], []),
        (["careers@example.test"], ["other@example.test"], []),
        (["careers@example.test"], [], ["other@example.test"]),
    ],
)
def test_send_gate_blocks_extra_unresolved_recipients(tmp_path, to, cc, bcc) -> None:
    repo = _repo(tmp_path)
    draft = build_draft_snapshot(
        opportunity_id="opp-1",
        brief_sha256_value="a" * 64,
        application_packet_sha256="b" * 64,
        provider_draft_id="draft-extra-recipient",
        to=to,
        cc=cc,
        bcc=bcc,
        subject="Application",
        body="Hello",
        attachments=[DraftAttachment(filename="cv.pdf", sha256="c" * 64, role="CV")],
        cv_sha256="c" * 64,
        content_type="text/plain",
        reply_message_id=None,
        verification_basis="CREATED_EXACT",
        now=NOW,
    )
    approval = _approval(draft)
    request = _request(draft, approval)
    result = _gate(repo, draft, approval, request)
    assert result.authorized is False
    assert result.error_code == "outreach_policy_blocked"


def test_already_sent_idempotency_key_blocks_second_send(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft()
    approval = _approval(draft)
    request = _request(draft, approval)
    first = _gate(repo, draft, approval, request)
    assert first.authorized is True and first.idempotency_key is not None
    repo.save_send_receipt(
        SendReceipt(
            receipt_id="receipt-existing",
            opportunity_id="opp-1",
            approval_id=approval.approval_id,
            send_request_id=request.request_id,
            draft_sha256=draft.draft_sha256,
            application_packet_sha256=draft.application_packet_sha256,
            idempotency_key=first.idempotency_key,
            provider_message_id="message-existing",
            recipient="careers@example.test",
            sent_at=NOW,
        )
    )
    second = _gate(repo, draft, approval, request)
    assert second.authorized is False
    assert second.error_code == "already_sent"


def test_valid_gate_returns_authorization_without_calling_provider(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft()
    approval = _approval(draft)
    request = _request(draft, approval)
    result = _gate(repo, draft, approval, request)
    assert result.authorized is True
    assert result.status == "AUTHORIZED"
    assert len(result.idempotency_key or "") == 64
    assert repo.get_send_receipt_by_idempotency_key(result.idempotency_key) is None


def test_failed_provider_attempt_is_not_sent(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft()
    approval = _approval(draft)
    _seed_to_approved(repo, approval)
    request = _request(draft, approval)
    _register_request(repo, request)
    authorization = _gate(repo, draft, approval, request)
    mark_send_attempted(
        authorization=authorization,
        send_request=request,
        ledger=repo,
        now=NOW + timedelta(seconds=30),
        id_factory=lambda: "attempt-1",
    )
    record_send_failure(
        authorization=authorization,
        send_request=request,
        ledger=repo,
        now=NOW + timedelta(seconds=31),
        id_factory=lambda: "failure-1",
    )
    assert repo.get_send_receipt_by_idempotency_key(authorization.idempotency_key) is None
    assert repo.list_events("opp-1")[-1].event_type == "SEND_FAILED"


def test_successful_provider_receipt_records_exactly_once(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft()
    approval = _approval(draft)
    _seed_to_approved(repo, approval)
    request = _request(draft, approval)
    _register_request(repo, request)
    authorization = _gate(repo, draft, approval, request)
    mark_send_attempted(
        authorization=authorization,
        send_request=request,
        ledger=repo,
        now=NOW + timedelta(seconds=30),
        id_factory=lambda: "attempt-1",
    )
    first = record_successful_send(
        authorization=authorization,
        approval=approval,
        send_request=request,
        draft_snapshot=draft,
        provider_message_id="message-1",
        provider_thread_id="thread-1",
        ledger=repo,
        now=NOW + timedelta(seconds=31),
        id_factory=lambda: "receipt-1",
    )
    second = record_successful_send(
        authorization=authorization,
        approval=approval,
        send_request=request,
        draft_snapshot=draft,
        provider_message_id="message-2",
        provider_thread_id="thread-2",
        ledger=repo,
        now=NOW + timedelta(seconds=32),
        id_factory=lambda: "receipt-2",
    )
    assert first.receipt_id == "receipt-1"
    assert second.receipt_id == "receipt-1"
    assert [event.event_type for event in repo.list_events("opp-1")].count("SENT") == 1


def test_changed_hash_cannot_bypass_one_initial_contact_per_opportunity(tmp_path) -> None:
    repo = _repo(tmp_path)
    first_draft = _draft(body="First")
    first_approval = _approval(first_draft)
    first_request = _request(first_draft, first_approval)
    first_auth = _gate(repo, first_draft, first_approval, first_request)
    assert first_auth.authorized is True and first_auth.idempotency_key is not None
    repo.save_send_receipt(
        SendReceipt(
            receipt_id="receipt-1",
            opportunity_id="opp-1",
            approval_id=first_approval.approval_id,
            send_request_id=first_request.request_id,
            draft_sha256=first_draft.draft_sha256,
            application_packet_sha256=first_draft.application_packet_sha256,
            idempotency_key=first_auth.idempotency_key,
            provider_message_id="message-1",
            recipient="careers@example.test",
            sent_at=NOW,
        )
    )

    changed_draft = _draft(body="Different body", provider_id="draft-2")
    changed_approval = _approval(changed_draft, approval_id="approval-2")
    changed_request = _request(changed_draft, changed_approval, request_id="request-2")
    second = _gate(repo, changed_draft, changed_approval, changed_request)
    assert changed_draft.draft_sha256 != first_draft.draft_sha256
    assert second.authorized is False
    assert second.error_code == "already_sent"


def test_success_requires_nonempty_provider_message_id(tmp_path) -> None:
    repo = _repo(tmp_path)
    draft = _draft()
    approval = _approval(draft)
    _seed_to_approved(repo, approval)
    request = _request(draft, approval)
    _register_request(repo, request)
    authorization = _gate(repo, draft, approval, request)
    mark_send_attempted(
        authorization=authorization,
        send_request=request,
        ledger=repo,
        now=NOW + timedelta(seconds=30),
        id_factory=lambda: "attempt-1",
    )
    with pytest.raises(ValueError, match="provider message"):
        record_successful_send(
            authorization=authorization,
            approval=approval,
            send_request=request,
            draft_snapshot=draft,
            provider_message_id="",
            provider_thread_id=None,
            ledger=repo,
            now=NOW + timedelta(seconds=31),
        )
