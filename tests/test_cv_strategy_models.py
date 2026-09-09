import pytest
from pydantic import ValidationError

from app.cv.strategy.models import CoreMessage, CVStrategy, StrategyTrackConfig


def _message(message_id: str, fact_id: str) -> CoreMessage:
    return CoreMessage(
        id=message_id,
        message=message_id,
        fact_ids=[fact_id],
        evidence_ids=[],
        importance=1.0,
        reason="synthetic test support",
    )


def test_strategy_accepts_at_most_three_core_messages() -> None:
    strategy = CVStrategy(
        strategy_version="cv-strategy-v1",
        application_track_id="tech",
        target_role="Data Analyst",
        target_company="Example Co",
        positioning="Data Engineer",
        recruiter_question="Can the candidate perform this role?",
        core_messages=[
            _message("positioning", "role-data"),
            _message("python", "skill-python"),
            _message("sql", "skill-sql"),
        ],
        must_show_fact_ids=["role-data", "skill-python"],
        supporting_fact_ids=["skill-sql"],
        optional_fact_ids=[],
        explicit_gaps=[],
        preferred_section_order=["summary", "skills", "experience"],
        preferred_layout_profile_id=None,
    )
    assert len(strategy.core_messages) == 3

    with pytest.raises(ValidationError):
        CVStrategy(
            **{
                **strategy.model_dump(),
                "core_messages": [
                    _message("one", "f1"),
                    _message("two", "f2"),
                    _message("three", "f3"),
                    _message("four", "f4"),
                ],
                "must_show_fact_ids": ["f1", "f2", "f3", "f4"],
                "supporting_fact_ids": [],
            }
        )


def test_strategy_rejects_overlapping_fact_buckets() -> None:
    with pytest.raises(ValueError, match="strategy fact buckets must be disjoint"):
        CVStrategy(
            strategy_version="cv-strategy-v1",
            application_track_id="tech",
            target_role="Data Analyst",
            target_company="Example Co",
            positioning="Data Engineer",
            recruiter_question="Can the candidate perform this role?",
            core_messages=[_message("positioning", "role-data")],
            must_show_fact_ids=["role-data"],
            supporting_fact_ids=["role-data"],
            optional_fact_ids=[],
            explicit_gaps=[],
            preferred_section_order=["summary", "skills"],
        )


def test_core_message_fact_must_exist_in_strategy_buckets() -> None:
    with pytest.raises(ValueError, match="core message facts must belong to strategy fact buckets"):
        CVStrategy(
            strategy_version="cv-strategy-v1",
            application_track_id="tech",
            target_role="Data Analyst",
            target_company="Example Co",
            positioning="Data Engineer",
            recruiter_question="Can the candidate perform this role?",
            core_messages=[_message("positioning", "role-data")],
            must_show_fact_ids=["different-fact"],
            supporting_fact_ids=[],
            optional_fact_ids=[],
            explicit_gaps=[],
            preferred_section_order=["summary", "skills"],
        )


def test_track_config_has_no_free_form_positioning_field() -> None:
    with pytest.raises(ValidationError):
        StrategyTrackConfig.model_validate(
            {
                "id": "tech",
                "positioning": "Senior BI Specialist",
            }
        )
