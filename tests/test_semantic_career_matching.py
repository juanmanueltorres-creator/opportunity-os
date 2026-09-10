from datetime import datetime, timezone
from pathlib import Path

from app.models.domain import CandidateProfile, CandidateTrack, EvidenceItem, Opportunity
from app.radar.models import ConfidenceAssessment, DerivedValue, EligibilityResult, OpportunityEnrichment, Requirement, TrackCareerAssessment
from app.radar.ranking import RadarPolicy, rank_assessment
from app.radar.scoring import assess_career
from app.radar.taxonomy import AliasRegistry, TaxonomyResolver

NOW = datetime(2026, 9, 10, 5, 25, tzinfo=timezone.utc)


def resolver() -> TaxonomyResolver:
    return TaxonomyResolver(alias_registry=AliasRegistry.load(Path("data/skill_aliases.yaml")))


def opportunity(**overrides) -> Opportunity:
    data = dict(
        id="manual:semantic",
        source="manual",
        source_id="semantic",
        source_url="https://example.com/job",
        company="Example",
        title="Software Engineer",
        description="Software engineering role",
        discovered_at=NOW,
        published_at=NOW,
        remote_policy="remote",
        required_skills=[],
    )
    data.update(overrides)
    return Opportunity(**data)


def requirement(value: str, *, kind: str = "skill", importance: str = "mandatory") -> Requirement:
    return Requirement(
        kind=kind,
        value=value,
        importance=importance,
        exactness="conceptual",
        provenance=DerivedValue(
            value=value,
            source_text=value,
            source_field="description",
            extraction_method="explicit_rule",
            confidence=0.9,
        ),
    )


def enrichment(requirements: list[Requirement]) -> OpportunityEnrichment:
    return OpportunityEnrichment(
        opportunity_id="manual:semantic",
        requirements=requirements,
        extractor_version="test",
        created_at=NOW,
    )


