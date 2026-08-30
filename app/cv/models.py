from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.domain import SearchIntent

FactKind = Literal[
    "identity",
    "contact",
    "summary_claim",
    "skill",
    "role",
    "employment",
    "education",
    "project",
    "language",
    "location",
    "link",
    "achievement",
    "metric",
    "other",
]
VerificationMethod = Literal[
    "manual_confirmation",
    "repository_evidence",
    "document_evidence",
    "employment_record",
    "education_record",
    "public_profile",
    "other_reviewed_source",
]
CVSection = Literal[
    "headline",
    "summary",
    "experience",
    "projects",
    "education",
    "skills",
    "languages",
    "links",
]
ClaimKind = Literal[
    "identity",
    "contact",
    "location",
    "headline",
    "summary",
    "organization",
    "title",
    "date",
    "bullet",
    "project",
    "education",
    "skill",
    "language",
    "link",
]
SupportLevel = Literal[
    "EXACT_VERIFIED",
    "APPROVED_ALIAS",
    "TAXONOMY_RELATED",
    "UNKNOWN",
]
PreparationStatus = Literal[
    "PREPARED",
    "BLOCKED_VALIDATION",
    "BLOCKED_MISSING_FACTS",
    "BLOCKED_TRACK_UNAVAILABLE",
    "BLOCKED_RENDER",
]
OutputLanguage = Literal["es", "en"]


class StrictCVModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _require_aware(value: datetime, *, field_name: str) -> datetime:
    if not _is_aware(value):
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


class MasterFact(StrictCVModel):
    id: str = Field(min_length=1)
    kind: FactKind
    value: str = Field(min_length=1)
    display_values: dict[str, str] = Field(default_factory=dict)
    track_ids: list[str] = Field(default_factory=list)
    verified: bool = False
    verification_method: VerificationMethod | None = None
    verified_at: datetime | None = None
    source_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_verification(self) -> "MasterFact":
        if self.verified:
            if self.verification_method is None or self.verified_at is None:
                raise ValueError(
                    "verified facts require verification_method and verified_at"
                )
            self.verified_at = _require_aware(
                self.verified_at,
                field_name="verified_at",
            )
            if self.verification_method != "manual_confirmation":
                if self.source_ref is None or not self.source_ref.strip():
                    raise ValueError(
                        "evidence-backed verification requires source_ref"
                    )
        elif self.verified_at is not None:
            self.verified_at = _require_aware(
                self.verified_at,
                field_name="verified_at",
            )
        return self


class ApprovedClaim(StrictCVModel):
    id: str = Field(min_length=1)
    section: CVSection
    kind: ClaimKind
    text_by_language: dict[str, str] = Field(min_length=1)
    fact_ids: list[str] = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)


class EvidenceModule(StrictCVModel):
    id: str = Field(min_length=1)
    track_ids: list[str] = Field(min_length=1)
    label: str = Field(min_length=1)
    fact_ids: list[str] = Field(min_length=1)
    claims: list[ApprovedClaim] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    verified: bool


class MasterFactsSnapshot(StrictCVModel):
    schema_version: str = Field(min_length=1)
    content_sha256: str = Field(min_length=64, max_length=64)
    facts: list[MasterFact] = Field(default_factory=list)


class EvidenceCatalogSnapshot(StrictCVModel):
    schema_version: str = Field(min_length=1)
    content_sha256: str = Field(min_length=64, max_length=64)
    modules: list[EvidenceModule] = Field(default_factory=list)


class CVPolicy(StrictCVModel):
    language: OutputLanguage = "en"
    required_identity_kinds: list[FactKind] = Field(default_factory=list)
    required_sections: list[CVSection] = Field(default_factory=list)
    section_order: list[CVSection] = Field(
        default_factory=lambda: [
            "summary",
            "skills",
            "experience",
            "projects",
            "education",
            "languages",
            "links",
        ]
    )


class RequirementSupport(StrictCVModel):
    requirement: str = Field(min_length=1)
    support_level: SupportLevel
    fact_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    explanation: str = Field(min_length=1)


class EvidenceSelection(StrictCVModel):
    application_track_id: str = Field(min_length=1)
    selected_fact_ids: list[str] = Field(default_factory=list)
    selected_evidence_ids: list[str] = Field(default_factory=list)
    requirement_support: dict[str, RequirementSupport] = Field(default_factory=dict)
    unsupported_requirements: list[str] = Field(default_factory=list)
    selection_explanations: list[str] = Field(default_factory=list)


