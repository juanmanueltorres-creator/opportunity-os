from app.cv.recruiter_composer import reduce_recruiter_document
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterExperienceEntry,
    RecruiterProjectEntry,
    TechnologyGroup,
)
from app.cv.recruiter_policy import load_recruiter_policy


def test_reduction_skips_last_skill_and_continues_with_projects() -> None:
    recruiter_policy = load_recruiter_policy("config/recruiter_policy.yaml")
    document = RecruiterDocumentModel(
        source_cv_document_version="cvdoc-v1",
        language="en",
        identity_claim_id="name",
        headline_claim_id="headline",
        technology_groups=[
            TechnologyGroup(label_id="software_data", skill_claim_ids=["skill-python"])
        ],
        selected_project_claim_ids=["project-1", "project-2", "project-3"],
        project_entries=[
            RecruiterProjectEntry(primary_claim_id="project-1"),
            RecruiterProjectEntry(primary_claim_id="project-2"),
            RecruiterProjectEntry(primary_claim_id="project-3"),
        ],
        experience_entries=[
            RecruiterExperienceEntry(primary_claim_id="experience-1"),
            RecruiterExperienceEntry(primary_claim_id="experience-2"),
        ],
        education_claim_ids=["education-1", "education-2"],
    )

    reduced = reduce_recruiter_document(
        document,
        recruiter_policy,
        step=0,
    )

    assert reduced.technology_groups == document.technology_groups
    assert [entry.primary_claim_id for entry in reduced.project_entries] == [
        "project-1",
        "project-2",
    ]
    assert reduced.selected_project_claim_ids == ["project-1", "project-2"]
