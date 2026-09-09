import pytest

from app.cv.layout import load_layout_profiles, select_layout_profile
from app.cv.strategy.models import CVStrategy, CoreMessage


def _strategy(track: str, preferred: str | None = None) -> CVStrategy:
    return CVStrategy(
        strategy_version="cv-strategy-v1",
        application_track_id=track,
        target_role="Example Role",
        target_company="Example Co",
        positioning="Verified Developer",
        recruiter_question="Can this candidate do the work?",
        core_messages=[
            CoreMessage(
                id="positioning",
                message="Verified Developer",
                fact_ids=["fact:role"],
                evidence_ids=[],
                importance=10.0,
                reason="validated positioning",
            )
        ],
        must_show_fact_ids=["fact:role"],
        supporting_fact_ids=[],
        optional_fact_ids=[],
        explicit_gaps=[],
        preferred_section_order=["summary", "skills", "experience"],
        preferred_layout_profile_id=preferred,
    )


def test_explicit_valid_preference_wins_over_mapping() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    result = select_layout_profile(
        strategy=_strategy("ops", "technical_clean"),
        profiles=profiles,
        track_layout_map={"ops": "operations_clean"},
    )
    assert result.id == "technical_clean"


def test_explicit_unknown_preference_fails_closed() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    strategy = _strategy("ops").model_copy(
        update={"preferred_layout_profile_id": "missing_profile"}
    )
    with pytest.raises(ValueError, match="layout_profile_unavailable"):
        select_layout_profile(strategy=strategy, profiles=profiles)


def test_injected_track_mapping_selects_profile() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    mapping = {"tech": "technical_clean", "ops": "operations_clean"}
    assert (
        select_layout_profile(
            strategy=_strategy("tech"), profiles=profiles, track_layout_map=mapping
        ).id
        == "technical_clean"
    )
    assert (
        select_layout_profile(
            strategy=_strategy("ops"), profiles=profiles, track_layout_map=mapping
        ).id
        == "operations_clean"
    )


def test_absent_track_mapping_uses_compact_ats() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    assert (
        select_layout_profile(strategy=_strategy("unknown"), profiles=profiles).id
        == "compact_ats"
    )


def test_mapping_to_missing_profile_fails_closed() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    with pytest.raises(ValueError, match="layout_profile_unavailable"):
        select_layout_profile(
            strategy=_strategy("tech"),
            profiles=profiles,
            track_layout_map={"tech": "missing_profile"},
        )


def test_mapping_insertion_order_does_not_change_selection() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    strategy = _strategy("tech")
    first = {"tech": "technical_clean", "ops": "operations_clean"}
    second = dict(reversed(list(first.items())))
    assert select_layout_profile(
        strategy=strategy, profiles=profiles, track_layout_map=first
    ) == select_layout_profile(
        strategy=strategy, profiles=profiles, track_layout_map=second
    )
