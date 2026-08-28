from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.domain import SearchIntent
from app.radar.models import ApplicationMode

ContactChannel = Literal[
    "PUBLISHED_VACANCY_EMAIL",
    "OFFICIAL_HR_EMAIL",
    "VERIFIED_RECRUITER",
    "MANUAL_FORM",
]
ContactVerificationStatus = Literal[
    "VERIFIED_DIRECT",
    "VERIFIED_OFFICIAL",
    "IDENTITY_VERIFIED_EMAIL_UNKNOWN",
    "VERIFIED_ENRICHED",
    "MANUAL_ONLY",
    "UNVERIFIED",
]
ContactSourceKind = Literal["VACANCY", "OFFICIAL_SITE", "APOLLO", "MANUAL"]
ContactResolutionStatus = Literal[
    "RESOLVED",
    "BLOCKED_NO_CONTACT",
    "MANUAL_ONLY",
    "REQUIRES_ENRICHMENT",
    "BLOCKED_POLICY",
]
OutreachPreparationStatus = Literal[
    "OUTREACH_READY",
    "BLOCKED_INVALID_PACKET",
    "BLOCKED_CV_CHANGED",
    "BLOCKED_CONTACT",
    "BLOCKED_STRETCH",
    "BLOCKED_POLICY",
]
DraftVerificationBasis = Literal[
    "CREATED_EXACT",
    "RECREATED_EXACT",
    "READBACK_EXACT",
    "UNVERIFIABLE",
]
ApprovalScope = Literal["SINGLE", "BATCH"]
ApprovalStatus = Literal["ACTIVE", "REVOKED", "EXPIRED"]
SendAuthorizationStatus = Literal["AUTHORIZED", "BLOCKED"]
OutreachEventType = Literal[
    "PACKET_ACCEPTED",
    "CONTACT_RESOLVED",
    "OUTREACH_READY",
    "DRAFT_CREATED",
    "DRAFT_REPLACED",
    "APPROVED",
    "APPROVAL_INVALIDATED",
    "SEND_REQUESTED",
    "SEND_ATTEMPTED",
    "SENT",
    "SEND_FAILED",
    "MANUAL_ROUTE",
    "RESPONSE_OBSERVED",
]


class StrictOutreachModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def require_aware_datetimes(self):
        for field_name in self.__class__.model_fields:
            value = getattr(self, field_name)
            if isinstance(value, datetime):
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError(f"{field_name} must be timezone-aware")
                setattr(self, field_name, value.astimezone(timezone.utc))
        return self


class ContactPolicy(StrictOutreachModel):
    resolver_version: str = "contact-v1"
    priority: list[ContactChannel] = Field(
        default_factory=lambda: [
            "PUBLISHED_VACANCY_EMAIL",
            "OFFICIAL_HR_EMAIL",
            "VERIFIED_RECRUITER",
            "MANUAL_FORM",
        ]
    )
    max_recruiter_contacts_per_company_day: int = Field(default=2, ge=0)


class ContactCandidate(StrictOutreachModel):
    candidate_id: str = Field(min_length=1)
    opportunity_id: str = Field(min_length=1)
    channel: ContactChannel
    email: str | None = None
    contact_name: str | None = None
    contact_role: str | None = None
    organization: str = Field(min_length=1)
    source_kind: ContactSourceKind
    source_ref: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    verification_status: ContactVerificationStatus
    requires_paid_enrichment: bool = False
    discovered_at: datetime


class ContactResolution(StrictOutreachModel):
    opportunity_id: str = Field(min_length=1)
    selected_candidate_id: str | None = None
    channel: ContactChannel
    email: str | None = None
    contact_name: str | None = None
    contact_role: str | None = None
    organization: str = Field(min_length=1)
    source_kind: ContactSourceKind
    source_ref: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    verification_status: ContactVerificationStatus
    resolution_reason: str = Field(min_length=1)
    resolved_at: datetime
    resolver_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_actionable_email(self):
        if self.email is not None and self.verification_status in {
            "UNVERIFIED",
            "IDENTITY_VERIFIED_EMAIL_UNKNOWN",
            "MANUAL_ONLY",
        }:
            raise ValueError("actionable email requires verified contact provenance")
        return self


