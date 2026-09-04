# Contribution Intake / Observation Bridge V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn one explicitly selected public GitHub issue or pull request into a strict, hash-bound contribution preview and, only after human confirmation, append the corresponding local contribution entry/event to SQLite without adding GitHub write authority or hiring inference.

**Architecture:** Keep contribution intake as a sibling of the relationship-oriented Operator Bridge. A GET-only `GitHubPublicContributionProvider` produces allowlisted transient snapshots; a deterministic normalizer selects one public fact and proposes either one immutable `PublicContributionEntry` or zero/one `ContributionEvent`; `ContributionObservationBridge` binds that proposal to current local state with a preview hash; import revalidates the embedded typed preview against SQLite and never re-fetches GitHub. `ContributionContext` remains a pure projection.

**Tech Stack:** Python 3.12+, Pydantic v2, stdlib `sqlite3`, existing `httpx`, `argparse`, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-04-contribution-observation-bridge-v1-design.md`

## Global Constraints

- Preserve: `OBSERVE != CLAIM`, `OBSERVE != COMMENT`, `OBSERVE != OPEN_PR`, and `IMPORT != EXTERNAL_ACTION`.
- Preserve: `PUBLIC_CONTRIBUTION_ENTRY != JOB_OPENING`, `PR_OPENED != EMPLOYMENT_INTEREST`, and `PR_MERGED != EMPLOYMENT_INTEREST`.
- Support exactly one explicitly selected public GitHub issue or pull request per preview; no search/radar/discovery endpoints.
- GitHub provider authority is GET-only. No POST, PUT, PATCH, DELETE, assignment, comment, review submission, PR mutation, merge, or repository mutation code belongs in V1.
- Do not add HTTP API routes. Do not modify `app/main.py` or `app/operator_bridge`, `app/relationships`, `app/outreach`, `app/process_email`, `app/cv`, or opportunity models.
- Do not add project dependencies; `httpx` already exists in `pyproject.toml`.
- Raw GitHub issue/PR bodies, review text, check logs, auth headers, and tokens remain transient and are never persisted or serialized into domain models.
- All typed timestamps are timezone-aware and normalized to UTC. Tests inject explicit wall-clock values; no domain hash or event identity depends on hidden `datetime.now()` calls.
- One preview proposes at most one new entry or one candidate event.
- PR lineage always requires an explicit existing contribution entry. PR body text such as `Closes #25` is ignored for lineage.
- Existing issue lineage requires both exact repository identity and exact `task_ref` equality.
- Generic CI failure is not an external blocker. Only `ACTION_REQUIRED` or allowlisted explicit authorization/access evidence can create `BLOCKED`.
- Preview is read-only. Import requires the exact serialized `IMPORTABLE` preview the operator reviewed.
- Import performs no GitHub call. It revalidates the embedded typed observation/proposal against current local SQLite state and rejects stale previews.
- Default local persistence path is `state/contributions.local.sqlite3`; reads against a missing DB are side-effect free; initialization is explicit.
- `ContributionContext` is projected and never stored as independent truth.
- Contribution outcomes never mutate Relationship Memory and never imply hiring/contact permission.

---

## File Structure

### Existing files to modify

- `app/contributions/models.py` — add `TASK_CLOSED` to the core event contract.
- `app/contributions/projector.py` — fix initial `CLAIMED_SELF -> TASK_READY` and project `TASK_CLOSED` without erasing PR/review work.
- `app/contributions/__init__.py` — export only stable public contribution intake types after their tasks are green.
- `.gitignore` — explicitly ignore `state/contributions.local.sqlite3` and SQLite sidecars.
- `.github/workflows/tests.yml` — add `state/contributions.local.sqlite3*` to the explicit private/generated-file guard.

### New runtime files

- `app/contributions/observations.py` — selection, snapshot, observation, preview, import, receipt/result models and canonical hashes.
- `app/contributions/repository.py` — immutable entries, append-only events, receipts, ordering validation, and atomic entry/event + receipt transactions.
- `app/contributions/github_provider.py` — URL parsing plus GET-only GitHub REST adapter using `httpx` and strict snapshot normalization.
- `app/contributions/normalizer.py` — deterministic issue/PR public-fact selection and mapping to entry/event candidates.
- `app/contributions/bridge.py` — preview/import orchestration, state hashes, stale-preview protection, idempotency, and receipts.
- `app/contributions/intake_cli.py` — explicit `preview` and `import` operator commands.

### New tests/fixtures/docs

- `tests/test_contribution_core_compatibility.py`
- `tests/test_contribution_observation_models.py`
- `tests/test_contribution_repository.py`
- `tests/test_contribution_github_provider.py`
- `tests/test_contribution_normalizer.py`
- `tests/test_contribution_bridge.py`
- `tests/test_contribution_intake_cli.py`
- `tests/test_contribution_intake_dogfood.py`
- `tests/test_contribution_intake_release_contract.py`
- `tests/fixtures/contributions/github_intake_v1.json`
- `docs/PUBLIC_CONTRIBUTION_INTAKE_V1.md`

`pyproject.toml` is intentionally unchanged.

---

### Task 1: Correct the contribution core for real intake

