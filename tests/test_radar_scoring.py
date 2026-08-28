from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.domain import CandidateProfile, CandidateTrack, EvidenceItem, Opportunity
from app.radar.models import DerivedValue, OpportunityEnrichment, Requirement
from app.radar.scoring import assess_career, assess_income, best_track_assessments
from app.radar.taxonomy import AliasRegistry, TaxonomyResolver

NOW = datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc)


def _resolver() -> TaxonomyResolver:
    return TaxonomyResolver(
        alias_registry=AliasRegistry.load(Path("data/skill_aliases.yaml"))
    )


def _opportunity(**overrides) -> Opportunity:
    data = {
        "id": "manual:score-1",
        "source": "manual",
        "source_id": "score-1",
        "source_url": "https://example.com/jobs/score-1",
        "company": "Example Co",
        "title": "Example Role",
        "description": "Example role",
        "discovered_at": NOW,
        "published_at": NOW - timedelta(days=1),
    }
    data.update(overrides)
    return Opportunity(**data)


def _profile(*, tracks: list[CandidateTrack], **overrides) -> CandidateProfile:
    data = {
        "name": "Test Candidate",
        "skills": ["Python", "PostGIS"],
        "domains": ["technology"],
        "locations": ["Córdoba, Argentina"],
        "remote_preferences": ["remote", "onsite"],
        "tracks": tracks,
    }
    data.update(overrides)
    return CandidateProfile(**data)


def _track(
    track_id: str,
    *,
    intents: list[str],
    skills: list[str],
    domains: list[str] | None = None,
    roles: list[str] | None = None,
    evidence: list[EvidenceItem] | None = None,
    accepted_work_modes: list[str] | None = None,
    no_go_constraints: list[str] | None = None,
) -> CandidateTrack:
    return CandidateTrack(
        id=track_id,
        label=track_id.replace("_", " ").title(),
        intents=intents,
        skills=skills,
        domains=domains or [],
        roles=roles or [],
        evidence=evidence or [],
        accepted_work_modes=accepted_work_modes or [],
        no_go_constraints=no_go_constraints or [],
    )


def _derived(value, *, field: str) -> DerivedValue:
    return DerivedValue(
        value=value,
        source_field=field,
        extraction_method="source_structured",
        confidence=1.0,
    )


def _requirement(
    value: str,
    *,
    kind: str = "skill",
    importance: str = "mandatory",
    exactness: str = "conceptual",
) -> Requirement:
    return Requirement(
        kind=kind,
        value=value,
        importance=importance,
        exactness=exactness,
        provenance=_derived(value, field="description"),
    )


def _enrichment(requirements: list[Requirement], **overrides) -> OpportunityEnrichment:
    data = {
        "opportunity_id": "manual:score-1",
        "requirements": requirements,
        "extractor_version": "test",
        "created_at": NOW,
    }
    data.update(overrides)
    return OpportunityEnrichment(**data)


def test_track_scoped_career_does_not_inherit_root_or_other_track_skills() -> None:
    tech = _track(
        "tech_geospatial",
        intents=["CAREER"],
        skills=["Python", "PostGIS"],
        domains=["gis"],
    )
    gastronomy = _track(
        "gastronomy_operations",
        intents=["INCOME_NOW"],
        skills=["food safety", "stock"],
        domains=["gastronomy"],
    )
    profile = _profile(tracks=[tech, gastronomy])
    opportunity = _opportunity(
        title="Python GIS Developer",
        description="Python GIS engineering",
        required_skills=["Python"],
    )
    enrichment = _enrichment([_requirement("Python")])

    assessment = assess_career(
        opportunity,
        enrichment,
        profile,
        gastronomy,
        _resolver(),
        now=NOW,
    )

    assert assessment.mandatory_fit == 0.0
    assert assessment.strengths == []
    assert "Python" in assessment.gaps


def test_approved_alias_gets_full_career_credit() -> None:
    track = _track("data", intents=["CAREER"], skills=["PostgreSQL"])
    profile = _profile(tracks=[track])

    assessment = assess_career(
        _opportunity(required_skills=[]),
        _enrichment([_requirement("postgres")]),
        profile,
        track,
        _resolver(),
        now=NOW,
    )

    assert assessment.mandatory_fit == 100.0
    assert assessment.strengths == ["postgres"]


def test_taxonomy_related_skill_is_partial_not_full_career_credit() -> None:
    track = _track("geo", intents=["CAREER"], skills=["PostGIS"])
    profile = _profile(tracks=[track])

    assessment = assess_career(
        _opportunity(required_skills=[]),
        _enrichment([_requirement("spatial database", exactness="conceptual")]),
        profile,
        track,
        _resolver(),
        now=NOW,
    )

    assert assessment.mandatory_fit == 70.0
    assert assessment.overall_score < 100.0


