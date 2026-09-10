from app.cv.models import (
    CVClaim,
    CVDocumentModel,
    ClaimProvenance,
    EvidenceSelection,
    RequirementSupport,
    ValidationResult,
)
from app.cv.narrative.composer import compose_strategy_recruiter_document
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.strategy.models import CoreMessage, CVStrategy, STRATEGY_VERSION


def _fixture():
    claims = [
        CVClaim(claim_id="fact:name", section="headline", kind="identity", text="Alex Example"),
        CVClaim(claim_id="fact:role", section="headline", kind="headline", text="Data & Automation Engineer"),
        CVClaim(claim_id="fact:email", section="headline", kind="contact", text="alex@example.test"),
        CVClaim(claim_id="summary:generic", section="summary", kind="summary", text="Builds reliable technical systems."),
        CVClaim(claim_id="summary:target", section="summary", kind="summary", text="Turns operational data into decision support."),
        CVClaim(claim_id="fact:python", section="skills", kind="skill", text="Python"),
        CVClaim(claim_id="fact:python-duplicate", section="skills", kind="skill", text="Python"),
        CVClaim(claim_id="fact:sql", section="skills", kind="skill", text="SQL"),
        CVClaim(claim_id="project:legacy-first", section="projects", kind="project", text="Generic Dashboard"),
        CVClaim(claim_id="project:strategy-first", section="projects", kind="project", text="Decision Support API"),
        CVClaim(claim_id="bullet:wrong-project", section="projects", kind="bullet", text="Unrelated project detail."),
        CVClaim(claim_id="bullet:strategy-project", section="projects", kind="bullet", text="Mapped the operational decision bottleneck and evidence boundary."),
        CVClaim(claim_id="bullet:strategy-project-2", section="projects", kind="bullet", text="Connected verified operational data to a deterministic decision workflow."),
        CVClaim(claim_id="experience:legacy-first", section="experience", kind="organization", text="Example Support | 2022–2023"),
        CVClaim(claim_id="experience:strategy-first", section="experience", kind="organization", text="Example Operations | 2024–Present"),
        CVClaim(claim_id="bullet:legacy-exp", section="experience", kind="bullet", text="Handled routine support requests."),
        CVClaim(claim_id="bullet:strategy-exp", section="experience", kind="bullet", text="Mapped recurring reporting and troubleshooting bottlenecks."),
        CVClaim(claim_id="bullet:strategy-exp-2", section="experience", kind="bullet", text="Automated operational reporting and troubleshooting workflows."),
        CVClaim(claim_id="fact:education", section="education", kind="education", text="BSc Applied Sciences"),
        CVClaim(claim_id="fact:language", section="languages", kind="language", text="Spanish — Native"),
        CVClaim(claim_id="fact:github", section="links", kind="link", text="github.com/example"),
    ]
    provenance = {
        "fact:name": ClaimProvenance(fact_ids=["name"]),
        "fact:role": ClaimProvenance(fact_ids=["role"]),
        "fact:email": ClaimProvenance(fact_ids=["email"]),
        "summary:generic": ClaimProvenance(fact_ids=["summary-generic"]),
        "summary:target": ClaimProvenance(fact_ids=["summary-target"], evidence_ids=["module-decision"]),
        "fact:python": ClaimProvenance(fact_ids=["python"]),
        "fact:python-duplicate": ClaimProvenance(fact_ids=["python-duplicate"]),
        "fact:sql": ClaimProvenance(fact_ids=["sql"]),
        "project:legacy-first": ClaimProvenance(fact_ids=["project-generic"]),
        "project:strategy-first": ClaimProvenance(fact_ids=["project-decision"], evidence_ids=["module-decision"]),
        "bullet:wrong-project": ClaimProvenance(fact_ids=["project-generic"]),
        "bullet:strategy-project": ClaimProvenance(fact_ids=["project-decision"], evidence_ids=["module-decision"]),
        "bullet:strategy-project-2": ClaimProvenance(fact_ids=["project-decision"], evidence_ids=["module-decision"]),
        "experience:legacy-first": ClaimProvenance(fact_ids=["employment-support"]),
        "experience:strategy-first": ClaimProvenance(fact_ids=["employment-ops"], evidence_ids=["module-ops"]),
        "bullet:legacy-exp": ClaimProvenance(fact_ids=["employment-support"]),
        "bullet:strategy-exp": ClaimProvenance(fact_ids=["employment-ops"], evidence_ids=["module-ops"]),
        "bullet:strategy-exp-2": ClaimProvenance(fact_ids=["employment-ops"], evidence_ids=["module-ops"]),
        "fact:education": ClaimProvenance(fact_ids=["education"]),
        "fact:language": ClaimProvenance(fact_ids=["language"]),
        "fact:github": ClaimProvenance(fact_ids=["github"]),
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
    selected_fact_ids = sorted({fact_id for item in provenance.values() for fact_id in item.fact_ids})
    selection = EvidenceSelection(
        application_track_id="tech",
        selected_fact_ids=selected_fact_ids,
        selected_evidence_ids=["module-decision", "module-ops"],
        requirement_support={
            "generic dashboard": RequirementSupport(
                requirement="generic dashboard",
                support_level="EXACT_VERIFIED",
                fact_ids=["project-generic"],
                explanation="legacy-supported project",
            ),
            "Python": RequirementSupport(
                requirement="Python",
                support_level="EXACT_VERIFIED",
                fact_ids=["python"],
                explanation="verified skill",
            ),
        },
        unsupported_requirements=[],
    )
    strategy = CVStrategy(
        strategy_version=STRATEGY_VERSION,
        application_track_id="tech",
        target_role="Data Analyst",
        target_company="Example Analytics",
        positioning="Data & Automation Engineer",
        recruiter_question="Can this candidate turn operational data into useful decisions?",
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
                id="decision-systems",
                message="Decision systems",
                fact_ids=["project-decision", "summary-target"],
                evidence_ids=["module-decision"],
                importance=8.0,
                reason="target narrative",
            ),
            CoreMessage(
                id="operations",
                message="Operations automation",
                fact_ids=["employment-ops"],
                evidence_ids=["module-ops"],
                importance=7.0,
                reason="target narrative",
            ),
        ],
        must_show_fact_ids=["role", "project-decision", "summary-target", "employment-ops"],
        supporting_fact_ids=["python", "sql"],
        optional_fact_ids=[
            "name",
            "email",
            "summary-generic",
            "python-duplicate",
            "project-generic",
            "employment-support",
            "education",
            "language",
            "github",
        ],
        explicit_gaps=[],
        preferred_section_order=["summary", "skills", "experience", "projects", "education", "languages", "links"],
    )
    return document, validation, selection, strategy


