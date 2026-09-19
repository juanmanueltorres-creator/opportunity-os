from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from app.availability.models import AvailabilityState
from app.radar.models import StrictRadarModel


VerificationDecision = Literal["OPEN", "CLOSED"]
VerificationEvidenceKind = Literal[
    "OFFICIAL_COMPANY_PAGE",
    "DIRECT_ATS",
    "DIRECT_PLATFORM",
    "MANUAL_REVIEW",
]
VerificationPreviewStatus = Literal[
    "READY",
    "ALREADY_VERIFIED",
    "BLOCKED",
]
VerificationConfirmStatus = Literal[
    "RECORDED",
    "ALREADY_RECORDED",
    "BLOCKED_STALE_PREVIEW",
    "BLOCKED",
]

VERIFICATION_PREVIEW_VERSION = "availability-verification-preview-v1"


class VerificationEvidence(StrictRadarModel):
    opportunity_id: str = Field(min_length=1)
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
        return normalize_http_source_url(value)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("note must not be blank")
        return normalized


def normalize_http_source_url(value: str) -> str:
    normalized = value.strip()
    try:
        parts = urlsplit(normalized)
        hostname = parts.hostname
    except ValueError as exc:
        raise ValueError(
            "source_url must use http or https with a valid host"
        ) from exc
    if (
        parts.scheme.casefold() not in {"http", "https"}
        or not parts.netloc
        or not hostname
        or any(char.isspace() for char in parts.netloc)
    ):
        raise ValueError(
            "source_url must use http or https with a valid host"
        )
    return normalized


class VerificationPreview(StrictRadarModel):
    preview_version: str = VERIFICATION_PREVIEW_VERSION
    status: VerificationPreviewStatus
    opportunity_id: str = Field(min_length=1)
    evidence_sha256: str = Field(min_length=64, max_length=64)
    preview_sha256: str = Field(min_length=64, max_length=64)
    current_state: AvailabilityState
    proposed_state: AvailabilityState
    observation_count: int = Field(ge=0)
    latest_observation_at: datetime | None = None
    errors: list[str] = Field(default_factory=list)
    external_actions: list[str] = Field(default_factory=list)

    @field_validator("latest_observation_at")
    @classmethod
    def normalize_latest_observation_at(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("latest_observation_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("external_actions")
    @classmethod
    def require_no_external_actions(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("external_actions must be empty")
        return value


class VerificationConfirmRequest(StrictRadarModel):
    evidence: VerificationEvidence
    preview_sha256: str = Field(min_length=64, max_length=64)
    confirmed_by: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9._@:-]+$",
    )
    confirmed_at: datetime

    @field_validator("confirmed_at")
    @classmethod
    def confirmed_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("confirmed_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def confirmation_cannot_precede_evidence(self) -> "VerificationConfirmRequest":
        if self.confirmed_at < self.evidence.observed_at:
            raise ValueError(
                "confirmed_at must be at or after evidence observed_at"
            )
        return self


class VerificationReceipt(StrictRadarModel):
    receipt_id: str = Field(min_length=1)
    opportunity_id: str = Field(min_length=1)
    decision: VerificationDecision
    evidence_sha256: str = Field(min_length=64, max_length=64)
    preview_sha256: str = Field(min_length=64, max_length=64)
    confirmed_by: str = Field(min_length=1)
    confirmed_at: datetime
    processed_at: datetime
    resulting_state: AvailabilityState

    @field_validator("confirmed_at", "processed_at")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)


class VerificationConfirmResult(StrictRadarModel):
    status: VerificationConfirmStatus
    receipt: VerificationReceipt | None = None
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result_shape(self) -> "VerificationConfirmResult":
        if self.status in {"RECORDED", "ALREADY_RECORDED"}:
            if self.receipt is None:
                raise ValueError("successful verification requires receipt")
        elif self.receipt is not None:
            raise ValueError("blocked verification cannot contain receipt")
        return self


def canonical_sha256(value: StrictRadarModel | dict[str, object]) -> str:
    if isinstance(value, StrictRadarModel):
        payload = value.model_dump(mode="json", exclude_none=False)
    else:
        payload = value
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evidence_sha256(evidence: VerificationEvidence) -> str:
    return canonical_sha256(evidence)
