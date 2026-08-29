from datetime import datetime, timezone

from app.relationships.models import RelationshipContext
from app.targets.models import (
    TargetAccountAssessment,
    TargetAccountBatch,
    TargetAccountPolicy,
    TargetAction,
)


_ACTION_ORDER = {
    "FOLLOW_UP": 0,
    "PREPARE_SPECULATIVE": 1,
    "RESEARCH_CONTACT": 2,
    "WATCH": 3,
}


def _action_for(
    item: TargetAccountAssessment,
    policy: TargetAccountPolicy,
    relationship: RelationshipContext,
) -> TargetAction:
    relationship_action = relationship.recommended_relationship_action
    if relationship_action != "PREPARE_SPECULATIVE":
        return relationship_action
    if (
        item.account_affinity < policy.minimum_affinity
        or item.confidence < policy.minimum_confidence
    ):
        return "WATCH"
    if item.contactability_fit <= 20:
        return "RESEARCH_CONTACT"
    return "PREPARE_SPECULATIVE"


def select_target_batch(
    assessments: list[TargetAccountAssessment],
    policy: TargetAccountPolicy,
    relationship_contexts: dict[str, RelationshipContext],
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
        relationship = relationship_contexts.get(item.account_id)
        if relationship is None:
            raise ValueError("relationship context missing for target account")
        action = _action_for(item, policy, relationship)
        materialized.append(
            item.model_copy(
                update={
                    "cooldown_active": relationship.cooldown_active,
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
