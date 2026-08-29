from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ContactType = Literal["RECRUITER", "HIRING_MANAGER", "TECHNICAL", "OTHER"]
VerificationStatus = Literal["VERIFIED", "PUBLIC_SOURCE", "STALE", "UNVERIFIED"]
ContactDisposition = Literal["AVAILABLE", "HELD", "INACTIVE"]
RelationshipState = Literal[
    "UNTOUCHED",
    "CONTACTED",
    "REPLIED",
    "PROCESS_OPEN",
    "PROCESS_CLOSED",
]
RelationshipContextState = Literal[
    "UNTOUCHED",
    "CONTACTED",
    "REPLIED",
    "PROCESS_OPEN",
    "PROCESS_CLOSED",
    "DORMANT",
]
RelationshipEventKind = Literal[
    "CONTACT_VERIFIED",
    "CONTACT_HELD",
    "CONTACT_RELEASED",
    "CONTACTED",
    "REPLIED",
    "PROCESS_OPENED",
    "PROCESS_UPDATED",
    "PROCESS_CLOSED",
    "COOLDOWN_SET",
    "COOLDOWN_CLEARED",
    "NOTE_RECORDED",
]
RelationshipAction = Literal[
    "WATCH",
    "FOLLOW_UP",
    "RESEARCH_CONTACT",
    "PREPARE_SPECULATIVE",
]


class StrictRelationshipModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


class CareerContact(StrictRelationshipModel):
    contact_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    person: str = Field(min_length=1)
    role: str = Field(min_length=1)
    contact_type: ContactType
    verification_status: VerificationStatus
    verification_source: str | None = None
    observed_at: datetime
    disposition: ContactDisposition = "AVAILABLE"
    channel_kind: str | None = None
    channel_value: str | None = None
    active: bool = True

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _aware_utc(value)


class RelationshipAccount(StrictRelationshipModel):
    account_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    relationship_state: RelationshipState = "UNTOUCHED"
    last_contacted_at: datetime | None = None
    last_reply_at: datetime | None = None
    cooldown_until: datetime | None = None
    open_process: bool = False
    process_label: str | None = None
    last_reason: str | None = None
    preferred_next_contact_id: str | None = None
    updated_at: datetime

    @field_validator("last_contacted_at", "last_reply_at", "cooldown_until", "updated_at")
    @classmethod
    def normalize_datetimes(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value)

    @model_validator(mode="after")
    def validate_process_state(self) -> "RelationshipAccount":
        if self.relationship_state == "PROCESS_OPEN" and not self.open_process:
            raise ValueError("PROCESS_OPEN relationship requires open_process")
        if self.open_process and self.relationship_state != "PROCESS_OPEN":
            raise ValueError("open_process requires PROCESS_OPEN relationship state")
        return self


class RelationshipEvent(StrictRelationshipModel):
    event_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    contact_id: str | None = None
    kind: RelationshipEventKind
    occurred_at: datetime
    reason: str | None = None
    source_ref: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        return _aware_utc(value)


class RelationshipPolicy(StrictRelationshipModel):
    spontaneous_contact_cooldown_days: int = Field(default=30, ge=0)
    follow_up_min_days: int = Field(default=5, ge=0)
    stale_contact_days: int = Field(default=180, ge=1)


class RelationshipContext(StrictRelationshipModel):
    account_id: str = Field(min_length=1)
    relationship_state: RelationshipContextState
    last_contacted_at: datetime | None = None
    last_reply_at: datetime | None = None
    cooldown_until: datetime | None = None
    cooldown_active: bool
    open_process: bool
    usable_contact_count: int = Field(ge=0)
    held_contact_count: int = Field(ge=0)
    preferred_contact_type: ContactType | None = None
    last_reason: str | None = None
    recommended_relationship_action: RelationshipAction
    reason: str = Field(min_length=1)
    generated_at: datetime

    @field_validator("last_contacted_at", "last_reply_at", "cooldown_until", "generated_at")
    @classmethod
    def normalize_context_datetimes(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value)


class RelationshipContextSnapshot(StrictRelationshipModel):
    generated_at: datetime
    accounts: list[RelationshipContext] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _aware_utc(value)
