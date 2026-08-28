from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.models.domain import Opportunity, SearchIntent
from app.radar.models import (
    ConfidenceAssessment,
    DiscoveryOrigin,
    EligibilityResult,
    IncomeAssessment,
    OpportunityEnrichment,
    RadarAssessment,
    RankingPenalty,
    Tier,
    TrackCareerAssessment,
    TrackAssessment,
)

SelectionMode = Literal["career_first", "income_first", "balanced"]


@dataclass(frozen=True)
class RadarPolicy:
    high_fit: float = 78.0
    high_confidence: float = 75.0
    medium_fit: float = 65.0
    medium_confidence: float = 65.0
    stretch_fit: float = 55.0
    income_high_fit: float = 75.0
    income_high_confidence: float = 75.0
    income_medium_fit: float = 62.0
    income_medium_confidence: float = 65.0
    fit_weight: float = 0.80
    confidence_weight: float = 0.20
    selection_mode: SelectionMode = "income_first"

    def __post_init__(self) -> None:
        if not (
            0.0 <= self.stretch_fit <= self.medium_fit <= self.high_fit <= 100.0
        ):
            raise ValueError("career fit thresholds must be ordered within 0..100")
        if not (0.0 <= self.medium_confidence <= self.high_confidence <= 100.0):
            raise ValueError("career confidence thresholds must be ordered within 0..100")
        if not (
            0.0
            <= self.stretch_fit
            <= self.income_medium_fit
            <= self.income_high_fit
            <= 100.0
        ):
            raise ValueError("income fit thresholds must be ordered within 0..100")
        if not (
            0.0
            <= self.income_medium_confidence
            <= self.income_high_confidence
            <= 100.0
        ):
            raise ValueError("income confidence thresholds must be ordered within 0..100")
        if round(self.fit_weight + self.confidence_weight, 10) != 1.0:
            raise ValueError("ranking weights must sum to 1")
        if self.selection_mode not in {"career_first", "income_first", "balanced"}:
            raise ValueError("unsupported selection mode")


def classify_fit(
    score: float | None,
    confidence: float,
    policy: RadarPolicy,
) -> Tier | None:
    """Classify the CAREER lane using the preserved V0.2A career thresholds."""
    if score is None:
        return None
    if score >= policy.high_fit and confidence >= policy.high_confidence:
        return "HIGH"
    if score >= policy.medium_fit and confidence >= policy.medium_confidence:
        return "MEDIUM"
    if score >= policy.stretch_fit:
        return "STRETCH"
    return "DISCARD"


def _classify_income_fit(
    score: float | None,
    confidence: float,
    policy: RadarPolicy,
) -> Tier | None:
    if score is None:
        return None
    if score >= policy.income_high_fit and confidence >= policy.income_high_confidence:
        return "HIGH"
    if score >= policy.income_medium_fit and confidence >= policy.income_medium_confidence:
        return "MEDIUM"
    if score >= policy.stretch_fit:
        return "STRETCH"
    return "DISCARD"