**Files:**
- Modify: `app/contributions/models.py`
- Modify: `app/contributions/projector.py`
- Test: `tests/test_contribution_core_compatibility.py`

**Interfaces:**
- Consumes: existing `PublicContributionEntry`, `ContributionEvent`, `ContributionProjector`.
- Produces: `ContributionEventKind` containing `TASK_CLOSED`; projector semantics required by all later intake tasks.

- [ ] **Step 1: Write failing compatibility tests**

Create `tests/test_contribution_core_compatibility.py` with fixed aware datetimes and helpers. Freeze these exact behaviors:

```python
from datetime import datetime, timezone

from app.contributions.models import ContributionEvent, PublicContributionEntry
from app.contributions.projector import ContributionProjector

NOW = datetime(2026, 9, 4, 6, 30, tzinfo=timezone.utc)
TASK = "https://github.com/WesleyHanauer/moracarta/issues/25"


def claimed_self_entry() -> PublicContributionEntry:
    return PublicContributionEntry(
        entry_id="contrib-moracarta-25",
        repository_full_name="WesleyHanauer/moracarta",
        repository_url="https://github.com/WesleyHanauer/moracarta",
        origin="PUBLIC_ISSUE",
        need_basis="OBSERVED",
        need_statement="tests: setup command",
        evidence_refs=[TASK],
        task_ref=TASK,
        bounded_task="tests: setup command",
        task_claim_state="CLAIMED_SELF",
        expected_effort="UNKNOWN",
        risk_level="UNKNOWN",
        discovered_at=NOW,
    )


def test_claimed_self_entry_initializes_task_ready():
    context = ContributionProjector().project(entry=claimed_self_entry(), events=[])
    assert context.stage == "TASK_READY"
    assert context.task_claim_state == "CLAIMED_SELF"


def test_task_closed_closes_task_ready_entry():
    event = ContributionEvent(
        event_id="event-close-task",
        entry_id="contrib-moracarta-25",
        kind="TASK_CLOSED",
        source_type="PUBLIC_GITHUB",
        source_ref=TASK,
        observed_at=NOW,
        task_ref=TASK,
    )
    context = ContributionProjector().project(entry=claimed_self_entry(), events=[event])
    assert context.stage == "CLOSED"
    assert context.task_claim_state == "CLOSED"


def test_task_closed_does_not_erase_open_pr_review_stage():
    pr = "https://github.com/WesleyHanauer/moracarta/pull/42"
    events = [
        ContributionEvent(
            event_id="event-pr-open",
            entry_id="contrib-moracarta-25",
            kind="PR_OPENED",
            source_type="PUBLIC_GITHUB",
            source_ref=pr,
            observed_at=NOW,
            work_ref=pr,
        ),
        ContributionEvent(
            event_id="event-task-close",
            entry_id="contrib-moracarta-25",
            kind="TASK_CLOSED",
            source_type="PUBLIC_GITHUB",
            source_ref=TASK,
            observed_at=NOW.replace(second=1),
            task_ref=TASK,
        ),
    ]
    context = ContributionProjector().project(entry=claimed_self_entry(), events=events)
    assert context.stage == "IN_REVIEW"
    assert context.task_claim_state == "CLOSED"
    assert context.active_work_ref == pr
```

Also assert `TASK_CLOSED` without `task_ref` raises Pydantic validation and that `TASK_RELEASED` after `TASK_CLOSED` restores `TASK_READY` + `AVAILABLE`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
python -m pytest tests/test_contribution_core_compatibility.py -v
```

Expected RED reasons:
- `CLAIMED_SELF` currently projects as `DISCOVERED`.
- `TASK_CLOSED` is rejected because it is not yet a valid `ContributionEventKind`.

- [ ] **Step 3: Implement the minimal core corrections**

In `models.py`:

```python
ContributionEventKind = Literal[
    # existing kinds preserved in existing order,
    "TASK_CLOSED",
]
```

Add `"TASK_CLOSED"` to `_TASK_EVENTS_REQUIRING_REF`.

In `projector.py`, initialize:

```python
stage = (
    "TASK_READY"
    if entry.task_claim_state in {"AVAILABLE", "CLAIMED_SELF"}
    else "DISCOVERED"
)
```

Add projection logic:

```python
elif kind == "TASK_CLOSED":
    task_claim_state = "CLOSED"
    if stage in {"DISCOVERED", "CONTACTED", "ENGAGED", "TASK_READY", "PAUSED"}:
        stage = "CLOSED"
```

Do not alter stage for `IN_PROGRESS`, `IN_REVIEW`, `COMPLETED`, `CLOSED`, or `DISCARDED`.

- [ ] **Step 4: Run compatibility and existing contribution suites**

Run:

```bash
python -m pytest \
  tests/test_contribution_core_compatibility.py \
  tests/test_contribution_models.py \
  tests/test_contribution_projection.py \
  tests/test_contribution_dogfood.py \
  tests/test_proof_of_work.py \
  tests/test_contribution_release_contract.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/contributions/models.py app/contributions/projector.py tests/test_contribution_core_compatibility.py
