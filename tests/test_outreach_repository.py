from datetime import date, datetime, timedelta, timezone

import pytest

from app.outreach.models import (
    ApprovalRecord,
    ContactResolution,
    OutreachEvent,
    SendReceipt,
)
from app.outreach.repository import SQLiteOutreachRepository

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _receipt(key: str, *, receipt_id: str = "receipt-1") -> SendReceipt:
    return SendReceipt(
        receipt_id=receipt_id,
        opportunity_id="opp-1",
        approval_id="approval-1",
        send_request_id="request-1",
        draft_sha256="d" * 64,
        application_packet_sha256="p" * 64,
        idempotency_key=key,
        provider_message_id="message-1",
        recipient="careers@example.test",
        sent_at=NOW,
    )


def _event(event_type: str, event_id: str, when: datetime, *, key: str | None = None):
    return OutreachEvent(
        event_id=event_id,
        opportunity_id="opp-1",
        event_type=event_type,
        entity_key=key,
        occurred_at=when,
    )


def _append_until_approved(repo: SQLiteOutreachRepository) -> None:
    chain = [
        ("PACKET_ACCEPTED", "event-1"),
        ("CONTACT_RESOLVED", "event-2"),
        ("OUTREACH_READY", "event-3"),
        ("DRAFT_CREATED", "event-4"),
        ("APPROVED", "event-5"),
    ]
    for offset, (event_type, event_id) in enumerate(chain):
        repo.append_event(_event(event_type, event_id, NOW + timedelta(seconds=offset)))


def test_receipt_idempotency_survives_repository_restart(tmp_path) -> None:
    path = tmp_path / "outreach.sqlite3"
    first = SQLiteOutreachRepository(path)
    first.initialize()
    first.save_send_receipt(_receipt("k" * 64))

    second = SQLiteOutreachRepository(path)
    second.initialize()
    loaded = second.get_send_receipt_by_idempotency_key("k" * 64)
    assert loaded is not None
    assert loaded.receipt_id == "receipt-1"
    assert second.has_successful_send_for_opportunity("opp-1") is True


def test_duplicate_receipt_key_cannot_create_second_success(tmp_path) -> None:
    repo = SQLiteOutreachRepository(tmp_path / "outreach.sqlite3")
    repo.initialize()
    repo.save_send_receipt(_receipt("k" * 64, receipt_id="receipt-1"))
    existing = repo.save_send_receipt(_receipt("k" * 64, receipt_id="receipt-2"))
    assert existing.receipt_id == "receipt-1"


def test_events_are_append_only_and_ordered(tmp_path) -> None:
    repo = SQLiteOutreachRepository(tmp_path / "outreach.sqlite3")
    repo.initialize()
    repo.append_event(_event("PACKET_ACCEPTED", "event-1", NOW))
    repo.append_event(
        _event("CONTACT_RESOLVED", "event-2", NOW + timedelta(seconds=1))
    )
    assert [event.event_type for event in repo.list_events("opp-1")] == [
        "PACKET_ACCEPTED",
        "CONTACT_RESOLVED",
    ]


def test_ledger_rejects_send_requested_before_approval(tmp_path) -> None:
    repo = SQLiteOutreachRepository(tmp_path / "outreach.sqlite3")
    repo.initialize()
    repo.append_event(_event("PACKET_ACCEPTED", "event-1", NOW))

    with pytest.raises(ValueError, match="required predecessor"):
        repo.append_event(
            _event("SEND_REQUESTED", "event-bad-1", NOW + timedelta(seconds=1))
        )


def test_sent_requires_send_attempted_even_after_approval(tmp_path) -> None:
    repo = SQLiteOutreachRepository(tmp_path / "outreach.sqlite3")
    repo.initialize()
    _append_until_approved(repo)

    with pytest.raises(ValueError, match="required predecessor"):
        repo.append_event(_event("SENT", "event-bad", NOW + timedelta(seconds=10)))


def test_active_approval_lookup_respects_expiry(tmp_path) -> None:
    repo = SQLiteOutreachRepository(tmp_path / "outreach.sqlite3")
    repo.initialize()
    approval = ApprovalRecord(
        approval_id="approval-1",
        opportunity_id="opp-1",
        draft_sha256="d" * 64,
        application_packet_sha256="p" * 64,
        approved_by="user",
        approval_scope="SINGLE",
        approved_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    repo.save_approval(approval)

    assert repo.get_active_approval("d" * 64, NOW) is not None
    assert repo.get_active_approval("d" * 64, NOW + timedelta(hours=2)) is None


def test_recruiter_daily_company_count_uses_resolved_snapshots(tmp_path) -> None:
    repo = SQLiteOutreachRepository(tmp_path / "outreach.sqlite3")
    repo.initialize()
    for index in range(2):
        repo.save_contact_resolution(
            ContactResolution(
                opportunity_id=f"opp-{index}",
                selected_candidate_id=f"candidate-{index}",
                channel="VERIFIED_RECRUITER",
                email=f"recruiter{index}@example.test",
                contact_name=f"Recruiter {index}",
                contact_role="Talent Acquisition",
                organization="Example Labs",
                source_kind="APOLLO",
                source_ref=f"apollo:person:{index}",
                confidence=0.9,
                verification_status="VERIFIED_ENRICHED",
                resolution_reason="verified recruiter",
                resolved_at=NOW + timedelta(minutes=index),
                resolver_version="contact-v1",
            )
        )

    assert repo.count_recruiter_contacts_for_company_day(
        "example labs", date(2026, 8, 28)
    ) == 2
