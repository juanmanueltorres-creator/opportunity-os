from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.contributions.models import ContributionContext, ContributionEvent, PublicContributionEntry

GitHubResourceKind = Literal["ISSUE", "PULL_REQUEST"]
GitHubIssueState = Literal["OPEN", "CLOSED"]
GitHubPullRequestState = Literal["OPEN", "CLOSED"]
GitHubReviewState = Literal["APPROVED", "COMMENTED", "CHANGES_REQUESTED", "DISMISSED"]
ContributionObservationKind = Literal[
    "ISSUE_AVAILABLE",
    "ISSUE_CLAIMED_SELF",
    "ISSUE_CLAIMED_OTHER",
    "ISSUE_CLOSED",
    "PR_OPENED",
    "REVIEW_RECEIVED",
    "CHANGES_REQUESTED",
    "PR_MERGED",
    "PR_CLOSED",
    "EXTERNAL_BLOCKER",
    "BLOCKER_CLEARED",
]
ContributionPreviewStatus = Literal["IMPORTABLE", "NO_CHANGE", "ALREADY_IMPORTED", "BLOCKED"]
ContributionImportStatus = Literal[
    "IMPORTED",
    "ALREADY_IMPORTED",
    "BLOCKED_STALE_PREVIEW",
    "BLOCKED_DOMAIN",
    "CONFLICT",
]
ReceiptStatus = Literal["IMPORTED", "ALREADY_IMPORTED"]
ReasonCode = Literal["EXTERNAL_AUTHORIZATION_REQUIRED"]
PREVIEW_VERSION = "contribution-preview-v1"

_ISSUE_OBSERVATION_KINDS = {
    "ISSUE_AVAILABLE",
    "ISSUE_CLAIMED_SELF",
    "ISSUE_CLAIMED_OTHER",
    "ISSUE_CLOSED",
}
_WORK_OBSERVATION_KINDS = {
    "PR_OPENED",
    "REVIEW_RECEIVED",
    "CHANGES_REQUESTED",
    "PR_MERGED",
    "PR_CLOSED",
    "EXTERNAL_BLOCKER",
    "BLOCKER_CLEARED",
}


class StrictObservationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _aware_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_selection_url(url: str) -> tuple[str, str, str, int]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError("source_url must be a canonical https://github.com URL")
    if parsed.query or parsed.fragment or parsed.params:
        raise ValueError("source_url must not contain query, fragment, or params")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 4:
        raise ValueError("source_url must identify exactly one GitHub issue or pull request")
    owner, repo, resource, raw_number = parts
    if resource not in {"issues", "pull"}:
        raise ValueError("source_url resource must be issues or pull")
    try:
        number = int(raw_number)
    except ValueError as exc:
        raise ValueError("source_url resource number must be an integer") from exc
    if number <= 0:
        raise ValueError("source_url resource number must be positive")
    return owner, repo, resource, number


class GitHubContributionSelection(StrictObservationModel):
    resource_kind: GitHubResourceKind
    repository_full_name: str = Field(min_length=3)
    number: int = Field(gt=0)
    source_url: str = Field(min_length=1)
    operator_github_login: str = Field(min_length=1)
    entry_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> "GitHubContributionSelection":
        owner, repo, resource, number = _parse_selection_url(self.source_url)
        expected_resource = "issues" if self.resource_kind == "ISSUE" else "pull"
        if f"{owner}/{repo}" != self.repository_full_name:
            raise ValueError("source_url repository does not match repository_full_name")
        if resource != expected_resource:
            raise ValueError("source_url resource kind does not match resource_kind")
        if number != self.number:
            raise ValueError("source_url number does not match number")
        if self.resource_kind == "PULL_REQUEST" and self.entry_id is None:
            raise ValueError("pull request selection requires entry_id")
        return self


class GitHubIssueSnapshot(StrictObservationModel):
    repository_full_name: str = Field(min_length=1)
    issue_number: int = Field(gt=0)
    issue_url: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=500)
    state: GitHubIssueState
    assignee_logins: list[str] = Field(default_factory=list)
    author_login: str | None = Field(default=None, min_length=1)
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    captured_at: datetime

    @field_validator("created_at", "updated_at", "closed_at", "captured_at")
    @classmethod
    def normalize_times(cls, value: datetime | None, info) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value, field=info.field_name)

    @model_validator(mode="after")
    def validate_state(self) -> "GitHubIssueSnapshot":
        if self.state == "CLOSED" and self.closed_at is None:
            raise ValueError("closed issue requires closed_at")
        return self


class GitHubReviewSnapshot(StrictObservationModel):
    review_ref: str = Field(min_length=1)
    reviewer_login: str | None = Field(default=None, min_length=1)
    state: GitHubReviewState
    submitted_at: datetime

    @field_validator("submitted_at")
    @classmethod
    def normalize_submitted_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field="submitted_at")


class GitHubCheckSnapshot(StrictObservationModel):
    check_ref: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    state_or_conclusion: str = Field(min_length=1, max_length=80)
    description_code: ReasonCode | None = None
    fact_at: datetime

    @field_validator("fact_at")
    @classmethod
    def normalize_fact_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field="fact_at")