git commit -m "fix: align contribution task lifecycle with intake"
```

---

### Task 2: Define strict selection, snapshot, observation, preview, and import contracts

**Files:**
- Create: `app/contributions/observations.py`
- Modify: `app/contributions/__init__.py`
- Test: `tests/test_contribution_observation_models.py`

**Interfaces:**
- Produces:
  - `GitHubContributionSelection`
  - `GitHubIssueSnapshot`
  - `GitHubReviewSnapshot`
  - `GitHubCheckSnapshot`
  - `GitHubPullRequestSnapshot`
  - `ContributionObservation`
  - `ContributionPreview`
  - `ContributionImportRequest`
  - `ContributionImportReceipt`
  - `ContributionImportResult`
  - `canonical_sha256()` and `observation_sha256()`
- Later tasks must import these exact names rather than duplicate contracts.

- [ ] **Step 1: Write strict-model RED tests**

Create tests that assert:

```python
with pytest.raises(ValidationError):
    GitHubContributionSelection(
        resource_kind="ISSUE",
        repository_full_name="owner/repo",
        number=1,
        source_url="https://github.com/owner/repo/issues/1",
        operator_github_login="juan",
        unexpected="forbidden",
    )
```

Freeze naive datetime rejection for every snapshot/observation/import timestamp. Freeze `external_actions=[]` as the only valid preview value. Freeze that `ContributionObservation(kind="ISSUE_AVAILABLE", ...)` requires `task_ref` and `public_title`, PR/review kinds require `work_ref`, and `EXTERNAL_BLOCKER` requires `reason_code="EXTERNAL_AUTHORIZATION_REQUIRED"`.

Add a serialization privacy test:

```python
payload = ContributionPreview(...).model_dump_json()
for forbidden in ["token", "authorization", "raw_body", "review_text", "check_log", "salary", "employment_interest"]:
    assert forbidden not in payload.lower()
```

- [ ] **Step 2: Run observation-model tests and verify RED**

```bash
python -m pytest tests/test_contribution_observation_models.py -v
```

Expected: import failure because `app.contributions.observations` does not exist.

- [ ] **Step 3: Implement exact strict contracts**

Use `ConfigDict(extra="forbid")` and a shared `_aware_utc()` helper. Define these literals:

```python
GitHubResourceKind = Literal["ISSUE", "PULL_REQUEST"]
GitHubIssueState = Literal["OPEN", "CLOSED"]
GitHubPullRequestState = Literal["OPEN", "CLOSED"]
GitHubReviewState = Literal["APPROVED", "COMMENTED", "CHANGES_REQUESTED", "DISMISSED"]
ContributionObservationKind = Literal[
    "ISSUE_AVAILABLE", "ISSUE_CLAIMED_SELF", "ISSUE_CLAIMED_OTHER", "ISSUE_CLOSED",
    "PR_OPENED", "REVIEW_RECEIVED", "CHANGES_REQUESTED", "PR_MERGED", "PR_CLOSED",
    "EXTERNAL_BLOCKER", "BLOCKER_CLEARED",
]
ContributionPreviewStatus = Literal["IMPORTABLE", "NO_CHANGE", "ALREADY_IMPORTED", "BLOCKED"]
ContributionImportStatus = Literal[
    "IMPORTED", "ALREADY_IMPORTED", "BLOCKED_STALE_PREVIEW", "BLOCKED_DOMAIN", "CONFLICT"
]
```

Use exact model shapes from the spec. Add `PREVIEW_VERSION = "contribution-preview-v1"` and canonical JSON hashing:

```python
def canonical_sha256(value: BaseModel | dict[str, object]) -> str:
    payload = value.model_dump(mode="json", exclude_none=False) if isinstance(value, BaseModel) else value
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def observation_sha256(observation: ContributionObservation) -> str:
    return canonical_sha256(observation)
