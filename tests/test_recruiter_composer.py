from app.cv.models import (
    CVClaim,
    CVDocumentModel,
    ClaimProvenance,
    EvidenceSelection,
    RequirementSupport,
    ValidationResult,
)
from app.cv.recruiter_composer import (
    compose_recruiter_document,
    reduce_recruiter_document,
)
from app.cv.recruiter_policy import load_recruiter_policy


def _source_fixture():
    claims = [
        CVClaim(claim_id="fact:name", section="headline", kind="identity", text="Alex Example"),
        CVClaim(claim_id="fact:role", section="headline", kind="headline", text="Software & Operations Developer"),
        CVClaim(claim_id="fact:email", section="headline", kind="contact", text="alex@example.test"),
        CVClaim(claim_id="approved:summary", section="summary", kind="summary", text="Builds software and operational workflows."),
        CVClaim(claim_id="fact:python", section="skills", kind="skill", text="Python"),
        CVClaim(claim_id="fact:sql", section="skills", kind="skill", text="SQL"),
        CVClaim(claim_id="fact:qgis", section="skills", kind="skill", text="QGIS"),
        CVClaim(claim_id="fact:project-1", section="projects", kind="project", text="Mapping Console"),
        CVClaim(claim_id="fact:project-2", section="projects", kind="project", text="Fleet Simulator"),
        CVClaim(
            claim_id="approved:project-2-bullet",
            section="projects",
            kind="bullet",
            text="Deterministic route simulation with auditable vehicle state.",
        ),
        CVClaim(claim_id="fact:employment-1", section="experience", kind="organization", text="Example Operations | 2024–Present"),
        CVClaim(claim_id="approved:employment-1-bullet", section="experience", kind="bullet", text="Improved inventory and workflow visibility."),
        CVClaim(claim_id="fact:education", section="education", kind="education", text="BSc Applied Sciences"),
        CVClaim(claim_id="fact:language", section="languages", kind="language", text="Spanish — Native"),
        CVClaim(claim_id="fact:github", section="links", kind="link", text="github.com/example"),
        CVClaim(claim_id="fact:portfolio", section="links", kind="link", text="example.test"),
    ]
    provenance = {
        "fact:name": ClaimProvenance(fact_ids=["name"]),
        "fact:role": ClaimProvenance(fact_ids=["role"]),
        "fact:email": ClaimProvenance(fact_ids=["email"]),
        "approved:summary": ClaimProvenance(fact_ids=["summary"], evidence_ids=["module-core"], approved_claim_id="summary"),
        "fact:python": ClaimProvenance(fact_ids=["python"]),
        "fact:sql": ClaimProvenance(fact_ids=["sql"]),
        "fact:qgis": ClaimProvenance(fact_ids=["qgis"]),
        "fact:project-1": ClaimProvenance(fact_ids=["project-1"]),
        "fact:project-2": ClaimProvenance(fact_ids=["project-2"], evidence_ids=["module-fleet"]),
        "approved:project-2-bullet": ClaimProvenance(
            fact_ids=["project-2"],
            evidence_ids=["module-fleet"],
            approved_claim_id="project-2-bullet",
        ),
        "fact:employment-1": ClaimProvenance(fact_ids=["employment-1"]),
        "approved:employment-1-bullet": ClaimProvenance(
            fact_ids=["employment-1"],
            evidence_ids=["module-ops"],
            approved_claim_id="employment-1-bullet",
        ),
        "fact:education": ClaimProvenance(fact_ids=["education"]),
        "fact:language": ClaimProvenance(fact_ids=["language"]),
        "fact:github": ClaimProvenance(fact_ids=["github"]),
        "fact:portfolio": ClaimProvenance(fact_ids=["portfolio"]),
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
        application_track_id="tech-operations",
        selected_fact_ids=list({fact_id for item in provenance.values() for fact_id in item.fact_ids}),
        selected_evidence_ids=["module-core", "module-fleet", "module-ops"],
        requirement_support={
            "Python": RequirementSupport(
                requirement="Python",
                support_level="EXACT_VERIFIED",
                fact_ids=["python"],
                explanation="Verified exact skill",
            ),
            "fleet workflows": RequirementSupport(
                requirement="fleet workflows",
                support_level="EXACT_VERIFIED",
                fact_ids=["project-2"],
                evidence_ids=["module-fleet"],
                explanation="Verified relevant project",
            ),
        },
        unsupported_requirements=["Power BI"],
    )
    return document, validation, selection


def _policy():
    return load_recruiter_policy("config/recruiter_policy.yaml")


