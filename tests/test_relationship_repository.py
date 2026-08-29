from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.relationships.models import CareerContact, RelationshipAccount, RelationshipEvent
from app.relationships.repository import SQLiteRelationshipRepository

NOW = datetime(2026, 8, 29, 5, 0, tzinfo=timezone.utc)


def _contact(contact_id: str = "contact-1", account_id: str = "account-1") -> CareerContact:
    return CareerContact(
        contact_id=contact_id,
        account_id=account_id,
        person="Example Person",
        role="Recruiter",
        contact_type="RECRUITER",
        verification_status="VERIFIED",
        observed_at=NOW,
        disposition="AVAILABLE",
        active=True,
    )


def _account(account_id: str = "account-1", preferred: str | None = None) -> RelationshipAccount:
    return RelationshipAccount(
        account_id=account_id,
        company="Example Co",
        preferred_next_contact_id=preferred,
        updated_at=NOW,
    )


def test_repository_round_trips_accounts_and_contacts(tmp_path: Path) -> None:
    repo = SQLiteRelationshipRepository(tmp_path / "relationships.sqlite3")
    repo.initialize()
    repo.save_contact(_contact())
    repo.save_account(_account(preferred="contact-1"))

    assert repo.get_account("account-1") == _account(preferred="contact-1")
    assert repo.get_contact("contact-1") == _contact()
    assert repo.list_contacts("account-1") == [_contact()]


def test_preferred_contact_must_belong_to_same_account_and_be_available(tmp_path: Path) -> None:
    repo = SQLiteRelationshipRepository(tmp_path / "relationships.sqlite3")
    repo.initialize()
    repo.save_contact(_contact(account_id="other-account"))

    with pytest.raises(ValueError, match="preferred contact"):
        repo.save_account(_account(preferred="contact-1"))


def test_duplicate_event_id_is_idempotent_but_conflicts_are_rejected(tmp_path: Path) -> None:
    repo = SQLiteRelationshipRepository(tmp_path / "relationships.sqlite3")
    repo.initialize()
    first = RelationshipEvent(
        event_id="event-1",
        account_id="account-1",
        kind="CONTACTED",
        occurred_at=NOW,
    )
    assert repo.append_event(first) == first
    assert repo.append_event(first) == first

    conflicting = first.model_copy(update={"kind": "REPLIED"})
    with pytest.raises(ValueError, match="event_id conflict"):
        repo.append_event(conflicting)


def test_apply_event_transaction_rolls_back_event_when_projector_fails(tmp_path: Path) -> None:
    repo = SQLiteRelationshipRepository(tmp_path / "relationships.sqlite3")
    repo.initialize()
    event = RelationshipEvent(
        event_id="event-rollback",
        account_id="account-1",
        kind="CONTACTED",
        occurred_at=NOW,
    )

    def broken_projector(account, contacts):
        raise ValueError("projection failed")

    with pytest.raises(ValueError, match="projection failed"):
        repo.apply_event_transaction(event, broken_projector)

    assert repo.get_event("event-rollback") is None
    assert repo.get_account("account-1") is None


def test_validate_event_identical_replay_precedes_chronology(tmp_path: Path) -> None:
    repo = SQLiteRelationshipRepository(tmp_path / "relationships.sqlite3")
    repo.initialize()
    event = RelationshipEvent(
        event_id="event-1",
        account_id="account-1",
        kind="CONTACTED",
        occurred_at=NOW,
        metadata={"official_channel": "manual"},
    )
    repo.append_event(event)

    assert repo.validate_event(event) == "IDENTICAL"
    assert repo.list_events("account-1") == [event]


def test_validate_event_rejects_new_out_of_order_event_without_write(tmp_path: Path) -> None:
    repo = SQLiteRelationshipRepository(tmp_path / "relationships.sqlite3")
    repo.initialize()
    newer = RelationshipEvent(
        event_id="event-new",
        account_id="account-1",
        kind="CONTACTED",
        occurred_at=NOW,
        metadata={"official_channel": "manual"},
    )
    older = RelationshipEvent(
        event_id="event-old",
        account_id="account-1",
        kind="CONTACTED",
        occurred_at=NOW - timedelta(days=1),
        metadata={"official_channel": "manual"},
    )
    repo.append_event(newer)

    with pytest.raises(ValueError, match="out-of-order relationship event"):
        repo.validate_event(older)

    assert repo.get_event("event-old") is None
    assert repo.list_events("account-1") == [newer]
