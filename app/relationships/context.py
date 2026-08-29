from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.relationships.models import (
    CareerContact,
    RelationshipContext,
    RelationshipContextSnapshot,
    RelationshipPolicy,
)
from app.relationships.repository import SQLiteRelationshipRepository

_USABLE_VERIFICATION = {"VERIFIED", "PUBLIC_SOURCE"}


class RelationshipMemory(Protocol):
    def context_for(
        self,
        account_id: str,
        *,
        now: datetime,
        current_reason: str | None = None,
    ) -> RelationshipContext: ...


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)


def _usable(contact: CareerContact) -> bool:
    return (
        contact.active
        and contact.disposition == "AVAILABLE"
        and contact.verification_status in _USABLE_VERIFICATION
    )


def _historical_timestamp(account) -> datetime | None:
    values = [
        value
        for value in (
            account.last_contacted_at,
            account.last_reply_at,
            account.updated_at if account.relationship_state == "PROCESS_CLOSED" else None,
        )
        if value is not None
    ]
    return max(values) if values else None


class EmptyRelationshipMemory:
    """Neutral fallback when relationship storage is not configured."""

    def __init__(self, policy: RelationshipPolicy | None = None) -> None:
        self.policy = policy or RelationshipPolicy()

    def context_for(
        self,
        account_id: str,
        *,
        now: datetime,
        current_reason: str | None = None,
    ) -> RelationshipContext:
        now = _aware_utc(now)
        return RelationshipContext(
            account_id=account_id,
            relationship_state="UNTOUCHED",
            cooldown_active=False,
            open_process=False,
            usable_contact_count=0,
            held_contact_count=0,
            recommended_relationship_action="PREPARE_SPECULATIVE",
            reason="no relationship memory configured",
            generated_at=now,
        )


class SQLiteRelationshipMemory:
    def __init__(
        self,
        repository: SQLiteRelationshipRepository,
        policy: RelationshipPolicy | None = None,
    ) -> None:
        self.repository = repository
        self.policy = policy or RelationshipPolicy()

    def context_for(
        self,
        account_id: str,
        *,
        now: datetime,
        current_reason: str | None = None,
    ) -> RelationshipContext:
        now = _aware_utc(now)
        account = self.repository.get_account(account_id)
        if account is None:
            return RelationshipContext(
                account_id=account_id,
                relationship_state="UNTOUCHED",
                cooldown_active=False,
                open_process=False,
                usable_contact_count=0,
                held_contact_count=0,
                recommended_relationship_action="RESEARCH_CONTACT",
                reason="no known relationship or usable contact",
                generated_at=now,
            )

        contacts = self.repository.list_contacts(account_id)
        usable = [contact for contact in contacts if _usable(contact)]
        held = [
            contact
            for contact in contacts
            if contact.active and contact.disposition == "HELD"
        ]

        cooldown_active = (
            account.cooldown_until is not None and now < account.cooldown_until
        )
        historical_at = _historical_timestamp(account)
        historical = historical_at is not None or account.relationship_state != "UNTOUCHED"
        follow_up_age_ok = (
            historical_at is not None
            and now >= historical_at + timedelta(days=self.policy.follow_up_min_days)
        )
        has_follow_up_reason = bool(current_reason and current_reason.strip())

        if account.open_process:
            action = "WATCH"
            reason = "open process already exists"
        elif cooldown_active:
            action = "WATCH"
            reason = "relationship cooldown is active"
        elif historical and has_follow_up_reason and follow_up_age_ok:
            action = "FOLLOW_UP"
            reason = current_reason.strip()
        elif not usable and held:
            action = "WATCH"
            reason = "known contacts are intentionally held"
        elif not usable:
            action = "RESEARCH_CONTACT"
            reason = "no usable verified contact"
        else:
            action = "PREPARE_SPECULATIVE"
            reason = "no relationship blocker"

        derived_state = account.relationship_state
        if (
            historical
            and not account.open_process
            and not cooldown_active
            and not (has_follow_up_reason and follow_up_age_ok)
            and account.relationship_state != "UNTOUCHED"
        ):
            derived_state = "DORMANT"

        preferred_contact_type = None
        if account.preferred_next_contact_id is not None:
            preferred = next(
                (
                    contact
                    for contact in usable
                    if contact.contact_id == account.preferred_next_contact_id
                ),
                None,
            )
            if preferred is not None:
                preferred_contact_type = preferred.contact_type
        if preferred_contact_type is None and usable:
            preferred_contact_type = sorted(
                usable,
                key=lambda contact: contact.contact_id,
            )[0].contact_type

        return RelationshipContext(
            account_id=account_id,
            relationship_state=derived_state,
            last_contacted_at=account.last_contacted_at,
            last_reply_at=account.last_reply_at,
            cooldown_until=account.cooldown_until,
            cooldown_active=cooldown_active,
            open_process=account.open_process,
            usable_contact_count=len(usable),
            held_contact_count=len(held),
            preferred_contact_type=preferred_contact_type,
            last_reason=account.last_reason,
            recommended_relationship_action=action,
            reason=reason,
            generated_at=now,
        )


def build_context_snapshot(
    memory: RelationshipMemory,
    account_ids: list[str],
    *,
    now: datetime,
) -> RelationshipContextSnapshot:
    now = _aware_utc(now)
    contexts = [
        memory.context_for(account_id, now=now)
        for account_id in sorted(set(account_ids))
    ]
    return RelationshipContextSnapshot(generated_at=now, accounts=contexts)


def render_context_snapshot(snapshot: RelationshipContextSnapshot) -> str:
    lines = ["TARGET RELATIONSHIPS"]
    for context in snapshot.accounts:
        last_contact = (
            context.last_contacted_at.date().isoformat()
            if context.last_contacted_at is not None
            else "never"
        )
        cooldown = "cooldown active" if context.cooldown_active else "no cooldown"
        lines.append(
            f"- {context.account_id}: {context.relationship_state} | "
            f"last contact {last_contact} | {cooldown} | "
            f"{context.recommended_relationship_action} | {context.reason}"
        )
    return "\n".join(lines)
