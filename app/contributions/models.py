from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ContributionOrigin = Literal[
    "PUBLIC_ISSUE",
    "HELP_WANTED",
    "REPOSITORY_RESEARCH",
    "MAINTAINER_PROPOSAL",
    "COLLABORATION_CALL",
]
NeedBasis = Literal["OBSERVED", "MAINTAINER_STATED", "HYPOTHESIZED"]
TaskClaimState = Literal[
    "NONE",
    "AVAILABLE",
    "CLAIMED_SELF",
    "CLAIMED_OTHER",
    "CLOSED",
    "UNKNOWN",
]
ExpectedEffort = Literal["XS", "S", "M", "L", "UNKNOWN"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"]
ContributionStage = Literal[
    "DISCOVERED",
    "CONTACTED",
    "ENGAGED",
    "TASK_READY",
    "IN_PROGRESS",
    "IN_REVIEW",
    "COMPLETED",
    "CLOSED",
    "PAUSED",
    "DISCARDED",
]
ContributionEventKind = Literal[
    "DISCOVERED",
    "OUTREACH_SENT",
    "MAINTAINER_REPLIED",
    "COLLABORATION_WELCOMED",
    "WORK_PROPOSED",
    "TASK_SELECTED",
    "TASK_CLAIMED_SELF",
    "TASK_CLAIMED_OTHER",
    "TASK_RELEASED",
    "TASK_CLOSED",
    "WORK_STARTED",
    "PR_OPENED",
    "REVIEW_RECEIVED",
    "CHANGES_REQUESTED",
    "BLOCKED",
    "UNBLOCKED",
    "PR_MERGED",
    "PR_CLOSED",
    "PAUSED",
    "RESUMED",
    "DISCARDED",
]
ContributionSourceType = Literal[
    "PUBLIC_GITHUB",
    "PUBLIC_RESEARCH",
    "EMAIL_PROVIDER",
    "MANUAL",
]
ProofArtifactKind = Literal["PULL_REQUEST"]
ProofStatus = Literal["OPEN", "MERGED", "CLOSED_UNMERGED"]

_TASK_STATES_REQUIRING_REF = {"AVAILABLE", "CLAIMED_SELF", "CLAIMED_OTHER", "CLOSED"}
_TASK_EVENTS_REQUIRING_REF = {
    "TASK_SELECTED",
    "TASK_CLAIMED_SELF",
    "TASK_CLAIMED_OTHER",
    "TASK_RELEASED",
    "TASK_CLOSED",
}
_WORK_EVENTS_REQUIRING_REF = {
    "PR_OPENED",
    "REVIEW_RECEIVED",
    "CHANGES_REQUESTED",
    "PR_MERGED",
    "PR_CLOSED",
}


class StrictContributionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _aware_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


class PublicContributionEntry(StrictContributionModel):
    entry_id: str = Field(min_length=1)
    repository_full_name: str = Field(min_length=1)
    repository_url: str = Field(min_length=1)
    account_id: str | None = Field(default=None, min_length=1)
    origin: ContributionOrigin
    need_basis: NeedBasis
    need_statement: str = Field(min_length=1, max_length=500)
    evidence_refs: list[str] = Field(default_factory=list)
    task_ref: str | None = Field(default=None, min_length=1)
    bounded_task: str | None = Field(default=None, min_length=1, max_length=500)
    task_claim_state: TaskClaimState = "UNKNOWN"
    expected_effort: ExpectedEffort = "UNKNOWN"
    risk_level: RiskLevel = "UNKNOWN"
    discovered_at: datetime

    @field_validator("discovered_at")
    @classmethod
    def normalize_discovered_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field="discovered_at")

    @model_validator(mode="after")
    def validate_semantics(self) -> "PublicContributionEntry":
        if self.need_basis in {"OBSERVED", "MAINTAINER_STATED"} and not self.evidence_refs:
            raise ValueError(f"{self.need_basis} need requires evidence_refs")
        if self.task_claim_state in _TASK_STATES_REQUIRING_REF and self.task_ref is None:
            raise ValueError(f"{self.task_claim_state} task state requires task_ref")
        return self


class ContributionEvent(StrictContributionModel):
    event_id: str = Field(min_length=1)
    entry_id: str = Field(min_length=1)
    kind: ContributionEventKind
    source_type: ContributionSourceType
    source_ref: str = Field(min_length=1)
    observed_at: datetime
    actor_ref: str | None = Field(default=None, min_length=1)
    work_ref: str | None = Field(default=None, min_length=1)
    task_ref: str | None = Field(default=None, min_length=1)
    reason: str | None = Field(default=None, min_length=1, max_length=280)

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field="observed_at")

    @model_validator(mode="after")
    def validate_references(self) -> "ContributionEvent":
        if self.kind in _TASK_EVENTS_REQUIRING_REF and self.task_ref is None:
            raise ValueError(f"{self.kind} requires task_ref")
        if self.kind in _WORK_EVENTS_REQUIRING_REF and self.work_ref is None:
            raise ValueError(f"{self.kind} requires work_ref")
        if self.kind == "BLOCKED" and self.reason is None:
            raise ValueError("BLOCKED requires reason")
        return self


class ContributionContext(StrictContributionModel):
    entry_id: str = Field(min_length=1)
    stage: ContributionStage
    blocking_reason: str | None = Field(default=None, min_length=1, max_length=280)
    last_event_kind: ContributionEventKind | None = None
    last_observed_at: datetime | None = None
    task_claim_state: TaskClaimState
    active_work_ref: str | None = Field(default=None, min_length=1)
    event_count: int = Field(ge=0)

    @field_validator("last_observed_at")
    @classmethod
    def normalize_last_observed_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value, field="last_observed_at")


class ProofOfWork(StrictContributionModel):
    proof_id: str = Field(min_length=1)
    entry_id: str = Field(min_length=1)
    artifact_kind: ProofArtifactKind = "PULL_REQUEST"
    repository_full_name: str = Field(min_length=1)
    artifact_ref: str = Field(min_length=1)
    artifact_url: str = Field(min_length=1)
    status: ProofStatus
    observed_at: datetime
    evidence_refs: list[str] = Field(min_length=1)

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field="observed_at")