class ContactResolutionResult(StrictOutreachModel):
    status: ContactResolutionStatus
    resolution: ContactResolution | None = None
    candidates: list[ContactCandidate] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class StretchPromotion(StrictOutreachModel):
    opportunity_id: str = Field(min_length=1)
    promoted_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    promoted_at: datetime


class OutreachPolicy(StrictOutreachModel):
    brief_version: str = "outreach-brief-v1"
    automatic_tiers: list[str] = Field(default_factory=lambda: ["HIGH", "MEDIUM"])
    max_allowed_claims: int = Field(default=6, ge=1)
    max_why_fit: int = Field(default=3, ge=1)
    tone_policy: str = "concise_professional"
    call_to_action_policy: str = "simple_next_step"


class OutreachClaim(StrictOutreachModel):
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    fact_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class OutreachBrief(StrictOutreachModel):
    brief_id: str = Field(min_length=1)
    opportunity_id: str = Field(min_length=1)
    opportunity_snapshot_hash: str = Field(min_length=64, max_length=64)
    company: str = Field(min_length=1)
    role: str = Field(min_length=1)
    selected_intent: SearchIntent
    application_track_id: str = Field(min_length=1)
    tier: str = Field(min_length=1)
    contact_resolution: ContactResolution
    application_mode: ApplicationMode
    why_fit: list[str] = Field(default_factory=list)
    strongest_evidence: list[OutreachClaim] = Field(default_factory=list)
    selected_fact_ids: list[str] = Field(default_factory=list)
    selected_evidence_ids: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    allowed_claims: list[OutreachClaim] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    language: Literal["es", "en"]
    tone_policy: str = Field(min_length=1)
    call_to_action_policy: str = Field(min_length=1)
    cv_pdf_path: str = Field(min_length=1)
    cv_filename: str = Field(min_length=1)
    cv_sha256: str = Field(min_length=64, max_length=64)
    application_packet_sha256: str = Field(min_length=64, max_length=64)
    brief_version: str = Field(min_length=1)
    brief_sha256: str = Field(min_length=64, max_length=64)
    created_at: datetime


class OutreachPreparationResult(StrictOutreachModel):
    status: OutreachPreparationStatus
    brief: OutreachBrief | None = None
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ready_state(self):
        if self.status == "OUTREACH_READY" and self.brief is None:
            raise ValueError("OUTREACH_READY requires brief")
        if self.status != "OUTREACH_READY" and self.brief is not None:
            raise ValueError("blocked outreach result cannot contain brief")
        return self


class DraftAttachment(StrictOutreachModel):
    filename: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    role: Literal["CV", "OTHER"]


class DraftSnapshot(StrictOutreachModel):
    draft_snapshot_id: str = Field(min_length=1)
    opportunity_id: str = Field(min_length=1)
    brief_sha256: str = Field(min_length=64, max_length=64)
    application_packet_sha256: str = Field(min_length=64, max_length=64)
    provider: Literal["gmail"] = "gmail"
    provider_draft_id: str = Field(min_length=1)
    reply_message_id: str | None = None
    to: list[str] = Field(min_length=1)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str = Field(min_length=1)
    body_canonical: str = Field(min_length=1)
    attachments: list[DraftAttachment] = Field(min_length=1)
    cv_sha256: str = Field(min_length=64, max_length=64)
    content_type: Literal["text/plain", "text/markdown", "text/html"]
    verification_basis: DraftVerificationBasis
    draft_sha256: str = Field(min_length=64, max_length=64)
    created_at: datetime
    verified_at: datetime

    @model_validator(mode="after")
    def validate_cv_attachment(self):
        cvs = [attachment for attachment in self.attachments if attachment.role == "CV"]
        if len(cvs) != 1:
            raise ValueError("draft requires exactly one CV attachment")
        if cvs[0].sha256 != self.cv_sha256:
            raise ValueError("CV attachment hash must match cv_sha256")
        return self


