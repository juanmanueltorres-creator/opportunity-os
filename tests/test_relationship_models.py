from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.relationships.models import (
    CareerContact,
    RelationshipAccount,
    RelationshipContext,
    RelationshipEvent,
    RelationshipPolicy,
)

NOW = datetime(2026, 8, 29, 4, 30, tzinfo=timezone.utc)


def test_contact_normalizes_observed_at_and_rejects_extra_fields() -> None:
    contact = CareerContact(
        contact_id="contact-1",
        account_id="account-1",
        person="Example Person",
        role="Recruiter",
        contact_type="RECRUITER",
        verification_status="VERIFIED",
        observed_at=NOW,
        disposition="AVAILABLE",
        active=True,
    )
    assert contact.observed_at.tzinfo is timezone.utc

    with pytest.raises(ValidationError):
        CareerContact(**contact.model_dump(), invented=True)


def test_relationship_event_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        RelationshipEvent(
            event_id="event-1",
            account_id="account-1",
            kind="CONTACTED",
            occurred_at=datetime(2026, 8, 29, 4, 30),
        )


def test_relationship_account_requires_open_process_state_consistency() -> None:
    with pytest.raises(ValidationError):
        RelationshipAccount(
            account_id="account-1",
            company="Example Co",
            relationship_state="PROCESS_OPEN",
            open_process=False,
            updated_at=NOW,
        )


def test_relationship_policy_defaults_are_explicit() -> None:
    policy = RelationshipPolicy()
    assert policy.spontaneous_contact_cooldown_days == 30
    assert policy.follow_up_min_days == 5
    assert policy.stale_contact_days == 180


def test_redacted_context_has_no_contact_pii_fields() -> None:
    assert "person" not in RelationshipContext.model_fields
    assert "email" not in RelationshipContext.model_fields
    assert "channel_value" not in RelationshipContext.model_fields
    assert "notes" not in RelationshipContext.model_fields
