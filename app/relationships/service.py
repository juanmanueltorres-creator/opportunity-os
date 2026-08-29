from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.relationships.models import (
    CareerContact,
    RelationshipAccount,
    RelationshipEvent,
    RelationshipPolicy,
)
from app.relationships.repository import SQLiteRelationshipRepository

_USABLE_VERIFICATION = {"VERIFIED", "PUBLIC_SOURCE"}


def _usable(contact: CareerContact) -> bool:
    return (
        contact.active
        and contact.disposition == "AVAILABLE"
        and contact.verification_status in _USABLE_VERIFICATION
    )


def _parse_aware_datetime(raw: str, *, field: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO datetime") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


class RelationshipService:
    def __init__(
        self,
        repository: SQLiteRelationshipRepository,
        policy: RelationshipPolicy | None = None,
    ) -> None:
        self.repository = repository
        self.policy = policy or RelationshipPolicy()

    def register_account(self, account: RelationshipAccount) -> RelationshipAccount:
        return self.repository.save_account(account)

    def register_contact(self, contact: CareerContact) -> CareerContact:
        account = self.repository.get_account(contact.account_id)
        if account is None:
            raise ValueError("relationship account must be registered before contact")
        return self.repository.save_contact(contact)

    def context_source_account(self, account_id: str) -> RelationshipAccount | None:
        return self.repository.get_account(account_id)

    def record(self, event: RelationshipEvent) -> RelationshipAccount:
        def projector(
            account: RelationshipAccount | None,
            contacts: list[CareerContact],
        ) -> tuple[RelationshipAccount, list[CareerContact]]:
            if account is None:
                raise ValueError("relationship account must be registered before events")

            contact_map = {item.contact_id: item for item in contacts}
            next_contacts = list(contacts)
            next_account = account

            def require_contact() -> CareerContact:
                if event.contact_id is None:
                    raise ValueError(f"{event.kind} requires contact_id")
                contact = contact_map.get(event.contact_id)
                if contact is None or contact.account_id != event.account_id:
                    raise ValueError("relationship event contact must belong to account")
                return contact

            def replace_contact(updated: CareerContact) -> None:
                nonlocal next_contacts
                next_contacts = [
                    updated if item.contact_id == updated.contact_id else item
                    for item in next_contacts
                ]
                contact_map[updated.contact_id] = updated

            if event.kind == "CONTACT_VERIFIED":
                contact = require_contact()
                observed_at = max(contact.observed_at, event.occurred_at)
                replace_contact(
                    contact.model_copy(
                        update={
                            "verification_status": "VERIFIED",
                            "observed_at": observed_at,
                        }
                    )
                )
                return next_account, next_contacts

            if event.kind == "CONTACT_HELD":
                contact = require_contact()
                replace_contact(contact.model_copy(update={"disposition": "HELD"}))
                updates = {"updated_at": event.occurred_at}
                if next_account.preferred_next_contact_id == contact.contact_id:
                    updates["preferred_next_contact_id"] = None
                return next_account.model_copy(update=updates), next_contacts

            if event.kind == "CONTACT_RELEASED":
                contact = require_contact()
                if (
                    not contact.active
                    or contact.disposition != "HELD"
                    or contact.verification_status not in _USABLE_VERIFICATION
                ):
                    raise ValueError("CONTACT_RELEASED requires active held contact with usable verification")
                replace_contact(contact.model_copy(update={"disposition": "AVAILABLE"}))
                return next_account.model_copy(update={"updated_at": event.occurred_at}), next_contacts

            if event.kind == "CONTACTED":
                official_channel = event.metadata.get("official_channel", "").strip()
                if event.contact_id is not None:
                    contact = require_contact()
                    if not _usable(contact):
                        raise ValueError("CONTACTED requires a usable contact")
                elif not official_channel:
                    raise ValueError("CONTACTED requires usable contact or official account channel")

                next_state = (
                    "PROCESS_OPEN"
                    if next_account.open_process
                    else "CONTACTED"
                )
                cooldown_until = next_account.cooldown_until
                if cooldown_until is None or cooldown_until <= event.occurred_at:
                    cooldown_until = event.occurred_at + timedelta(
                        days=self.policy.spontaneous_contact_cooldown_days
                    )
                return next_account.model_copy(
                    update={
                        "relationship_state": next_state,
                        "last_contacted_at": event.occurred_at,
                        "cooldown_until": cooldown_until,
                        "last_reason": event.reason or next_account.last_reason,
                        "updated_at": event.occurred_at,
                    }
                ), next_contacts

            if event.kind == "REPLIED":
                if event.contact_id is not None:
                    require_contact()
                next_state = "PROCESS_OPEN" if next_account.open_process else "REPLIED"
                return next_account.model_copy(
                    update={
                        "relationship_state": next_state,
                        "last_reply_at": event.occurred_at,
                        "last_reason": event.reason or next_account.last_reason,
                        "updated_at": event.occurred_at,
                    }
                ), next_contacts

            if event.kind == "PROCESS_OPENED":
                return next_account.model_copy(
                    update={
                        "relationship_state": "PROCESS_OPEN",
                        "open_process": True,
                        "process_label": event.metadata.get("process_label") or next_account.process_label,
                        "last_reason": event.reason or next_account.last_reason,
                        "updated_at": event.occurred_at,
                    }
                ), next_contacts

            if event.kind == "PROCESS_UPDATED":
                if not next_account.open_process:
                    raise ValueError("PROCESS_UPDATED requires open process")
                return next_account.model_copy(
                    update={
                        "relationship_state": "PROCESS_OPEN",
                        "process_label": event.metadata.get("process_label") or next_account.process_label,
                        "last_reason": event.reason or next_account.last_reason,
                        "updated_at": event.occurred_at,
                    }
                ), next_contacts

            if event.kind == "PROCESS_CLOSED":
                if not next_account.open_process:
                    raise ValueError("PROCESS_CLOSED requires open process")
                return next_account.model_copy(
                    update={
                        "relationship_state": "PROCESS_CLOSED",
                        "open_process": False,
                        "last_reason": event.reason or next_account.last_reason,
                        "updated_at": event.occurred_at,
                    }
                ), next_contacts

            if event.kind == "COOLDOWN_SET":
                raw = event.metadata.get("cooldown_until")
                if not raw:
                    raise ValueError("COOLDOWN_SET requires cooldown_until")
                cooldown_until = _parse_aware_datetime(raw, field="cooldown_until")
                if cooldown_until < event.occurred_at:
                    raise ValueError("cooldown_until must be at or after occurred_at")
                return next_account.model_copy(
                    update={
                        "cooldown_until": cooldown_until,
                        "updated_at": event.occurred_at,
                    }
                ), next_contacts

            if event.kind == "COOLDOWN_CLEARED":
                return next_account.model_copy(
                    update={"cooldown_until": None, "updated_at": event.occurred_at}
                ), next_contacts

            if event.kind == "NOTE_RECORDED":
                return next_account, next_contacts

            raise ValueError("unsupported relationship event kind")

        _, account = self.repository.apply_event_transaction(event, projector)
        return account
