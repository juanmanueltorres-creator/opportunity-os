from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.relationships.context import (
    EmptyRelationshipMemory,
    SQLiteRelationshipMemory,
    build_context_snapshot,
    render_context_snapshot,
)
from app.relationships.models import CareerContact, RelationshipAccount, RelationshipPolicy
from app.relationships.repository import SQLiteRelationshipRepository

NOW = datetime(2026, 8, 29, 6, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path) -> SQLiteRelationshipRepository:
    repo = SQLiteRelationshipRepository(tmp_path / "relationships.sqlite3")
    repo.initialize()
    return repo


def _account(**updates) -> RelationshipAccount:
    base = RelationshipAccount(account_id="account-1", company="Example Co", updated_at=NOW)
    return base.model_copy(update=updates)


def _contact(*, disposition="AVAILABLE", verification="VERIFIED") -> CareerContact:
    return CareerContact(
        contact_id="contact-1",
        account_id="account-1",
        person="Private Person",
        role="Recruiter",
        contact_type="RECRUITER",
        verification_status=verification,
        verification_source="private-source",
        observed_at=NOW,
        disposition=disposition,
        channel_kind="email",
        channel_value="private@example.com",
        active=True,
    )


def test_empty_memory_returns_untouched_context_without_pii() -> None:
    context = EmptyRelationshipMemory().context_for("account-1", now=NOW)
    assert context.relationship_state == "UNTOUCHED"
    assert context.open_process is False
    assert "person" not in context.model_dump()
    assert "channel_value" not in context.model_dump()


def test_open_process_and_active_cooldown_are_watch(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.save_account(
        _account(
            relationship_state="PROCESS_OPEN",
            open_process=True,
            cooldown_until=NOW + timedelta(days=10),
        )
    )
    repo.save_contact(_contact())
    memory = SQLiteRelationshipMemory(repo)

    context = memory.context_for("account-1", now=NOW)

    assert context.recommended_relationship_action == "WATCH"
    assert context.cooldown_active is True


def test_no_usable_contacts_is_research_contact(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.save_account(_account())
    memory = SQLiteRelationshipMemory(repo)

    context = memory.context_for("account-1", now=NOW)

    assert context.usable_contact_count == 0
    assert context.recommended_relationship_action == "RESEARCH_CONTACT"


def test_held_contacts_are_counted_but_not_usable_and_force_watch(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.save_account(_account())
    repo.save_contact(_contact(disposition="HELD"))
    memory = SQLiteRelationshipMemory(repo)

    context = memory.context_for("account-1", now=NOW)

    assert context.usable_contact_count == 0
    assert context.held_contact_count == 1
    assert context.recommended_relationship_action == "WATCH"


def test_follow_up_requires_history_new_reason_and_min_days(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.save_contact(_contact())
    repo.save_account(
        _account(
            relationship_state="CONTACTED",
            last_contacted_at=NOW - timedelta(days=10),
            updated_at=NOW - timedelta(days=10),
        )
    )
    memory = SQLiteRelationshipMemory(repo, RelationshipPolicy(follow_up_min_days=5))

    without_reason = memory.context_for("account-1", now=NOW)
    assert without_reason.relationship_state == "DORMANT"
    assert without_reason.recommended_relationship_action == "PREPARE_SPECULATIVE"

    with_reason = memory.context_for(
        "account-1",
        now=NOW,
        current_reason="new backend role published",
    )
    assert with_reason.recommended_relationship_action == "FOLLOW_UP"
    assert with_reason.reason == "new backend role published"


def test_dormant_derivation_does_not_mutate_stored_account(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.save_contact(_contact())
    repo.save_account(
        _account(
            relationship_state="CONTACTED",
            last_contacted_at=NOW - timedelta(days=10),
            updated_at=NOW - timedelta(days=10),
        )
    )
    memory = SQLiteRelationshipMemory(repo)

    assert memory.context_for("account-1", now=NOW).relationship_state == "DORMANT"
    assert repo.get_account("account-1").relationship_state == "CONTACTED"


def test_rendered_snapshot_contains_no_contact_pii(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.save_contact(_contact())
    repo.save_account(_account(preferred_next_contact_id="contact-1"))
    memory = SQLiteRelationshipMemory(repo)

    snapshot = build_context_snapshot(memory, ["account-1"], now=NOW)
    rendered = render_context_snapshot(snapshot).lower()

    assert "private person" not in rendered
    assert "private@example.com" not in rendered
    assert "private-source" not in rendered
    assert "account-1" in rendered
