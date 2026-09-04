# Public Contribution Core V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strict, deterministic, domain-only lifecycle for public contribution opportunities without conflating contribution activity with job openings, hiring interest, or external action authority.

**Architecture:** Create an isolated `app/contributions/` package with strict Pydantic domain models and a pure deterministic projector. Use append-only `ContributionEvent` values plus immutable `PublicContributionEntry` discovery state to derive `ContributionContext`; keep blockers orthogonal to stage and represent public PR artifacts separately as `ProofOfWork`. Dogfood is fixture-driven and public/sanitized only.

**Tech Stack:** Python 3.12+, Pydantic v2, pytest; no new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-09-04-public-contribution-core-v1-design.md`

## Global Constraints

- `PUBLIC_CONTRIBUTION_ENTRY != JOB_OPENING`.
- `PR_OPENED != EMPLOYMENT_INTEREST`.
- `PR_MERGED != EMPLOYMENT_INTEREST`.
- No existing `Opportunity`, `TargetAccount`, `RelationshipMemory`, Process Email, Outreach Core, DB, or API contract may be modified.
- `TargetAccount` linkage is optional.
- Public need and contribution hypothesis remain distinct.
- Task quality and task availability remain distinct.
- Blocking is orthogonal to lifecycle stage.
- State is projected deterministically from immutable entry data plus append-only events ordered by `(observed_at, event_id)`.
- Strict models use `ConfigDict(extra="forbid")`.
- All timestamps must be timezone-aware and normalized to UTC.
- Public dogfood fixtures must not contain private Gmail bodies, personal email addresses, private notes, or provider payloads.
- No DB persistence, HTTP API route, background worker, Gmail integration, GitHub mutation, automatic relationship mutation, automatic EvidenceItem promotion, autonomous outreach, or new external action authority.
- No new package dependency.

---

## File Structure

Create:

```text
app/contributions/
  __init__.py          # public imports for V1 domain objects/projector
  models.py            # strict domain models + enums + UTC normalization
  projector.py         # pure deterministic ContributionContext projection

examples/contributions/
  public_contribution_dogfood.json

tests/
  test_contribution_models.py
  test_contribution_projection.py
  test_contribution_dogfood.py
  test_proof_of_work.py
  test_contribution_release_contract.py
```

Modify only after the domain is green:

```text
README.md              # document the new domain and its epistemic boundary
ROADMAP.md             # record Public Contribution Core V1 as domain-only
```

Do **not** modify `app/main.py`, API routers, DB repositories, relationship models, opportunity models, target-account models, process-email code, outreach code, CV code, or `pyproject.toml`.

---

### Task 1: Add strict contribution domain models

**Files:**
- Create: `app/contributions/__init__.py`
- Create: `app/contributions/models.py`
- Create: `tests/test_contribution_models.py`
- Create: `tests/test_proof_of_work.py`

**Interfaces:**
- Consumes: Pydantic v2 already in the project.
- Produces:
  - `PublicContributionEntry`
  - `ContributionEvent`
  - `ContributionContext`
  - `ProofOfWork`
  - enum-like `Literal` aliases used by the projector.

Define these exact public type aliases in `app/contributions/models.py`:

```python
ContributionOrigin = Literal[
    "PUBLIC_ISSUE",
    "HELP_WANTED",
    "REPOSITORY_RESEARCH",
    "MAINTAINER_PROPOSAL",
    "COLLABORATION_CALL",
]
NeedBasis = Literal["OBSERVED", "MAINTAINER_STATED", "HYPOTHESIZED"]
TaskClaimState = Literal[
    "NONE", "AVAILABLE", "CLAIMED_SELF", "CLAIMED_OTHER", "CLOSED", "UNKNOWN"
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
    "PUBLIC_GITHUB", "PUBLIC_RESEARCH", "EMAIL_PROVIDER", "MANUAL"
]
ProofArtifactKind = Literal["PULL_REQUEST"]
ProofStatus = Literal["OPEN", "MERGED", "CLOSED_UNMERGED"]
```

Define model shapes exactly:

```python
class PublicContributionEntry(StrictContributionModel):
    entry_id: str
    repository_full_name: str
    repository_url: str
    account_id: str | None = None
    origin: ContributionOrigin
    need_basis: NeedBasis
    need_statement: str
    evidence_refs: list[str] = Field(default_factory=list)
    task_ref: str | None = None
    bounded_task: str | None = None
    task_claim_state: TaskClaimState = "UNKNOWN"
    expected_effort: ExpectedEffort = "UNKNOWN"
    risk_level: RiskLevel = "UNKNOWN"
    discovered_at: datetime

