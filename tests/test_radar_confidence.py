from datetime import datetime, timezone

from app.models.domain import EvidenceItem, OpportunityAssessment
from app.radar.confidence import score_confidence
from app.radar.models import (
    DerivedValue,
    IncomeAssessment,
    OpportunityEnrichment,
    Requirement,
    TrackCareerAssessment,
)

NOW = datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc)


def _requirement(confidence: float, *, method: str = "explicit_rule") -> Requirement:
    value = "Python"
    return Requirement(
        kind="skill",
        value=value,
        importance="mandatory",
        exactness="conceptual",
        provenance=DerivedValue(
            value=value,
            source_text="Python required." if method != "source_structured" else None,
            source_field="description" if method != "source_structured" else "required_skills",
            extraction_method=method,
            confidence=confidence,
        ),
    )


def _enrichment(
    *,
    requirement_confidence: float,
    source_reliability: str = "DIRECT_ATS",
    freshness_quality: str = "DIRECT_TIMESTAMP",
    taxonomy_versions: dict[str, str] | None = None,
) -> OpportunityEnrichment:
    return OpportunityEnrichment(
        opportunity_id="job-1",
        requirements=[_requirement(requirement_confidence)],
        region=DerivedValue(
            value="Córdoba, Argentina",
            source_field="location",
            extraction_method="source_structured",
            confidence=1.0,
        ),
        seniority=DerivedValue(
            value="mid",
            source_field="title",
            extraction_method="explicit_rule",
            source_text="Mid Python Developer",
            confidence=0.9,
        ),
        source_reliability=source_reliability,
        source_freshness_quality=freshness_quality,
        extractor_version="rules-v1",
        taxonomy_versions=taxonomy_versions or {},
        created_at=NOW,
    )


def _career(score: float = 80.0, *, with_evidence: bool = True) -> TrackCareerAssessment:
    evidence = (
        [
            EvidenceItem(
                label="Verified Python project",
                type="project",
                skills=["Python"],
                domains=["software"],
                verified=True,
            )
        ]
        if with_evidence
        else []
    )
    return TrackCareerAssessment(
        track_id="career",
        assessment=OpportunityAssessment(
            opportunity_id="job-1",
            overall_score=score,
            mandatory_fit=80.0,
            domain_fit=80.0,
            evidence_fit=80.0,
            location_fit=100.0,
            freshness_fit=100.0,
            strengths=["Python"],
            gaps=[],
            risks=[],
            evidence=evidence,
            recommendation="apply",
            explanation="fixture",
        ),
    )


def _income(score: float = 82.0) -> IncomeAssessment:
    return IncomeAssessment(
        track_id="income",
        income_viability=score,
        capability_fit=80.0,
        logistics_fit=100.0,
        schedule_fit=50.0,
        entry_friction_fit=100.0,
        freshness_fit=100.0,
        matched_capabilities=["Python"],
        gaps=[],
        unknown_barriers=[],
    )


def test_stronger_requirement_provenance_raises_confidence_not_fit() -> None:
    career = _career(score=81.0)
    income = _income(score=84.0)

    weak = score_confidence(
        _enrichment(requirement_confidence=0.5),
        career,
        income,
    )
    strong = score_confidence(
        _enrichment(requirement_confidence=1.0),
        career,
        income,
    )

    assert strong.requirement_extraction_quality > weak.requirement_extraction_quality
    assert strong.score > weak.score
    assert career.assessment.overall_score == 81.0
    assert income.income_viability == 84.0


def test_missing_taxonomy_snapshot_is_not_fatal() -> None:
    result = score_confidence(
        _enrichment(requirement_confidence=1.0, taxonomy_versions={}),
        _career(),
        _income(),
    )

    assert 0.0 <= result.skill_normalization_coverage <= 100.0
    assert 0.0 <= result.score <= 100.0


def test_confidence_weighted_sum_is_exact_and_deterministic() -> None:
    enrichment = _enrichment(
        requirement_confidence=0.8,
        source_reliability="AGGREGATOR",
        freshness_quality="DELAYED_TIMESTAMP",
    )

    first = score_confidence(enrichment, _career(with_evidence=False), _income())
    second = score_confidence(enrichment, _career(with_evidence=False), _income())

    expected = round(
        0.25 * first.requirement_extraction_quality
        + 0.20 * first.skill_normalization_coverage
        + 0.20 * first.evidence_traceability
        + 0.20 * first.seniority_location_legal_clarity
        + 0.15 * first.source_freshness_completeness,
        1,
    )
    assert first == second
    assert first.score == expected
