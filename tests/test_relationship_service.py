from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.relationships.models import CareerContact, RelationshipAccount, RelationshipEvent
from app.relationships.repository import SQLiteRelationshipRepository
from app.relationships.service import RelationshipService

NOW = datetime(2026, 8, 29, 5, 15, tzinfo=timezone.utc)


def _repo(tmp_path: Path) -> SQLiteRelationshipRepository:
    repo = SQLiteRelationshipRepository(tmp_path / "relationships.sqlite3")
    repo.initialize()
    return repo


def _account() -> RelationshipAccount:
    return RelationshipAccount(account_id="account-1", company="Example Co", updated_at=NOW)


def _contact(disposition: str = "AVAILABLE") -> CareerContact:
    return CareerContact(
        contact_id="contact-1",
        account_id="account-1",
        person="Example Person",
        role="Recruiter",
        contact_type="RECRUITER",
        verification_status="VERIFIED",
        observed_at=NOW,
        disposition=disposition,
        active=True,
    )


def _event(event_id: str, kind: str, *, at: datetime = NOW, metadata=None, contact=True):
    return RelationshipEvent(
        event_id=event_id,
        account_id="account-1",
        contact_id="contact-1" if contact else None,
        kind=kind,
        occurred_at=at,
        metadata=metadata or {},
    )


def test_process_open_is_not_downgraded_by_later_contacted_event(tmp_path: Path) -> None:
    service = RelationshipService(_repo(tmp_path))
    service.register_account(_account())
    service.register_contact(_contact())
    service.record(_event("open", "PROCESS_OPENED", contact=False))
    later = _event("contacted", "CONTACTED", at=NOW + timedelta(days=1))

    account = service.record(later)

    assert account.relationship_state == "PROCESS_OPEN"
    assert account.open_process is True
    assert account.last_contacted_at == later.occurred_at


def test_replied_preserves_process_open(tmp_path: Path) -> None:
    service = RelationshipService(_repo(tmp_path))
    service.register_account(_account())
    service.register_contact(_contact())
    service.record(_event("open", "PROCESS_OPENED", contact=False))

    account = service.record(_event("reply", "REPLIED", at=NOW + timedelta(hours=2)))

    assert account.relationship_state == "PROCESS_OPEN"
    assert account.last_reply_at == NOW + timedelta(hours=2)


def test_process_updated_and_closed_require_open_process(tmp_path: Path) -> None:
    service = RelationshipService(_repo(tmp_path))
    service.register_account(_account())

    with pytest.raises(ValueError, match="open process"):
        service.record(_event("update", "PROCESS_UPDATED", contact=False))
    with pytest.raises(ValueError, match="open process"):
        service.record(_event("close", "PROCESS_CLOSED", contact=False))


def test_contact_held_clears_preferred_contact_and_release_restores_availability(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    service = RelationshipService(repo)
    service.register_account(_account())
    service.register_contact(_contact())
    service.register_account(_account().model_copy(update={"preferred_next_contact_id": "contact-1"}))

    held_account = service.record(_event("hold", "CONTACT_HELD"))
    assert held_account.preferred_next_contact_id is None
    assert repo.get_contact("contact-1").disposition == "HELD"

    service.record(_event("release", "CONTACT_RELEASED", at=NOW + timedelta(hours=1)))
    assert repo.get_contact("contact-1").disposition == "AVAILABLE"


def test_contact_release_requires_active_held_verified_contact(tmp_path: Path) -> None:
    service = RelationshipService(_repo(tmp_path))
    service.register_account(_account())
    service.register_contact(_contact(disposition="AVAILABLE"))

    with pytest.raises(ValueError, match="held contact"):
        service.record(_event("release", "CONTACT_RELEASED"))


def test_cooldown_set_rejects_past_timestamp(tmp_path: Path) -> None:
    service = RelationshipService(_repo(tmp_path))
    service.register_account(_account())
    past = (NOW - timedelta(days=1)).isoformat()

    with pytest.raises(ValueError, match="cooldown_until"):
        service.record(
            _event("cooldown", "COOLDOWN_SET", metadata={"cooldown_until": past}, contact=False)
        )


def test_invalid_projection_rolls_back_event_and_state(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    service = RelationshipService(repo)
    service.register_account(_account())
    event = _event("bad-open", "PROCESS_UPDATED", contact=False)

    with pytest.raises(ValueError):
        service.record(event)

    assert repo.get_event("bad-open") is None
    assert repo.get_account("account-1").relationship_state == "UNTOUCHED"