class ContributionEvent(StrictContributionModel):
    event_id: str
    entry_id: str
    kind: ContributionEventKind
    source_type: ContributionSourceType
    source_ref: str
    observed_at: datetime
    actor_ref: str | None = None
    work_ref: str | None = None
    task_ref: str | None = None
    reason: str | None = None

class ContributionContext(StrictContributionModel):
    entry_id: str
    stage: ContributionStage
    blocking_reason: str | None = None
    last_event_kind: ContributionEventKind | None = None
    last_observed_at: datetime | None = None
    task_claim_state: TaskClaimState
    active_work_ref: str | None = None
    event_count: int = Field(ge=0)

class ProofOfWork(StrictContributionModel):
    proof_id: str
    entry_id: str
    artifact_kind: ProofArtifactKind = "PULL_REQUEST"
    repository_full_name: str
    artifact_ref: str
    artifact_url: str
    status: ProofStatus
    observed_at: datetime
    evidence_refs: list[str] = Field(min_length=1)
```

Model validators must enforce:

```text
OBSERVED -> evidence_refs non-empty
MAINTAINER_STATED -> evidence_refs non-empty
AVAILABLE -> task_ref required
CLAIMED_SELF -> task_ref required
CLAIMED_OTHER -> task_ref required
CLOSED -> task_ref required
PR_OPENED / PR_MERGED / PR_CLOSED -> work_ref required
REVIEW_RECEIVED / CHANGES_REQUESTED -> work_ref required
BLOCKED -> non-empty reason required
TASK_SELECTED / TASK_CLAIMED_SELF / TASK_CLAIMED_OTHER / TASK_RELEASED -> task_ref required
```

- [ ] **Step 1: Write failing strict-model tests**

Create `tests/test_contribution_models.py` with at least these concrete tests:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contributions.models import ContributionEvent, PublicContributionEntry

NOW = datetime(2026, 9, 4, 3, 30, tzinfo=timezone.utc)


def _entry(**overrides):
    payload = {
        "entry_id": "entry-1",
        "repository_full_name": "example/project",
        "repository_url": "https://github.com/example/project",
        "origin": "PUBLIC_ISSUE",
        "need_basis": "OBSERVED",
        "need_statement": "A reproducible issue exists.",
        "evidence_refs": ["github:issue:1"],
        "task_ref": "github:issue:1",
        "task_claim_state": "AVAILABLE",
        "discovered_at": NOW,
    }
    payload.update(overrides)
    return PublicContributionEntry(**payload)


def test_entry_is_strict_and_normalizes_utc() -> None:
    entry = _entry()
    assert entry.discovered_at.tzinfo is timezone.utc
    with pytest.raises(ValidationError):
        PublicContributionEntry(**entry.model_dump(), invented=True)


def test_observed_need_requires_provenance() -> None:
    with pytest.raises(ValidationError):
        _entry(evidence_refs=[])


def test_hypothesis_may_exist_without_claiming_maintainer_need() -> None:
    entry = _entry(
        need_basis="HYPOTHESIZED",
        evidence_refs=[],
        task_ref=None,
        task_claim_state="NONE",
    )
    assert entry.need_basis == "HYPOTHESIZED"
    assert entry.evidence_refs == []


def test_available_task_requires_task_ref() -> None:
    with pytest.raises(ValidationError):
        _entry(task_ref=None, task_claim_state="AVAILABLE")


def test_contribution_event_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        ContributionEvent(
            event_id="event-1",
            entry_id="entry-1",
            kind="DISCOVERED",
            source_type="PUBLIC_GITHUB",
            source_ref="github:repo:example/project",
            observed_at=datetime(2026, 9, 4, 3, 30),
        )
```

Add explicit tests for every validator listed above, especially `BLOCKED` reason and task/work references.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
pytest -q tests/test_contribution_models.py
```

Expected: collection/import failure because `app.contributions` does not exist.

- [ ] **Step 3: Implement minimal strict models**

Implement `StrictContributionModel`, `_aware_utc`, the aliases, models, field validators, and model validators in `app/contributions/models.py`. Re-export the four domain objects and `ContributionEventKind` from `app/contributions/__init__.py`.

Use the existing repository pattern:

```python
class StrictContributionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _aware_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)
```

- [ ] **Step 4: Run focused model tests and verify GREEN**

Run:

```bash
pytest -q tests/test_contribution_models.py
python -m compileall -q app/contributions
```

Expected: all contribution-model tests pass; compile exits 0.

- [ ] **Step 5: Write failing ProofOfWork tests**

Create `tests/test_proof_of_work.py`:

```python
from datetime import datetime, timezone

