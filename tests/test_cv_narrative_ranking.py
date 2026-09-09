from app.cv.models import (
    CVClaim,
    CVDocumentModel,
    ClaimProvenance,
    EvidenceSelection,
    RequirementSupport,
    ValidationResult,
)
from app.cv.narrative.ranking import rank_validated_claims
from app.cv.strategy.models import CoreMessage, CVStrategy, STRATEGY_VERSION


def _strategy(
    *,
    must_show: list[str] | None = None,
    supporting: list[str] | None = None,
    optional: list[str] | None = None,
    messages: list[CoreMessage] | None = None,
) -> CVStrategy:
    must_show = must_show or ["role"]
    supporting = supporting or []
    optional = optional or []
    messages = messages or [
        CoreMessage(
            id="positioning",
            message="Data Engineer",
            fact_ids=[must_show[0]],
            evidence_ids=[],
            importance=10.0,
            reason="validated positioning",
        )
    ]
    return CVStrategy(
        strategy_version=STRATEGY_VERSION,
        application_track_id="tech",
        target_role="Data Analyst",
        target_company="Example Co",
        positioning="Data Engineer",
        recruiter_question="Can this candidate do the work?",
        core_messages=messages,
        must_show_fact_ids=must_show,
        supporting_fact_ids=supporting,
        optional_fact_ids=optional,
        explicit_gaps=[],
        preferred_section_order=["skills", "projects", "experience"],
    )


def _document(specs: list[tuple[str, str, str]]) -> CVDocumentModel:
    claims = [
        CVClaim(claim_id=claim_id, section="skills", kind="skill", text=claim_id)
        for claim_id, _, _ in specs
    ]
    provenance = {
        claim_id: ClaimProvenance(
            fact_ids=[fact_id],
            evidence_ids=[evidence_id] if evidence_id else [],
        )
        for claim_id, fact_id, evidence_id in specs
    }
    return CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=claims,
        entries=[],
        provenance_map=provenance,
    )


def _selection(*facts: str, supported_fact: str | None = None) -> EvidenceSelection:
    support = {}
    if supported_fact is not None:
        support["supported"] = RequirementSupport(
            requirement="supported",
            support_level="EXACT_VERIFIED",
            fact_ids=[supported_fact],
            evidence_ids=[],
            explanation="exact support",
        )
    return EvidenceSelection(
        application_track_id="tech",
        selected_fact_ids=list(facts),
        selected_evidence_ids=[],
        requirement_support=support,
        unsupported_requirements=[],
    )


def _rank(
    specs: list[tuple[str, str, str]],
    strategy: CVStrategy,
    *,
    supported_fact: str | None = None,
    validated_ids: list[str] | None = None,
) -> list[str]:
    document = _document(specs)
    validation = ValidationResult(
        valid=True,
        validated_claim_ids=validated_ids or [item[0] for item in specs],
    )
    selection = _selection(
        *(item[1] for item in specs),
        supported_fact=supported_fact,
    )
    return [
        claim.claim_id
        for claim in rank_validated_claims(
            claims=document.claims,
            document=document,
            validation=validation,
            selection=selection,
            strategy=strategy,
        )
    ]


def test_strategy_bucket_priority_beats_requirement_support() -> None:
    strategy = _strategy(
        must_show=["must"],
        supporting=["support"],
        optional=["optional"],
    )
    ranked = _rank(
        [
            ("claim-optional", "optional", ""),
            ("claim-support", "support", ""),
            ("claim-must", "must", ""),
        ],
        strategy,
        supported_fact="optional",
    )

    assert ranked == ["claim-must", "claim-support", "claim-optional"]


def test_core_message_overlap_breaks_same_bucket_tie() -> None:
    strategy = _strategy(
        must_show=["role"],
        supporting=["support-a", "support-b"],
        messages=[
            CoreMessage(
                id="positioning",
                message="Data Engineer",
                fact_ids=["role"],
                evidence_ids=[],
                importance=10.0,
                reason="positioning",
            ),
            CoreMessage(
                id="automation",
                message="Automation",
                fact_ids=["support-a"],
                evidence_ids=["module-a"],
                importance=5.0,
                reason="target message",
            ),
        ],
    )
    ranked = _rank(
        [
            ("claim-b", "support-b", ""),
            ("claim-a", "support-a", "module-a"),
        ],
        strategy,
    )

    assert ranked == ["claim-a", "claim-b"]


def test_requirement_support_breaks_equal_strategy_tie() -> None:
    strategy = _strategy(
        must_show=["role"],
        supporting=["support-a", "support-b"],
    )
    ranked = _rank(
        [
            ("claim-a", "support-a", ""),
            ("claim-b", "support-b", ""),
        ],
        strategy,
        supported_fact="support-b",
    )

    assert ranked == ["claim-b", "claim-a"]


def test_source_order_then_claim_id_is_final_tiebreak() -> None:
    strategy = _strategy(
        must_show=["role"],
        optional=["a", "b", "c"],
    )
    ranked = _rank(
        [
            ("claim-b", "b", ""),
            ("claim-a", "a", ""),
            ("claim-c", "c", ""),
        ],
        strategy,
    )

    assert ranked == ["claim-b", "claim-a", "claim-c"]


def test_unvalidated_claim_is_never_ranked() -> None:
    strategy = _strategy(
        must_show=["safe"],
        optional=["unsafe"],
    )
    ranked = _rank(
        [
            ("safe", "safe", ""),
            ("unsafe", "unsafe", ""),
        ],
        strategy,
        validated_ids=["safe"],
        supported_fact="unsafe",
    )

    assert ranked == ["safe"]
