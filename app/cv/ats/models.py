from __future__ import annotations

from pydantic import Field, model_validator

from app.cv.models import StrictCVModel, ValidationIssue


class ParsedResume(StrictCVModel):
    parser_version: str = Field(min_length=1)
    identity: str | None = None
    headline: str | None = None
    contacts: list[str] = Field(default_factory=list)
    profile: list[str] = Field(default_factory=list)
    technology: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    link_uris: list[str] = Field(default_factory=list)
    extracted_text: str = ""


class ATSCategoryRecovery(StrictCVModel):
    expected_claim_ids: list[str] = Field(default_factory=list)
    recovered_claim_ids: list[str] = Field(default_factory=list)
    recovery_ratio: float = Field(ge=0, le=1)


class ATSRoundTripQAResult(StrictCVModel):
    valid: bool
    parser_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    categories: dict[str, ATSCategoryRecovery] = Field(default_factory=dict)
    aggregate_recovery_ratio: float = Field(ge=0, le=1)
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self) -> "ATSRoundTripQAResult":
        if self.valid != (not self.errors):
            raise ValueError("valid must match absence of ATS round-trip errors")
        return self
