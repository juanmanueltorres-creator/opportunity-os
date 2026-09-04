# Public Contribution Core V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strict, deterministic, domain-only lifecycle for public repository contributions without conflating contribution activity with job openings, hiring interest, or external-action authority.

**Architecture:** Add an isolated `app/contributions/` package containing strict Pydantic models and a pure deterministic projector. `PublicContributionEntry` stores discovery-time evidence, append-only `ContributionEvent` values describe subsequent public contribution activity, and `ContributionProjector` derives `ContributionContext`; blocking remains orthogonal to stage, and public PR artifacts are represented separately as `ProofOfWork`.

**Tech Stack:** Python 3.12+, Pydantic v2, pytest. No new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-09-04-public-contribution-core-v1-design.md`

## Global Constraints

- `PUBLIC_CONTRIBUTION_ENTRY != JOB_OPENING`.
- `PR_OPENED != EMPLOYMENT_INTEREST`.
- `PR_MERGED != EMPLOYMENT_INTEREST`.
- Do not modify `Opportunity`, `TargetAccount`, `RelationshipMemory`, Process Email, Outreach Core, CV Factory, DB repositories, or API contracts.
- `TargetAccount` linkage is optional.
- Public observed need, maintainer-stated need, and contribution hypothesis remain distinct.
- Task usefulness and task availability remain distinct.
- Blocking is orthogonal to lifecycle stage.
- Projection is deterministic from immutable entry data plus append-only events ordered by `(observed_at, event_id)`.
- Strict models use `ConfigDict(extra="forbid")`.
- Every timestamp is timezone-aware and normalized to UTC.
- Public dogfood fixtures contain no private Gmail body text, personal email address, private note, raw MIME, or provider payload.
- V1 has no DB persistence, HTTP API, background worker, Gmail integration, GitHub mutation, automatic Relationship Memory mutation, automatic `EvidenceItem` promotion, autonomous outreach, or new external-action authority.
- Do not modify `pyproject.toml` or add dependencies.

---

## File Map

Create:

```text
app/contributions/__init__.py
app/contributions/models.py
app/contributions/projector.py
examples/contributions/public_contribution_dogfood.json
tests/test_contribution_models.py
tests/test_contribution_projection.py
tests/test_contribution_dogfood.py
tests/test_proof_of_work.py
tests/test_contribution_release_contract.py
```

Modify only after the domain tests are green:

```text
README.md
ROADMAP.md
```

Do not modify:

```text
app/main.py
app/api/**
app/models/**
app/relationships/**
app/operator_bridge/**
app/process_email/**
app/outreach/**
app/cv/**
app/targets/**
pyproject.toml
```

---

### Task 1: Add strict contribution domain models

**Files:**
- Create: `app/contributions/__init__.py`
- Create: `app/contributions/models.py`
- Create: `tests/test_contribution_models.py`
- Create: `tests/test_proof_of_work.py`

**Interfaces:**
- Consumes: `pydantic.BaseModel`, `ConfigDict`, `Field`, `field_validator`, `model_validator`.
- Produces: `PublicContributionEntry`, `ContributionEvent`, `ContributionContext`, `ProofOfWork`, plus the Literal aliases below.

Use these exact aliases:

```python
from typing import Literal

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
```

Use these exact public model fields:

```python
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


class ContributionContext(StrictContributionModel):
    entry_id: str = Field(min_length=1)
    stage: ContributionStage
    blocking_reason: str | None = Field(default=None, min_length=1, max_length=280)
    last_event_kind: ContributionEventKind | None = None
    last_observed_at: datetime | None = None
    task_claim_state: TaskClaimState
    active_work_ref: str | None = Field(default=None, min_length=1)
    event_count: int = Field(ge=0)


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
```

Validators must enforce:

```text
OBSERVED requires evidence_refs
MAINTAINER_STATED requires evidence_refs
AVAILABLE requires task_ref
CLAIMED_SELF requires task_ref
CLAIMED_OTHER requires task_ref
CLOSED requires task_ref
TASK_SELECTED requires task_ref
TASK_CLAIMED_SELF requires task_ref
TASK_CLAIMED_OTHER requires task_ref
TASK_RELEASED requires task_ref
PR_OPENED requires work_ref
REVIEW_RECEIVED requires work_ref
CHANGES_REQUESTED requires work_ref
PR_MERGED requires work_ref
PR_CLOSED requires work_ref
BLOCKED requires reason
```

- [ ] **Step 1: Write strict entry tests first**

Create `tests/test_contribution_models.py` with this setup and tests:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contributions.models import ContributionEvent, PublicContributionEntry

NOW = datetime(2026, 9, 4, 3, 30, tzinfo=timezone.utc)


def make_entry(**overrides) -> PublicContributionEntry:
    payload = {
        "entry_id": "entry-1",
        "repository_full_name": "example/project",
        "repository_url": "https://github.com/example/project",
        "origin": "PUBLIC_ISSUE",
        "need_basis": "OBSERVED",
        "need_statement": "A reproducible issue exists.",
        "evidence_refs": ["github:issue:example/project#1"],
        "task_ref": "github:issue:example/project#1",
        "task_claim_state": "AVAILABLE",
        "discovered_at": NOW,
    }
    payload.update(overrides)
    return PublicContributionEntry(**payload)


def test_entry_is_strict_and_normalizes_utc() -> None:
    entry = make_entry()
    assert entry.discovered_at.tzinfo is timezone.utc
    with pytest.raises(ValidationError):
        PublicContributionEntry(**entry.model_dump(), invented=True)


def test_entry_rejects_naive_discovered_at() -> None:
    with pytest.raises(ValidationError):
        make_entry(discovered_at=datetime(2026, 9, 4, 3, 30))


def test_observed_need_requires_provenance() -> None:
    with pytest.raises(ValidationError):
        make_entry(evidence_refs=[])


def test_maintainer_stated_need_requires_provenance() -> None:
    with pytest.raises(ValidationError):
        make_entry(need_basis="MAINTAINER_STATED", evidence_refs=[])


def test_hypothesis_can_exist_without_claiming_observed_need() -> None:
    entry = make_entry(
        need_basis="HYPOTHESIZED",
        evidence_refs=[],
        task_ref=None,
        task_claim_state="NONE",
    )
    assert entry.need_basis == "HYPOTHESIZED"
    assert entry.evidence_refs == []


@pytest.mark.parametrize(
    "claim_state",
    ["AVAILABLE", "CLAIMED_SELF", "CLAIMED_OTHER", "CLOSED"],
)
def test_task_claim_states_require_task_ref(claim_state: str) -> None:
    with pytest.raises(ValidationError):
        make_entry(task_ref=None, task_claim_state=claim_state)
```

Add event validator coverage to the same file:

```python
def make_event(kind: str, **overrides) -> ContributionEvent:
    payload = {
        "event_id": "event-1",
        "entry_id": "entry-1",
        "kind": kind,
        "source_type": "PUBLIC_GITHUB",
        "source_ref": "github:event:1",
        "observed_at": NOW,
    }
    payload.update(overrides)
    return ContributionEvent(**payload)


def test_event_rejects_naive_observed_at() -> None:
    with pytest.raises(ValidationError):
        make_event("DISCOVERED", observed_at=datetime(2026, 9, 4, 3, 30))


@pytest.mark.parametrize(
    "kind",
    [
        "TASK_SELECTED",
        "TASK_CLAIMED_SELF",
        "TASK_CLAIMED_OTHER",
        "TASK_RELEASED",
    ],
)
def test_task_events_require_task_ref(kind: str) -> None:
    with pytest.raises(ValidationError):
        make_event(kind)


@pytest.mark.parametrize(
    "kind",
    [
        "PR_OPENED",
        "REVIEW_RECEIVED",
        "CHANGES_REQUESTED",
        "PR_MERGED",
        "PR_CLOSED",
    ],
)
def test_pr_events_require_work_ref(kind: str) -> None:
    with pytest.raises(ValidationError):
        make_event(kind)


def test_blocked_event_requires_reason() -> None:
    with pytest.raises(ValidationError):
        make_event("BLOCKED")


def test_valid_blocked_event_keeps_bounded_reason() -> None:
    event = make_event(
        "BLOCKED",
        reason="external deployment authorization required",
    )
    assert event.reason == "external deployment authorization required"
```

- [ ] **Step 2: Run the model tests and confirm RED**

Run:

```bash
pytest -q tests/test_contribution_models.py
```

Expected result: test collection fails because `app.contributions` does not exist.

- [ ] **Step 3: Implement the strict model layer**

Create `app/contributions/models.py` with the aliases and public models above. Use this strict base and UTC helper:

```python
class StrictContributionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _aware_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)
```

Use `field_validator` on every datetime-bearing public model and `model_validator(mode="after")` for cross-field invariants.

Create `app/contributions/__init__.py` with these exports:

```python
from app.contributions.models import (
    ContributionContext,
    ContributionEvent,
    ContributionEventKind,
    ProofOfWork,
    PublicContributionEntry,
)

__all__ = [
    "ContributionContext",
    "ContributionEvent",
    "ContributionEventKind",
    "ProofOfWork",
    "PublicContributionEntry",
]
```

- [ ] **Step 4: Run the model tests and compile gate**

Run:

```bash
pytest -q tests/test_contribution_models.py
python -m compileall -q app/contributions
```

Expected result: all model tests pass and compile exits 0.

- [ ] **Step 5: Write ProofOfWork tests**

Create `tests/test_proof_of_work.py`:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contributions.models import ProofOfWork

NOW = datetime(2026, 9, 4, 3, 30, tzinfo=timezone.utc)


def make_proof(**overrides) -> ProofOfWork:
    payload = {
        "proof_id": "proof-1",
        "entry_id": "entry-1",
        "repository_full_name": "example/project",
        "artifact_ref": "github:pr:example/project#42",
        "artifact_url": "https://github.com/example/project/pull/42",
        "status": "OPEN",
        "observed_at": NOW,
        "evidence_refs": ["github:pr:example/project#42"],
    }
    payload.update(overrides)
    return ProofOfWork(**payload)


def test_merged_pr_is_public_proof_without_employment_semantics() -> None:
    proof = make_proof(status="MERGED")
    dumped = proof.model_dump()
    assert proof.status == "MERGED"
    assert "employment_interest" not in dumped
    assert "job_opening" not in dumped
    assert "hiring" not in dumped


def test_closed_unmerged_remains_distinct_from_merged() -> None:
    proof = make_proof(status="CLOSED_UNMERGED")
    assert proof.status == "CLOSED_UNMERGED"


def test_proof_requires_public_provenance() -> None:
    with pytest.raises(ValidationError):
        make_proof(evidence_refs=[])


def test_proof_rejects_naive_observed_at() -> None:
    with pytest.raises(ValidationError):
        make_proof(observed_at=datetime(2026, 9, 4, 3, 30))
```

- [ ] **Step 6: Run all Task 1 tests**

Run:

```bash
pytest -q tests/test_contribution_models.py tests/test_proof_of_work.py
```

Expected result: PASS.

- [ ] **Step 7: Commit Task 1**

Run:

```bash
git add \
  app/contributions/__init__.py \
  app/contributions/models.py \
  tests/test_contribution_models.py \
  tests/test_proof_of_work.py
git commit -m "feat: add public contribution domain models"
```

---

### Task 2: Add deterministic contribution projection

**Files:**
- Create: `app/contributions/projector.py`
- Create: `tests/test_contribution_projection.py`
- Modify: `app/contributions/__init__.py`

**Interfaces:**
- Consumes: `PublicContributionEntry`, `ContributionEvent`, `ContributionContext`.
- Produces:

```python
class ContributionProjectionError(ValueError):
    pass


class ContributionProjector:
    def project(
        self,
        *,
        entry: PublicContributionEntry,
        events: list[ContributionEvent],
    ) -> ContributionContext:
        raise NotImplementedError
```

The final implementation must replace `raise NotImplementedError` during this task; it is shown only as the exact public signature to create before the TDD implementation.

Projection is pure: no IO, DB, clock read, environment variable, network call, or external mutation.

Initial stage:

```text
entry.task_claim_state == AVAILABLE -> TASK_READY
all other entry task states -> DISCOVERED
CLAIMED_OTHER explicitly remains DISCOVERED
```

Transitions:

```text
DISCOVERED -> preserve stage
OUTREACH_SENT -> CONTACTED
MAINTAINER_REPLIED -> ENGAGED
COLLABORATION_WELCOMED -> ENGAGED
WORK_PROPOSED -> ENGAGED
TASK_SELECTED -> TASK_READY
TASK_CLAIMED_SELF -> TASK_READY and CLAIMED_SELF
TASK_CLAIMED_OTHER -> preserve current stage and CLAIMED_OTHER
TASK_RELEASED -> TASK_READY and AVAILABLE
WORK_STARTED -> IN_PROGRESS
PR_OPENED -> IN_REVIEW and set active_work_ref
REVIEW_RECEIVED -> IN_REVIEW
CHANGES_REQUESTED -> IN_REVIEW
BLOCKED -> preserve stage and set blocking_reason
UNBLOCKED -> preserve stage and clear blocking_reason
PR_MERGED -> COMPLETED
PR_CLOSED -> CLOSED
PAUSED -> PAUSED
RESUMED -> restore the stage immediately preceding the active pause
DISCARDED -> DISCARDED
```

`active_work_ref` is set by `PR_OPENED` and preserved through review, merge, and close in V1 so the projected context retains the public work artifact reference. `ProofOfWork.status` carries whether that artifact is still open.

- [ ] **Step 1: Write the normal lifecycle projection tests**

Create `tests/test_contribution_projection.py` with these helpers:

```python
from datetime import datetime, timedelta, timezone

import pytest

from app.contributions.models import ContributionEvent, PublicContributionEntry
from app.contributions.projector import ContributionProjectionError, ContributionProjector

NOW = datetime(2026, 9, 4, 3, 30, tzinfo=timezone.utc)


def make_entry(*, claim: str = "NONE") -> PublicContributionEntry:
    return PublicContributionEntry(
        entry_id="entry-1",
        repository_full_name="example/project",
        repository_url="https://github.com/example/project",
        origin="REPOSITORY_RESEARCH",
        need_basis="HYPOTHESIZED",
        need_statement="A bounded contribution may be useful.",
        evidence_refs=[],
        task_ref="github:issue:example/project#25" if claim != "NONE" else None,
        task_claim_state=claim,
        discovered_at=NOW,
    )


def make_event(kind: str, minute: int, **overrides) -> ContributionEvent:
    payload = {
        "event_id": f"event-{minute:02d}-{kind.lower()}",
        "entry_id": "entry-1",
        "kind": kind,
        "source_type": "PUBLIC_GITHUB",
        "source_ref": f"github:event:{minute}",
        "observed_at": NOW + timedelta(minutes=minute),
    }
    payload.update(overrides)
    return ContributionEvent(**payload)
```

Add these exact tests:

```python
def test_available_entry_starts_task_ready() -> None:
    context = ContributionProjector().project(
        entry=make_entry(claim="AVAILABLE"),
        events=[],
    )
    assert context.stage == "TASK_READY"
    assert context.task_claim_state == "AVAILABLE"
    assert context.event_count == 0


def test_claimed_other_entry_stays_discovered() -> None:
    context = ContributionProjector().project(
        entry=make_entry(claim="CLAIMED_OTHER"),
        events=[],
    )
    assert context.stage == "DISCOVERED"
    assert context.task_claim_state == "CLAIMED_OTHER"


def test_outreach_without_reply_is_contacted_not_engaged() -> None:
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[make_event("OUTREACH_SENT", 1)],
    )
    assert context.stage == "CONTACTED"


def test_maintainer_reply_is_engaged_without_fabricating_task() -> None:
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[
            make_event("OUTREACH_SENT", 1),
            make_event("MAINTAINER_REPLIED", 2),
        ],
    )
    assert context.stage == "ENGAGED"
    assert context.task_claim_state == "NONE"


def test_self_claim_and_work_start_progress_to_in_progress() -> None:
    task_ref = "github:issue:example/project#25"
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[
            make_event("TASK_SELECTED", 1, task_ref=task_ref),
            make_event("TASK_CLAIMED_SELF", 2, task_ref=task_ref),
            make_event("WORK_STARTED", 3),
        ],
    )
    assert context.stage == "IN_PROGRESS"
    assert context.task_claim_state == "CLAIMED_SELF"


def test_claim_by_other_never_fabricates_task_ready() -> None:
    task_ref = "github:issue:example/project#25"
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[make_event("TASK_CLAIMED_OTHER", 1, task_ref=task_ref)],
    )
    assert context.stage == "DISCOVERED"
    assert context.task_claim_state == "CLAIMED_OTHER"


def test_open_pr_projects_in_review() -> None:
    work_ref = "github:pr:example/project#42"
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[make_event("PR_OPENED", 1, work_ref=work_ref)],
    )
    assert context.stage == "IN_REVIEW"
    assert context.active_work_ref == work_ref


def test_merged_pr_projects_completed() -> None:
    work_ref = "github:pr:example/project#42"
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[
            make_event("PR_OPENED", 1, work_ref=work_ref),
            make_event("PR_MERGED", 2, work_ref=work_ref),
        ],
    )
    assert context.stage == "COMPLETED"
    assert context.active_work_ref == work_ref


def test_closed_unmerged_pr_projects_closed() -> None:
    work_ref = "github:pr:example/project#42"
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[
            make_event("PR_OPENED", 1, work_ref=work_ref),
            make_event("PR_CLOSED", 2, work_ref=work_ref),
        ],
    )
    assert context.stage == "CLOSED"
    assert context.active_work_ref == work_ref
```

- [ ] **Step 2: Run projection tests and confirm RED**

Run:

```bash
pytest -q tests/test_contribution_projection.py
```

Expected result: collection fails because `app.contributions.projector` does not exist.

- [ ] **Step 3: Implement deterministic event ordering and normal transitions**

Create `app/contributions/projector.py`. Sort with:

```python
ordered = sorted(events, key=lambda event: (event.observed_at, event.event_id))
```

Initialize with:

```python
stage = "TASK_READY" if entry.task_claim_state == "AVAILABLE" else "DISCOVERED"
task_claim_state = entry.task_claim_state
blocking_reason = None
active_work_ref = None
last_event_kind = None
last_observed_at = None
pause_restore_stage = None
known_pr_ref = None
```

For every event, first enforce:

```python
if event.entry_id != entry.entry_id:
    raise ContributionProjectionError("event entry_id does not match contribution entry")
```

Implement every transition listed above. Set `last_event_kind` and `last_observed_at` after each successful event. Return `ContributionContext(event_count=len(ordered), ...)`.

- [ ] **Step 4: Add fail-closed sequence tests**

Append these tests to `tests/test_contribution_projection.py`:

```python
@pytest.mark.parametrize(
    "kind",
    ["REVIEW_RECEIVED", "CHANGES_REQUESTED", "PR_MERGED", "PR_CLOSED"],
)
def test_pr_followup_without_open_pr_fails_closed(kind: str) -> None:
    with pytest.raises(ContributionProjectionError):
        ContributionProjector().project(
            entry=make_entry(),
            events=[
                make_event(
                    kind,
                    1,
                    work_ref="github:pr:example/project#42",
                )
            ],
        )


def test_unblock_without_active_blocker_fails_closed() -> None:
    with pytest.raises(ContributionProjectionError):
        ContributionProjector().project(
            entry=make_entry(),
            events=[make_event("UNBLOCKED", 1)],
        )


def test_double_block_fails_closed() -> None:
    with pytest.raises(ContributionProjectionError):
        ContributionProjector().project(
            entry=make_entry(),
            events=[
                make_event("BLOCKED", 1, reason="first blocker"),
                make_event("BLOCKED", 2, reason="second blocker"),
            ],
        )


def test_event_for_another_entry_fails_closed() -> None:
    foreign = make_event("OUTREACH_SENT", 1).model_copy(
        update={"entry_id": "entry-other"}
    )
    with pytest.raises(ContributionProjectionError):
        ContributionProjector().project(entry=make_entry(), events=[foreign])


def test_review_work_ref_must_match_open_pr() -> None:
    with pytest.raises(ContributionProjectionError):
        ContributionProjector().project(
            entry=make_entry(),
            events=[
                make_event(
                    "PR_OPENED",
                    1,
                    work_ref="github:pr:example/project#42",
                ),
                make_event(
                    "REVIEW_RECEIVED",
                    2,
                    work_ref="github:pr:example/project#99",
                ),
            ],
        )
```

The projector must reject review/change/merge/close events when `work_ref` differs from the known open PR reference.

- [ ] **Step 5: Add blocker orthogonality tests**

Append:

```python
def test_blocker_preserves_in_review_stage() -> None:
    work_ref = "github:pr:example/project#115"
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[
            make_event("PR_OPENED", 1, work_ref=work_ref),
            make_event(
                "BLOCKED",
                2,
                reason="external deployment authorization required",
            ),
        ],
    )
    assert context.stage == "IN_REVIEW"
    assert context.blocking_reason == "external deployment authorization required"
    assert context.active_work_ref == work_ref


def test_unblock_clears_only_blocker() -> None:
    work_ref = "github:pr:example/project#115"
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[
            make_event("PR_OPENED", 1, work_ref=work_ref),
            make_event(
                "BLOCKED",
                2,
                reason="external deployment authorization required",
            ),
            make_event("UNBLOCKED", 3),
        ],
    )
    assert context.stage == "IN_REVIEW"
    assert context.blocking_reason is None
    assert context.active_work_ref == work_ref
```

- [ ] **Step 6: Add pause/resume and deterministic-order tests**

Append:

```python
def test_pause_and_resume_restore_previous_stage() -> None:
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[
            make_event("OUTREACH_SENT", 1),
            make_event("MAINTAINER_REPLIED", 2),
            make_event("PAUSED", 3),
            make_event("RESUMED", 4),
        ],
    )
    assert context.stage == "ENGAGED"


def test_projection_is_deterministic_for_equal_timestamps() -> None:
    timestamp = NOW + timedelta(minutes=1)
    event_a = ContributionEvent(
        event_id="event-a",
        entry_id="entry-1",
        kind="OUTREACH_SENT",
        source_type="PUBLIC_GITHUB",
        source_ref="github:event:a",
        observed_at=timestamp,
    )
    event_b = ContributionEvent(
        event_id="event-b",
        entry_id="entry-1",
        kind="MAINTAINER_REPLIED",
        source_type="PUBLIC_GITHUB",
        source_ref="github:event:b",
        observed_at=timestamp,
    )
    projector = ContributionProjector()
    first = projector.project(entry=make_entry(), events=[event_b, event_a])
    second = projector.project(entry=make_entry(), events=[event_a, event_b])
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.stage == "ENGAGED"
```

- [ ] **Step 7: Run the full projector suite and compile gate**

Run:

```bash
pytest -q tests/test_contribution_projection.py
python -m compileall -q app/contributions
```

Expected result: PASS.

- [ ] **Step 8: Export the projector and commit Task 2**

Add to `app/contributions/__init__.py`:

```python
from app.contributions.projector import (
    ContributionProjectionError,
    ContributionProjector,
)
```

Add both names to `__all__`, then run:

```bash
git add \
  app/contributions/__init__.py \
  app/contributions/projector.py \
  tests/test_contribution_projection.py
git commit -m "feat: project contribution lifecycle deterministically"
```

---

### Task 3: Add five sanitized dogfood fixtures

**Files:**
- Create: `examples/contributions/public_contribution_dogfood.json`
- Create: `tests/test_contribution_dogfood.py`

**Interfaces:**
- Consumes: V1 models and `ContributionProjector`.
- Produces: one stable public fixture file; no runtime loader API.

Use this exact top-level JSON structure:

```json
{
  "version": "public-contribution-dogfood-v1",
  "cases": []
}
```

Use these exact case IDs and expectations:

```text
hypothesized-geospatial-sdk
  need_basis=HYPOTHESIZED
  task_claim_state=NONE
  stage=DISCOVERED

open-unassigned-explicit-bug
  need_basis=OBSERVED
  task_claim_state=AVAILABLE
  stage=TASK_READY

strong-issue-claimed-other
  need_basis=OBSERVED
  task_claim_state=CLAIMED_OTHER
  stage=DISCOVERED

moracarta-self-claimed-open-pr
  final task_claim_state=CLAIMED_SELF
  final stage=IN_REVIEW
  blocker=null
  ProofOfWork status=OPEN

sunat-draft-pr-external-blocker
  final stage=IN_REVIEW
  blocker="external deployment authorization required"
  ProofOfWork status=OPEN
```

Fixture refs may use public values such as:

```text
github:repo:WesleyHanauer/moracarta
github:issue:WesleyHanauer/moracarta#25
github:pr:WesleyHanauer/moracarta#42
github:pr:crafter-research/sunat-cli#115
```

Do not include private email content.

- [ ] **Step 1: Write the dogfood loader/projection test before the fixture**

Create `tests/test_contribution_dogfood.py`:

```python
import json
from pathlib import Path

from app.contributions.models import (
    ContributionEvent,
    ProofOfWork,
    PublicContributionEntry,
)
from app.contributions.projector import ContributionProjector

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "contributions" / "public_contribution_dogfood.json"
EXPECTED_CASE_IDS = {
    "hypothesized-geospatial-sdk",
    "open-unassigned-explicit-bug",
    "strong-issue-claimed-other",
    "moracarta-self-claimed-open-pr",
    "sunat-draft-pr-external-blocker",
}


def test_public_contribution_dogfood_projects_expected_contexts() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["version"] == "public-contribution-dogfood-v1"
    assert {case["case_id"] for case in payload["cases"]} == EXPECTED_CASE_IDS

    projector = ContributionProjector()
    for case in payload["cases"]:
        entry = PublicContributionEntry.model_validate(case["entry"])
        events = [
            ContributionEvent.model_validate(event)
            for event in case["events"]
        ]
        context = projector.project(entry=entry, events=events)
        expected = case["expected"]
        assert context.stage == expected["stage"], case["case_id"]
        assert (
            context.task_claim_state == expected["task_claim_state"]
        ), case["case_id"]
        assert context.blocking_reason == expected["blocking_reason"], case["case_id"]
        if case["proof"] is not None:
            proof = ProofOfWork.model_validate(case["proof"])
            assert proof.status == expected["proof_status"], case["case_id"]
```

- [ ] **Step 2: Run the dogfood test and confirm RED**

Run:

```bash
pytest -q tests/test_contribution_dogfood.py
```

Expected result: `FileNotFoundError` for `public_contribution_dogfood.json`.

- [ ] **Step 3: Create all five fixture cases**

Create `examples/contributions/public_contribution_dogfood.json`. Every datetime must include `Z`. Use public GitHub refs and sanitized need statements. For Moracarta use this event sequence:

```text
DISCOVERED
TASK_SELECTED
TASK_CLAIMED_SELF
WORK_STARTED
PR_OPENED
```

For SUNAT use:

```text
PR_OPENED
BLOCKED
```

For `strong-issue-claimed-other`, do not add a self-claim event and do not project `TASK_READY`.

- [ ] **Step 4: Add raw-fixture privacy assertions**

Append to `tests/test_contribution_dogfood.py`:

```python
def test_public_contribution_fixture_contains_no_private_mail_material() -> None:
    raw = FIXTURE.read_text(encoding="utf-8")
    lower = raw.lower()
    assert "@gmail.com" not in lower
    assert "@mi.unc.edu.ar" not in lower
    assert '"email_body"' not in lower
    assert '"provider_payload"' not in lower
    assert '"raw_mime"' not in lower
    assert '"private_note"' not in lower
```

- [ ] **Step 5: Run all contribution tests and confirm GREEN**

Run:

```bash
pytest -q \
  tests/test_contribution_models.py \
  tests/test_contribution_projection.py \
  tests/test_contribution_dogfood.py \
  tests/test_proof_of_work.py
```

Expected result: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add \
  examples/contributions/public_contribution_dogfood.json \
  tests/test_contribution_dogfood.py
git commit -m "test: add public contribution dogfood fixtures"
```

---

### Task 4: Lock the public release boundary

**Files:**
- Create: `tests/test_contribution_release_contract.py`
- Modify: `README.md`
- Modify: `ROADMAP.md`

**Interfaces:**
- Consumes: completed contribution domain.
- Produces: public documentation plus regressions preventing accidental employment/action coupling.

- [ ] **Step 1: Write release-contract tests before documentation changes**

Create `tests/test_contribution_release_contract.py`:

```python
from pathlib import Path

from app.contributions.models import (
    ContributionContext,
    ProofOfWork,
    PublicContributionEntry,
)

ROOT = Path(__file__).resolve().parents[1]


def test_contribution_models_have_no_employment_authority_fields() -> None:
    forbidden = {
        "employment_interest",
        "job_opening",
        "application_status",
        "send_authorized",
        "apply_authorized",
    }
    for model in (PublicContributionEntry, ContributionContext, ProofOfWork):
        assert forbidden.isdisjoint(model.model_fields)


def test_public_contribution_v1_does_not_wire_an_api_route() -> None:
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "app.contributions" not in main
    assert "/contributions" not in main
    assert "/contribution" not in main


def test_public_docs_state_the_epistemic_boundary() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "PUBLIC_CONTRIBUTION_ENTRY != JOB_OPENING" in readme
    assert "PR_OPENED != EMPLOYMENT_INTEREST" in readme
    assert "PR_MERGED != EMPLOYMENT_INTEREST" in readme


def test_roadmap_keeps_contribution_and_hiring_funnels_separate() -> None:
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    assert "Public Contribution Core" in roadmap
    assert "contribution funnel" in roadmap.lower()
    assert "hiring funnel" in roadmap.lower()
```

- [ ] **Step 2: Run the release-contract test and confirm RED**

Run:

```bash
pytest -q tests/test_contribution_release_contract.py
```

Expected result: documentation assertions fail because README/ROADMAP do not yet describe V1.

- [ ] **Step 3: Update README with the bounded V1 contract**

Add a concise `Public Contribution Core` section containing this exact text block:

```text
PUBLIC_CONTRIBUTION_ENTRY
= a public repository contribution surface backed by observed evidence or an explicitly labeled hypothesis

PUBLIC_CONTRIBUTION_ENTRY != JOB_OPENING
PR_OPENED != EMPLOYMENT_INTEREST
PR_MERGED != EMPLOYMENT_INTEREST
```

Document only what V1 actually provides:

```text
strict domain models
deterministic contribution-stage projection
orthogonal blocker state
PR-only ProofOfWork
five sanitized dogfood cases
```

State explicitly that V1 has no GitHub automation, DB, HTTP API, Gmail collaboration classifier, or automatic CV-evidence promotion.

- [ ] **Step 4: Update ROADMAP with the domain-only slice**

Add `Public Contribution Core V1` with this flow:

```text
public repo
-> PublicContributionEntry
-> append-only ContributionEvent
-> deterministic ContributionContext
-> ProofOfWork
```

Add these two lines verbatim:

```text
Contribution funnel metrics remain separate from hiring funnel metrics.
A contribution outcome does not imply employment interest.
```

- [ ] **Step 5: Run the release contract and focused suite**

Run:

```bash
pytest -q \
  tests/test_contribution_models.py \
  tests/test_contribution_projection.py \
  tests/test_contribution_dogfood.py \
  tests/test_proof_of_work.py \
  tests/test_contribution_release_contract.py
```

Expected result: PASS.

- [ ] **Step 6: Commit Task 4**

Run:

```bash
git add README.md ROADMAP.md tests/test_contribution_release_contract.py
git commit -m "docs: expose public contribution core boundaries"
```

---

### Task 5: Run the full repository gate and prepare the implementation PR

**Files:**
- No new production file outside the file map above.
- No API or persistence wiring.

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: a verified implementation branch and reviewable PR.

- [ ] **Step 1: Run the focused contribution suite**

Run:

```bash
pytest -q \
  tests/test_contribution_models.py \
  tests/test_contribution_projection.py \
  tests/test_contribution_dogfood.py \
  tests/test_proof_of_work.py \
  tests/test_contribution_release_contract.py
```

Expected result: PASS.

- [ ] **Step 2: Run the full pytest gate**

Run:

```bash
python -m pytest -v
```

Expected result: all existing and new tests pass. Any failure must be investigated before continuing.

- [ ] **Step 3: Run compile and whitespace gates**

Run:

```bash
python -m compileall app
git diff --check origin/main...HEAD
```

Expected result: both commands exit 0.

- [ ] **Step 4: Run the exact CI private/generated-file guard**

Run this command exactly as `.github/workflows/tests.yml` does:

```bash
set -euo pipefail
forbidden="$(git ls-files -- \
  '.env' \
  'profile.local.yaml' \
  'sources.local.yaml' \
  'profile/master_facts.local.yaml' \
  'profile/evidence_catalog.local.yaml' \
  'profile/*.local.yaml' \
  '*.local.yaml' \
  'state/outreach.local.sqlite3' \
  'state/relationships.local.sqlite3*' \
  'state/history.local.sqlite3*' \
  'state/history-import*.local.json' \
  'artifacts/relationships/**' \
  'artifacts/applications/**' \
  'artifacts/applications/**/outreach/**' \
  'artifacts/metrics/**' \
  '*.pdf' \
  '*.docx')"
if [[ -n "$forbidden" ]]; then
  printf 'Forbidden private/generated files are tracked:\n%s\n' "$forbidden"
  exit 1
fi
```

Expected result: exit 0 with no output.

- [ ] **Step 5: Run the existing recruiter preview CI gate**

Run:

```bash
python scripts/render_recruiter_previews.py
```

Expected result: exit 0. Do not commit generated preview artifacts.

- [ ] **Step 6: Verify changed-file scope**

Run:

```bash
git diff --name-only origin/main...HEAD
```

Allowed implementation files are:

```text
app/contributions/__init__.py
app/contributions/models.py
app/contributions/projector.py
examples/contributions/public_contribution_dogfood.json
tests/test_contribution_models.py
tests/test_contribution_projection.py
tests/test_contribution_dogfood.py
tests/test_proof_of_work.py
tests/test_contribution_release_contract.py
README.md
ROADMAP.md
docs/superpowers/specs/2026-09-04-public-contribution-core-v1-design.md
docs/superpowers/plans/2026-09-04-public-contribution-core-v1.md
```

If any file under these paths appears, stop and inspect why before opening the PR:

```text
app/main.py
app/api/
app/relationships/
app/operator_bridge/
app/process_email/
app/outreach/
app/cv/
pyproject.toml
```

- [ ] **Step 7: Verify the four acceptance objects and projector import**

Run:

```bash
python - <<'PY'
from app.contributions import (
    ContributionContext,
    ContributionEvent,
    ContributionProjector,
    ProofOfWork,
    PublicContributionEntry,
)

print(PublicContributionEntry.__name__)
print(ContributionEvent.__name__)
print(ContributionContext.__name__)
print(ProofOfWork.__name__)
print(ContributionProjector.__name__)
PY
```

Expected output:

```text
PublicContributionEntry
ContributionEvent
ContributionContext
ProofOfWork
ContributionProjector
```

- [ ] **Step 8: Open the implementation PR only after all gates pass**

Use title:

```text
feat: add Public Contribution Core V1
```

The PR body must report all of these facts with the actual measured test results:

```text
four strict domain objects added
deterministic append-only event projection
blocker state orthogonal to stage
optional TargetAccount linkage
five sanitized/public dogfood fixtures
PR-only ProofOfWork
focused suite result
full pytest result
compile result
diff whitespace result
private/generated-file guard result
recruiter preview result
no DB/API/Gmail/GitHub mutation/external action authority
```

Keep the implementation PR draft until every Task 5 gate is green. Mark ready for review only after verification has been rerun on the final head commit.

---

## Plan Self-Review Result

Spec coverage is complete:

```text
Spec sections 1-4 -> Task 1
Spec section 5 -> Task 2
Spec section 6 -> Task 1 ProofOfWork
Spec section 7 -> Task 3
Spec sections 8-9 -> Tasks 1-3 testing/layout
Spec section 10 -> Tasks 4-5 isolation/non-goals
Spec section 11 -> future seams remain unimplemented
Spec section 12 -> Task 5 acceptance gate
```

Type consistency is locked to these public names:

```text
PublicContributionEntry
ContributionEvent
ContributionContext
ProofOfWork
ContributionProjector
ContributionProjectionError
```

The plan contains no implementation placeholders. If execution discovers a need to change an approved enum, public model field, projection rule, or non-goal, stop implementation and revise/review the spec before making that deviation.
