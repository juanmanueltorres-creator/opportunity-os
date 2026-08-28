from __future__ import annotations

from statistics import fmean

from app.radar.models import (
    ConfidenceAssessment,
    IncomeAssessment,
    OpportunityEnrichment,
    TrackCareerAssessment,
)


_REQUIREMENT_WEIGHT = 0.25
_NORMALIZATION_WEIGHT = 0.20
_EVIDENCE_WEIGHT = 0.20
_CLARITY_WEIGHT = 0.20
_SOURCE_WEIGHT = 0.15

_SOURCE_RELIABILITY = {
    "DIRECT_ATS": 100.0,
    "DIRECT_OFFICIAL": 100.0,
    "AGGREGATOR": 75.0,
    "MANUAL": 60.0,
    "UNKNOWN": 50.0,
}
_FRESHNESS_QUALITY = {
    "DIRECT_TIMESTAMP": 100.0,
    "DELAYED_TIMESTAMP": 75.0,
    "DISCOVERED_AT_ONLY": 50.0,
    "UNKNOWN": 50.0,
}


def score_confidence(
    enrichment: OpportunityEnrichment,
    career: TrackCareerAssessment | None,
    income: IncomeAssessment | None,
) -> ConfidenceAssessment:
    """Measure confidence in the inputs used by ranking, never candidate fit itself."""

    requirement_quality = _requirement_extraction_quality(enrichment)
    normalization_coverage = _skill_normalization_coverage(enrichment)
    evidence_traceability = _evidence_traceability(career, income)
    clarity = _seniority_location_legal_clarity(enrichment)
    source_quality = _source_freshness_completeness(enrichment)

    score = round(
        _REQUIREMENT_WEIGHT * requirement_quality
        + _NORMALIZATION_WEIGHT * normalization_coverage
        + _EVIDENCE_WEIGHT * evidence_traceability
        + _CLARITY_WEIGHT * clarity
        + _SOURCE_WEIGHT * source_quality,
        1,
    )

    return ConfidenceAssessment(
        score=score,
        requirement_extraction_quality=requirement_quality,
        skill_normalization_coverage=normalization_coverage,
        evidence_traceability=evidence_traceability,
        seniority_location_legal_clarity=clarity,
        source_freshness_completeness=source_quality,
    )


def _requirement_extraction_quality(enrichment: OpportunityEnrichment) -> float:
    if not enrichment.requirements:
        return 50.0
    return _average_percent(
        requirement.provenance.confidence
        for requirement in enrichment.requirements
    )


def _skill_normalization_coverage(enrichment: OpportunityEnrichment) -> float:
    skill_requirements = [
        requirement
        for requirement in enrichment.requirements
        if requirement.kind == "skill"
    ]
    if not skill_requirements:
        return 50.0

    # Coverage here is confidence that skill terms were extracted cleanly enough to
    # normalize. Candidate match results are deliberately excluded so a poor fit
    # cannot masquerade as poor data quality (or vice versa).
    return _average_percent(
        requirement.provenance.confidence
        for requirement in skill_requirements
    )


def _evidence_traceability(
    career: TrackCareerAssessment | None,
    income: IncomeAssessment | None,
) -> float:
    if career is not None and career.assessment.evidence:
        # V0.1 only exposes verified evidence in OpportunityAssessment.evidence.
        return 100.0
    if career is not None or income is not None:
        # Absence of selected evidence is neutral confidence, not a fit penalty.
        return 50.0
    return 50.0


def _seniority_location_legal_clarity(
    enrichment: OpportunityEnrichment,
) -> float:
    seniority = (
        enrichment.seniority.confidence * 100.0
        if enrichment.seniority is not None
        else 50.0
    )
    location_values = [
        value
        for value in (enrichment.country, enrichment.region)
        if value is not None
    ]
    location = (
        max(value.confidence for value in location_values) * 100.0
        if location_values
        else 50.0
    )

    legal_requirements = [
        requirement
        for requirement in enrichment.requirements
        if requirement.importance == "mandatory"
        and requirement.kind in {"license", "work_authorization"}
    ]
    legal = (
        _average_percent(
            requirement.provenance.confidence
            for requirement in legal_requirements
        )
        if legal_requirements
        else 50.0
    )

    return round(fmean((seniority, location, legal)), 1)


def _source_freshness_completeness(enrichment: OpportunityEnrichment) -> float:
    reliability = _SOURCE_RELIABILITY[enrichment.source_reliability]
    freshness = _FRESHNESS_QUALITY[enrichment.source_freshness_quality]
    return round(fmean((reliability, freshness)), 1)


def _average_percent(values) -> float:
    materialized = list(values)
    if not materialized:
        return 50.0
    return round(fmean(materialized) * 100.0, 1)
