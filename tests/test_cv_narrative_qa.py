from app.cv.models import CVClaim, CVDocumentModel, ClaimProvenance
from app.cv.narrative import NarrativeQualityQA
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterExperienceEntry,
    RecruiterProjectEntry,
    TechnologyGroup,
)
from app.cv.strategy.models import CoreMessage, CVStrategy, STRATEGY_VERSION
from app.cv.strategy.policy import NarrativePolicy, load_narrative_policy


def _fixture() -> tuple[CVDocumentModel, RecruiterDocumentModel, CVStrategy, NarrativePolicy]:
    claims = [
        CVClaim(claim_id="name", section="headline", kind="identity", text="Alex Example"),
        CVClaim(claim_id="role", section="headline", kind="headline", text="Data & Automation Engineer"),
        CVClaim(claim_id="email", section="headline", kind="contact", text="alex@example.test"),
        CVClaim(claim_id="summary:target", section="summary", kind="summary", text="Turns operational data into decision support."),
        CVClaim(claim_id="summary:noise", section="summary", kind="summary", text="Passionate geologist and team player."),
        CVClaim(claim_id="skill:python", section="skills", kind="skill", text="Python"),
        CVClaim(claim_id="project:decision", section="projects", kind="project", text="Decision Support API"),
        CVClaim(claim_id="project:noise", section="projects", kind="project", text="Unrelated Mapping Demo"),
        CVClaim(claim_id="bullet:decision", section="projects", kind="bullet", text="Connected operational data to a decision workflow."),
        CVClaim(claim_id="bullet:noise", section="projects", kind="bullet", text="Built an unrelated showcase."),
        CVClaim(claim_id="experience:history", section="experience", kind="organization", text="Hospitality Operations | 2019–2026"),
        CVClaim(claim_id="bullet:operations", section="experience", kind="bullet", text="Automated operational reporting and troubleshooting workflows."),
        CVClaim(claim_id="education", section="education", kind="education", text="BSc Applied Sciences"),
        CVClaim(claim_id="language", section="languages", kind="language", text="Spanish — Native"),
    ]
    provenance = {
        "name": ClaimProvenance(fact_ids=["name"]),
        "role": ClaimProvenance(fact_ids=["role"]),
        "email": ClaimProvenance(fact_ids=["email"]),
        "summary:target": ClaimProvenance(fact_ids=["summary-target"], evidence_ids=["module-decision"]),
        "summary:noise": ClaimProvenance(fact_ids=["noise-identity"]),
        "skill:python": ClaimProvenance(fact_ids=["python"]),
        "project:decision": ClaimProvenance(fact_ids=["project-decision"], evidence_ids=["module-decision"]),
        "project:noise": ClaimProvenance(fact_ids=["noise-project"]),
        "bullet:decision": ClaimProvenance(fact_ids=["project-decision"], evidence_ids=["module-decision"]),
        "bullet:noise": ClaimProvenance(fact_ids=["noise-project"]),
        "experience:history": ClaimProvenance(fact_ids=["employment-history"]),
        "bullet:operations": ClaimProvenance(fact_ids=["employment-ops"], evidence_ids=["module-ops"]),
        "education": ClaimProvenance(fact_ids=["education"]),
        "language": ClaimProvenance(fact_ids=["language"]),
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
        contact_claim_ids=["email"],
        profile_claim_ids=["summary:target"],
        technology_groups=[TechnologyGroup(label_id="programming", skill_claim_ids=["skill:python"])],
        selected_project_claim_ids=["project:decision"],
        project_entries=[RecruiterProjectEntry(primary_claim_id="project:decision", bullet_claim_ids=["bullet:decision"])],
        experience_entries=[RecruiterExperienceEntry(primary_claim_id="experience:history", bullet_claim_ids=["bullet:operations"])],
        education_claim_ids=["education"],
        language_claim_ids=["language"],
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
                id="decision-systems",
                message="Decision systems",
                fact_ids=["summary-target", "project-decision"],
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
        must_show_fact_ids=["role", "summary-target", "project-decision", "employment-ops"],
        supporting_fact_ids=["python"],
        optional_fact_ids=["name", "email", "employment-history", "education", "language"],
        explicit_gaps=[],
        preferred_section_order=["summary", "skills", "experience", "projects", "education", "languages", "links"],
    )
    return document, recruiter, strategy, load_narrative_policy("config/narrative_policy.yaml")


def _error_codes(result) -> set[str]:
    return {issue.code for issue in result.errors}


def test_all_core_messages_have_visible_provenance_coverage() -> None:
    document, recruiter, strategy, policy = _fixture()

    result = NarrativeQualityQA().evaluate(
        recruiter_document=recruiter,
        source_document=document,
        strategy=strategy,
        policy=policy,
    )

    assert result.core_message_coverage == {
        "positioning": 1.0,
        "decision-systems": 1.0,
        "operations": 1.0,
    }
    assert "narrative_core_message_uncovered" not in _error_codes(result)


