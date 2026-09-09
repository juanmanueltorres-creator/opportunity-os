from datetime import datetime, timezone

import pytest

from app.cv.models import (
    ClaimProvenance,
    CVClaim,
    CVDocumentModel,
    CVEntry,
    EvidenceSelection,
    RequirementSupport,
    ValidationIssue,
    ValidationResult,
)
from app.cv.strategy.builder import build_cv_strategy
from app.cv.strategy.models import StrategyTrackConfig
from app.cv.strategy.policy import NarrativePolicy
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


def _policy() -> NarrativePolicy:
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


def _assessment(*requirements: Requirement, title: str = "Senior BI Specialist") -> RadarAssessment:
    opportunity = Opportunity(
        id="opp-1",
        source="synthetic",
        source_id="source-1",
        source_url="https://example.test/job/1",
        company="Example Co",
        title=title,
        description="Synthetic job description",
        discovered_at=NOW,
    )
    enrichment = OpportunityEnrichment(
        opportunity_id=opportunity.id,
        normalized_title=DerivedValue[str](
            value=title,
            source_field="title",
            extraction_method="source_structured",
            confidence=1.0,
        ),
        requirements=list(requirements),
        extractor_version="test-v1",
        created_at=NOW,
    )
    return RadarAssessment(
        opportunity=opportunity,
        enrichment=enrichment,
        eligibility=EligibilityResult(eligible=True),
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


def _document() -> CVDocumentModel:
    claims = [
        CVClaim(
            claim_id="fact:role-data",
            section="headline",
            kind="headline",
            text="Data Engineer",
        ),
        CVClaim(
            claim_id="fact:skill-python",
            section="skills",
            kind="skill",
            text="Python",
        ),
        CVClaim(
            claim_id="fact:skill-sql",
            section="skills",
            kind="skill",
            text="SQL",
        ),
    ]
    return CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=claims,
        entries=[
            CVEntry(entry_id="section:headline", section="headline", claim_ids=["fact:role-data"]),
            CVEntry(
                entry_id="section:skills",
                section="skills",
                claim_ids=["fact:skill-python", "fact:skill-sql"],
            ),
        ],
        provenance_map={
            "fact:role-data": ClaimProvenance(fact_ids=["role-data"], evidence_ids=[]),
            "fact:skill-python": ClaimProvenance(fact_ids=["skill-python"], evidence_ids=["module-python"]),
            "fact:skill-sql": ClaimProvenance(fact_ids=["skill-sql"], evidence_ids=[]),
        },
    )


def _validation() -> ValidationResult:
    return ValidationResult(
        valid=True,
        validated_claim_ids=[
            "fact:role-data",
            "fact:skill-python",
            "fact:skill-sql",
        ],
    )


def _selection() -> EvidenceSelection:
    return EvidenceSelection(
        application_track_id="tech",
        selected_fact_ids=["role-data", "skill-python", "skill-sql"],
        selected_evidence_ids=["module-python"],
        requirement_support={
            "Python": RequirementSupport(
                requirement="Python",
                support_level="EXACT_VERIFIED",
                fact_ids=["skill-python"],
                evidence_ids=[],
                explanation="Python exactly supported",
            ),
            "SQL": RequirementSupport(
                requirement="SQL",
                support_level="EXACT_VERIFIED",
                fact_ids=["skill-sql"],
                evidence_ids=[],
                explanation="SQL exactly supported",
            ),
            "Power BI": RequirementSupport(
                requirement="Power BI",
                support_level="UNKNOWN",
                fact_ids=[],
                evidence_ids=[],
                explanation="No verified support for Power BI",
            ),
        },
        unsupported_requirements=["Power BI"],
    )


def test_strategy_requires_valid_semantic_document() -> None:
    invalid = ValidationResult(
        valid=False,
        errors=[ValidationIssue(code="bad", message="synthetic failure")],
        validated_claim_ids=[],
    )

    with pytest.raises(ValueError, match="strategy_requires_valid_semantic_document"):
        build_cv_strategy(
            assessment=_assessment(_requirement("Python", "mandatory")),
            selection=_selection(),
            document=_document(),
            validation=invalid,
            policy=_policy(),
        )


def test_target_seniority_does_not_become_candidate_positioning() -> None:
    strategy = build_cv_strategy(
        assessment=_assessment(
            _requirement("Python", "mandatory"),
            _requirement("SQL", "preferred"),
            _requirement("Power BI", "mandatory"),
        ),
        selection=_selection(),
        document=_document(),
        validation=_validation(),
        policy=_policy(),
    )

    assert strategy.target_role == "Senior BI Specialist"
    assert strategy.positioning == "Data Engineer"
    assert strategy.positioning != strategy.target_role
    assert strategy.explicit_gaps == ["Power BI"]


def test_strategy_uses_no_more_than_three_core_messages() -> None:
    strategy = build_cv_strategy(
        assessment=_assessment(
            _requirement("Python", "mandatory"),
            _requirement("SQL", "preferred"),
            _requirement("Power BI", "mandatory"),
        ),
        selection=_selection(),
        document=_document(),
        validation=_validation(),
        policy=_policy(),
    )

    assert [message.message for message in strategy.core_messages] == [
        "Data Engineer",
        "Python",
        "SQL",
    ]


def test_unvalidated_headline_cannot_be_selected_as_positioning() -> None:
    validation = _validation().model_copy(
        update={
            "validated_claim_ids": ["fact:skill-python", "fact:skill-sql"],
        }
    )

    with pytest.raises(ValueError, match="strategy_positioning_unavailable"):
        build_cv_strategy(
            assessment=_assessment(_requirement("Python", "mandatory")),
            selection=_selection(),
            document=_document(),
            validation=validation,
            policy=_policy(),
        )


def test_configured_positioning_must_reference_existing_validated_headline_claim() -> None:
    config = StrategyTrackConfig(
        id="tech",
        positioning_claim_id="fact:senior-bi-specialist",
    )

    with pytest.raises(ValueError, match="strategy_positioning_claim_invalid"):
        build_cv_strategy(
            assessment=_assessment(_requirement("Python", "mandatory")),
            selection=_selection(),
            document=_document(),
            validation=_validation(),
            policy=_policy(),
            track_config=config,
        )


def test_track_config_must_match_selected_application_track() -> None:
    config = StrategyTrackConfig(id="hospitality")

    with pytest.raises(ValueError, match="strategy_track_config_mismatch"):
        build_cv_strategy(
            assessment=_assessment(_requirement("Python", "mandatory")),
            selection=_selection(),
            document=_document(),
            validation=_validation(),
            policy=_policy(),
            track_config=config,
        )
