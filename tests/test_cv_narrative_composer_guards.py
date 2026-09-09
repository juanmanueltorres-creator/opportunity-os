import pytest

from app.cv.models import (
    CVClaim,
    CVDocumentModel,
    ClaimProvenance,
    EvidenceSelection,
    ValidationIssue,
    ValidationResult,
)
from app.cv.narrative.composer import compose_strategy_recruiter_document
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.strategy.models import CoreMessage, CVStrategy, STRATEGY_VERSION


def _inputs():
    claims = [
        CVClaim(claim_id="name", section="headline", kind="identity", text="Alex Example"),
        CVClaim(claim_id="role", section="headline", kind="headline", text="Data Engineer"),
        CVClaim(claim_id="email", section="headline", kind="contact", text="alex@example.test"),
    ]
    document = CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=claims,
        entries=[],
        provenance_map={
            "name": ClaimProvenance(fact_ids=["name"]),
            "role": ClaimProvenance(fact_ids=["role"]),
            "email": ClaimProvenance(fact_ids=["email"]),
        },
    )
    validation = ValidationResult(
        valid=True,
        validated_claim_ids=["name", "role", "email"],
    )
    selection = EvidenceSelection(
        application_track_id="tech",
        selected_fact_ids=["name", "role", "email"],
        selected_evidence_ids=[],
        requirement_support={},
        unsupported_requirements=[],
    )
    strategy = CVStrategy(
        strategy_version=STRATEGY_VERSION,
        application_track_id="tech",
        target_role="Senior BI Specialist",
        target_company="Example Co",
        positioning="Data Engineer",
        recruiter_question="Can this candidate do the work?",
        core_messages=[
            CoreMessage(
                id="positioning",
                message="Data Engineer",
                fact_ids=["role"],
                evidence_ids=[],
                importance=10.0,
                reason="validated positioning",
            )
        ],
        must_show_fact_ids=["role"],
        supporting_fact_ids=[],
        optional_fact_ids=["name", "email"],
        explicit_gaps=[],
        preferred_section_order=["summary", "skills", "experience", "projects"],
    )
    return document, validation, selection, strategy


def _call(document, validation, selection, strategy):
    return compose_strategy_recruiter_document(
        document=document,
        validation=validation,
        selection=selection,
        strategy=strategy,
        policy=load_recruiter_policy("config/recruiter_policy.yaml"),
    )


def test_invalid_semantic_validation_fails_with_bounded_error() -> None:
    document, _, selection, strategy = _inputs()
    validation = ValidationResult(
        valid=False,
        errors=[ValidationIssue(code="synthetic", message="invalid")],
        validated_claim_ids=[],
    )
    with pytest.raises(ValueError, match="narrative_requires_valid_semantic_document"):
        _call(document, validation, selection, strategy)


def test_strategy_selection_track_mismatch_fails_closed() -> None:
    document, validation, selection, strategy = _inputs()
    strategy = strategy.model_copy(update={"application_track_id": "operations"})
    with pytest.raises(ValueError, match="narrative_strategy_track_mismatch"):
        _call(document, validation, selection, strategy)


def test_strategy_fact_outside_evidence_selection_fails_closed() -> None:
    document, validation, selection, strategy = _inputs()
    strategy = strategy.model_copy(
        update={"must_show_fact_ids": ["role", "unselected-fact"]}
    )
    with pytest.raises(ValueError, match="narrative_strategy_fact_outside_selection"):
        _call(document, validation, selection, strategy)


def test_positioning_existing_only_as_unvalidated_headline_fails_closed() -> None:
    document, _, selection, strategy = _inputs()
    validation = ValidationResult(
        valid=True,
        validated_claim_ids=["name", "email"],
    )
    with pytest.raises(ValueError, match="narrative_positioning_claim_unresolved"):
        _call(document, validation, selection, strategy)


def test_target_vacancy_title_cannot_become_positioning_without_candidate_claim() -> None:
    document, validation, selection, strategy = _inputs()
    strategy = strategy.model_copy(
        update={
            "positioning": "Senior BI Specialist",
            "core_messages": [
                CoreMessage(
                    id="positioning",
                    message="Senior BI Specialist",
                    fact_ids=["role"],
                    evidence_ids=[],
                    importance=10.0,
                    reason="tampered target title",
                )
            ],
        }
    )
    with pytest.raises(ValueError, match="narrative_positioning_claim_unresolved"):
        _call(document, validation, selection, strategy)
