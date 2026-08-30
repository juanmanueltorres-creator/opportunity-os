from __future__ import annotations

from pydantic import Field, model_validator

from app.cv.models import (
    OutputLanguage,
    RenderedCVArtifact,
    StrictCVModel,
    ValidationIssue,
)

RECRUITER_DOCUMENT_VERSION = "recruiter-doc-v1"


class TechnologyGroup(StrictCVModel):
    label_id: str = Field(min_length=1)
    skill_claim_ids: list[str] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def skill_claim_ids_must_be_unique(self) -> "TechnologyGroup":
        if len(self.skill_claim_ids) != len(set(self.skill_claim_ids)):
            raise ValueError("technology group skill claim ids must be unique")
        return self


class RecruiterProjectEntry(StrictCVModel):
    primary_claim_id: str = Field(min_length=1)
    bullet_claim_ids: list[str] = Field(default_factory=list, max_length=1)


class RecruiterExperienceEntry(StrictCVModel):
    primary_claim_id: str = Field(min_length=1)
    bullet_claim_ids: list[str] = Field(default_factory=list, max_length=1)


class RecruiterDocumentModel(StrictCVModel):
    document_version: str = RECRUITER_DOCUMENT_VERSION
    source_cv_document_version: str = Field(min_length=1)
    language: OutputLanguage
    identity_claim_id: str = Field(min_length=1)
    headline_claim_id: str = Field(min_length=1)
    contact_claim_ids: list[str] = Field(default_factory=list)
    profile_claim_ids: list[str] = Field(default_factory=list, max_length=3)
    technology_groups: list[TechnologyGroup] = Field(default_factory=list, max_length=4)
    selected_project_claim_ids: list[str] = Field(default_factory=list, max_length=4)
    project_entries: list[RecruiterProjectEntry] = Field(default_factory=list, max_length=4)
    experience_entries: list[RecruiterExperienceEntry] = Field(
        default_factory=list,
        max_length=5,
    )
    education_claim_ids: list[str] = Field(default_factory=list, max_length=4)
    language_claim_ids: list[str] = Field(default_factory=list)
    link_claim_ids: list[str] = Field(default_factory=list)

    def all_claim_ids(self) -> list[str]:
        ordered = [self.identity_claim_id, self.headline_claim_id]
        ordered.extend(self.contact_claim_ids)
        ordered.extend(self.profile_claim_ids)
        for group in self.technology_groups:
            ordered.extend(group.skill_claim_ids)
        if self.project_entries:
            for entry in self.project_entries:
                ordered.append(entry.primary_claim_id)
                ordered.extend(entry.bullet_claim_ids)
        else:
            ordered.extend(self.selected_project_claim_ids)
        for entry in self.experience_entries:
            ordered.append(entry.primary_claim_id)
            ordered.extend(entry.bullet_claim_ids)
        ordered.extend(self.education_claim_ids)
        ordered.extend(self.language_claim_ids)
        ordered.extend(self.link_claim_ids)
        return ordered

    @model_validator(mode="after")
    def project_claim_ids_must_be_unique(self) -> "RecruiterDocumentModel":
        project_ids = self.selected_project_claim_ids
        if len(project_ids) != len(set(project_ids)):
            raise ValueError("recruiter project claim ids must be unique")
        return self


class RecruiterRenderMetrics(StrictCVModel):
    # Metrics describe renderer output; QA owns the >=9pt acceptance gate.
    body_font_size: float = Field(gt=0)
    headline_line_count: int = Field(ge=0)
    overflow_detected: bool = False


class RecruiterRenderResult(StrictCVModel):
    artifact: RenderedCVArtifact
    metrics: RecruiterRenderMetrics


class RecruiterQAResult(StrictCVModel):
    valid: bool
    page_count: int = Field(ge=0)
    extracted_text: str = ""
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
