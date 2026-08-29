from datetime import datetime, timezone

from app.relationships.models import RelationshipContext
from app.targets.models import TargetAccountAssessment, TargetAccountPolicy
from app.targets.selector import select_target_batch

NOW = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)


def relationship(
    account_id: str = "example",
    *,
    action: str = "PREPARE_SPECULATIVE",
    cooldown: bool = False,
) -> RelationshipContext:
    return RelationshipContext(
        account_id=account_id,
        relationship_state="CONTACTED" if cooldown else "UNTOUCHED",
        cooldown_active=cooldown,
        open_process=False,
        usable_contact_count=1,
        held_contact_count=0,
        recommended_relationship_action=action,
        reason="test relationship context",
        generated_at=NOW,
    )


def assessment(
    account_id: str = "example",
    *,
    affinity: float = 80,
    confidence: float = 90,
    contact: float = 85,
) -> TargetAccountAssessment:
    return TargetAccountAssessment(
        account_id=account_id,
        account_name=account_id.title(),
        best_track_id="tech",
        capability_sector_fit=80,
        proximity_fit=100,
        scale_stability=80,
        innovation=80,
        contactability_fit=contact,
        hiring_signal=50,
        account_affinity=affinity,
        confidence=confidence,
        reasons=[],
        risks=[],
    )


def test_recent_spontaneous_contact_suppresses_action() -> None:
    batch = select_target_batch(
        [assessment()],
        TargetAccountPolicy(),
        {"example": relationship(action="WATCH", cooldown=True)},
        now=NOW,
        profile_fingerprint="profile",
    )
    assert batch.items[0].cooldown_active is True
    assert batch.items[0].recommended_action == "WATCH"


def test_no_contact_history_can_recommend_prepare_outreach() -> None:
    batch = select_target_batch(
        [assessment()],
        TargetAccountPolicy(),
        {"example": relationship()},
        now=NOW,
        profile_fingerprint="profile",
    )
    assert batch.items[0].recommended_action == "PREPARE_SPECULATIVE"


def test_weak_contactability_recommends_research_contact() -> None:
    batch = select_target_batch(
        [assessment(contact=20)],
        TargetAccountPolicy(),
        {"example": relationship()},
        now=NOW,
        profile_fingerprint="profile",
    )
    assert batch.items[0].recommended_action == "RESEARCH_CONTACT"


def test_below_threshold_is_watch() -> None:
    batch = select_target_batch(
        [assessment(affinity=50)],
        TargetAccountPolicy(),
        {"example": relationship()},
        now=NOW,
        profile_fingerprint="profile",
    )
    assert batch.items[0].recommended_action == "WATCH"


def test_selector_orders_actionable_first_and_deduplicates() -> None:
    batch = select_target_batch(
        [
            assessment("watch", affinity=50),
            assessment("prepare", affinity=90),
            assessment("prepare", affinity=70),
        ],
        TargetAccountPolicy(max_items=20),
        {
            "watch": relationship("watch"),
            "prepare": relationship("prepare"),
        },
        now=NOW,
        profile_fingerprint="profile",
    )
    assert [item.account_id for item in batch.items] == ["prepare", "watch"]