from app.contributions.models import ProofOfWork

NOW = datetime(2026, 9, 4, 3, 30, tzinfo=timezone.utc)


def test_merged_pr_is_public_proof_without_employment_semantics() -> None:
    proof = ProofOfWork(
        proof_id="proof-1",
        entry_id="entry-1",
        repository_full_name="example/project",
        artifact_ref="github:pr:42",
        artifact_url="https://github.com/example/project/pull/42",
        status="MERGED",
        observed_at=NOW,
        evidence_refs=["github:pr:42"],
    )
    assert proof.status == "MERGED"
    dumped = proof.model_dump()
    assert "employment_interest" not in dumped
    assert "job_opening" not in dumped
    assert "hiring" not in dumped
```

Also test empty `evidence_refs` fails and naive `observed_at` fails.

- [ ] **Step 6: Run ProofOfWork tests and verify GREEN**

Run:

```bash
pytest -q tests/test_proof_of_work.py tests/test_contribution_models.py
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```bash
git add app/contributions/__init__.py app/contributions/models.py tests/test_contribution_models.py tests/test_proof_of_work.py
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
class ContributionProjectionError(ValueError): ...

class ContributionProjector:
    def project(
        self,
        *,
        entry: PublicContributionEntry,
        events: list[ContributionEvent],
    ) -> ContributionContext: ...
```

Projection must be pure: no IO, DB, clock reads, network access, environment variables, or external mutations.

Initial stage from entry:

```text
AVAILABLE -> TASK_READY
all other task_claim_state values -> DISCOVERED
CLAIMED_OTHER -> DISCOVERED specifically
```

Event transitions:

```text
DISCOVERED -> preserve stage
OUTREACH_SENT -> CONTACTED
MAINTAINER_REPLIED -> ENGAGED
COLLABORATION_WELCOMED -> ENGAGED
WORK_PROPOSED -> ENGAGED
TASK_SELECTED -> TASK_READY
TASK_CLAIMED_SELF -> TASK_READY + CLAIMED_SELF
TASK_CLAIMED_OTHER -> preserve stage + CLAIMED_OTHER
TASK_RELEASED -> TASK_READY + AVAILABLE
WORK_STARTED -> IN_PROGRESS
PR_OPENED -> IN_REVIEW + active_work_ref
REVIEW_RECEIVED -> IN_REVIEW
CHANGES_REQUESTED -> IN_REVIEW
PR_MERGED -> COMPLETED
PR_CLOSED -> CLOSED
PAUSED -> PAUSED
RESUMED -> recompute last substantive non-pause stage
DISCARDED -> DISCARDED
BLOCKED -> preserve stage + blocker
UNBLOCKED -> preserve stage + clear blocker
```

- [ ] **Step 1: Write failing projection tests for normal lifecycle**

Create helpers in `tests/test_contribution_projection.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from app.contributions.models import ContributionEvent, PublicContributionEntry
from app.contributions.projector import ContributionProjectionError, ContributionProjector

NOW = datetime(2026, 9, 4, 3, 30, tzinfo=timezone.utc)


def _entry(*, claim="NONE") -> PublicContributionEntry:
    return PublicContributionEntry(
        entry_id="entry-1",
        repository_full_name="example/project",
        repository_url="https://github.com/example/project",
        origin="REPOSITORY_RESEARCH",
        need_basis="HYPOTHESIZED",
        need_statement="A bounded contribution may be useful.",
        evidence_refs=[],
        task_ref="github:issue:25" if claim != "NONE" else None,
        task_claim_state=claim,
        discovered_at=NOW,
    )


def _event(kind: str, minute: int, **extra) -> ContributionEvent:
    return ContributionEvent(
        event_id=f"event-{minute:02d}-{kind.lower()}",
        entry_id="entry-1",
        kind=kind,
        source_type="PUBLIC_GITHUB",
        source_ref=f"github:event:{minute}",
        observed_at=NOW + timedelta(minutes=minute),
        **extra,
    )
```

Cover at minimum:

