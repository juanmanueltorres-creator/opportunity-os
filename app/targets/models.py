from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TargetMode = Literal["TARGET_ACCOUNT", "SPECULATIVE_OUTREACH"]
ProximityBucket = Literal[
    "VERY_CLOSE",
    "CLOSE",
    "CITY_WIDE",
    "LONG_COMMUTE",
    "REMOTE",
    "UNKNOWN",
]
Contactability = Literal[
    "APPLICATION_EMAIL",
    "VERIFIED_RECRUITER",
    "GENERAL_CV",
    "CAREERS_FORM",
    "NONE",
    "UNKNOWN",
]
TargetAction = Literal[
    "FOLLOW_UP",
    "PREPARE_SPECULATIVE",
    "RESEARCH_CONTACT",
    "WATCH",
]


class StrictTargetModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TargetSignal(StrictTargetModel):
    label: str = Field(min_length=1)
    value: float = Field(ge=0, le=100)
    source_url: str | None = None
    source_note: str | None = None
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def require_provenance(self) -> "TargetSignal":
        if not self.source_url and not self.source_note:
            raise ValueError("target signal requires provenance")
        return self


class TargetAccount(StrictTargetModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    website: str | None = None
    sectors: list[str] = Field(default_factory=list)
    role_families: list[str] = Field(default_factory=list)
    capability_tags: list[str] = Field(default_factory=list)
    proximity_bucket: ProximityBucket = "UNKNOWN"
    scale_stability_signal: TargetSignal
    innovation_signal: TargetSignal
    contactability: Contactability = "UNKNOWN"
    hiring_signal: TargetSignal
    application_channel: str | None = None
    notes: str | None = None


class TargetAccountAssessment(StrictTargetModel):
    account_id: str = Field(min_length=1)
    account_name: str = Field(min_length=1)
    best_track_id: str | None = None
    capability_sector_fit: float = Field(ge=0, le=100)
    proximity_fit: float = Field(ge=0, le=100)
    scale_stability: float = Field(ge=0, le=100)
    innovation: float = Field(ge=0, le=100)
    contactability_fit: float = Field(ge=0, le=100)
    hiring_signal: float = Field(ge=0, le=100)
    account_affinity: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    cooldown_active: bool = False
    recommended_action: TargetAction = "WATCH"


class TargetAccountPolicy(StrictTargetModel):
    cooldown_days: int = Field(default=30, ge=0)
    max_items: int = Field(default=20, ge=1)
    minimum_affinity: float = Field(default=65, ge=0, le=100)
    minimum_confidence: float = Field(default=60, ge=0, le=100)


class TargetRadarRunRequest(StrictTargetModel):
    current_reasons: dict[str, str] = Field(default_factory=dict)

    @field_validator("current_reasons")
    @classmethod
    def normalize_current_reasons(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_account_id, raw_reason in value.items():
            account_id = raw_account_id.strip()
            reason = raw_reason.strip()
            if not account_id:
                raise ValueError("current reason account_id must be non-empty")
            if not reason:
                raise ValueError("current reason must be non-empty")
            if account_id in normalized:
                raise ValueError("duplicate current reason account_id")
            normalized[account_id] = reason
        return normalized


class TargetAccountBatch(StrictTargetModel):
    policy: TargetAccountPolicy
    profile_fingerprint: str = Field(min_length=1)
    generated_at: datetime
    items: list[TargetAccountAssessment] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)
