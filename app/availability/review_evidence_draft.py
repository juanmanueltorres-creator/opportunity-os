from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.availability.repository import SQLiteAvailabilityRepository
from app.availability.verification_models import (
    VerificationDecision,
    VerificationEvidence,
    VerificationEvidenceKind,
    VerificationPreview,
)
from app.availability.verification_review_session import (
    VerificationReviewCard,
    review_card_sha256,
)
from app.availability.verification_service import AvailabilityVerificationService
from app.radar.models import StrictRadarModel
from app.repositories.opportunities import SQLiteOpportunityRepository


EvidenceDraftStatus = Literal[
    "READY",
    "BLOCKED_STALE_CARD",
    "BLOCKED_NOT_FOUND",
    "BLOCKED_EVIDENCE_KIND",
    "BLOCKED_FUTURE_OBSERVATION",
]

EVIDENCE_DRAFT_VERSION = "review-evidence-draft-v1"


class ReviewEvidenceDraftRequest(StrictRadarModel):
    card: VerificationReviewCard
    decision: VerificationDecision
    observed_at: datetime
    evidence_kind: VerificationEvidenceKind
    evidence_source: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    source_url: str = Field(min_length=1, max_length=2048)
    note: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("observed_at")
    @classmethod
    def observed_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("source_url")
    @classmethod
    def source_url_must_be_http(cls, value: str) -> str:
        normalized = value.strip()
        if not (
            normalized.startswith("https://")
            or normalized.startswith("http://")
        ):
            raise ValueError("source_url must use http or https")
        return normalized

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("note must not be blank")
        return normalized


class ReviewEvidenceDraft(StrictRadarModel):
    draft_version: str = EVIDENCE_DRAFT_VERSION
    draft_id: str = Field(min_length=1)
    status: EvidenceDraftStatus
    opportunity_id: str = Field(min_length=1)
    card_sha256: str = Field(min_length=64, max_length=64)
    evidence: VerificationEvidence | None = None
    verification_preview: VerificationPreview | None = None
    errors: list[str] = Field(default_factory=list)
    external_actions: list[str] = Field(default_factory=list)

    @field_validator("external_actions")
    @classmethod
    def require_no_external_actions(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("external_actions must be empty")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> "ReviewEvidenceDraft":
        if self.status == "READY":
            if self.evidence is None or self.verification_preview is None:
                raise ValueError("ready draft requires evidence and preview")
            if self.errors:
                raise ValueError("ready draft cannot contain errors")
        else:
            if self.evidence is not None or self.verification_preview is not None:
                raise ValueError("blocked draft cannot contain evidence or preview")
            if not self.errors:
                raise ValueError("blocked draft requires errors")
        return self


class ReviewEvidenceDraftService:
    def __init__(
        self,
        *,
        opportunity_repository: SQLiteOpportunityRepository,
        availability_repository: SQLiteAvailabilityRepository,
        verification_service: AvailabilityVerificationService,
    ) -> None:
        self.opportunity_repository = opportunity_repository
        self.availability_repository = availability_repository
        self.verification_service = verification_service

    def build(
        self,
        request: ReviewEvidenceDraftRequest,
        *,
        now: datetime,
    ) -> ReviewEvidenceDraft:
        generated_at = _aware_utc(now)
        card = request.card

        if review_card_sha256(card) != card.card_sha256:
            return _blocked(
                request,
                "BLOCKED_STALE_CARD",
                "review_card_hash_mismatch",
            )

        opportunity = self.opportunity_repository.get(card.opportunity_id)
        if opportunity is None:
            return _blocked(request, "BLOCKED_NOT_FOUND", "opportunity_not_found")

        current = self.availability_repository.get(card.opportunity_id)
        current_state = (
            current.availability_state
            if current is not None
            else "UNVERIFIED"
        )
        current_last_seen = current.last_seen_at if current is not None else None
        current_last_verified = (
            current.last_verified_at if current is not None else None
        )
        if (
            current_state != card.availability_state
            or current_last_seen != card.last_seen_at
            or current_last_verified != card.last_verified_at
        ):
            return _blocked(
                request,
                "BLOCKED_STALE_CARD",
                "review_card_availability_changed",
            )

        if request.evidence_kind not in card.acceptable_evidence_kinds:
            return _blocked(
                request,
                "BLOCKED_EVIDENCE_KIND",
                "evidence_kind_not_allowed_for_review_card",
            )

        if request.observed_at > generated_at:
            return _blocked(
                request,
                "BLOCKED_FUTURE_OBSERVATION",
                "evidence_observed_at_in_future",
            )

        evidence = VerificationEvidence(
            opportunity_id=card.opportunity_id,
            decision=request.decision,
            observed_at=request.observed_at,
            evidence_kind=request.evidence_kind,
            evidence_source=request.evidence_source,
            source_url=request.source_url,
            note=request.note,
        )
        preview = self.verification_service.preview(evidence)
        if preview.status == "BLOCKED":
            return _blocked(
                request,
                "BLOCKED_STALE_CARD",
                *preview.errors,
            )

        return ReviewEvidenceDraft(
            draft_id=_draft_id(
                card_sha256=card.card_sha256,
                evidence=evidence,
                preview=preview,
            ),
            status="READY",
            opportunity_id=card.opportunity_id,
            card_sha256=card.card_sha256,
            evidence=evidence,
            verification_preview=preview,
            errors=[],
            external_actions=[],
        )


def _blocked(
    request: ReviewEvidenceDraftRequest,
    status: EvidenceDraftStatus,
    *errors: str,
) -> ReviewEvidenceDraft:
    return ReviewEvidenceDraft(
        draft_id=_blocked_draft_id(
            card_sha256=request.card.card_sha256,
            request=request,
            status=status,
            errors=list(errors),
        ),
        status=status,
        opportunity_id=request.card.opportunity_id,
        card_sha256=request.card.card_sha256,
        errors=list(errors),
        external_actions=[],
    )


def _draft_id(
    *,
    card_sha256: str,
    evidence: VerificationEvidence,
    preview: VerificationPreview,
) -> str:
    payload = {
        "draft_version": EVIDENCE_DRAFT_VERSION,
        "card_sha256": card_sha256,
        "evidence": evidence.model_dump(mode="json", exclude_none=False),
        "preview_sha256": preview.preview_sha256,
    }
    return _hash_id(payload)


def _blocked_draft_id(
    *,
    card_sha256: str,
    request: ReviewEvidenceDraftRequest,
    status: EvidenceDraftStatus,
    errors: list[str],
) -> str:
    payload = {
        "draft_version": EVIDENCE_DRAFT_VERSION,
        "card_sha256": card_sha256,
        "opportunity_id": request.card.opportunity_id,
        "decision": request.decision,
        "observed_at": request.observed_at.isoformat(),
        "evidence_kind": request.evidence_kind,
        "evidence_source": request.evidence_source,
        "source_url": request.source_url,
        "note": request.note,
        "status": status,
        "errors": errors,
    }
    return _hash_id(payload)


def _hash_id(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"review-evidence-draft-{digest[:20]}"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)