```python
def test_available_entry_starts_task_ready(): ...
def test_claimed_other_entry_stays_discovered(): ...
def test_outreach_without_reply_is_contacted_not_engaged(): ...
def test_maintainer_reply_is_engaged_without_fabricating_task(): ...
def test_self_claim_and_work_start_progress_to_in_progress(): ...
def test_open_pr_projects_in_review(): ...
def test_merged_pr_projects_completed(): ...
def test_closed_unmerged_pr_projects_closed(): ...
```

- [ ] **Step 2: Run focused projector tests and verify RED**

```bash
pytest -q tests/test_contribution_projection.py
```

Expected: import failure for `app.contributions.projector`.

- [ ] **Step 3: Implement the minimal projector**

Implement deterministic sorting:

```python
ordered = sorted(events, key=lambda event: (event.observed_at, event.event_id))
```

Fail if any event has a different `entry_id` than the supplied entry.

Keep local projection variables only:

```python
stage = "TASK_READY" if entry.task_claim_state == "AVAILABLE" else "DISCOVERED"
task_claim_state = entry.task_claim_state
blocking_reason = None
active_work_ref = None
last_event_kind = None
last_observed_at = None
```

Track whether a PR is open/known before review/merge/close events. Track the last substantive stage before `PAUSED` so `RESUMED` can restore it.

- [ ] **Step 4: Add fail-closed sequence tests**

Add explicit tests:

```python
def test_review_before_pr_fails_closed(): ...
def test_changes_requested_before_pr_fails_closed(): ...
def test_merge_before_pr_fails_closed(): ...
def test_close_before_pr_fails_closed(): ...
def test_unblock_without_block_fails_closed(): ...
def test_double_block_fails_closed(): ...
def test_event_for_other_entry_fails_closed(): ...
```

Each must use:

```python
with pytest.raises(ContributionProjectionError):
    ContributionProjector().project(entry=entry, events=events)
```

- [ ] **Step 5: Add blocker orthogonality regression**

Use this exact semantic sequence:

```python
events = [
    _event("PR_OPENED", 1, work_ref="github:pr:115"),
    _event(
        "BLOCKED",
        2,
        reason="external deployment authorization required",
    ),
]
context = ContributionProjector().project(entry=_entry(), events=events)
assert context.stage == "IN_REVIEW"
assert context.blocking_reason == "external deployment authorization required"
assert context.active_work_ref == "github:pr:115"
```

Then append `UNBLOCKED` and assert stage remains `IN_REVIEW` while blocker becomes `None`.

- [ ] **Step 6: Add deterministic ordering regression**

Construct two equal-timestamp events with different `event_id` values and verify the same canonical result regardless of input list order:

```python
first = ContributionProjector().project(entry=entry, events=[event_b, event_a])
second = ContributionProjector().project(entry=entry, events=[event_a, event_b])
assert first.model_dump(mode="json") == second.model_dump(mode="json")
```

- [ ] **Step 7: Run focused projection suite and verify GREEN**

```bash
pytest -q tests/test_contribution_projection.py
python -m compileall -q app/contributions
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

```bash
git add app/contributions/projector.py app/contributions/__init__.py tests/test_contribution_projection.py
git commit -m "feat: project contribution lifecycle deterministically"
```

---

### Task 3: Add five public/sanitized dogfood fixtures

**Files:**
- Create: `examples/contributions/public_contribution_dogfood.json`
- Create: `tests/test_contribution_dogfood.py`

**Interfaces:**
- Consumes: V1 models and `ContributionProjector`.
- Produces: a stable fixture file with five cases and no runtime loader API.

Use this JSON top-level shape:

```json
{
  "version": "public-contribution-dogfood-v1",
  "cases": [
    {
      "case_id": "hypothesized-geospatial-sdk",
      "entry": {},
      "events": [],
      "proof": null,
      "expected": {
        "stage": "DISCOVERED",
        "task_claim_state": "NONE",
        "blocking_reason": null
      }
    }
  ]
}
```

Case IDs and semantic targets must be exactly:

```text
hypothesized-geospatial-sdk
  HYPOTHESIZED + NONE -> DISCOVERED

open-unassigned-explicit-bug
  OBSERVED + AVAILABLE -> TASK_READY

strong-issue-claimed-other
  OBSERVED + CLAIMED_OTHER -> DISCOVERED

