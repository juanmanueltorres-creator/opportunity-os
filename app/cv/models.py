from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
PreparationStatus = Literal[
    "PREPARED",
    "BLOCKED_VALIDATION",
    "BLOCKED_MISSING_FACTS",
    "BLOCKED_TRACK_UNAVAILABLE",
    "BLOCKED_RENDER",
]


class StrictCVModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


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
            if not _is_aware(self.verified_at):
                raise ValueError("verified_at must be timezone-aware")
            self.verified_at = self.verified_at.astimezone(timezone.utc)
            if self.verification_method != "manual_confirmation":
                if self.source_ref is None or not self.source_ref.strip():
                    raise ValueError(
                        "evidence-backed verification requires source_ref"
                    )
        elif self.verified_at is not None and not _is_aware(self.verified_at):
            raise ValueError("verified_at must be timezone-aware")
        return self


class ValidationIssue(StrictCVModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    claim_id: str | None = None


class ApplicationPacket(StrictCVModel):
    status: Literal["PREPARED"] = "PREPARED"


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