class ClaimProvenance(StrictCVModel):
    fact_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    approved_claim_id: str | None = None


class CVClaim(StrictCVModel):
    claim_id: str = Field(min_length=1)
    section: CVSection
    kind: ClaimKind
    text: str = Field(min_length=1)


class CVEntry(StrictCVModel):
    entry_id: str = Field(min_length=1)
    section: CVSection
    claim_ids: list[str] = Field(min_length=1)


class CVDocumentModel(StrictCVModel):
    document_version: str = Field(min_length=1)
    language: OutputLanguage
    claims: list[CVClaim] = Field(default_factory=list)
    entries: list[CVEntry] = Field(default_factory=list)
    provenance_map: dict[str, ClaimProvenance] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_claim_references(self) -> "CVDocumentModel":
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("CV claim ids must be unique")
        missing_provenance = [
            claim_id for claim_id in claim_ids if claim_id not in self.provenance_map
        ]
        if missing_provenance:
            raise ValueError("every visible CV claim requires provenance")
        known = set(claim_ids)
        for entry in self.entries:
            if any(claim_id not in known for claim_id in entry.claim_ids):
                raise ValueError("CV entry references unknown claim")
        return self


class ValidationIssue(StrictCVModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    claim_id: str | None = None


class ValidationResult(StrictCVModel):
    valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    validated_claim_ids: list[str] = Field(default_factory=list)


class RenderedCVArtifact(StrictCVModel):
    path: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    renderer_version: str = Field(min_length=1)


class RenderLayoutMetrics(StrictCVModel):
    page_count: int = Field(ge=0)
    usable_height: float = Field(gt=0)
    rendered_content_height: float = Field(ge=0)
    headline_line_count: int = Field(ge=0)
    body_font_size: float = Field(gt=0)


class LayoutQAResult(StrictCVModel):
    valid: bool
    page_count: int = Field(ge=0)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    errors: list[ValidationIssue] = Field(default_factory=list)
    used_height_ratio: float = Field(ge=0)


class ApplicationPacket(StrictCVModel):
    status: Literal["PREPARED"] = "PREPARED"
    application_id: str = Field(min_length=1)
    opportunity_id: str = Field(min_length=1)
    opportunity_snapshot_hash: str = Field(min_length=64, max_length=64)
    radar_batch_id: str | None = None
    selected_intent: SearchIntent
    application_track_id: str = Field(min_length=1)
    career_match: float | None = Field(default=None, ge=0, le=100)
    income_viability: float | None = Field(default=None, ge=0, le=100)
    confidence_score: float = Field(ge=0, le=100)
    scoring_version: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    alias_registry_version: str = Field(min_length=1)
    taxonomy_versions: dict[str, str] = Field(default_factory=dict)
    master_facts_version: str = Field(min_length=64, max_length=64)
    evidence_catalog_version: str = Field(min_length=64, max_length=64)
    composer_version: str = Field(min_length=1)
    cv_document_version: str = Field(min_length=1)
    recruiter_policy_version: str = Field(min_length=1)
    renderer_version: str = Field(min_length=1)
    selected_fact_ids: list[str] = Field(default_factory=list)
    selected_evidence_ids: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    cv_document: CVDocumentModel
    recruiter_document: Any
    cv_pdf_path: str = Field(min_length=1)
    cv_sha256: str = Field(min_length=64, max_length=64)
    packet_sha256: str = Field(min_length=64, max_length=64)
    created_at: datetime

    @field_validator("recruiter_document", mode="before")
    @classmethod
    def recruiter_document_must_be_typed(cls, value: Any) -> Any:
        # Imported lazily to keep app.cv.models independent from recruiter_models,
        # which itself depends on the core CV models in this module.
        from app.cv.recruiter_models import RecruiterDocumentModel

        return RecruiterDocumentModel.model_validate(value)

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_aware(cls, value: datetime) -> datetime:
        return _require_aware(value, field_name="created_at")


class PreparationResult(StrictCVModel):
    status: PreparationStatus
    packet: ApplicationPacket | None = None
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_packet_state(self) -> "PreparationResult":
        if self.status == "PREPARED" and self.packet is None:
            raise ValueError("PREPARED result requires a packet")
        if self.status != "PREPARED" and self.packet is not None:
            raise ValueError("blocked preparation result cannot contain a packet")
        return self