class GitHubPullRequestSnapshot(StrictObservationModel):
    repository_full_name: str = Field(min_length=1)
    pr_number: int = Field(gt=0)
    pr_url: str = Field(min_length=1)
    state: GitHubPullRequestState
    merged: bool
    draft: bool
    author_login: str | None = Field(default=None, min_length=1)
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    merged_at: datetime | None = None
    head_sha: str = Field(min_length=1)
    reviews: list[GitHubReviewSnapshot] = Field(default_factory=list)
    checks: list[GitHubCheckSnapshot] = Field(default_factory=list)
    captured_at: datetime

    @field_validator("created_at", "updated_at", "closed_at", "merged_at", "captured_at")
    @classmethod
    def normalize_times(cls, value: datetime | None, info) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value, field=info.field_name)

    @model_validator(mode="after")
    def validate_terminal_times(self) -> "GitHubPullRequestSnapshot":
        if self.merged and self.merged_at is None:
            raise ValueError("merged pull request requires merged_at")
        if self.state == "CLOSED" and self.closed_at is None:
            raise ValueError("closed pull request requires closed_at")
        return self


class ContributionObservation(StrictObservationModel):
    observation_id: str = Field(min_length=1)
    source_type: Literal["PUBLIC_GITHUB"] = "PUBLIC_GITHUB"
    source_name: Literal["github"] = "github"
    source_ref: str = Field(min_length=1)
    kind: ContributionObservationKind
    entry_id: str | None = Field(default=None, min_length=1)
    repository_full_name: str = Field(min_length=1)
    public_title: str | None = Field(default=None, min_length=1, max_length=500)
    fact_at: datetime
    captured_at: datetime
    task_ref: str | None = Field(default=None, min_length=1)
    work_ref: str | None = Field(default=None, min_length=1)
    actor_ref: str | None = Field(default=None, min_length=1)
    reason_code: ReasonCode | None = None
    source_fact_identity: str = Field(min_length=1, max_length=500)

    @field_validator("fact_at", "captured_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware_utc(value, field=info.field_name)

    @model_validator(mode="after")
    def validate_kind_refs(self) -> "ContributionObservation":
        if self.kind in _ISSUE_OBSERVATION_KINDS:
            if self.task_ref is None:
                raise ValueError(f"{self.kind} requires task_ref")
            if self.public_title is None:
                raise ValueError(f"{self.kind} requires public_title")
        if self.kind in _WORK_OBSERVATION_KINDS and self.work_ref is None:
            raise ValueError(f"{self.kind} requires work_ref")
        if self.kind == "EXTERNAL_BLOCKER" and self.reason_code is None:
            raise ValueError("EXTERNAL_BLOCKER requires reason_code")
        return self


class ContributionPreview(StrictObservationModel):
    preview_version: str = Field(min_length=1)
    status: ContributionPreviewStatus
    observation: ContributionObservation
    observation_sha256: str = Field(min_length=64, max_length=64)
    preview_sha256: str = Field(min_length=64, max_length=64)
    entry_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    proposed_entry: PublicContributionEntry | None = None
    candidate_event: ContributionEvent | None = None
    context_before: ContributionContext | None = None
    context_after: ContributionContext | None = None
    errors: list[str] = Field(default_factory=list)
    external_actions: list[str] = Field(default_factory=list)

    @field_validator("external_actions")
    @classmethod
    def require_no_external_actions(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("external_actions must be empty")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> "ContributionPreview":
        proposals = int(self.proposed_entry is not None) + int(self.candidate_event is not None)
        if self.status == "IMPORTABLE":
            if proposals != 1:
                raise ValueError("IMPORTABLE preview requires exactly one proposal")
        elif proposals:
            raise ValueError(f"{self.status} preview cannot contain a proposal")
        if self.status == "BLOCKED" and not self.errors:
            raise ValueError("BLOCKED preview requires errors")
        return self


class ContributionImportRequest(StrictObservationModel):
    preview: ContributionPreview
    confirmed_by: str = Field(min_length=1)
    confirmed_at: datetime

    @field_validator("confirmed_at")
    @classmethod
    def normalize_confirmed_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field="confirmed_at")

    @model_validator(mode="after")
    def validate_confirmation(self) -> "ContributionImportRequest":
        if self.preview.status != "IMPORTABLE":
            raise ValueError("import request requires IMPORTABLE preview")
        if self.confirmed_at < self.preview.observation.captured_at:
            raise ValueError("confirmed_at must be at or after observation captured_at")
        return self


class ContributionImportReceipt(StrictObservationModel):
    receipt_id: str = Field(min_length=1)
    observation_id: str = Field(min_length=1)
    observation_sha256: str = Field(min_length=64, max_length=64)
    preview_sha256: str = Field(min_length=64, max_length=64)
    entry_id: str = Field(min_length=1)
    contribution_event_id: str | None = Field(default=None, min_length=1)
    source_ref: str = Field(min_length=1)
    confirmed_by: str = Field(min_length=1)
    confirmed_at: datetime
    processed_at: datetime
    status: ReceiptStatus

    @field_validator("confirmed_at", "processed_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware_utc(value, field=info.field_name)


class ContributionImportResult(StrictObservationModel):
    status: ContributionImportStatus
    receipt: ContributionImportReceipt | None = None
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result_shape(self) -> "ContributionImportResult":
        if self.status in {"IMPORTED", "ALREADY_IMPORTED"}:
            if self.receipt is None:
                raise ValueError("successful import result requires receipt")
            if self.receipt.status != self.status:
                raise ValueError("receipt status must match import result status")
        elif self.receipt is not None:
            raise ValueError("blocked/conflict import result cannot contain receipt")
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


def observation_sha256(observation: ContributionObservation) -> str:
    return canonical_sha256(observation)