def test_exact_product_does_not_accept_related_taxonomy_as_satisfaction() -> None:
    track = _track("geo", intents=["CAREER"], skills=["PostGIS"])
    profile = _profile(tracks=[track])

    assessment = assess_career(
        _opportunity(required_skills=[]),
        _enrichment(
            [_requirement("spatial database", exactness="exact_product")]
        ),
        profile,
        track,
        _resolver(),
        now=NOW,
    )

    assert assessment.mandatory_fit == 0.0
    assert "spatial database" in assessment.gaps


def test_income_score_uses_exact_component_weights_and_unknown_neutral() -> None:
    track = _track(
        "ops",
        intents=["INCOME_NOW"],
        skills=["Python"],
        accepted_work_modes=["remote"],
    )
    profile = _profile(tracks=[track], verified_licenses=[])
    opportunity = _opportunity(
        remote_policy="remote",
        published_at=NOW - timedelta(days=10),
    )
    enrichment = _enrichment(
        [
            _requirement("Python"),
            _requirement("SQL"),
            _requirement("Professional License C", kind="license", exactness="declarative"),
        ]
    )

    assessment = assess_income(
        opportunity,
        enrichment,
        profile,
        track,
        _resolver(),
        now=NOW,
    )

    assert assessment.capability_fit == 50.0
    assert assessment.logistics_fit == 100.0
    assert assessment.schedule_fit == 50.0
    assert assessment.entry_friction_fit == 50.0
    assert assessment.freshness_fit == 75.0
    assert assessment.income_viability == 65.0
    assert "Professional License C" in assessment.unknown_barriers


def test_kitchen_role_can_be_high_income_without_high_tech_career_score() -> None:
    tech = _track(
        "tech_geospatial",
        intents=["CAREER"],
        skills=["Python", "PostGIS"],
        domains=["gis"],
    )
    kitchen_evidence = EvidenceItem(
        label="Kitchen operations",
        type="experience",
        skills=["food safety", "stock"],
        domains=["gastronomy"],
        verified=True,
    )
    kitchen = _track(
        "gastronomy_operations",
        intents=["INCOME_NOW"],
        skills=["food safety", "stock"],
        domains=["gastronomy"],
        evidence=[kitchen_evidence],
        accepted_work_modes=["onsite"],
    )
    profile = _profile(tracks=[tech, kitchen])
    opportunity = _opportunity(
        title="Kitchen Shift Lead",
        description="Food safety and stock operations in gastronomy",
        location="Córdoba, Argentina",
        remote_policy="onsite",
        required_skills=["food safety", "stock"],
    )
    enrichment = _enrichment(
        [_requirement("food safety"), _requirement("stock")],
        work_schedule=_derived("day shift", field="work_schedule"),
    )

    income = assess_income(
        opportunity,
        enrichment,
        profile,
        kitchen,
        _resolver(),
        now=NOW,
    )
    career = assess_career(
        opportunity,
        enrichment,
        profile,
        tech,
        _resolver(),
        now=NOW,
    )

    assert income.income_viability == 100.0
    assert career.overall_score < 55.0


def test_best_tracks_are_selected_per_intent_without_cross_contamination() -> None:
    career_b = _track(
        "career_b",
        intents=["CAREER"],
        skills=["Python"],
        domains=["gis"],
    )
    career_a = _track(
        "career_a",
        intents=["CAREER"],
        skills=["Python"],
        domains=["gis"],
    )
    income = _track(
        "income",
        intents=["INCOME_NOW"],
        skills=["Python"],
        accepted_work_modes=["remote"],
    )
    profile = _profile(tracks=[career_b, income, career_a])
    opportunity = _opportunity(
        title="Python GIS Role",
        description="Python GIS work",
        required_skills=["Python"],
        remote_policy="remote",
    )
    enrichment = _enrichment([_requirement("Python")])

    best_career, best_income = best_track_assessments(
        opportunity,
        enrichment,
        profile,
        _resolver(),
        now=NOW,
    )

    assert best_career is not None
    assert best_career.track_id == "career_a"
    assert best_income is not None
    assert best_income.track_id == "income"


def test_best_tracks_return_none_when_intent_is_not_supported() -> None:
    career = _track("career", intents=["CAREER"], skills=["Python"])
    profile = _profile(tracks=[career])

    best_career, best_income = best_track_assessments(
        _opportunity(required_skills=["Python"]),
        _enrichment([_requirement("Python")]),
        profile,
        _resolver(),
        now=NOW,
    )

    assert best_career is not None
    assert best_income is None
