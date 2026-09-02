from datetime import datetime, timezone
from pathlib import Path

from app.models.domain import CandidateProfile, CandidateTrack, EvidenceItem, Opportunity
from app.radar.models import (
    ConfidenceAssessment,
    DerivedValue,
    EligibilityResult,
    OpportunityEnrichment,
    Requirement,
    TrackCareerAssessment,
)
from app.radar.ranking import RadarPolicy, rank_assessment
from app.radar.scoring import assess_career
from app.radar.taxonomy import AliasRegistry, TaxonomyResolver

NOW = datetime(2026, 9, 2, 2, 0, tzinfo=timezone.utc)


def resolver() -> TaxonomyResolver:
    return TaxonomyResolver(alias_registry=AliasRegistry.load(Path("data/skill_aliases.yaml")))


def opportunity() -> Opportunity:
    return Opportunity(
        id="manual:dogfood",
        source="manual",
        source_id="dogfood",
        source_url="https://example.com/job",
        company="Example",
        title="Software Engineer",
        description="Software engineering role",
        discovered_at=NOW,
        published_at=NOW,
        remote_policy="remote",
        required_skills=[],
    )


def requirement(
    value: str,
    *,
    kind: str = "skill",
    importance: str = "mandatory",
) -> Requirement:
    return Requirement(
        kind=kind,
        value=value,
        importance=importance,
        exactness="conceptual",
        provenance=DerivedValue(
            value=value,
            source_text=f"Minimum: {value}",
            source_field="description",
            extraction_method="explicit_rule",
            confidence=0.9,
        ),
    )


def enrichment(requirements: list[Requirement]) -> OpportunityEnrichment:
    return OpportunityEnrichment(
        opportunity_id="manual:dogfood",
        requirements=requirements,
        extractor_version="test",
        created_at=NOW,
    )


def profile(track: CandidateTrack) -> CandidateProfile:
    return CandidateProfile(
        name="Candidate",
        skills=["Python"],
        locations=["Argentina"],
        remote_preferences=["remote"],
        tracks=[track],
    )


def confidence() -> ConfidenceAssessment:
    return ConfidenceAssessment(
        score=90.0,
        requirement_extraction_quality=90.0,
        skill_normalization_coverage=90.0,
        evidence_traceability=90.0,
        seniority_location_legal_clarity=90.0,
        source_freshness_completeness=90.0,
    )


def test_verified_evidence_skills_count_as_candidate_skills() -> None:
    linux_evidence = EvidenceItem(
        label="Verified IT support",
        type="experience",
        skills=["Linux"],
        verified=True,
    )
    track = CandidateTrack(
        id="career",
        label="Career",
        intents=["CAREER"],
        skills=["Python"],
        evidence=[linux_evidence],
        accepted_work_modes=["remote"],
    )

    assessment = assess_career(
        opportunity(),
        enrichment([requirement("Linux")]),
        profile(track),
        track,
        resolver(),
        now=NOW,
    )

    assert assessment.mandatory_fit == 100.0
    assert assessment.gaps == []
    assert assessment.strengths == ["Linux"]


def test_mandatory_numeric_experience_is_not_ignored_by_career_score() -> None:
    track = CandidateTrack(
        id="career",
        label="Career",
        intents=["CAREER"],
        skills=["Python"],
        accepted_work_modes=["remote"],
    )
    exp = "4+ years of software development experience"

    assessment = assess_career(
        opportunity(),
        enrichment([requirement("Python"), requirement(exp, kind="experience")]),
        profile(track),
        track,
        resolver(),
        now=NOW,
    )

    assert assessment.mandatory_fit == 50.0
    assert exp in assessment.gaps
    assert "mandatory_experience_unverified" in assessment.risks


def test_unverified_mandatory_numeric_experience_caps_career_tier_at_stretch() -> None:
    track = CandidateTrack(
        id="career",
        label="Career",
        intents=["CAREER"],
        skills=["Python"],
        accepted_work_modes=["remote"],
    )
    exp = "4+ years of software development experience"
    assessment = assess_career(
        opportunity(),
        enrichment([requirement("Python"), requirement(exp, kind="experience")]),
        profile(track),
        track,
        resolver(),
        now=NOW,
    )

    ranked = rank_assessment(
        opportunity(),
        enrichment([requirement("Python"), requirement(exp, kind="experience")]),
        EligibilityResult(eligible=True),
        TrackCareerAssessment(track_id="career", assessment=assessment),
        None,
        confidence(),
        policy=RadarPolicy(medium_fit=30.0, stretch_fit=20.0, high_fit=90.0),
        scoring_version="test",
        alias_registry_version="test",
    )

    assert ranked.intent_tiers["CAREER"] == "STRETCH"


def test_preferred_numeric_experience_does_not_create_mandatory_risk() -> None:
    track = CandidateTrack(
        id="career",
        label="Career",
        intents=["CAREER"],
        skills=["Python"],
        accepted_work_modes=["remote"],
    )
    exp = "4+ years of software development experience"

    assessment = assess_career(
        opportunity(),
        enrichment([requirement(exp, kind="experience", importance="preferred")]),
        profile(track),
        track,
        resolver(),
        now=NOW,
    )

    assert "mandatory_experience_unverified" not in assessment.risks


def test_verified_relevant_experience_can_satisfy_numeric_minimum() -> None:
    evidence = EvidenceItem(
        label="5 years software engineering",
        type="experience",
        skills=["Python"],
        domains=["software"],
        verified=True,
    )
    track = CandidateTrack(
        id="career",
        label="Career",
        intents=["CAREER"],
        skills=["Python"],
        evidence=[evidence],
        accepted_work_modes=["remote"],
    )
    exp = "4+ years of software development experience"

    assessment = assess_career(
        opportunity(),
        enrichment([requirement("Python"), requirement(exp, kind="experience")]),
        profile(track),
        track,
        resolver(),
        now=NOW,
    )

    assert assessment.mandatory_fit == 100.0
    assert exp in assessment.strengths
    assert "mandatory_experience_unverified" not in assessment.risks


def test_irrelevant_experience_does_not_satisfy_numeric_minimum() -> None:
    evidence = EvidenceItem(
        label="5 years kitchen operations",
        type="experience",
        skills=["food safety"],
        domains=["gastronomy"],
        verified=True,
    )
    track = CandidateTrack(
        id="career",
        label="Career",
        intents=["CAREER"],
        skills=["Python"],
        evidence=[evidence],
        accepted_work_modes=["remote"],
    )
    exp = "4+ years of software development experience"

    assessment = assess_career(
        opportunity(),
        enrichment([requirement("Python"), requirement(exp, kind="experience")]),
        profile(track),
        track,
        resolver(),
        now=NOW,
    )

    assert assessment.mandatory_fit == 50.0
    assert exp in assessment.gaps
    assert "mandatory_experience_unverified" in assessment.risks
