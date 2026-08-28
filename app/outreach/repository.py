from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import sqlite3
from typing import TypeVar

from pydantic import BaseModel

from app.cv.hashing import canonical_sha256
from app.outreach.models import (
    ApprovalRecord,
    ContactResolution,
    DraftSnapshot,
    OutreachBrief,
    OutreachEvent,
    SendReceipt,
    SendRequest,
)

ModelT = TypeVar("ModelT", bound=BaseModel)

_REQUIRED_PREDECESSOR: dict[str, set[str]] = {
    "CONTACT_RESOLVED": {"PACKET_ACCEPTED"},
    "OUTREACH_READY": {"CONTACT_RESOLVED"},
    "DRAFT_CREATED": {"OUTREACH_READY"},
    "DRAFT_REPLACED": {"DRAFT_CREATED", "DRAFT_REPLACED"},
    "APPROVED": {"DRAFT_CREATED", "DRAFT_REPLACED"},
    "SEND_REQUESTED": {"APPROVED"},
    "SEND_ATTEMPTED": {"SEND_REQUESTED"},
    "SENT": {"SEND_ATTEMPTED"},
    "SEND_FAILED": {"SEND_ATTEMPTED"},
}


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def _validate_event_transition(
    event: OutreachEvent,
    prior_events: list[OutreachEvent],
) -> None:
    required = _REQUIRED_PREDECESSOR.get(event.event_type)
    if required is None:
        return
    prior_types = {item.event_type for item in prior_events}
    if not prior_types.intersection(required):
        raise ValueError("outreach event transition missing required predecessor")


class SQLiteOutreachRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outreach_snapshots (
                    entity_type TEXT NOT NULL,
                    entity_key TEXT NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (entity_type, entity_key)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_outreach_snapshots_opportunity
                ON outreach_snapshots(opportunity_id)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outreach_events (
                    event_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_outreach_events_history
                ON outreach_events(opportunity_id, occurred_at, event_id)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS send_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    sent_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_send_receipts_opportunity
                ON send_receipts(opportunity_id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_send_receipts_sent_at
                ON send_receipts(sent_at)
                """
            )

    def _save_snapshot(
        self,
        *,
        entity_type: str,
        entity_key: str,
        opportunity_id: str,
        value: ModelT,
        created_at: datetime,
        model_type: type[ModelT],
    ) -> ModelT:
        timestamp = _require_aware(created_at).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO outreach_snapshots (
                    entity_type, entity_key, opportunity_id, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(entity_type, entity_key) DO NOTHING
                """,
                (
                    entity_type,
                    entity_key,
                    opportunity_id,
                    value.model_dump_json(),
                    timestamp,
                ),
            )
            row = conn.execute(
                """
                SELECT payload_json
                FROM outreach_snapshots
                WHERE entity_type = ? AND entity_key = ?
                LIMIT 1
                """,
                (entity_type, entity_key),
            ).fetchone()
        if row is None:
            raise RuntimeError("outreach snapshot could not be reloaded")
        return model_type.model_validate_json(row["payload_json"])

    def save_contact_resolution(self, value: ContactResolution) -> ContactResolution:
        key = canonical_sha256(value.model_dump(mode="json"))
        return self._save_snapshot(
            entity_type="contact_resolution",
            entity_key=key,
            opportunity_id=value.opportunity_id,
            value=value,
            created_at=value.resolved_at,
            model_type=ContactResolution,
        )

    def save_outreach_brief(self, value: OutreachBrief) -> OutreachBrief:
        return self._save_snapshot(
            entity_type="outreach_brief",
            entity_key=value.brief_id,
            opportunity_id=value.opportunity_id,
            value=value,
            created_at=value.created_at,
            model_type=OutreachBrief,
        )

    def save_draft_snapshot(self, value: DraftSnapshot) -> DraftSnapshot:
        return self._save_snapshot(
            entity_type="draft_snapshot",
            entity_key=value.draft_snapshot_id,
            opportunity_id=value.opportunity_id,
            value=value,
            created_at=value.created_at,
            model_type=DraftSnapshot,
        )

    def save_approval(self, value: ApprovalRecord) -> ApprovalRecord:
        return self._save_snapshot(
            entity_type="approval",
            entity_key=value.approval_id,
            opportunity_id=value.opportunity_id,
            value=value,
            created_at=value.approved_at,
            model_type=ApprovalRecord,
        )

    def save_send_request(self, value: SendRequest) -> SendRequest:
        return self._save_snapshot(
            entity_type="send_request",
            entity_key=value.request_id,
            opportunity_id=value.opportunity_id,
            value=value,
            created_at=value.requested_at,
            model_type=SendRequest,
        )

    def _snapshot_payloads(self, entity_type: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM outreach_snapshots
                WHERE entity_type = ?
                ORDER BY created_at ASC, entity_key ASC
                """,
                (entity_type,),
            ).fetchall()
        return [str(row["payload_json"]) for row in rows]

    def append_event(self, value: OutreachEvent) -> OutreachEvent:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT payload_json FROM outreach_events WHERE event_id = ? LIMIT 1",
                (value.event_id,),
            ).fetchone()
        if existing is not None:
            return OutreachEvent.model_validate_json(existing["payload_json"])

        prior_events = self.list_events(value.opportunity_id)
        _validate_event_transition(value, prior_events)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO outreach_events (
                    event_id, opportunity_id, event_type, payload_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    value.event_id,
                    value.opportunity_id,
                    value.event_type,
                    value.model_dump_json(),
                    value.occurred_at.isoformat(),
                ),
            )
        return value

    def list_events(self, opportunity_id: str) -> list[OutreachEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM outreach_events
                WHERE opportunity_id = ?
                ORDER BY occurred_at ASC, rowid ASC
                """,
                (opportunity_id,),
            ).fetchall()
        return [OutreachEvent.model_validate_json(row["payload_json"]) for row in rows]

    def get_active_approval(
        self,
        draft_sha256: str,
        now: datetime,
    ) -> ApprovalRecord | None:
        now_utc = _require_aware(now)
        matches: list[ApprovalRecord] = []
        for payload in self._snapshot_payloads("approval"):
            approval = ApprovalRecord.model_validate_json(payload)
            if approval.draft_sha256 != draft_sha256 or approval.status != "ACTIVE":
                continue
            if approval.revoked_at is not None:
                continue
            if approval.expires_at is not None and approval.expires_at <= now_utc:
                continue
            matches.append(approval)
        if not matches:
            return None
        return max(matches, key=lambda item: (item.approved_at, item.approval_id))

    def get_send_receipt_by_idempotency_key(self, key: str) -> SendReceipt | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM send_receipts
                WHERE idempotency_key = ?
                LIMIT 1
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        return SendReceipt.model_validate_json(row["payload_json"])

    def save_send_receipt(self, value: SendReceipt) -> SendReceipt:
        existing = self.get_send_receipt_by_idempotency_key(value.idempotency_key)
        if existing is not None:
            return existing
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO send_receipts (
                        receipt_id, opportunity_id, idempotency_key, payload_json, sent_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        value.receipt_id,
                        value.opportunity_id,
                        value.idempotency_key,
                        value.model_dump_json(),
                        value.sent_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError:
            existing = self.get_send_receipt_by_idempotency_key(value.idempotency_key)
            if existing is not None:
                return existing
            raise
        return value

    def has_successful_send_for_opportunity(self, opportunity_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM send_receipts
                WHERE opportunity_id = ?
                LIMIT 1
                """,
                (opportunity_id,),
            ).fetchone()
        return row is not None

    def count_recruiter_contacts_for_company_day(
        self,
        company: str,
        day: date,
    ) -> int:
        normalized_company = " ".join(company.casefold().split())
        count = 0
        for payload in self._snapshot_payloads("contact_resolution"):
            resolution = ContactResolution.model_validate_json(payload)
            if resolution.channel != "VERIFIED_RECRUITER":
                continue
            if " ".join(resolution.organization.casefold().split()) != normalized_company:
                continue
            if resolution.resolved_at.date() == day:
                count += 1
        return count
