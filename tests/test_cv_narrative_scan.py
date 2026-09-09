from app.cv.models import CVClaim, CVDocumentModel, ClaimProvenance
from app.cv.narrative import NarrativeQualityQA
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterExperienceEntry,
    RecruiterProjectEntry,
    TechnologyGroup,
)
from app.cv.strategy.models import CoreMessage, CVStrategy, STRATEGY_VERSION
from app.cv.strategy.policy import load_narrative_policy


def _fixture():
    claims = [
        CVClaim(claim_id="name", section="headline", kind="identity", text="Alex Example"),
        CVClaim(claim_id="role", section="headline", kind="headline", text="Data & Automation Engineer"),
        CVClaim(claim_id="summary", section="summary", kind="summary", text="Turns operational data into decision support."),
        CVClaim(claim_id="python", section="skills", kind="skill", text="Python"),
        CVClaim(claim_id="experience", section="experience", kind="organization", text="Example Operations | 2024–Present"),
        CVClaim(claim_id="ops-bullet", section="experience", kind="bullet", text="Automated operational reporting workflows."),
        CVClaim(claim_id="project", section="projects", kind="project", text="Decision Support API"),
        CVClaim(claim_id="project-bullet", section="projects", kind="bullet", text="Connected verified data to a decision workflow."),
    ]
    provenance = {
        "name": ClaimProvenance(fact_ids=["name"]),
        "role": ClaimProvenance(fact_ids=["role"]),
        "summary": ClaimProvenance(fact_ids=["decision"]),
        "python": ClaimProvenance(fact_ids=["python"]),
        "experience": ClaimProvenance(fact_ids=["employment-history"]),
        "ops-bullet": ClaimProvenance(fact_ids=["operations"]),
        "project": ClaimProvenance(fact_ids=["project"]),
        "project-bullet": ClaimProvenance(fact_ids=["project"]),
    }
    document = CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=claims,
        entries=[],
        provenance_map=provenance,
    )
    recruiter = RecruiterDocumentModel(
        source_cv_document_version="cvdoc-v1",
        language="en",
        identity_claim_id="name",
        headline_claim_id="role",
        contact_claim_ids=[],
        profile_claim_ids=["summary"],
        technology_groups=[TechnologyGroup(label_id="programming", skill_claim_ids=["python"])],
        selected_project_claim_ids=["project"],
        project_entries=[RecruiterProjectEntry(primary_claim_id="project", bullet_claim_ids=["project-bullet"])],
        experience_entries=[RecruiterExperienceEntry(primary_claim_id="experience", bullet_claim_ids=["ops-bullet"])],
        education_claim_ids=[],
        language_claim_ids=[],
        link_claim_ids=[],
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
                id="decision",
                message="Decision systems",
                fact_ids=["decision"],
                evidence_ids=[],
                importance=8.0,
                reason="target narrative",
            ),
            CoreMessage(
                id="operations",
                message="Operations automation",
                fact_ids=["operations"],
                evidence_ids=[],
                importance=7.0,
                reason="target narrative",
            ),
        ],
        must_show_fact_ids=["role", "decision", "operations"],
        supporting_fact_ids=["python", "project"],
        optional_fact_ids=["name", "employment-history"],
        explicit_gaps=[],
        preferred_section_order=["summary", "skills", "experience", "projects"],
    )
    return document, recruiter, strategy


def _evaluate(max_scan_claims: int, min_score: float = 0.67):
    document, recruiter, strategy = _fixture()
    policy = load_narrative_policy("config/narrative_policy.yaml").model_copy(
        update={"max_scan_claims": max_scan_claims, "min_scanability_score": min_score}
    )
    return NarrativeQualityQA().evaluate(
        recruiter_document=recruiter,
        source_document=document,
        strategy=strategy,
        policy=policy,
    )


def test_two_of_three_core_messages_round_to_point_67_and_pass() -> None:
    result = _evaluate(max_scan_claims=2)

    assert result.scanability_score == 0.67
    assert result.valid is True
    assert "narrative_scanability_below_threshold" not in {
        issue.code for issue in result.errors
    }


def test_one_of_three_core_messages_fails_scanability_gate() -> None:
    result = _evaluate(max_scan_claims=1)

    assert result.scanability_score == 0.33
    assert result.valid is False
    assert "narrative_scanability_below_threshold" in {
        issue.code for issue in result.errors
    }


def test_scanability_is_deterministic_for_identical_inputs() -> None:
    first = _evaluate(max_scan_claims=5)
    second = _evaluate(max_scan_claims=5)

    assert first.scanability_score == second.scanability_score
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