```

`ContributionPreview` contains the complete typed `observation`, optional `proposed_entry`, optional `candidate_event`, optional `context_before/context_after`, and validator-enforced empty `external_actions`.

`ContributionImportRequest` contains the complete preview plus `confirmed_by` and `confirmed_at`; reject confirmations earlier than `preview.observation.captured_at`.

`ContributionImportResult` mirrors the Operator Bridge result discipline: successful statuses require a receipt; blocked/conflict statuses cannot contain one.

- [ ] **Step 4: Run strict-model tests GREEN**

```bash
python -m pytest tests/test_contribution_observation_models.py -v
```

- [ ] **Step 5: Export stable contract types and commit**

Add the intake contracts to `app/contributions/__init__.py` only after tests pass.

```bash
git add app/contributions/observations.py app/contributions/__init__.py tests/test_contribution_observation_models.py
git commit -m "feat: add contribution observation contracts"
```

---

### Task 3: Add immutable, append-only SQLite contribution persistence

**Files:**
- Create: `app/contributions/repository.py`
- Test: `tests/test_contribution_repository.py`
- Modify: `.gitignore`
- Modify: `.github/workflows/tests.yml`

**Interfaces:**
- Produces `SQLiteContributionRepository` with:

```python
initialize() -> None
get_entry(entry_id: str) -> PublicContributionEntry | None
list_events(entry_id: str) -> list[ContributionEvent]
get_event(event_id: str) -> ContributionEvent | None
get_receipt_for_observation(observation_id: str) -> ContributionImportReceipt | None
insert_entry_with_receipt(entry: PublicContributionEntry, receipt: ContributionImportReceipt) -> tuple[PublicContributionEntry, ContributionImportReceipt, bool]
append_event_with_receipt(event: ContributionEvent, receipt: ContributionImportReceipt, projector: ContributionProjector) -> tuple[ContributionEvent, ContributionImportReceipt, bool]
```

- [ ] **Step 1: Write repository RED tests**

Cover all of these separately:

1. `get_entry`, `list_events`, and `get_receipt_for_observation` on a missing DB return `None`/`[]` without creating the DB file or parent directory.
2. `initialize()` creates exactly `contribution_entries`, `contribution_events`, and `contribution_import_receipts`.
3. identical entry replay is idempotent; same `entry_id` with changed payload raises `ValueError("contribution entry_id conflict")`.
4. events are returned in `(observed_at, event_id)` order.
5. out-of-order append is rejected.
6. same event id + different payload conflicts.
7. same observation id + different receipt hash conflicts.
8. entry + receipt is atomic: pre-create a conflicting receipt, call `insert_entry_with_receipt`, assert the entry was not inserted.
9. event + receipt is atomic: pre-create a conflicting receipt, call `append_event_with_receipt`, assert the event was not inserted.
10. complete sequence is run through `ContributionProjector` before event commit.

- [ ] **Step 2: Run repository tests and verify RED**

```bash
python -m pytest tests/test_contribution_repository.py -v
```

Expected: module import failure.

- [ ] **Step 3: Implement SQLite schema and side-effect-free reads**

Schema:

```sql
CREATE TABLE contribution_entries (
    entry_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    discovered_at TEXT NOT NULL
);

CREATE TABLE contribution_events (
    event_id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    observed_at TEXT NOT NULL
);

CREATE INDEX idx_contribution_events_entry
ON contribution_events(entry_id, observed_at, event_id);

CREATE TABLE contribution_import_receipts (
    receipt_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL UNIQUE,
    entry_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    processed_at TEXT NOT NULL
);
```

Every read method begins with `if not self.path.exists(): ...` before opening SQLite. `initialize()` is the only method allowed to create parent directories for a fresh path.

For event insertion, load the immutable entry + full existing event list, append the candidate in memory, run `projector.project(entry=entry, events=events + [event])`, then insert event and receipt in one transaction.

- [ ] **Step 4: Run repository tests GREEN**

```bash
python -m pytest tests/test_contribution_repository.py -v
```

- [ ] **Step 5: Lock private-file handling**

Add explicit ignore lines:

```text
state/contributions.local.sqlite3
state/contributions.local.sqlite3-*
```

Add this glob inside the workflow's existing forbidden list:

```text
'state/contributions.local.sqlite3*'
```

Do not alter any other CI command.

- [ ] **Step 6: Re-run repository tests and workflow syntax-adjacent checks**

```bash
python -m pytest tests/test_contribution_repository.py -v
python -m compileall app/contributions
git diff --check
```

- [ ] **Step 7: Commit**

```bash
git add app/contributions/repository.py tests/test_contribution_repository.py .gitignore .github/workflows/tests.yml
git commit -m "feat: persist contribution intake locally"
```

---

### Task 4: Implement the explicit GET-only GitHub provider

**Files:**
- Create: `app/contributions/github_provider.py`
- Test: `tests/test_contribution_github_provider.py`

**Interfaces:**
- Produces:

```python
class GitHubContributionProvider(Protocol):
    def fetch(
        self,
        selection: GitHubContributionSelection,
        *,
        captured_at: datetime,
    ) -> GitHubIssueSnapshot | GitHubPullRequestSnapshot: ...

class GitHubPublicContributionProvider:
    def __init__(self, client: httpx.Client, *, token: str | None = None) -> None: ...
    def fetch(...): ...


def selection_from_github_url(
    url: str,
    *,
    operator_github_login: str,
    entry_id: str | None = None,
) -> GitHubContributionSelection: ...
```

- [ ] **Step 1: Write provider RED tests with `httpx.MockTransport`**

Create a request recorder that asserts `request.method == "GET"` for every call. Test:

- issue URL parsing for `https://github.com/trixocom/odoo-argentina-trx-ce/issues/1`;
- PR URL parsing for `https://github.com/WesleyHanauer/moracarta/pull/42`;
- malformed/non-GitHub URLs fail closed;
- explicit token becomes only `Authorization: Bearer ...` on outbound requests and never appears in returned snapshot JSON or raised error strings;
- issue fetch ignores body text and retains only allowlisted fields;
- PR fetch performs only these bounded GET families: PR metadata, PR reviews, check runs for the selected head SHA, combined commit status for the same SHA;
- review body text/check output text is absent from snapshots;
- generic `failure` maps to no blocker description code;
- `ACTION_REQUIRED` maps to `description_code="EXTERNAL_AUTHORIZATION_REQUIRED"`;
- allowlisted descriptions such as `team authorization required` map to that same bounded code.

