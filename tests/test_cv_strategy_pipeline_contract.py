from datetime import datetime, timezone

from app.cv.composer import compose_cv
from app.cv.models import (
    CVPolicy,
    EvidenceCatalogSnapshot,
    MasterFact,
    MasterFactsSnapshot,
)
from app.cv.selector import select_evidence
from app.cv.strategy.builder import build_cv_strategy
from app.cv.strategy.policy import NarrativePolicy
from app.cv.validator import validate_cv
from app.models.domain import Opportunity
from app.radar.models import (
    ConfidenceAssessment,
    DerivedValue,
    EligibilityResult,
    OpportunityEnrichment,
    RadarAssessment,
    Requirement,
)

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def _fact(fact_id: str, kind: str, value: str) -> MasterFact:
    method = "manual_confirmation" if kind in {"identity", "contact"} else "repository_evidence"
    return MasterFact(
        id=fact_id,
        kind=kind,
        value=value,
        track_ids=["tech"],
        verified=True,
        verification_method=method,
        verified_at=NOW,
        source_ref=None if method == "manual_confirmation" else f"https://example.test/{fact_id}",
    )


def _requirement(value: str, importance: str) -> Requirement:
    return Requirement(
        kind="skill",
        value=value,
        importance=importance,
        exactness="conceptual",
        provenance=DerivedValue[str](
            value=value,
            source_text=f"Required: {value}",
            source_field="description",
            extraction_method="explicit_rule",
            confidence=1.0,
        ),
    )


def _assessment(requirements: list[Requirement]) -> RadarAssessment:
    opportunity = Opportunity(
        id="opp-strategy-contract",
        source="synthetic",
        source_id="source-strategy-contract",
        source_url="https://example.test/jobs/data-analyst",
        company="Example Analytics",
        title="Data Analyst",
        description="Python SQL Power BI",
        discovered_at=NOW,
    )
    enrichment = OpportunityEnrichment(
        opportunity_id=opportunity.id,
        normalized_title=DerivedValue[str](
            value="Data Analyst",
            source_field="title",
            extraction_method="source_structured",
            confidence=1.0,
        ),
        requirements=requirements,
        extractor_version="test-v1",
        created_at=NOW,
    )
    return RadarAssessment(
        opportunity=opportunity,
        enrichment=enrichment,
        eligibility=EligibilityResult(eligible=True),
        best_career_track="tech",
        confidence_score=100.0,
        confidence_breakdown=ConfidenceAssessment(
            score=100.0,
            requirement_extraction_quality=100.0,
            skill_normalization_coverage=100.0,
            evidence_traceability=100.0,
            seniority_location_legal_clarity=100.0,
            source_freshness_completeness=100.0,
        ),
        priority_score=100.0,
        selected_intent="CAREER",
        scoring_version="test-v1",
        extractor_version="test-v1",
        alias_registry_version="test-v1",
    )


def _narrative_policy() -> NarrativePolicy:
    return NarrativePolicy(
        version="narrative-policy-v1",
        max_core_messages=3,
        positioning_message_importance=10.0,
        default_section_order=[
            "summary",
            "skills",
            "experience",
            "projects",
            "education",
            "languages",
            "links",
        ],
        requirement_importance_weights={
            "mandatory": 3.0,
            "preferred": 2.0,
            "unknown": 1.0,
        },
        support_level_weights={
            "EXACT_VERIFIED": 3.0,
            "APPROVED_ALIAS": 2.5,
            "TAXONOMY_RELATED": 1.0,
            "UNKNOWN": 0.0,
        },
        priority_requirement_bonus=1.0,
    )


def _build(facts: list[MasterFact], requirements: list[Requirement]):
    master = MasterFactsSnapshot(
        schema_version="v1",
        content_sha256="a" * 64,
        facts=facts,
    )
    catalog = EvidenceCatalogSnapshot(
        schema_version="v1",
        content_sha256="b" * 64,
        modules=[],
    )
    assessment = _assessment(requirements)
    cv_policy = CVPolicy(
        language="en",
        required_identity_kinds=["identity", "contact"],
        required_sections=["skills", "projects"],
    )
    selection = select_evidence(
        enrichment=assessment.enrichment,
        application_track_id="tech",
        master_facts=master,
        evidence_catalog=catalog,
        policy=cv_policy,
    )
    document = compose_cv(
        selection=selection,
        master_facts=master,
        evidence_catalog=catalog,
        policy=cv_policy,
        language="en",
    )
    validation = validate_cv(
        document=document,
        master_facts=master,
        evidence_catalog=catalog,
        application_track_id="tech",
        selection=selection,
    )
    assert validation.valid
    return build_cv_strategy(
        assessment=assessment,
        selection=selection,
        document=document,
        validation=validation,
        policy=_narrative_policy(),
    )


def test_current_selector_composer_and_validator_feed_deterministic_strategy() -> None:
    facts = [
        _fact("identity", "identity", "Alex Example"),
        _fact("contact", "contact", "alex@example.test"),
        _fact("role", "role", "Data & Automation Engineer"),
        _fact("python", "skill", "Python"),
        _fact("sql", "skill", "SQL"),
        _fact("project", "project", "Decision Support API"),
    ]
    requirements = [
        _requirement("Python", "mandatory"),
        _requirement("SQL", "preferred"),
        _requirement("Power BI", "mandatory"),
    ]

    first = _build(facts, requirements)
    second = _build(list(reversed(facts)), list(reversed(requirements)))

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.positioning == "Data & Automation Engineer"
    assert [message.message for message in first.core_messages] == [
        "Data & Automation Engineer",
        "Python",
        "SQL",
    ]
    assert first.explicit_gaps == ["Power BI"]
    assert {"role", "python"}.issubset(first.must_show_fact_ids)
    assert "sql" in first.supporting_fact_ids