class ApprovalRequest(StrictOutreachModel):
    requested_by: str = Field(min_length=1)
    approval_scope: ApprovalScope
    draft_sha256: str = Field(min_length=64, max_length=64)
    draft_sha256s: list[str] = Field(default_factory=list)
    batch_manifest_sha256: str | None = None
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        if self.approval_scope == "BATCH":
            if self.batch_manifest_sha256 is None or not self.draft_sha256s:
                raise ValueError("batch approval request requires manifest and draft hashes")
        elif self.batch_manifest_sha256 is not None:
            raise ValueError("single approval request forbids batch manifest")
        return self


class ApprovalRecord(StrictOutreachModel):
    approval_id: str = Field(min_length=1)
    opportunity_id: str = Field(min_length=1)
    draft_sha256: str = Field(min_length=64, max_length=64)
    application_packet_sha256: str = Field(min_length=64, max_length=64)
    approved_by: str = Field(min_length=1)
    approval_scope: ApprovalScope
    batch_manifest_sha256: str | None = None
    approved_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    status: ApprovalStatus = "ACTIVE"

    @model_validator(mode="after")
    def validate_scope_and_status(self):
        if self.approval_scope == "BATCH" and self.batch_manifest_sha256 is None:
            raise ValueError("batch approval requires batch manifest")
        if self.approval_scope == "SINGLE" and self.batch_manifest_sha256 is not None:
            raise ValueError("single approval forbids batch manifest")
        if self.status == "ACTIVE" and self.revoked_at is not None:
            raise ValueError("revoked approval cannot remain ACTIVE")
        if self.status == "REVOKED" and self.revoked_at is None:
            raise ValueError("REVOKED approval requires revoked_at")
        if self.status == "EXPIRED" and self.expires_at is None:
            raise ValueError("EXPIRED approval requires expires_at")
        return self


class SendRequest(StrictOutreachModel):
    request_id: str = Field(min_length=1)
    opportunity_id: str = Field(min_length=1)
    draft_sha256: str = Field(min_length=64, max_length=64)
    requested_by: str = Field(min_length=1)
    requested_at: datetime
    approval_id: str = Field(min_length=1)
    batch_manifest_sha256: str | None = None


class SendAuthorizationResult(StrictOutreachModel):
    status: SendAuthorizationStatus
    authorized: bool
    idempotency_key: str | None = None
    error_code: str | None = None

    @model_validator(mode="after")
    def validate_authorization(self):
        if self.authorized:
            if self.status != "AUTHORIZED" or self.idempotency_key is None:
                raise ValueError("authorized result requires idempotency key")
        elif self.status != "BLOCKED" or self.error_code is None:
            raise ValueError("blocked result requires error code")
        return self


class SendReceipt(StrictOutreachModel):
    receipt_id: str = Field(min_length=1)
    opportunity_id: str = Field(min_length=1)
    approval_id: str = Field(min_length=1)
    send_request_id: str = Field(min_length=1)
    draft_sha256: str = Field(min_length=64, max_length=64)
    application_packet_sha256: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=64, max_length=64)
    provider: Literal["gmail"] = "gmail"
    provider_message_id: str = Field(min_length=1)
    provider_thread_id: str | None = None
    recipient: str = Field(min_length=1)
    sent_at: datetime
    status: Literal["SENT"] = "SENT"


class OutreachEvent(StrictOutreachModel):
    event_id: str = Field(min_length=1)
    opportunity_id: str = Field(min_length=1)
    event_type: OutreachEventType
    entity_key: str | None = None
    occurred_at: datetime
    metadata: dict[str, str] = Field(default_factory=dict)