def test_missing_core_message_is_hard_error() -> None:
    document, recruiter, strategy, policy = _fixture()
    recruiter = recruiter.model_copy(
        update={
            "experience_entries": [
                RecruiterExperienceEntry(primary_claim_id="experience:history", bullet_claim_ids=[])
            ]
        }
    )

    result = NarrativeQualityQA().evaluate(
        recruiter_document=recruiter,
        source_document=document,
        strategy=strategy,
        policy=policy,
    )

    assert result.core_message_coverage["operations"] == 0.0
    assert "narrative_core_message_uncovered" in _error_codes(result)
    assert result.valid is False


def test_off_strategy_editorial_ratio_excludes_structural_chronology() -> None:
    document, recruiter, strategy, policy = _fixture()
    assert "employment-history" in document.provenance_map["experience:history"].fact_ids
    assert "employment-history" not in strategy.must_show_fact_ids + strategy.supporting_fact_ids

    result = NarrativeQualityQA().evaluate(
        recruiter_document=recruiter,
        source_document=document,
        strategy=strategy,
        policy=policy,
    )

    assert result.off_strategy_claim_ratio == 0.0


def test_off_strategy_ratio_above_policy_is_hard_error() -> None:
    document, recruiter, strategy, policy = _fixture()
    recruiter = recruiter.model_copy(
        update={
            "project_entries": [
                RecruiterProjectEntry(primary_claim_id="project:noise", bullet_claim_ids=["bullet:noise"])
            ],
            "selected_project_claim_ids": ["project:noise"],
        }
    )
    policy = policy.model_copy(update={"max_off_strategy_claim_ratio": 0.25})

    result = NarrativeQualityQA().evaluate(
        recruiter_document=recruiter,
        source_document=document,
        strategy=strategy,
        policy=policy,
    )

    assert result.off_strategy_claim_ratio > policy.max_off_strategy_claim_ratio
    assert "narrative_off_strategy_ratio_exceeded" in _error_codes(result)
    assert result.valid is False


def test_off_strategy_profile_claim_counts_as_competing_identity_signal() -> None:
    document, recruiter, strategy, policy = _fixture()
    recruiter = recruiter.model_copy(update={"profile_claim_ids": ["summary:target", "summary:noise"]})

    result = NarrativeQualityQA().evaluate(
        recruiter_document=recruiter,
        source_document=document,
        strategy=strategy,
        policy=policy,
    )

    assert result.competing_identity_count == 1


def test_competing_identity_limit_is_hard_error() -> None:
    document, recruiter, strategy, policy = _fixture()
    recruiter = recruiter.model_copy(update={"profile_claim_ids": ["summary:target", "summary:noise"]})
    policy = policy.model_copy(update={"max_competing_identity_signals": 0})

    result = NarrativeQualityQA().evaluate(
        recruiter_document=recruiter,
        source_document=document,
        strategy=strategy,
        policy=policy,
    )

    assert "narrative_competing_identity_limit_exceeded" in _error_codes(result)
    assert result.valid is False


def test_generic_phrase_emits_warning_without_independent_failure() -> None:
    document, recruiter, strategy, policy = _fixture()
    recruiter = recruiter.model_copy(update={"profile_claim_ids": ["summary:target", "summary:noise"]})
    policy = policy.model_copy(
        update={
            "max_off_strategy_claim_ratio": 1.0,
            "max_competing_identity_signals": 1,
        }
    )

    result = NarrativeQualityQA().evaluate(
        recruiter_document=recruiter,
        source_document=document,
        strategy=strategy,
        policy=policy,
    )

    assert "narrative_generic_claim_detected" in {issue.code for issue in result.warnings}
    assert result.valid is True


def test_headline_must_match_strategy_positioning() -> None:
    document, recruiter, strategy, policy = _fixture()
    changed_claims = [
        claim.model_copy(update={"text": "Geospatial Developer"}) if claim.claim_id == "role" else claim
        for claim in document.claims
    ]
    document = document.model_copy(update={"claims": changed_claims})

    result = NarrativeQualityQA().evaluate(
        recruiter_document=recruiter,
        source_document=document,
        strategy=strategy,
        policy=policy,
    )

    assert "narrative_positioning_mismatch" in _error_codes(result)
    assert result.valid is False


def test_headline_must_overlap_positioning_core_message_provenance() -> None:
    document, recruiter, strategy, policy = _fixture()
    provenance = dict(document.provenance_map)
    provenance["role"] = ClaimProvenance(fact_ids=["other-role"])
    document = document.model_copy(update={"provenance_map": provenance})

    result = NarrativeQualityQA().evaluate(
        recruiter_document=recruiter,
        source_document=document,
        strategy=strategy,
        policy=policy,
    )

    assert "narrative_positioning_unsupported" in _error_codes(result)
    assert result.valid is False
