from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from app.outreach.approval import is_active
from app.outreach.hashing import draft_sha256, send_idempotency_key
from app.outreach.models import (
    ApprovalRecord,
    ContactResolution,
    DraftSnapshot,
    OutreachEvent,
    OutreachPolicy,
    SendAuthorizationResult,
    SendReceipt,
    SendRequest,
)
from app.outreach.repository import SQLiteOutreachRepository


class SendGate:
    def validate(
        self,
        *,
        draft_snapshot: DraftSnapshot,
        approval_record: ApprovalRecord | None,
        send_request: SendRequest | None,
        contact_resolution: ContactResolution,
        ledger: SQLiteOutreachRepository,
        policy: OutreachPolicy,
        now: datetime,
    ) -> SendAuthorizationResult:
        now_utc = _require_aware(now)

        if send_request is None:
            return _blocked("send_request_missing")
        if approval_record is None:
            return _blocked("approval_missing")

        if (
            send_request.opportunity_id != draft_snapshot.opportunity_id
            or send_request.draft_sha256 != draft_snapshot.draft_sha256
            or send_request.approval_id != approval_record.approval_id
            or approval_record.opportunity_id != draft_snapshot.opportunity_id
        ):
            return _blocked("send_request_invalid")

        if approval_record.status == "EXPIRED":
            return _blocked("approval_expired")
        if approval_record.expires_at is not None and approval_record.expires_at <= now_utc:
            return _blocked("approval_expired")
        if not is_active(approval_record, now=now_utc):
            return _blocked("approval_invalid")
        if (
            approval_record.draft_sha256 != draft_snapshot.draft_sha256
            or approval_record.application_packet_sha256
            != draft_snapshot.application_packet_sha256
        ):
            return _blocked("approval_invalid")
        if approval_record.approval_scope == "BATCH":
            if send_request.batch_manifest_sha256 != approval_record.batch_manifest_sha256:
                return _blocked("send_request_invalid")

        if draft_sha256(draft_snapshot) != draft_snapshot.draft_sha256:
            return _blocked("draft_changed")
        if draft_snapshot.verification_basis == "UNVERIFIABLE":
            return _blocked("draft_unverifiable")

        if (
            contact_resolution.opportunity_id != draft_snapshot.opportunity_id
            or contact_resolution.email is None
            or not draft_snapshot.to
            or draft_snapshot.to[0].casefold().strip()
            != contact_resolution.email.casefold().strip()
        ):
            return _blocked("outreach_policy_blocked")

        cv_attachments = [
            attachment
            for attachment in draft_snapshot.attachments
            if attachment.role == "CV"
        ]
        if (
            len(cv_attachments) != 1
            or cv_attachments[0].sha256 != draft_snapshot.cv_sha256
        ):
            return _blocked("draft_changed")

        if ledger.has_successful_send_for_opportunity(draft_snapshot.opportunity_id):
            return _blocked("already_sent")

        key = send_idempotency_key(
            opportunity_id=draft_snapshot.opportunity_id,
            primary_recipient=draft_snapshot.to[0],
            packet_sha256=draft_snapshot.application_packet_sha256,
            draft_hash=draft_snapshot.draft_sha256,
        )
        if ledger.get_send_receipt_by_idempotency_key(key) is not None:
            return _blocked("already_sent")

        return SendAuthorizationResult(
            status="AUTHORIZED",
            authorized=True,
            idempotency_key=key,
        )