- [ ] **Step 2: Run provider tests RED**

```bash
python -m pytest tests/test_contribution_github_provider.py -v
```

- [ ] **Step 3: Implement URL parsing and GET-only provider**

Use `urllib.parse.urlparse` only for URL parsing and existing `httpx` for HTTP. The provider contains no method named `post`, `put`, `patch`, `delete`, `assign`, `comment`, `review`, or `merge`.

For issues call:

```text
GET /repos/{owner}/{repo}/issues/{number}
```

Reject payloads containing `pull_request` when selection kind is `ISSUE`.

For PRs call:

```text
GET /repos/{owner}/{repo}/pulls/{number}
GET /repos/{owner}/{repo}/pulls/{number}/reviews
GET /repos/{owner}/{repo}/commits/{head_sha}/check-runs
GET /repos/{owner}/{repo}/commits/{head_sha}/status
```

Normalize raw states to uppercase literals. Convert every timestamp through one aware-UTC parser. Convert external-gate evidence to bounded `description_code`; do not store raw descriptions.

- [ ] **Step 4: Run provider tests GREEN and prove method authority**

```bash
python -m pytest tests/test_contribution_github_provider.py -v
python - <<'PY'
from app.contributions.github_provider import GitHubPublicContributionProvider
for name in ["post", "put", "patch", "delete", "assign", "comment", "merge"]:
    assert not hasattr(GitHubPublicContributionProvider, name), name
PY
```

- [ ] **Step 5: Commit**

```bash
git add app/contributions/github_provider.py tests/test_contribution_github_provider.py
git commit -m "feat: add read-only GitHub contribution provider"
```

---

### Task 5: Normalize public GitHub facts into zero/one contribution transition

**Files:**
- Create: `app/contributions/normalizer.py`
- Test: `tests/test_contribution_normalizer.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class ContributionNormalization:
    observation: ContributionObservation
    status: Literal["IMPORTABLE", "NO_CHANGE", "BLOCKED"]
    proposed_entry: PublicContributionEntry | None = None
    candidate_event: ContributionEvent | None = None
    errors: tuple[str, ...] = ()


def deterministic_issue_entry_id(repository_full_name: str, issue_number: int) -> str: ...

def normalize_snapshot(
    *,
    selection: GitHubContributionSelection,
    snapshot: GitHubIssueSnapshot | GitHubPullRequestSnapshot,
    entry: PublicContributionEntry | None,
    events: list[ContributionEvent],
    projector: ContributionProjector,
) -> ContributionNormalization: ...

def normalize_embedded_observation(
    *,
    observation: ContributionObservation,
    entry: PublicContributionEntry | None,
    events: list[ContributionEvent],
    projector: ContributionProjector,
) -> ContributionNormalization: ...
```

`normalize_embedded_observation` is the no-network import revalidation seam.

- [ ] **Step 1: Write issue-normalization RED tests**

Freeze:

- open/unassigned new issue -> deterministic `PublicContributionEntry(task_claim_state="AVAILABLE")`, `candidate_event is None`;
- open/self-assigned new issue, case-insensitive login -> `CLAIMED_SELF`, projected `TASK_READY`;
- open/other-assigned new issue -> `CLAIMED_OTHER`, projected `DISCOVERED`;
- closed issue without existing entry -> `BLOCKED`, `closed_issue_requires_existing_entry`;
- existing repository mismatch -> `BLOCKED`, `repository_mismatch`;
- existing wrong/missing `task_ref` -> `BLOCKED`, `task_ref_mismatch`;
- unchanged claim state -> `NO_CHANGE` even if `updated_at` changed;
- `CLAIMED_OTHER -> unassigned` -> `TASK_RELEASED`;
- open -> closed -> `TASK_CLOSED`;
- `TASK_CLOSED` + reopened/unassigned -> `TASK_RELEASED`.

- [ ] **Step 2: Write PR chronology and blocker RED tests**

Freeze:

- PR selection without entry id -> blocked `pr_requires_entry_id`;
- selected upstream repository mismatch -> blocked `repository_mismatch`;
- text like `Closes #25` is never read by the normalizer and cannot create lineage;
- missing local `PR_OPENED` always selects `PR_OPENED` first even if reviews/merge already exist;
- after PR open, unseen facts sort by `(fact_at, kind_order, source_fact_identity)`;
- equal timestamp order is exactly `CHANGES_REQUESTED`, `REVIEW_RECEIVED`, `EXTERNAL_BLOCKER`, `BLOCKER_CLEARED`, `PR_MERGED`, `PR_CLOSED`;
- an older review is selected before a later merge;
- `DISMISSED` review is ignored;
- generic failed checks do not create blockers;
- explicit external authorization evidence creates `ContributionEvent(kind="BLOCKED", reason="EXTERNAL_AUTHORIZATION_REQUIRED")`;
- a later success for the same blocked `source_ref` can produce `UNBLOCKED` only when a blocker is active;
- one normalization result contains at most one candidate event;
- event ids are deterministic hashes of observation identity and are stable across repeated runs.

- [ ] **Step 3: Run normalizer tests RED**