def test_composer_never_selects_claim_outside_validated_claim_ids():
    document, validation, selection = _source_fixture()
    tampered = document.model_copy(
        update={
            "claims": [
                *document.claims,
                CVClaim(
                    claim_id="bad",
                    section="skills",
                    kind="skill",
                    text="AWS Expert",
                ),
            ]
        }
    )

    recruiter = compose_recruiter_document(
        document=tampered,
        validation=validation,
        selection=selection,
        policy=_policy(),
    )

    assert "bad" not in recruiter.all_claim_ids()


def test_skills_are_grouped_under_policy_caps():
    document, validation, selection = _source_fixture()

    recruiter = compose_recruiter_document(
        document=document,
        validation=validation,
        selection=selection,
        policy=_policy(),
    )

    assert len(recruiter.technology_groups) <= 4
    assert sum(len(group.skill_claim_ids) for group in recruiter.technology_groups) <= 24
    assert recruiter.technology_groups[0].label_id == "software_data"
    assert recruiter.technology_groups[0].skill_claim_ids[0] == "fact:python"
    assert all(group.skill_claim_ids for group in recruiter.technology_groups)


def test_target_supported_project_precedes_fallback_project():
    document, validation, selection = _source_fixture()

    recruiter = compose_recruiter_document(
        document=document,
        validation=validation,
        selection=selection,
        policy=_policy(),
    )

    assert recruiter.selected_project_claim_ids[:2] == [
        "fact:project-2",
        "fact:project-1",
    ]


def test_project_bullet_is_associated_only_by_overlapping_provenance():
    document, validation, selection = _source_fixture()

    recruiter = compose_recruiter_document(
        document=document,
        validation=validation,
        selection=selection,
        policy=_policy(),
    )

    assert len(recruiter.project_entries) == 2
    assert recruiter.project_entries[0].primary_claim_id == "fact:project-2"
    assert recruiter.project_entries[0].bullet_claim_ids == [
        "approved:project-2-bullet"
    ]
    assert recruiter.project_entries[1].primary_claim_id == "fact:project-1"
    assert recruiter.project_entries[1].bullet_claim_ids == []


def test_experience_bullet_is_associated_only_by_overlapping_provenance():
    document, validation, selection = _source_fixture()

    recruiter = compose_recruiter_document(
        document=document,
        validation=validation,
        selection=selection,
        policy=_policy(),
    )

    assert len(recruiter.experience_entries) == 1
    assert recruiter.experience_entries[0].primary_claim_id == "fact:employment-1"
    assert recruiter.experience_entries[0].bullet_claim_ids == [
        "approved:employment-1-bullet"
    ]


def test_reduction_is_deterministic_and_removes_optional_links_first():
    document, validation, selection = _source_fixture()
    recruiter = compose_recruiter_document(
        document=document,
        validation=validation,
        selection=selection,
        policy=_policy(),
    )

    reduced = reduce_recruiter_document(recruiter, _policy(), step=0)
    reduced_again = reduce_recruiter_document(recruiter, _policy(), step=0)

    assert reduced.model_dump(mode="json") == reduced_again.model_dump(mode="json")
    assert reduced.link_claim_ids == ["fact:github"]


def test_reduction_never_drops_below_two_projects_when_two_are_available():
    document, validation, selection = _source_fixture()
    recruiter = compose_recruiter_document(
        document=document,
        validation=validation,
        selection=selection,
        policy=_policy(),
    )

    maximally_reduced = reduce_recruiter_document(recruiter, _policy(), step=100)

    assert len(maximally_reduced.selected_project_claim_ids) == 2


def test_reduction_trims_canonical_project_entries_and_keeps_legacy_ids_in_sync():
    document, validation, selection = _source_fixture()
    recruiter = compose_recruiter_document(
        document=document,
        validation=validation,
        selection=selection,
        policy=_policy(),
    )
    third_entry = recruiter.project_entries[-1].model_copy(
        update={"primary_claim_id": "fact:project-3", "bullet_claim_ids": []}
    )
    recruiter = recruiter.model_copy(
        update={
            "selected_project_claim_ids": [
                "fact:project-2",
                "fact:project-1",
                "fact:project-3",
            ],
            "project_entries": [*recruiter.project_entries, third_entry],
        }
    )

    maximally_reduced = reduce_recruiter_document(recruiter, _policy(), step=100)

    assert [entry.primary_claim_id for entry in maximally_reduced.project_entries] == [
        "fact:project-2",
        "fact:project-1",
    ]
    assert maximally_reduced.selected_project_claim_ids == [
        "fact:project-2",
        "fact:project-1",
    ]