def create_send_request(
    *,
    opportunity_id: str,
    draft_sha256: str,
    approval_id: str,
    requested_by: str,
    now: datetime,
    batch_manifest_sha256: str | None = None,
    id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> SendRequest:
    return SendRequest(
        request_id=id_factory(),
        opportunity_id=opportunity_id,
        draft_sha256=draft_sha256,
        requested_by=requested_by,
        requested_at=_require_aware(now),
        approval_id=approval_id,
        batch_manifest_sha256=batch_manifest_sha256,
    )


def mark_send_attempted(
    *,
    authorization: SendAuthorizationResult,
    send_request: SendRequest,
    ledger: SQLiteOutreachRepository,
    now: datetime,
    id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> OutreachEvent:
    if not authorization.authorized or authorization.idempotency_key is None:
        raise ValueError("send attempt requires authorization")
    event = OutreachEvent(
        event_id=id_factory(),
        opportunity_id=send_request.opportunity_id,
        event_type="SEND_ATTEMPTED",
        entity_key=authorization.idempotency_key,
        occurred_at=_require_aware(now),
    )
    return ledger.append_event(event)


def record_successful_send(
    *,
    authorization: SendAuthorizationResult,
    approval: ApprovalRecord,
    send_request: SendRequest,
    draft_snapshot: DraftSnapshot,
    provider_message_id: str,
    provider_thread_id: str | None,
    ledger: SQLiteOutreachRepository,
    now: datetime,
    id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> SendReceipt:
    if not authorization.authorized or authorization.idempotency_key is None:
        raise ValueError("successful send requires authorization")
    existing = ledger.get_send_receipt_by_idempotency_key(
        authorization.idempotency_key
    )
    if existing is not None:
        return existing
    if not provider_message_id.strip():
        raise ValueError("provider message id is required")
    if send_request.approval_id != approval.approval_id:
        raise ValueError("send request approval mismatch")
    if send_request.draft_sha256 != draft_snapshot.draft_sha256:
        raise ValueError("send request draft mismatch")

    attempt_exists = any(
        event.event_type == "SEND_ATTEMPTED"
        and event.entity_key == authorization.idempotency_key
        for event in ledger.list_events(send_request.opportunity_id)
    )
    if not attempt_exists:
        raise ValueError("successful send requires matching SEND_ATTEMPTED event")

    receipt = SendReceipt(
        receipt_id=id_factory(),
        opportunity_id=draft_snapshot.opportunity_id,
        approval_id=approval.approval_id,
        send_request_id=send_request.request_id,
        draft_sha256=draft_snapshot.draft_sha256,
        application_packet_sha256=draft_snapshot.application_packet_sha256,
        idempotency_key=authorization.idempotency_key,
        provider="gmail",
        provider_message_id=provider_message_id.strip(),
        provider_thread_id=(provider_thread_id.strip() if provider_thread_id else None),
        recipient=draft_snapshot.to[0],
        sent_at=_require_aware(now),
        status="SENT",
    )
    saved = ledger.save_send_receipt(receipt)
    if saved.receipt_id != receipt.receipt_id:
        return saved

    ledger.append_event(
        OutreachEvent(
            event_id=f"sent:{receipt.receipt_id}",
            opportunity_id=receipt.opportunity_id,
            event_type="SENT",
            entity_key=receipt.idempotency_key,
            occurred_at=receipt.sent_at,
            metadata={"provider_message_id": receipt.provider_message_id},
        )
    )
    return receipt


def record_send_failure(
    *,
    authorization: SendAuthorizationResult,
    send_request: SendRequest,
    ledger: SQLiteOutreachRepository,
    now: datetime,
    id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> OutreachEvent:
    if not authorization.authorized or authorization.idempotency_key is None:
        raise ValueError("send failure requires prior authorization")
    attempt_exists = any(
        event.event_type == "SEND_ATTEMPTED"
        and event.entity_key == authorization.idempotency_key
        for event in ledger.list_events(send_request.opportunity_id)
    )
    if not attempt_exists:
        raise ValueError("send failure requires matching SEND_ATTEMPTED event")
    return ledger.append_event(
        OutreachEvent(
            event_id=id_factory(),
            opportunity_id=send_request.opportunity_id,
            event_type="SEND_FAILED",
            entity_key=authorization.idempotency_key,
            occurred_at=_require_aware(now),
        )
    )


def _blocked(code: str) -> SendAuthorizationResult:
    return SendAuthorizationResult(
        status="BLOCKED",
        authorized=False,
        error_code=code,
    )


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)
