import pytest

from app.cv.narrative.models import NarrativeQAResult


def test_narrative_qa_result_defaults_to_empty_issues() -> None:
    result = NarrativeQAResult(
        valid=True,
        core_message_coverage={"positioning": 1.0},
        off_strategy_claim_ratio=0.0,
        competing_identity_count=0,
        scanability_score=1.0,
    )

    assert result.errors == []
    assert result.warnings == []


def test_narrative_qa_result_rejects_metric_out_of_range() -> None:
    with pytest.raises(ValueError):
        NarrativeQAResult(
            valid=False,
            core_message_coverage={"positioning": 1.0},
            off_strategy_claim_ratio=1.1,
            competing_identity_count=0,
            scanability_score=1.0,
        )


def test_narrative_qa_result_rejects_invalid_core_message_coverage() -> None:
    with pytest.raises(ValueError):
        NarrativeQAResult(
            valid=False,
            core_message_coverage={"positioning": -0.1},
            off_strategy_claim_ratio=0.0,
            competing_identity_count=0,
            scanability_score=1.0,
        )