moracarta-self-claimed-open-pr
  TASK_CLAIMED_SELF + PR_OPENED -> IN_REVIEW + ProofOfWork OPEN

sunat-draft-pr-external-blocker
  PR_OPENED + BLOCKED -> IN_REVIEW with blocker + ProofOfWork OPEN
```

Use only public GitHub-style refs/URLs. Do not include email addresses or copied mail text.

- [ ] **Step 1: Write failing dogfood projection test**

Create `tests/test_contribution_dogfood.py` that loads JSON with `json.loads(Path(...).read_text())`, validates each `entry` via `PublicContributionEntry`, each event via `ContributionEvent`, optional proof via `ProofOfWork`, projects context, and compares only the explicit `expected` fields.

Core loop:

```python
for case in payload["cases"]:
    entry = PublicContributionEntry.model_validate(case["entry"])
    events = [ContributionEvent.model_validate(item) for item in case["events"]]
    context = ContributionProjector().project(entry=entry, events=events)
    expected = case["expected"]
    assert context.stage == expected["stage"]
    assert context.task_claim_state == expected["task_claim_state"]
    assert context.blocking_reason == expected["blocking_reason"]
    if case["proof"] is not None:
        ProofOfWork.model_validate(case["proof"])
```

- [ ] **Step 2: Run dogfood test and verify RED**

```bash
pytest -q tests/test_contribution_dogfood.py
```

Expected: FAIL because fixture file does not exist.

- [ ] **Step 3: Add the five fixture cases**

Populate all timestamps with explicit `Z` offsets and evidence refs with typed public strings such as:

```text
github:repo:owner/name
github:issue:owner/name#25
github:pr:owner/name#42
github:pr-comment:owner/name#115:deployment-authorization
```

Do not store raw provider payloads.

- [ ] **Step 4: Add fixture privacy regression**

Test the raw serialized fixture text:

```python
raw = path.read_text(encoding="utf-8")
lower = raw.lower()
assert "@gmail.com" not in lower
assert "@mi.unc.edu.ar" not in lower
assert '"email_body"' not in lower
assert '"provider_payload"' not in lower
assert '"raw_mime"' not in lower
```

Also assert all five case IDs exist exactly once.

- [ ] **Step 5: Run dogfood suite and verify GREEN**

```bash
pytest -q tests/test_contribution_dogfood.py tests/test_contribution_projection.py tests/test_contribution_models.py tests/test_proof_of_work.py
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add examples/contributions/public_contribution_dogfood.json tests/test_contribution_dogfood.py
git commit -m "test: add public contribution dogfood fixtures"
```

---

### Task 4: Lock the isolation and epistemic release contract

**Files:**
- Create: `tests/test_contribution_release_contract.py`
- Modify: `README.md`
- Modify: `ROADMAP.md`

**Interfaces:**
- Consumes: completed contribution domain.
- Produces: public documentation and regressions that prevent accidental coupling to hiring or external-action surfaces.

- [ ] **Step 1: Write failing release-contract tests**

Create `tests/test_contribution_release_contract.py` with concrete checks:

```python
from pathlib import Path

from app.contributions.models import ContributionContext, ProofOfWork, PublicContributionEntry

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
    assert "contributions" not in main
    assert "contribution" not in main


def test_public_docs_state_the_epistemic_boundary() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "PUBLIC_CONTRIBUTION_ENTRY != JOB_OPENING" in readme
    assert "PR_MERGED != EMPLOYMENT_INTEREST" in readme
```

Do not assert absence of generic words in unrelated files; keep the contract focused on `app/main.py` and contribution model fields.

- [ ] **Step 2: Run release-contract tests and verify RED**

```bash
pytest -q tests/test_contribution_release_contract.py
```

Expected: documentation assertion fails until README is updated.

- [ ] **Step 3: Update README minimally**

Add a short `Public Contribution Core` section after Target Accounts / relationship boundaries. Include this exact block:

```text
PUBLIC_CONTRIBUTION_ENTRY
= a public repository contribution surface backed by observed evidence or an explicitly labeled hypothesis