```bash
python -m pytest tests/test_contribution_normalizer.py -v
```

- [ ] **Step 4: Implement deterministic identity and issue intake**

Entry identity:

```python
identity = f"PUBLIC_GITHUB|{repository_full_name}|ISSUE|{issue_number}"
entry_id = f"contrib-{hashlib.sha256(identity.encode()).hexdigest()}"
```

Issue observation identity includes canonical state, sorted normalized assignee logins, and public `updated_at`; closure identity uses `closed_at`.

Sanitize public title to normalized whitespace, strip control characters, and cap to the existing contribution field maximum (500 characters). Never inspect issue body.

- [ ] **Step 5: Implement chronological PR fact selection**

Always synthesize the real `PR_OPENED` public fact from `created_at`; represent review facts by `review_ref`; merge/close facts by public terminal timestamp; blocker facts by check/status `check_ref`.

Use this exact equal-time order mapping:

```python
_KIND_ORDER = {
    "CHANGES_REQUESTED": 0,
    "REVIEW_RECEIVED": 1,
    "EXTERNAL_BLOCKER": 2,
    "BLOCKER_CLEARED": 3,
    "PR_MERGED": 4,
    "PR_CLOSED": 5,
}
```

Before returning an event, run the full candidate sequence through `ContributionProjector`. Invalid facts are skipped only when another later admissible fact can be valid; if the selected source fact itself violates lineage/core semantics, return `BLOCKED` with `invalid_contribution_transition`.

- [ ] **Step 6: Run normalizer tests GREEN plus core suites**

```bash
python -m pytest \
  tests/test_contribution_normalizer.py \
  tests/test_contribution_core_compatibility.py \
  tests/test_contribution_projection.py -v
```

- [ ] **Step 7: Commit**

```bash
git add app/contributions/normalizer.py tests/test_contribution_normalizer.py
git commit -m "feat: normalize GitHub contribution facts"
```

---

### Task 6: Add hash-bound preview/import bridge with stale-state protection

**Files:**
- Create: `app/contributions/bridge.py`
- Test: `tests/test_contribution_bridge.py`

**Interfaces:**
- Produces:

```python
class ContributionObservationBridge:
    def __init__(
        self,
        *,
        provider: GitHubContributionProvider,
        repository: SQLiteContributionRepository,
        projector: ContributionProjector,
        clock: Callable[[], datetime],
    ) -> None: ...

    def preview(self, selection: GitHubContributionSelection) -> ContributionPreview: ...

    def import_preview(self, request: ContributionImportRequest) -> ContributionImportResult: ...
```

- [ ] **Step 1: Write preview RED tests**

Use a fake provider with a call counter and deterministic snapshots. Assert:

1. `preview()` calls provider once and mutates no DB state.
2. proposed new entry yields `IMPORTABLE`, candidate event `None`, correct `context_after`.
3. existing transition yields one candidate event and projected before/after contexts.
4. unchanged state yields `NO_CHANGE`.
5. exact observation with an existing receipt yields `ALREADY_IMPORTED`.
6. same typed observation + same entry/event history produces identical `preview_sha256`.
7. preview hash changes when local event history changes.
8. `external_actions` is always empty.

State hash must canonicalize:

```text
existing entry payload or null
ordered full event payload list
```

Preview hash binds exactly the spec fields: preview version, observation hash, proposed/existing entry, candidate event, event-history hash, context before, context after.

- [ ] **Step 2: Write import RED tests**

Assert:

- only `IMPORTABLE` previews may import;
- provider call count does not change during `import_preview()`;
- new entry + receipt commits atomically;
- event + receipt commits atomically;
- exact second import returns `ALREADY_IMPORTED` with receipt;
- changed local state after preview returns `BLOCKED_STALE_PREVIEW` and writes nothing;
- same observation id with different hash returns `CONFLICT`;
- domain/lineage revalidation failure returns `BLOCKED_DOMAIN`;
- `processed_at` comes from injected clock and is aware UTC;
- receipt id is deterministic from observation identity, e.g. `contrib-receipt-<sha256(observation_id)>`.

- [ ] **Step 3: Run bridge tests RED**

```bash
python -m pytest tests/test_contribution_bridge.py -v
```

- [ ] **Step 4: Implement preview hash and preview orchestration**

Provider snapshot is normalized once. Load current entry/events. Call `normalize_snapshot`. If a proposed entry exists, project it with zero events for `context_after`; if a candidate event exists, project current events and current+candidate for before/after.

Before checking exact prior receipt, compute the deterministic observation hash. If a receipt for the same `observation_id` exists with a different observation hash, return `BLOCKED` + `observation_identity_conflict`; if identical, return `ALREADY_IMPORTED`.

- [ ] **Step 5: Implement no-network import revalidation**

`import_preview()` must not reference `self.provider` at all. Re-load current local entry/events, call `normalize_embedded_observation()` using `request.preview.observation`, rebuild the canonical preview hash against current state, and compare with `request.preview.preview_sha256`.

If hashes differ:

```python
return ContributionImportResult(
    status="BLOCKED_STALE_PREVIEW",
    errors=["stale_preview"],
)
```

