from datetime import datetime, timezone

from app.relationships.context import EmptyRelationshipMemory
from app.relationships.models import RelationshipContext
from app.targets.models import TargetAccountAssessment, TargetAccountPolicy
from app.targets.selector import select_target_batch

NOW = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)


def assessment(account_id: str = "example") -> TargetAccountAssessment:
    return TargetAccountAssessment(
        account_id=account_id,
        account_name="Example",
        best_track_id="tech",
        capability_sector_fit=95,
        proximity_fit=100,
        scale_stability=90,
        innovation=90,
        contactability_fit=90,
        hiring_signal=80,
        account_affinity=92,
        confidence=95,
        reasons=[],
        risks=[],
    )


def context(action: str, *, cooldown: bool = False, held: int = 0) -> RelationshipContext:
    return RelationshipContext(
        account_id="example",
        relationship_state="PROCESS_OPEN" if action == "WATCH" and held == 0 else "DORMANT",
        cooldown_active=cooldown,
        open_process=action == "WATCH" and held == 0,
        usable_contact_count=0 if held else 1,
        held_contact_count=held,
        recommended_relationship_action=action,
        reason="relationship policy",
        generated_at=NOW,
    )


def test_open_process_forces_watch_even_for_high_affinity() -> None:
    batch = select_target_batch(
        [assessment()],
        TargetAccountPolicy(),
        {"example": context("WATCH")},
        now=NOW,
        profile_fingerprint="profile",
    )
    assert batch.items[0].recommended_action == "WATCH"


def test_follow_up_propagates_when_relationship_context_allows_it() -> None:
    batch = select_target_batch(
        [assessment()],
        TargetAccountPolicy(),
        {"example": context("FOLLOW_UP")},
        now=NOW,
        profile_fingerprint="profile",
    )
    assert batch.items[0].recommended_action == "FOLLOW_UP"


def test_held_only_contact_forces_watch() -> None:
    batch = select_target_batch(
        [assessment()],
        TargetAccountPolicy(),
        {"example": context("WATCH", held=1)},
        now=NOW,
        profile_fingerprint="profile",
    )
    assert batch.items[0].recommended_action == "WATCH"


def test_empty_memory_context_preserves_existing_prepare_behavior() -> None:
    neutral = EmptyRelationshipMemory().context_for("example", now=NOW)
    batch = select_target_batch(
        [assessment()],
        TargetAccountPolicy(),
        {"example": neutral},
        now=NOW,
        profile_fingerprint="profile",
    )
    assert batch.items[0].recommended_action == "PREPARE_SPECULATIVE"


def test_selector_never_returns_send() -> None:
    actions = ["WATCH", "FOLLOW_UP", "RESEARCH_CONTACT", "PREPARE_SPECULATIVE"]
    for relationship_action in actions:
        batch = select_target_batch(
            [assessment()],
            TargetAccountPolicy(),
            {"example": context(relationship_action)},
            now=NOW,
            profile_fingerprint="profile",
        )
        assert batch.items[0].recommended_action != "SEND"