def _compose():
    document, validation, selection, strategy = _fixture()
    recruiter = compose_strategy_recruiter_document(
        document=document,
        validation=validation,
        selection=selection,
        strategy=strategy,
        policy=load_recruiter_policy("config/recruiter_policy.yaml"),
    )
    return document, recruiter


def test_must_show_project_beats_requirement_supported_optional_project() -> None:
    _, recruiter = _compose()
    assert recruiter.selected_project_claim_ids[:2] == [
        "project:strategy-first",
        "project:legacy-first",
    ]


def test_core_message_overlap_prioritizes_target_summary() -> None:
    _, recruiter = _compose()
    assert recruiter.profile_claim_ids[:2] == ["summary:target", "summary:generic"]


def test_unvalidated_injected_claim_never_appears() -> None:
    document, validation, selection, strategy = _fixture()
    tampered = document.model_copy(
        update={
            "claims": [
                *document.claims,
                CVClaim(claim_id="bad", section="skills", kind="skill", text="AWS Expert"),
            ]
        }
    )
    recruiter = compose_strategy_recruiter_document(
        document=tampered,
        validation=validation,
        selection=selection,
        strategy=strategy,
        policy=load_recruiter_policy("config/recruiter_policy.yaml"),
    )
    assert "bad" not in recruiter.all_claim_ids()


def test_skills_keep_policy_caps_and_visible_text_deduplication() -> None:
    document, recruiter = _compose()
    claim_by_id = {claim.claim_id: claim for claim in document.claims}
    visible_skills = [
        claim_by_id[claim_id].text.casefold()
        for group in recruiter.technology_groups
        for claim_id in group.skill_claim_ids
    ]
    assert visible_skills.count("python") == 1
    assert len(recruiter.technology_groups) <= 4
    assert sum(len(group.skill_claim_ids) for group in recruiter.technology_groups) <= 24


def test_project_and_experience_bullets_keep_two_ranked_overlapping_claims() -> None:
    _, recruiter = _compose()
    assert recruiter.project_entries[0].primary_claim_id == "project:strategy-first"
    assert recruiter.project_entries[0].bullet_claim_ids == [
        "bullet:strategy-project",
        "bullet:strategy-project-2",
    ]
    assert "bullet:wrong-project" not in recruiter.project_entries[0].bullet_claim_ids
    assert recruiter.experience_entries[0].primary_claim_id == "experience:strategy-first"
    assert recruiter.experience_entries[0].bullet_claim_ids == [
        "bullet:strategy-exp",
        "bullet:strategy-exp-2",
    ]


def test_output_never_mints_claim_ids_and_is_deterministic() -> None:
    document, first = _compose()
    _, second = _compose()
    source_ids = {claim.claim_id for claim in document.claims}
    assert set(first.all_claim_ids()).issubset(source_ids)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