PUBLIC_CONTRIBUTION_ENTRY != JOB_OPENING
PR_OPENED != EMPLOYMENT_INTEREST
PR_MERGED != EMPLOYMENT_INTEREST
```

Describe only V1 capabilities: strict domain objects, deterministic stage projection, blocker tracking, PR proof-of-work representation, sanitized dogfood. Explicitly say there is no GitHub automation, API, DB, Gmail classifier, or automatic CV evidence promotion.

- [ ] **Step 4: Update ROADMAP minimally**

Add one completed/design-aligned entry for `Public Contribution Core V1` with:

```text
public repo -> contribution entry -> append-only contribution events -> deterministic context -> proof of work
```

Repeat that contribution funnel metrics remain separate from hiring funnel metrics.

- [ ] **Step 5: Run release-contract and contribution suites**

```bash
pytest -q \
  tests/test_contribution_models.py \
  tests/test_contribution_projection.py \
  tests/test_contribution_dogfood.py \
  tests/test_proof_of_work.py \
  tests/test_contribution_release_contract.py
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add README.md ROADMAP.md tests/test_contribution_release_contract.py
git commit -m "docs: expose public contribution core boundaries"
```

---

### Task 5: Run the full repository gate and prepare the implementation PR

**Files:**
- No production file should be added outside the files listed above.
- Review branch diff against the approved spec before opening/refreshing the implementation PR.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: verified implementation branch ready for review.

- [ ] **Step 1: Run the complete contribution suite**

```bash
pytest -q \
  tests/test_contribution_models.py \
  tests/test_contribution_projection.py \
  tests/test_contribution_dogfood.py \
  tests/test_proof_of_work.py \
  tests/test_contribution_release_contract.py
```

Expected: PASS.

- [ ] **Step 2: Run the full repository pytest gate**

```bash
pytest -q
```

Expected: all existing and new tests pass. Do not accept pre-existing failures without investigating whether the branch caused them.

- [ ] **Step 3: Run compile and whitespace gates**

```bash
python -m compileall -q app
git diff --check origin/main...HEAD
```

Expected: both exit 0.

- [ ] **Step 4: Run the repository private/generated-file guard used by CI**

Inspect `.github/workflows/ci.yml` on the execution branch and run the same private/generated-file guard command locally, unchanged. The expected result is success with no private Gmail content, credentials, local state, generated private files, or personal email data added by this slice.

- [ ] **Step 5: Verify scope by changed-file list**

```bash
git diff --name-only origin/main...HEAD
```

Expected files are limited to:

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
```

The already-approved spec/plan docs may also be present if the implementation branch is based on the design branch. No `app/main.py`, DB, relationship, opportunity, target, process-email, outreach, CV, or dependency file should change.

- [ ] **Step 6: Verify the four acceptance objects exist**

Run:

```bash
python - <<'PY'
from app.contributions.models import (
    ContributionContext,
    ContributionEvent,
    ProofOfWork,
    PublicContributionEntry,
)
print(PublicContributionEntry.__name__)
print(ContributionEvent.__name__)
print(ContributionContext.__name__)
print(ProofOfWork.__name__)
PY
```

Expected output names are exactly the four classes above.

- [ ] **Step 7: Commit any verification-only documentation correction if required**

Only if verification exposed a documentation mismatch, correct that mismatch and commit it separately:

```bash
git add README.md ROADMAP.md
git commit -m "docs: align contribution core verification"
```

Do not add new runtime behavior during this step.

- [ ] **Step 8: Open or update the implementation PR**

PR title:

```text
feat: add Public Contribution Core V1
```

PR body must report:

```text
- four strict domain objects added
- deterministic append-only event projection
- blocker orthogonal to stage
- optional TargetAccount linkage
- five sanitized dogfood fixtures
- PR-only ProofOfWork
- focused test count/result
- full pytest result
- compile/diff/private-file gate result
- explicit statement: no DB/API/Gmail/GitHub mutation/external action authority
```

Keep the PR non-draft only after all verification steps pass.

---

## Self-Review Checklist

Before execution, the implementer should verify this plan against the approved spec:

- Spec sections 1-4 -> Task 1 models and strict boundaries.
- Spec section 5 -> Task 2 deterministic projection and fail-closed sequences.
- Spec section 6 -> Task 1 `ProofOfWork` tests/model.
- Spec section 7 -> Task 3 five dogfood cases.
- Spec sections 8-9 -> file layout and TDD tasks above.
- Spec section 10 -> Task 4/5 isolation tests and changed-file gate.
- Spec section 11 -> seams remain conceptual only; no adapter/promotion implementation.
- Spec section 12 -> Task 5 full acceptance verification.

No placeholder behavior is permitted. If implementation discovers a case that requires changing an approved enum, model field, projection rule, or non-goal, stop and update/review the spec before coding that deviation.
