# Opportunity OS V0.2C Plan — Self-review Corrections

Date: 2026-08-28
Status: normative companion
Plan: `docs/superpowers/plans/2026-08-28-opportunity-os-v0.2c-email-outreach.md`
Spec: `docs/superpowers/specs/2026-08-28-opportunity-os-v0.2c-email-outreach-design.md`

This file is part of the implementation plan. Where the base plan is abbreviated, this file supplies the exact contract or invariant. If wording conflicts, this file wins.

## 1. Exact outreach contracts

Task 2 must define these contracts exactly enough that later tasks do not invent fields ad hoc.

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.domain import SearchIntent
from app.radar.models import ApplicationMode


class StrictOutreachModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
```

Every datetime field above must use a shared validator that rejects naive values and normalizes to UTC.

## 2. Exact brief hash payload

Task 2's `brief_semantic_payload()` must be:

```python
def brief_semantic_payload(brief: OutreachBrief) -> dict:
    return {
        "opportunity_id": brief.opportunity_id,
        "opportunity_snapshot_hash": brief.opportunity_snapshot_hash,
        "company": brief.company,
        "role": brief.role,
        "selected_intent": brief.selected_intent,
        "application_track_id": brief.application_track_id,
        "tier": brief.tier,
        "contact_resolution": brief.contact_resolution.model_dump(mode="json"),
        "application_mode": brief.application_mode,
        "why_fit": brief.why_fit,
        "strongest_evidence": [
            claim.model_dump(mode="json") for claim in brief.strongest_evidence
        ],
        "selected_fact_ids": brief.selected_fact_ids,
        "selected_evidence_ids": brief.selected_evidence_ids,
        "unresolved_gaps": brief.unresolved_gaps,
        "allowed_claims": [claim.model_dump(mode="json") for claim in brief.allowed_claims],
        "forbidden_claims": brief.forbidden_claims,
        "language": brief.language,
        "tone_policy": brief.tone_policy,
        "call_to_action_policy": brief.call_to_action_policy,
        "cv_filename": brief.cv_filename,
        "cv_sha256": brief.cv_sha256,
        "application_packet_sha256": brief.application_packet_sha256,
        "brief_version": brief.brief_version,
    }
```

`brief_id`, `created_at`, and local `cv_pdf_path` are intentionally excluded.

## 3. Ledger transition validation is mandatory

The base plan's append-only ledger is insufficient unless it rejects impossible later states.

Add to `app/outreach/repository.py`:

```python
_REQUIRED_PREDECESSOR: dict[str, set[str]] = {
    "CONTACT_RESOLVED": {"PACKET_ACCEPTED"},
    "OUTREACH_READY": {"CONTACT_RESOLVED"},
    "DRAFT_CREATED": {"OUTREACH_READY"},
    "DRAFT_REPLACED": {"DRAFT_CREATED", "DRAFT_REPLACED"},
    "APPROVED": {"DRAFT_CREATED", "DRAFT_REPLACED"},
    "SEND_REQUESTED": {"APPROVED"},
    "SEND_ATTEMPTED": {"SEND_REQUESTED"},
    "SENT": {"SEND_ATTEMPTED"},
    "SEND_FAILED": {"SEND_ATTEMPTED"},
}


def _validate_event_transition(
    event: OutreachEvent,
    prior_events: list[OutreachEvent],
) -> None:
    required = _REQUIRED_PREDECESSOR.get(event.event_type)
    if required is None:
        return
    prior_types = {item.event_type for item in prior_events}
    if not prior_types.intersection(required):
        raise ValueError("outreach event transition missing required predecessor")
```

`append_event()` must load the opportunity history, call this validator, then insert. Add tests that `SENT` cannot be appended after only `APPROVED`, and `SEND_REQUESTED` cannot exist before `APPROVED`.

## 4. Provider call boundary needs SEND_ATTEMPTED before receipt

The safe external sequence is:

```text
SendGate AUTHORIZED
→ repository append SEND_ATTEMPTED
→ ChatGPT calls Gmail send_draft
→ success: record SendReceipt + SENT
→ failure: append SEND_FAILED
```

Add to `app/outreach/send.py`:

```python
def mark_send_attempted(
    *,
    authorization: SendAuthorizationResult,
    send_request: SendRequest,
    ledger: SQLiteOutreachRepository,
    now: datetime,
    id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> OutreachEvent:
    if not authorization.authorized or authorization.idempotency_key is None:
        raise ValueError("send attempt requires authorization")
    event = OutreachEvent(
        event_id=id_factory(),
        opportunity_id=send_request.opportunity_id,
        event_type="SEND_ATTEMPTED",
        entity_key=authorization.idempotency_key,
        occurred_at=now,
    )
    return ledger.append_event(event)
```

`record_successful_send()` must verify that the latest event chain contains `SEND_ATTEMPTED` for the same idempotency key before creating a receipt.

## 5. One initial contact per requisition is stronger than hash idempotency

A new body/hash must not become a loophole for another initial email to the same opportunity.

`SendGate.validate()` must check both:

```python
if ledger.has_successful_send_for_opportunity(draft_snapshot.opportunity_id):
    return blocked("already_sent")

existing = ledger.get_send_receipt_by_idempotency_key(key)
if existing is not None:
    return blocked("already_sent")
```

The opportunity-level check occurs before authorization. Add a regression where the second draft has a different body/hash but the same `opportunity_id`; it must still block after the first successful receipt.

## 6. Exact re-created Gmail draft behavior

When exact Gmail readback is unavailable, V0.2C remains usable only by reconstructing the approved semantic payload.

Rules:

1. Original reviewed snapshot may have `verification_basis="CREATED_EXACT"`.
2. Approval binds its `draft_sha256`.
3. At send time, ChatGPT may create a fresh Gmail draft using the exact canonical recipient/subject/body/attachment filename+bytes.
4. Register the new provider ID with `verification_basis="RECREATED_EXACT"`.
5. Recompute hash.
6. If the hash differs, approval is invalid and send blocks.
7. If the hash is identical, approval remains semantically valid despite a different Gmail draft ID.

Add an integration test with provider IDs `draft-reviewed` and `draft-send-copy` and assert equal semantic hashes.

## 7. Release contract test must be executable

Do not use an undefined helper such as `project_version()`.

Use Python 3.12 stdlib `tomllib`:

```python
from pathlib import Path
import tomllib


def test_package_version_is_v02c_prerelease() -> None:
    payload = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert payload["project"]["version"] == "0.2.0c1"
```

## 8. Exact first operational milestone

V0.2C does not need Apollo to be considered usable for the first real application.

Release candidate acceptance path:

```text
real valid ApplicationPacket
→ real vacancy-published or manually verified official email
→ deterministic OutreachBrief
→ ChatGPT creates Gmail draft with exact CV
→ known DraftSnapshot recorded
→ user reviews
→ ApprovalRecord
→ separate explicit user send instruction / SendRequest
→ if needed, exact semantic draft recreated
→ SendGate AUTHORIZED
→ SEND_ATTEMPTED
→ Gmail send_draft
→ valid Gmail provider message ID
→ SendReceipt + SENT event
```

Recruiter identity search/enrichment is a follow-on use of the existing `ContactCandidate` interface; it must not delay the direct-email path.
