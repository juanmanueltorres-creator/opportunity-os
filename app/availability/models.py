from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.radar.models import StrictRadarModel


AvailabilityObservationType = Literal[
    "SEEN",
    "VERIFIED_OPEN",
    "VERIFIED_CLOSED",
]
AvailabilityState = Literal[
    "UNVERIFIED",
    "VERIFIED_OPEN",
    "VERIFIED_CLOSED",
]


class AvailabilityObservation(StrictRadarModel):
    opportunity_id: str = Field(min_length=1)
    observation_type: AvailabilityObservationType
    observed_at: datetime
    evidence_source: str = Field(min_length=1)
    source_url: str | None = None
    note: str | None = None
    evidence_kind: str | None = None
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    preview_sha256: str | None = None

    @field_validator("observed_at")
    @classmethod
    def observed_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("evidence_source")
    @classmethod
    def evidence_source_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("evidence_source must not be blank")
        return normalized

    @field_validator("confirmed_at")
    @classmethod
    def confirmed_at_must_be_aware(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("confirmed_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator(
        "source_url",
        "note",
        "evidence_kind",
        "confirmed_by",
        "preview_sha256",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class OpportunityAvailability(StrictRadarModel):
    opportunity_id: str = Field(min_length=1)
    first_seen_at: datetime
    last_seen_at: datetime | None = None
    last_verified_at: datetime | None = None
    verification_source: str | None = None
    availability_state: AvailabilityState = "UNVERIFIED"
    observation_count: int = Field(ge=1)
    latest_observation_at: datetime

    @field_validator(
        "first_seen_at",
        "last_seen_at",
        "last_verified_at",
        "latest_observation_at",
    )
    @classmethod
    def datetimes_must_be_aware(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def verification_fields_must_agree(self) -> "OpportunityAvailability":
        if self.availability_state == "UNVERIFIED":
            if self.last_verified_at is not None or self.verification_source is not None:
                raise ValueError(
                    "unverified availability cannot expose verification metadata"
                )
        else:
            if self.last_verified_at is None or self.verification_source is None:
                raise ValueError(
                    "verified availability requires verification metadata"
                )
        return self
