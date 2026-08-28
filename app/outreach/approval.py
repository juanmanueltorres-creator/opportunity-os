from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from app.outreach.hashing import batch_manifest_sha256
from app.outreach.models import (
    ApprovalRecord,
    ApprovalRequest,
    DraftSnapshot,
    OutreachEvent,
)
from app.outreach.repository import SQLiteOutreachRepository


class ApprovalService:
    def __init__(
        self,
        *,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.id_factory = id_factory or (lambda: str(uuid4()))

    def approve(
        self,
        *,
        draft_snapshot: DraftSnapshot,
        approval_request: ApprovalRequest,
        ledger: SQLiteOutreachRepository,
        now: datetime,
    ) -> ApprovalRecord:
        now_utc = _require_aware(now)
        if approval_request.draft_sha256 != draft_snapshot.draft_sha256:
            raise ValueError("approval request must match exact draft hash")
        if draft_snapshot.verification_basis == "UNVERIFIABLE":
            raise ValueError("unverifiable draft cannot be approved for automated send")
        if approval_request.expires_at is not None:
            if approval_request.expires_at <= now_utc:
                raise ValueError("approval expiry must be in the future")

        if approval_request.approval_scope == "BATCH":
            expected_manifest = batch_manifest_sha256(
                approval_request.draft_sha256s
            )
            if approval_request.batch_manifest_sha256 != expected_manifest:
                raise ValueError("batch manifest does not match exact draft hashes")
            if draft_snapshot.draft_sha256 not in approval_request.draft_sha256s:
                raise ValueError("batch manifest must include current draft hash")

        approval_id = self.id_factory()
        record = ApprovalRecord(
            approval_id=approval_id,
            opportunity_id=draft_snapshot.opportunity_id,
            draft_sha256=draft_snapshot.draft_sha256,
            application_packet_sha256=draft_snapshot.application_packet_sha256,
            approved_by=approval_request.requested_by,
            approval_scope=approval_request.approval_scope,
            batch_manifest_sha256=approval_request.batch_manifest_sha256,
            approved_at=now_utc,
            expires_at=approval_request.expires_at,
            status="ACTIVE",
        )

        ledger.append_event(
            OutreachEvent(
                event_id=f"approval:{approval_id}",
                opportunity_id=draft_snapshot.opportunity_id,
                event_type="APPROVED",
                entity_key=approval_id,
                occurred_at=now_utc,
                metadata={"draft_sha256": draft_snapshot.draft_sha256},
            )
        )
        return ledger.save_approval(record)


def is_active(record: ApprovalRecord, *, now: datetime) -> bool:
    now_utc = _require_aware(now)
    if record.status != "ACTIVE" or record.revoked_at is not None:
        return False
    if record.expires_at is not None and record.expires_at <= now_utc:
        return False
    return True


def revoke(record: ApprovalRecord, *, revoked_at: datetime) -> ApprovalRecord:
    revoked_at_utc = _require_aware(revoked_at)
    if revoked_at_utc < record.approved_at:
        raise ValueError("revoked_at cannot precede approved_at")
    return record.model_copy(
        update={
            "status": "REVOKED",
            "revoked_at": revoked_at_utc,
        }
    )


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)