def rank_assessment(
    opportunity: Opportunity,
    enrichment: OpportunityEnrichment,
    eligibility: EligibilityResult,
    career: TrackCareerAssessment | None,
    income: IncomeAssessment | None,
    confidence: ConfidenceAssessment,
    *,
    policy: RadarPolicy,
    scoring_version: str,
    alias_registry_version: str,
    ranking_penalties: list[RankingPenalty] | None = None,
    track_assessments: list[TrackAssessment] | None = None,
    discovery_origin: DiscoveryOrigin = "targeted",
) -> RadarAssessment:
    penalties = ranking_penalties or []
    penalty_total = sum(penalty.value for penalty in penalties)

    career_score = career.assessment.overall_score if career is not None else None
    income_score = income.income_viability if income is not None else None

    if eligibility.eligible:
        career_tier = classify_fit(career_score, confidence.score, policy)
        income_tier = _classify_income_fit(income_score, confidence.score, policy)
    else:
        career_tier = "DISCARD" if career_score is not None else None
        income_tier = "DISCARD" if income_score is not None else None

    intent_tiers: dict[str, Tier] = {}
    if career_tier is not None:
        intent_tiers["CAREER"] = career_tier
    if income_tier is not None:
        intent_tiers["INCOME_NOW"] = income_tier

    career_priority = _lane_priority(
        career_score,
        confidence.score,
        policy,
        penalty_total,
    )
    income_priority = _lane_priority(
        income_score,
        confidence.score,
        policy,
        penalty_total,
    )

    selected_intent = _select_intent(
        eligibility=eligibility,
        career_tier=career_tier,
        income_tier=income_tier,
        career_priority=career_priority,
        income_priority=income_priority,
    )

    if not eligibility.eligible:
        priority_score = 0.0
        tier: Tier | None = "DISCARD" if intent_tiers else None
    else:
        present_priorities = [
            priority
            for priority in (career_priority, income_priority)
            if priority is not None
        ]
        priority_score = max(present_priorities, default=0.0)
        tier = _overall_tier(
            selected_intent=selected_intent,
            career_tier=career_tier,
            income_tier=income_tier,
        )

    return RadarAssessment(
        opportunity=opportunity,
        enrichment=enrichment,
        eligibility=eligibility,
        match_assessment=career.assessment if career is not None else None,
        track_assessments=track_assessments or [],
        best_career_track=career.track_id if career is not None else None,
        career_match=career_score,
        best_income_track=income.track_id if income is not None else None,
        income_viability=income_score,
        confidence_score=confidence.score,
        confidence_breakdown=confidence,
        tier=tier,
        intent_tiers=intent_tiers,
        channel_tags=list(enrichment.channel_tags),
        discovery_origin=discovery_origin,
        priority_score=priority_score,
        ranking_penalties=penalties,
        selected_intent=selected_intent,
        scoring_version=scoring_version,
        extractor_version=enrichment.extractor_version,
        alias_registry_version=alias_registry_version,
        taxonomy_versions=dict(enrichment.taxonomy_versions),
    )


def _lane_priority(
    fit: float | None,
    confidence: float,
    policy: RadarPolicy,
    penalty_total: float,
) -> float | None:
    if fit is None:
        return None
    raw = policy.fit_weight * fit + policy.confidence_weight * confidence
    return round(max(0.0, raw - penalty_total), 1)


def _select_intent(
    *,
    eligibility: EligibilityResult,
    career_tier: Tier | None,
    income_tier: Tier | None,
    career_priority: float | None,
    income_priority: float | None,
) -> SearchIntent | None:
    if not eligibility.eligible:
        return None

    candidates: list[tuple[float, SearchIntent]] = []
    if career_tier in {"HIGH", "MEDIUM"} and career_priority is not None:
        candidates.append((career_priority, "CAREER"))
    if income_tier in {"HIGH", "MEDIUM"} and income_priority is not None:
        candidates.append((income_priority, "INCOME_NOW"))
    if not candidates:
        return None

    # Higher priority wins. On exact ties, CAREER wins deterministically so the
    # assessment itself stays stable. Daily selection mode is applied later by
    # the selector, not by mutating the per-opportunity assessment.
    candidates.sort(key=lambda item: (-item[0], 0 if item[1] == "CAREER" else 1))
    return candidates[0][1]


def _overall_tier(
    *,
    selected_intent: SearchIntent | None,
    career_tier: Tier | None,
    income_tier: Tier | None,
) -> Tier | None:
    if selected_intent == "CAREER":
        return career_tier
    if selected_intent == "INCOME_NOW":
        return income_tier

    present = [tier for tier in (career_tier, income_tier) if tier is not None]
    if not present:
        return None
    order: dict[Tier, int] = {
        "HIGH": 4,
        "MEDIUM": 3,
        "STRETCH": 2,
        "DISCARD": 1,
    }
    return max(present, key=order.__getitem__)
