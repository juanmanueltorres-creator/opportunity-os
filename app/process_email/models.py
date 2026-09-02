from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.operator_bridge.models import ObservationPreview, OperatorObservation

ProcessSignalKind = Literal[
    "APPLICATION_ACKNOWLEDGED",
    "INTERVIEW_PROPOSED",
    "STAGE_ADVANCED",
    "PROCESS_UPDATED",
    "OFFER_RECEIVED",
    "REJECTED",
]
ProcessConfidence = Literal["HIGH", "MEDIUM", "LOW"]
ClassificationDisposition = Literal["CLASSIFIED", "NOT_PROCESS", "AMBIGUOUS"]
ProcessEmailStatus = Literal[
    "CLASSIFIED",
    "NOT_PROCESS",
    "AMBIGUOUS",
    "CONTENT_UNAVAILABLE",
    "PROVIDER_ERROR",
    "INVALID_SELECTION",
    "BLOCKED",
]

CLASSIFIER_VERSION = "deterministic-process-email-v1"
RULESET_VERSION = "es-en-2026-09-v2"


class StrictProcessEmailModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _aware_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


class EvidenceSpan(StrictProcessEmailModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def check_range(self) -> "EvidenceSpan":
        if self.end <= self.start:
            raise ValueError("evidence span end must be after start")
        return self


class ProcessSignal(StrictProcessEmailModel):
    kind: ProcessSignalKind
    confidence: ProcessConfidence
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,79}$")
    evidence_spans: list[EvidenceSpan] = Field(min_length=1)


class ProcessClassification(StrictProcessEmailModel):
    disposition: ClassificationDisposition
    classifier_version: Literal["deterministic-process-email-v1"] = CLASSIFIER_VERSION
    ruleset_version: Literal["es-en-2026-09-v2"] = RULESET_VERSION
    signals: list[ProcessSignal] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_disposition_shape(self) -> "ProcessClassification":
        if self.disposition == "CLASSIFIED" and not self.signals:
            raise ValueError("CLASSIFIED requires signals")
        if self.disposition == "NOT_PROCESS" and self.signals:
            raise ValueError("NOT_PROCESS requires empty signals")
        if (
            self.disposition == "AMBIGUOUS"
            and self.signals
            and "conflicting_process_signals" not in self.warnings
        ):
            raise ValueError(
                "AMBIGUOUS signals require conflicting_process_signals warning"
            )
        return self


class ProcessEmailSelection(StrictProcessEmailModel):
    account_id: str = Field(min_length=1)
    contact_id: str | None = Field(default=None, min_length=1)
    message_id: str = Field(min_length=1)
    selected_by: str = Field(min_length=1, max_length=120)


class ProcessProjection(StrictProcessEmailModel):
    proposed_observation: OperatorObservation | None = None
    warnings: list[str] = Field(default_factory=list)


class ProcessEmailPreview(StrictProcessEmailModel):
    status: ProcessEmailStatus
    classifier_version: Literal["deterministic-process-email-v1"] = CLASSIFIER_VERSION
    ruleset_version: Literal["es-en-2026-09-v2"] = RULESET_VERSION
    source_ref: str | None = Field(default=None, min_length=1)
    observed_at: datetime | None = None
    signals: list[ProcessSignal] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    proposed_observation: OperatorObservation | None = None
    operator_preview: ObservationPreview | None = None
    external_actions: list[str] = Field(default_factory=list)

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value, field="observed_at")

    @field_validator("external_actions")
    @classmethod
    def require_no_external_actions(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("external_actions must be empty")
        return value

    @model_validator(mode="after")
    def validate_preview_shape(self) -> "ProcessEmailPreview":
        if self.proposed_observation is None and self.operator_preview is not None:
            raise ValueError("operator_preview requires proposed_observation")
        if self.status == "AMBIGUOUS" and self.proposed_observation is not None:
            raise ValueError("AMBIGUOUS cannot propose observation")
        if self.status == "NOT_PROCESS" and self.signals:
            raise ValueError("NOT_PROCESS requires empty signals")
        if (
            self.status == "AMBIGUOUS"
            and self.signals
            and "conflicting_process_signals" not in self.warnings
        ):
            raise ValueError(
                "AMBIGUOUS signals require conflicting_process_signals warning"
            )
        return self
