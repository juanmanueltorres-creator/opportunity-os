from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.relationships.models import RelationshipEventKind, RelationshipState

ObservationSourceType = Literal[
    "EMAIL_PROVIDER",
    "CONTACT_DISCOVERY",
    "PUBLIC_RESEARCH",
    "PRIVATE_WORKSPACE",
    "MANUAL",
]
ObservationKind = Literal[
    "CONTACT_VERIFIED",
    "MESSAGE_SENT",
    "REPLY_RECEIVED",
    "PROCESS_OPENED",
    "PROCESS_UPDATED",
    "PROCESS_CLOSED",
]
PreviewStatus = Literal["IMPORTABLE", "ALREADY_IMPORTED", "BLOCKED"]
ObservationImportStatus = Literal[
    "IMPORTED",
    "ALREADY_IMPORTED",
    "BLOCKED_STALE_PREVIEW",
    "BLOCKED_DOMAIN",
    "CONFLICT",
]
ReceiptStatus = Literal["IMPORTED", "ALREADY_IMPORTED"]

PREVIEW_VERSION = "operator-preview-v1"
STATE_VERSION = "relationship-state-v1"


class StrictOperatorModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _aware_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


class OperatorObservation(StrictOperatorModel):
    observation_id: str = Field(min_length=1)
    source_type: ObservationSourceType
    source_name: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    kind: ObservationKind
    account_id: str = Field(min_length=1)
    contact_id: str | None = Field(default=None, min_length=1)
    observed_at: datetime
    reason: str | None = Field(default=None, min_length=1, max_length=280)
    process_label: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field="observed_at")


class ObservationPreview(StrictOperatorModel):
    preview_version: str = Field(min_length=1)
    status: PreviewStatus
    observation_id: str = Field(min_length=1)
    observation_sha256: str = Field(min_length=64, max_length=64)
    preview_sha256: str = Field(min_length=64, max_length=64)
    account_id: str = Field(min_length=1)
    contact_id: str | None = Field(default=None, min_length=1)
    event_kind: RelationshipEventKind | None = None
    state_before: RelationshipState | None = None
    state_after: RelationshipState | None = None
    open_process_before: bool | None = None
    open_process_after: bool | None = None
    source_type: ObservationSourceType
    source_name: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    reason: str | None = Field(default=None, min_length=1, max_length=280)
    errors: list[str] = Field(default_factory=list)
    external_actions: list[str] = Field(default_factory=list)

    @field_validator("external_actions")
    @classmethod
    def require_no_external_actions(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("external_actions must be empty")
        return value


class ObservationImportRequest(StrictOperatorModel):
    observation: OperatorObservation
    preview_sha256: str = Field(min_length=64, max_length=64)
    confirmed_by: str = Field(min_length=1)
    confirmed_at: datetime

    @field_validator("confirmed_at")
    @classmethod
    def normalize_confirmed_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field="confirmed_at")

    @model_validator(mode="after")
    def validate_confirmation_time(self) -> "ObservationImportRequest":
        if self.confirmed_at < self.observation.observed_at:
            raise ValueError("confirmed_at must be at or after observation observed_at")
        return self


class ObservationImportReceipt(StrictOperatorModel):
    receipt_id: str = Field(min_length=1)
    observation_id: str = Field(min_length=1)
    observation_sha256: str = Field(min_length=64, max_length=64)
    preview_sha256: str = Field(min_length=64, max_length=64)
    relationship_event_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    contact_id: str | None = Field(default=None, min_length=1)
    source_type: ObservationSourceType
    source_name: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    confirmed_by: str = Field(min_length=1)
    confirmed_at: datetime
    processed_at: datetime
    status: ReceiptStatus

    @field_validator("confirmed_at", "processed_at")
    @classmethod
    def normalize_receipt_times(cls, value: datetime, info) -> datetime:
        return _aware_utc(value, field=info.field_name)


class ObservationImportResult(StrictOperatorModel):
    status: ObservationImportStatus
    receipt: ObservationImportReceipt | None = None
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result_shape(self) -> "ObservationImportResult":
        if self.status in {"IMPORTED", "ALREADY_IMPORTED"}:
            if self.receipt is None:
                raise ValueError("successful import result requires receipt")
            if self.receipt.status != self.status:
                raise ValueError("receipt status must match import result status")
        elif self.receipt is not None:
            raise ValueError("blocked import result cannot contain receipt")
        return self


def canonical_sha256(value: BaseModel | dict[str, object]) -> str:
    if isinstance(value, BaseModel):
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


def observation_sha256(observation: OperatorObservation) -> str:
    return canonical_sha256(observation)