If identical, build receipt and call exactly one repository atomic transaction.

- [ ] **Step 6: Run bridge tests GREEN and explicit no-network proof**

```bash
python -m pytest tests/test_contribution_bridge.py -v
```

The test fake provider's `fetch()` should raise `AssertionError("provider called during import")` after preview; import must still PASS.

- [ ] **Step 7: Commit**

```bash
git add app/contributions/bridge.py tests/test_contribution_bridge.py
git commit -m "feat: add confirmed contribution observation bridge"
```

---

### Task 7: Add CLI, sanitized dogfood, public boundary docs, and release gates

**Files:**
- Create: `app/contributions/intake_cli.py`
- Create: `tests/test_contribution_intake_cli.py`
- Create: `tests/test_contribution_intake_dogfood.py`
- Create: `tests/test_contribution_intake_release_contract.py`
- Create: `tests/fixtures/contributions/github_intake_v1.json`
- Create: `docs/PUBLIC_CONTRIBUTION_INTAKE_V1.md`
- Modify: `app/contributions/__init__.py`

**Interfaces:**
- Produces operator commands exactly matching the spec:

```text
python -m app.contributions.intake_cli preview --url ... --operator-login ... [--entry-id ...] [--db ...] --out ...
python -m app.contributions.intake_cli import --preview-file ... --confirmed-by ... [--db ...]
```

- [ ] **Step 1: Write CLI RED tests**

Monkeypatch provider construction so tests never require live GitHub. Freeze:

- `preview` parses the GitHub URL, initializes the explicitly selected DB when needed, calls bridge preview, writes exact `ContributionPreview.model_dump_json(indent=2)` to `--out`, and prints a compact summary containing only repository/resource/entry/status identifiers;
- `preview` never imports;
- `import` reads exact preview JSON, builds `ContributionImportRequest`, performs zero provider/network calls, and prints `ContributionImportReceipt` JSON;
- `import` refuses `NO_CHANGE`, `ALREADY_IMPORTED`, and `BLOCKED` preview files;
- neither command auto-confirms or accepts a hidden confirmation default.

Use `argparse` subparsers and a `main(argv: list[str] | None = None) -> int` entrypoint so tests invoke it directly.

- [ ] **Step 2: Create five sanitized public fixture cases and dogfood RED tests**

`tests/fixtures/contributions/github_intake_v1.json` contains only allowlisted typed snapshot fields for:

1. Trixo `trixocom/odoo-argentina-trx-ce#1`: open + unassigned -> new entry `AVAILABLE` -> `TASK_READY`.
2. Moracarta `WesleyHanauer/moracarta#25`: open + assigned to `juanmanueltorres-creator` -> `CLAIMED_SELF` -> `TASK_READY`.
3. One public claimed-other issue: open + different assignee -> `CLAIMED_OTHER` -> `DISCOVERED`.
4. Moracarta PR #42: explicit existing entry -> first candidate `PR_OPENED` -> `IN_REVIEW`.
5. SUNAT PR #115: explicit existing entry + sanitized explicit authorization gate -> first `PR_OPENED`; later chronological preview `BLOCKED(reason="EXTERNAL_AUTHORIZATION_REQUIRED")` while stage stays `IN_REVIEW`.

Fixture privacy test rejects keys/substrings:

```python
for forbidden in ["email", "token", "authorization_header", "body", "review_body", "check_log", "private_message", "employment_interest"]:
    assert forbidden not in json.dumps(payload).lower()
```

Use `authorization_gate_code` rather than raw gate text in persisted fixture snapshots where possible.

- [ ] **Step 3: Write release-contract RED tests**

Freeze boundaries:

```python
def test_contribution_intake_does_not_register_fastapi_routes():
    from app.main import app
    before = set(app.openapi()["paths"])
    import app.contributions.bridge  # noqa: F401
    import app.contributions.intake_cli  # noqa: F401
    app.openapi_schema = None
    after = set(app.openapi()["paths"])
    assert after == before
```

Also assert:

- no contribution intake module imports `app.relationships`, `app.operator_bridge`, `app.outreach`, `app.process_email`, or `app.cv`;
- no observation/receipt model field name contains `employment`, `salary`, `hiring`, or `contact_permission`;
- provider public surface exposes no mutating method names;
- `pyproject.toml` has no dependency diff for this feature;
- private guard includes `state/contributions.local.sqlite3*`.

- [ ] **Step 4: Run CLI/dogfood/release tests RED**

```bash
python -m pytest \
  tests/test_contribution_intake_cli.py \
  tests/test_contribution_intake_dogfood.py \
  tests/test_contribution_intake_release_contract.py -v
```

- [ ] **Step 5: Implement thin CLI**

`preview`:

```python
selection = selection_from_github_url(
    args.url,
    operator_github_login=args.operator_login,
    entry_id=args.entry_id,
)
repository = SQLiteContributionRepository(args.db)
repository.initialize()
preview = bridge.preview(selection)
Path(args.out).write_text(preview.model_dump_json(indent=2), encoding="utf-8")
```

`import`:

```python
preview = ContributionPreview.model_validate_json(Path(args.preview_file).read_text(encoding="utf-8"))
request = ContributionImportRequest(
    preview=preview,
    confirmed_by=args.confirmed_by,
    confirmed_at=clock(),
)
result = bridge.import_preview(request)
```

Construct import bridge with a provider object that is never invoked by `import_preview`; tests must prove zero network calls. Return nonzero exit code for blocked/conflict results.

- [ ] **Step 6: Add public boundary document**

Create `docs/PUBLIC_CONTRIBUTION_INTAKE_V1.md` containing these exact statements:

```text
GitHub reads are explicit and read-only.
Preview is local and non-mutating.
Import mutates only local contribution state after confirmation.
No GitHub write authority is added.
Contribution outcomes do not imply employment interest.
V1 is explicit-resource intake, not discovery/radar.
```

Document the two CLI commands and the private SQLite path. Do not claim background monitoring, search, Gmail classification, automatic proof-of-work promotion, or GitHub mutation.

- [ ] **Step 7: Run all contribution-focused tests**

```bash
python -m pytest \
  tests/test_contribution_models.py \
  tests/test_contribution_projection.py \
  tests/test_contribution_dogfood.py \
  tests/test_proof_of_work.py \
  tests/test_contribution_release_contract.py \
  tests/test_contribution_core_compatibility.py \
  tests/test_contribution_observation_models.py \
  tests/test_contribution_repository.py \
  tests/test_contribution_github_provider.py \
  tests/test_contribution_normalizer.py \
  tests/test_contribution_bridge.py \
  tests/test_contribution_intake_cli.py \
  tests/test_contribution_intake_dogfood.py \
  tests/test_contribution_intake_release_contract.py -v
```

Expected: 0 failures.

- [ ] **Step 8: Run the full repository release gate**

```bash
python -m pytest -v
python -m compileall app
git diff --check origin/main...HEAD
```

Run the exact private-file guard logic from `.github/workflows/tests.yml`, now including `state/contributions.local.sqlite3*`, then:

```bash
python scripts/render_recruiter_previews.py
```

Push the implementation branch and require GitHub Actions success for:

```text
pytest
build-offline-runtime (Python 3.12)
build-offline-runtime (Python 3.13)
verify-offline-runtime (Python 3.12)
verify-offline-runtime (Python 3.13)
```

Do not mark the implementation PR ready if any gate is pending or failing.

- [ ] **Step 9: Verify changed-file scope**

The implementation diff may contain only:

```text
app/contributions/**
tests/test_contribution_*.py
tests/fixtures/contributions/**
docs/PUBLIC_CONTRIBUTION_INTAKE_V1.md
docs/superpowers/specs/2026-09-04-contribution-observation-bridge-v1-design.md
docs/superpowers/plans/2026-09-04-contribution-observation-bridge-v1.md
.gitignore
.github/workflows/tests.yml
```

Explicitly fail review if `app/main.py`, relationships, Operator Bridge, Outreach, Process Email, CV, opportunity models, or `pyproject.toml` changed.

- [ ] **Step 10: Commit final slice**

```bash
git add \
  app/contributions/intake_cli.py \
  app/contributions/__init__.py \
  tests/test_contribution_intake_cli.py \
  tests/test_contribution_intake_dogfood.py \
  tests/test_contribution_intake_release_contract.py \
  tests/fixtures/contributions/github_intake_v1.json \
  docs/PUBLIC_CONTRIBUTION_INTAKE_V1.md
git commit -m "feat: expose confirmed contribution intake cli"
```

---

## Implementation PR Contract

Open the implementation PR as draft with title:

```text
feat: add Contribution Observation Bridge V1
```

The PR body must state:

- explicit public GitHub issue/PR intake only;
- GET-only provider authority;
- preview-before-import human boundary;
- local SQLite mutation only;
- one candidate event per preview;
- exact repository + task lineage rules;
- chronology-before-terminal-state rule;
- evidence-aware external blocker rule;
- no GitHub writes, search/radar, Gmail classifier, Relationship mutation, CV/outreach changes, HTTP routes, or hiring inference;
- full CI evidence from the exact head SHA.

Keep the PR draft until all release gates above are green. Request code review before merge. Do not merge to `main` without explicit operator approval.

## Self-Review Checklist

Before executing this plan, verify these mappings against the approved spec:

- Sections 5.1–5.2 -> Task 1 core compatibility tests and implementation.
- Sections 6, 8–10, 15–18 -> Task 2 typed contracts and hashes.
- Section 19 -> Task 3 SQLite repository and private-file guard.
- Sections 6–8 and 14 -> Task 4 GET-only provider and sanitized external-gate evidence.
- Sections 11–14 -> Task 5 new issue intake, exact lineage, PR chronology, review mapping, blockers.
- Sections 15–20 -> Task 6 preview/import, hash binding, stale-state protection, idempotent receipts.
- Sections 21–24 -> Task 7 CLI, five dogfood fixtures, public docs, release contract, full CI.
- Section 25 remains deferred; no implementation task covers radar, Gmail contribution classification, proof-of-work promotion, or background polling.

No task authorizes a GitHub mutation or hiring inference. No implementation step requires a new dependency. No placeholder implementation is permitted.