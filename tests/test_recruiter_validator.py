from app.cv.models import (
    CVClaim,
    CVDocumentModel,
    ClaimProvenance,
    ValidationResult,
)
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterExperienceEntry,
    RecruiterProjectEntry,
    TechnologyGroup,
)
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.recruiter_validator import validate_recruiter_document


def _source_document() -> CVDocumentModel:
    claims = [
        CVClaim(
            claim_id="fact:name",
            section="headline",
            kind="identity",
            text="Alex Example",
        ),
        CVClaim(
            claim_id="fact:role",
            section="headline",
            kind="headline",
            text="Software & Operations Developer",
        ),
        CVClaim(
            claim_id="fact:email",
            section="headline",
            kind="contact",
            text="alex@example.test",
        ),
        CVClaim(
            claim_id="approved:summary",
            section="summary",
            kind="summary",
            text="Builds software and operational workflows.",
        ),
        CVClaim(
            claim_id="fact:python",
            section="skills",
            kind="skill",
            text="Python",
        ),
        CVClaim(
            claim_id="fact:project",
            section="projects",
            kind="project",
            text="Fleet Simulator",
        ),
        CVClaim(
            claim_id="fact:employment",
            section="experience",
            kind="organization",
            text="Example Operations | 2024–Present",
        ),
        CVClaim(
            claim_id="approved:employment-bullet",
            section="experience",
            kind="bullet",
            text="Improved workflow visibility.",
        ),
        CVClaim(
            claim_id="fact:education",
            section="education",
            kind="education",
            text="BSc Applied Sciences",
        ),
    ]
    return CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=claims,
        entries=[],
        provenance_map={
            claim.claim_id: ClaimProvenance(fact_ids=[claim.claim_id])
            for claim in claims
        },
    )


def _source_validation(document: CVDocumentModel) -> ValidationResult:
    return ValidationResult(
        valid=True,
        validated_claim_ids=[claim.claim_id for claim in document.claims],
    )


def _recruiter_document() -> RecruiterDocumentModel:
    return RecruiterDocumentModel(
        source_cv_document_version="cvdoc-v1",
        language="en",
        identity_claim_id="fact:name",
        headline_claim_id="fact:role",
        contact_claim_ids=["fact:email"],
        profile_claim_ids=["approved:summary"],
        technology_groups=[
            TechnologyGroup(
                label_id="software_data",
                skill_claim_ids=["fact:python"],
            )
        ],
        selected_project_claim_ids=["fact:project"],
        experience_entries=[
            RecruiterExperienceEntry(
                primary_claim_id="fact:employment",
                bullet_claim_ids=["approved:employment-bullet"],
            )
        ],
        education_claim_ids=["fact:education"],
    )


def _policy():
    return load_recruiter_policy("config/recruiter_policy.yaml")


def test_valid_recruiter_document_passes_structural_validation():
    source = _source_document()
    result = validate_recruiter_document(
        recruiter_document=_recruiter_document(),
        source_document=source,
        source_validation=_source_validation(source),
        policy=_policy(),
    )

    assert result.valid
    assert result.errors == []
    assert set(result.validated_claim_ids) == set(_recruiter_document().all_claim_ids())


def test_recruiter_validator_rejects_unvalidated_claim_reference():
    source = _source_document()
    source_validation = _source_validation(source).model_copy(
        update={
            "validated_claim_ids": [
                claim_id
                for claim_id in _source_validation(source).validated_claim_ids
                if claim_id != "fact:role"
            ]
        }
    )

    result = validate_recruiter_document(
        recruiter_document=_recruiter_document(),
        source_document=source,
        source_validation=source_validation,
        policy=_policy(),
    )

    assert not result.valid
    assert "recruiter_unvalidated_claim_reference" in {
        issue.code for issue in result.errors
    }


def test_recruiter_validator_rejects_unknown_claim_reference():
    source = _source_document()
    recruiter = _recruiter_document().model_copy(
        update={"headline_claim_id": "claim:not-in-source"}
    )

    result = validate_recruiter_document(
        recruiter_document=recruiter,
        source_document=source,
        source_validation=_source_validation(source),
        policy=_policy(),
    )

    assert not result.valid
    assert "recruiter_unknown_claim_reference" in {
        issue.code for issue in result.errors
    }


def test_recruiter_validator_rejects_unknown_group_label():
    source = _source_document()
    recruiter = _recruiter_document().model_copy(
        update={
            "technology_groups": [
                TechnologyGroup(
                    label_id="aws_expert",
                    skill_claim_ids=["fact:python"],
                )
            ]
        }
    )

    result = validate_recruiter_document(
        recruiter_document=recruiter,
        source_document=source,
        source_validation=_source_validation(source),
        policy=_policy(),
    )

    assert not result.valid
    assert "recruiter_group_label_not_allowed" in {
        issue.code for issue in result.errors
    }


def test_recruiter_validator_rejects_source_document_version_mismatch():
    source = _source_document()
    recruiter = _recruiter_document().model_copy(
        update={"source_cv_document_version": "cvdoc-other"}
    )

    result = validate_recruiter_document(
        recruiter_document=recruiter,
        source_document=source,
        source_validation=_source_validation(source),
        policy=_policy(),
    )

    assert not result.valid
    assert "recruiter_source_document_version_mismatch" in {
        issue.code for issue in result.errors
    }


def test_recruiter_validator_enforces_dynamic_policy_caps():
    source = _source_document()
    recruiter = _recruiter_document()
    stricter_policy = _policy().model_copy(update={"max_projects": 0})

    result = validate_recruiter_document(
        recruiter_document=recruiter,
        source_document=source,
        source_validation=_source_validation(source),
        policy=stricter_policy,
    )

    assert not result.valid
    assert "recruiter_project_cap_exceeded" in {
        issue.code for issue in result.errors
    }


def test_recruiter_validator_rejects_wrong_kind_in_project_entry():
    source = _source_document()
    recruiter = _recruiter_document().model_copy(
        update={
            "project_entries": [
                RecruiterProjectEntry(
                    primary_claim_id="fact:project",
                    bullet_claim_ids=["fact:education"],
                )
            ]
        }
    )

    result = validate_recruiter_document(
        recruiter_document=recruiter,
        source_document=source,
        source_validation=_source_validation(source),
        policy=_policy(),
    )

    assert not result.valid
    assert "recruiter_claim_role_mismatch" in {
        issue.code for issue in result.errors
    }