def profile(track: CandidateTrack) -> CandidateProfile:
    return CandidateProfile(
        name="Candidate",
        roles=list(track.roles),
        skills=list(track.skills),
        domains=list(track.domains),
        locations=["Argentina"],
        remote_preferences=["remote"],
        evidence=list(track.evidence),
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


def test_career_domain_fit_is_compatibility_not_fraction_of_candidate_domains() -> None:
    evidence = EvidenceItem(label="Verified software platform", type="project", skills=["Python"], domains=["software"], verified=True)
    track = CandidateTrack(
        id="career", label="Career", intents=["CAREER"], roles=["Software Engineer"], skills=["Python"],
        domains=["software", "geospatial", "applied AI"], evidence=[evidence], accepted_work_modes=["remote"],
    )
    assessment = assess_career(
        opportunity(title="Backend Software Engineer", description="Build software systems and backend integrations"),
        enrichment([requirement("Python")]), profile(track), track, resolver(), now=NOW,
    )
    assert assessment.domain_fit == 100.0


def test_role_shaped_requirement_can_match_verified_candidate_role() -> None:
    track = CandidateTrack(
        id="career", label="Career", intents=["CAREER"], roles=["Product Engineer"], skills=["Python"],
        domains=["software"], accepted_work_modes=["remote"],
    )
    assessment = assess_career(
        opportunity(title="Product Engineer", description="Product engineering role in software"),
        enrichment([requirement("Product Engineering")]), profile(track), track, resolver(), now=NOW,
    )
    assert assessment.mandatory_fit == 100.0
    assert "Product Engineering" in assessment.strengths


def test_role_shaped_requirement_does_not_match_unrelated_candidate_role() -> None:
    track = CandidateTrack(
        id="career", label="Career", intents=["CAREER"], roles=["Product Engineer"], skills=["Python"],
        domains=["software"], accepted_work_modes=["remote"],
    )
    assessment = assess_career(
        opportunity(title="Account Executive", description="Enterprise sales and account management"),
        enrichment([requirement("Account Executive")]), profile(track), track, resolver(), now=NOW,
    )
    assert assessment.mandatory_fit == 0.0
    assert "Account Executive" in assessment.gaps


def test_role_match_can_be_backed_by_verified_domain_relevant_project_evidence() -> None:
    evidence = EvidenceItem(
        label="Opportunity workflow product", type="project", skills=["Python", "Automation"], domains=["software"], verified=True,
    )
    track = CandidateTrack(
        id="career", label="Career", intents=["CAREER"], roles=["Product Engineer"], skills=["Python", "Automation"],
        domains=["software", "geospatial"], evidence=[evidence], accepted_work_modes=["remote"],
    )
    assessment = assess_career(
        opportunity(title="Product Engineer", description="Product engineering for software integrations and automation"),
        enrichment([requirement("Product Engineering")]), profile(track), track, resolver(), now=NOW,
    )
    assert assessment.evidence_fit == 100.0
    assert [item.label for item in assessment.evidence] == ["Opportunity workflow product"]


def test_bord_like_role_is_selectable_with_duration_gap_visible() -> None:
    evidence = [
        EvidenceItem(
            label="GeoPlatform - full stack platform", type="project",
            skills=["React", "Python", "FastAPI", "PostgreSQL", "Automation"], domains=["software", "geospatial"], verified=True,
        ),
        EvidenceItem(
            label="Opportunity OS - application workflow system", type="project",
            skills=["Python", "Automation", "CI/CD"], domains=["software", "applied AI"], verified=True,
        ),
    ]
    track = CandidateTrack(
        id="career", label="Software / Product Engineering", intents=["CAREER"],
        roles=["Software Engineer", "Product Engineer", "Full Stack Developer"],
        skills=["React", "Python", "FastAPI", "PostgreSQL", "Automation", "CI/CD"],
        domains=["software", "geospatial", "applied AI"], evidence=evidence, accepted_work_modes=["remote"],
    )
    exp = "3 años de experiencia en desarrollo de software (backend preferentemente)"
    opp = opportunity(
        title="Product Engineer",
        description="Product engineering role combining software engineering, integrations, automation, QA and product stakeholders",
        remote_policy="remote",
    )
    enr = enrichment([requirement(exp, kind="experience"), requirement("Product Engineering", importance="preferred")])
    assessment = assess_career(opp, enr, profile(track), track, resolver(), now=NOW)
    ranked = rank_assessment(
        opp, enr, EligibilityResult(eligible=True), TrackCareerAssessment(track_id="career", assessment=assessment), None,
        confidence(), policy=RadarPolicy(), scoring_version="test", alias_registry_version="test",
    )
    assert assessment.mandatory_fit == 50.0
    assert assessment.domain_fit == 100.0
    assert assessment.evidence_fit == 100.0
    assert assessment.overall_score >= 65.0
    assert assessment.recommendation == "apply"
    assert exp in assessment.gaps
    assert "experience_duration_unverified" in assessment.risks
    assert ranked.intent_tiers["CAREER"] in {"MEDIUM", "HIGH"}
    assert ranked.selected_intent == "CAREER"


def test_exact_product_requirement_does_not_use_role_fallback() -> None:
    track = CandidateTrack(
        id="career",
        label="Career",
        intents=["CAREER"],
        roles=["Product Engineer"],
        skills=["Python"],
        domains=["software"],
        accepted_work_modes=["remote"],
    )
    req = requirement("Product Engineering").model_copy(update={"exactness": "exact_product"})
    assessment = assess_career(
        opportunity(title="Product Engineer", description="Product engineering role in software"),
        enrichment([req]),
        profile(track),
        track,
        resolver(),
        now=NOW,
    )
    assert assessment.mandatory_fit == 0.0
    assert "Product Engineering" in assessment.gaps


def test_role_backed_evidence_requires_a_matched_opportunity_domain() -> None:
    evidence = EvidenceItem(
        label="Unrelated geospatial project",
        type="project",
        skills=["QGIS"],
        domains=["geospatial"],
        verified=True,
    )
    track = CandidateTrack(
        id="career",
        label="Career",
        intents=["CAREER"],
        roles=["Product Engineer"],
        skills=["Python"],
        domains=["software", "geospatial"],
        evidence=[evidence],
        accepted_work_modes=["remote"],
    )
    assessment = assess_career(
        opportunity(title="Product Engineer", description="Product engineering role for software products"),
        enrichment([requirement("Product Engineering")]),
        profile(track),
        track,
        resolver(),
        now=NOW,
    )
    assert assessment.mandatory_fit == 100.0
    assert assessment.domain_fit == 100.0
    assert assessment.evidence_fit == 0.0
    assert assessment.evidence == []
