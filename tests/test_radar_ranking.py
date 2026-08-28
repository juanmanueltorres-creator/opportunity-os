from datetime import datetime, timezone

from app.models.domain import Opportunity, OpportunityAssessment
from app.radar.models import (
    ConfidenceAssessment,
    EligibilityResult,
    IncomeAssessment,
    OpportunityEnrichment,
    TrackCareerAssessment,
)
from app.radar.ranking import RadarPolicy, classify_fit, rank_assessment

NOW = datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc)


def _policy() -> RadarPolicy:
    return RadarPolicy()


def _confidence(score: float) -> ConfidenceAssessment:
    return ConfidenceAssessment(
        score=score,
        requirement_extraction_quality=score,
        skill_normalization_coverage=score,
        evidence_traceability=score,
        seniority_location_legal_clarity=score,
        source_freshness_completeness=score,
    )


def _opportunity() -> Opportunity:
    return Opportunity(
        id="job-1",
        source="manual",
        source_id="1",
        source_url="https://example.com/jobs/1",
        company="Example Co",
        title="Example Role",
        description="Example",
        discovered_at=NOW,
    )


def _enrichment() -> OpportunityEnrichment:
    return OpportunityEnrichment(
        opportunity_id="job-1",
        extractor_version="rules-v1",
        created_at=NOW,
    )


def _career(score: float) -> TrackCareerAssessment:
    return TrackCareerAssessment(
        track_id="career",
        assessment=OpportunityAssessment(
            opportunity_id="job-1",
            overall_score=score,
            mandatory_fit=score,
            domain_fit=score,
            evidence_fit=score,
            location_fit=score,
            freshness_fit=score,
            strengths=[],
            gaps=[],
            risks=[],
            evidence=[],
            recommendation="apply" if score >= 75 else "stretch",
            explanation="fixture",
        ),
    )


def _income(score: float) -> IncomeAssessment:
    return IncomeAssessment(
        track_id="income",
        income_viability=score,
        capability_fit=score,
        logistics_fit=score,
        schedule_fit=score,
        entry_friction_fit=score,
        freshness_fit=score,
    )


def test_default_tier_thresholds_are_explicit() -> None:
    policy = _policy()

    assert classify_fit(78.0, 75.0, policy) == "HIGH"
    assert classify_fit(77.9, 75.0, policy) == "MEDIUM"
    assert classify_fit(65.0, 65.0, policy) == "MEDIUM"
    assert classify_fit(64.9, 99.0, policy) == "STRETCH"
    assert classify_fit(55.0, 10.0, policy) == "STRETCH"
    assert classify_fit(54.9, 100.0, policy) == "DISCARD"
    assert classify_fit(None, 100.0, policy) is None


def test_low_career_score_does_not_suppress_high_income_lane() -> None:
    assessment = rank_assessment(
        _opportunity(),
        _enrichment(),
        EligibilityResult(eligible=True),
        _career(45.0),
        _income(90.0),
        _confidence(80.0),
        policy=_policy(),
        scoring_version="v0.2a1",
        alias_registry_version="1",
    )

    assert assessment.intent_tiers["CAREER"] == "DISCARD"
    assert assessment.intent_tiers["INCOME_NOW"] == "HIGH"
    assert assessment.selected_intent == "INCOME_NOW"
    assert assessment.priority_score == 88.0
    assert assessment.tier == "HIGH"


def test_lane_priority_is_eighty_twenty_fit_confidence() -> None:
    assessment = rank_assessment(
        _opportunity(),
        _enrichment(),
        EligibilityResult(eligible=True),
        _career(80.0),
        None,
        _confidence(70.0),
        policy=_policy(),
        scoring_version="v0.2a1",
        alias_registry_version="1",
    )

    assert assessment.priority_score == 78.0
    assert assessment.selected_intent == "CAREER"
    assert assessment.intent_tiers["CAREER"] == "MEDIUM"


def test_hard_fail_discards_all_present_lanes_and_selects_none() -> None:
    assessment = rank_assessment(
        _opportunity(),
        _enrichment(),
        EligibilityResult(eligible=False, hard_fail_reasons=["posting_closed"]),
        _career(95.0),
        _income(95.0),
        _confidence(95.0),
        policy=_policy(),
        scoring_version="v0.2a1",
        alias_registry_version="1",
    )

    assert assessment.intent_tiers == {
        "CAREER": "DISCARD",
        "INCOME_NOW": "DISCARD",
    }
    assert assessment.selected_intent is None
    assert assessment.tier == "DISCARD"


def test_stretch_lane_is_diagnostic_but_not_selected_for_daily_batch() -> None:
    assessment = rank_assessment(
        _opportunity(),
        _enrichment(),
        EligibilityResult(eligible=True),
        _career(60.0),
        None,
        _confidence(90.0),
        policy=_policy(),
        scoring_version="v0.2a1",
        alias_registry_version="1",
    )

    assert assessment.intent_tiers["CAREER"] == "STRETCH"
    assert assessment.selected_intent is None
    assert assessment.tier == "STRETCH"
