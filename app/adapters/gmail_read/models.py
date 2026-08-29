from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.operator_bridge.models import OperatorObservation

GmailObservationStatus = Literal[
    "OBSERVATION_READY",
    "AMBIGUOUS",
    "PROVIDER_ERROR",
    "INVALID_SELECTION",
]


class StrictGmailModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _aware_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


class GmailReadSelection(StrictGmailModel):
    account_id: str = Field(min_length=1)
    contact_id: str | None = Field(default=None, min_length=1)
    message_id: str | None = Field(default=None, min_length=1)
    thread_id: str | None = Field(default=None, min_length=1)
    selected_by: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def require_exactly_one_provider_id(self) -> "GmailReadSelection":
        if (self.message_id is None) == (self.thread_id is None):
            raise ValueError("exactly one of message_id or thread_id is required")
        return self


class GmailMessageEnvelope(StrictGmailModel):
    message_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    internal_date: datetime
    label_ids: tuple[str, ...] = ()
    from_address: str = Field(min_length=1)
    to_addresses: tuple[str, ...] = ()
    cc_addresses: tuple[str, ...] = ()
    subject: str | None = Field(default=None, max_length=200)
    in_reply_to: str | None = Field(default=None, min_length=1, max_length=500)
    references: tuple[str, ...] = ()

    @field_validator("internal_date")
    @classmethod
    def normalize_internal_date(cls, value: datetime) -> datetime:
        return _aware_utc(value, field="internal_date")


class GmailThreadEnvelope(StrictGmailModel):
    thread_id: str = Field(min_length=1)
    messages: tuple[GmailMessageEnvelope, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_matching_thread_ids(self) -> "GmailThreadEnvelope":
        if any(message.thread_id != self.thread_id for message in self.messages):
            raise ValueError("message thread_id must match Gmail thread_id")
        return self


class GmailObservationResult(StrictGmailModel):
    status: GmailObservationStatus
    observation: OperatorObservation | None = None
    provider: Literal["gmail"] = "gmail"
    source_ref: str | None = Field(default=None, min_length=1)
    errors: list[str] = Field(default_factory=list)
    external_actions: list[str] = Field(default_factory=list)

    @field_validator("external_actions")
    @classmethod
    def require_no_external_actions(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("external_actions must be empty")
        return value

    @model_validator(mode="after")
    def validate_observation_shape(self) -> "GmailObservationResult":
        if self.status == "OBSERVATION_READY":
            if self.observation is None:
                raise ValueError("OBSERVATION_READY requires observation")
        elif self.observation is not None:
            raise ValueError("observation is only allowed for OBSERVATION_READY")
        return self
