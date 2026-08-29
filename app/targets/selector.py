from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.targets.models import TargetAccountAssessment, TargetAccountBatch, TargetAccountPolicy


class OutreachHistory(Protocol):
    def last_contacted_at(self, account_id: str) -> datetime | None: ...


_ACTION_ORDER = {
    "PREPARE_SPECULATIVE": 0,
    "RESEARCH_CONTACT": 1,
    "WATCH": 2,
}


def _action_for(
    item: TargetAccountAssessment,
    policy: TargetAccountPolicy,
    *,
    cooldown_active: bool,
) -> str:
    if cooldown_active:
        return "WATCH"
    if item.account_affinity < policy.minimum_affinity or item.confidence < policy.minimum_confidence:
        return "WATCH"
    if item.contactability_fit <= 20:
        return "RESEARCH_CONTACT"
    return "PREPARE_SPECULATIVE"


def select_target_batch(
    assessments: list[TargetAccountAssessment],
    policy: TargetAccountPolicy,
    history: OutreachHistory,
    *,
    now: datetime,
    profile_fingerprint: str = "unbound",
) -> TargetAccountBatch:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)

    selected: dict[str, TargetAccountAssessment] = {}
    for item in assessments:
        previous = selected.get(item.account_id)
        if previous is None or (item.account_affinity, item.confidence) > (
            previous.account_affinity,
            previous.confidence,
        ):
            selected[item.account_id] = item

    materialized: list[TargetAccountAssessment] = []
    for item in selected.values():
        last_contact = history.last_contacted_at(item.account_id)
        cooldown_active = False
        if last_contact is not None:
            if last_contact.tzinfo is None or last_contact.utcoffset() is None:
                raise ValueError("history timestamps must be timezone-aware")
            cooldown_active = now < last_contact.astimezone(timezone.utc) + timedelta(days=policy.cooldown_days)
        action = _action_for(item, policy, cooldown_active=cooldown_active)
        materialized.append(
            item.model_copy(
                update={
                    "cooldown_active": cooldown_active,
                    "recommended_action": action,
                }
            )
        )

    materialized.sort(
        key=lambda item: (
            _ACTION_ORDER[item.recommended_action],
            -item.account_affinity,
            -item.confidence,
            -item.proximity_fit,
            item.account_id,
        )
    )

    return TargetAccountBatch(
        policy=policy,
        profile_fingerprint=profile_fingerprint,
        generated_at=now,
        items=materialized[: policy.max_items],
    )
