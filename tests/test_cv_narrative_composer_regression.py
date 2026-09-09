from app.cv.models import (
    CVClaim,
    CVDocumentModel,
    ClaimProvenance,
    EvidenceSelection,
    RequirementSupport,
    ValidationResult,
)
from app.cv.narrative import compose_strategy_recruiter_document
from app.cv.recruiter_composer import compose_recruiter_document, reduce_recruiter_document
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.strategy.models import CoreMessage, CVStrategy, STRATEGY_VERSION


def _fixture():
    claims = [
        CVClaim(claim_id="name", section="headline", kind="identity", text="Alex Example"),
        CVClaim(claim_id="role", section="headline", kind="headline", text="Data & Automation Engineer"),
        CVClaim(claim_id="email", section="headline", kind="contact", text="alex@example.test"),
        CVClaim(claim_id="python", section="skills", kind="skill", text="Python"),
        CVClaim(claim_id="project:legacy", section="projects", kind="project", text="Generic Dashboard"),
        CVClaim(claim_id="project:strategy", section="projects", kind="project", text="Decision Support API"),
        CVClaim(claim_id="education", section="education", kind="education", text="BSc Applied Sciences"),
    ]
    provenance = {
        "name": ClaimProvenance(fact_ids=["name"]),
        "role": ClaimProvenance(fact_ids=["role"]),
        "email": ClaimProvenance(fact_ids=["email"]),
        "python": ClaimProvenance(fact_ids=["python"]),
        "project:legacy": ClaimProvenance(fact_ids=["project-legacy"]),
        "project:strategy": ClaimProvenance(
            fact_ids=["project-strategy"],
            evidence_ids=["module-decision"],
        ),
        "education": ClaimProvenance(fact_ids=["education"]),
    }
    document = CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=claims,
        entries=[],
        provenance_map=provenance,
    )
    validation = ValidationResult(
        valid=True,
        validated_claim_ids=[claim.claim_id for claim in claims],
    )
    selection = EvidenceSelection(
        application_track_id="tech",
        selected_fact_ids=[
            "name",
            "role",
            "email",
            "python",
            "project-legacy",
            "project-strategy",
            "education",
        ],
        selected_evidence_ids=["module-decision"],
        requirement_support={
            "dashboard": RequirementSupport(
                requirement="dashboard",
                support_level="EXACT_VERIFIED",
                fact_ids=["project-legacy"],
                evidence_ids=[],
                explanation="Direct vacancy requirement match",
            )
        },
        unsupported_requirements=[],
    )
    strategy = CVStrategy(
        strategy_version=STRATEGY_VERSION,
        application_track_id="tech",
        target_role="Data Analyst",
        target_company="Example Analytics",
        positioning="Data & Automation Engineer",
        recruiter_question="Can this candidate build decision-support systems?",
        core_messages=[
            CoreMessage(
                id="positioning",
                message="Data & Automation Engineer",
                fact_ids=["role"],
                evidence_ids=[],
                importance=10.0,
                reason="validated positioning",
            ),
            CoreMessage(
                id="decision-support",
                message="Decision support",
                fact_ids=["project-strategy"],
                evidence_ids=["module-decision"],
                importance=9.0,
                reason="target narrative",
            ),
        ],
        must_show_fact_ids=["role", "project-strategy"],
        supporting_fact_ids=["python"],
        optional_fact_ids=["name", "email", "project-legacy", "education"],
        explicit_gaps=[],
        preferred_section_order=["skills", "projects", "education"],
    )
    return document, validation, selection, strategy


def test_strategy_composer_corrects_legacy_project_priority_without_breaking_contract() -> None:
    document, validation, selection, strategy = _fixture()
    policy = load_recruiter_policy("config/recruiter_policy.yaml")

    legacy = compose_recruiter_document(
        document=document,
        validation=validation,
        selection=selection,
        policy=policy,
    )
    legacy_again = compose_recruiter_document(
        document=document,
        validation=validation,
        selection=selection,
        policy=policy,
    )
    narrative = compose_strategy_recruiter_document(
        document=document,
        validation=validation,
        selection=selection,
        strategy=strategy,
        policy=policy,
    )

    assert legacy.model_dump(mode="json") == legacy_again.model_dump(mode="json")
    assert legacy.selected_project_claim_ids[0] == "project:legacy"
    assert narrative.selected_project_claim_ids[0] == "project:strategy"
    assert legacy.selected_project_claim_ids[0] != narrative.selected_project_claim_ids[0]

    source_ids = {claim.claim_id for claim in document.claims}
    assert set(narrative.all_claim_ids()).issubset(source_ids)

    reduced = reduce_recruiter_document(narrative, policy, step=0)
    assert set(reduced.all_claim_ids()).issubset(source_ids)
    assert reduced.source_cv_document_version == narrative.source_cv_document_version
