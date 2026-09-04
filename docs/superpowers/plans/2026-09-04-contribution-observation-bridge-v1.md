# Contribution Intake / Observation Bridge V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn one explicitly selected public GitHub issue or pull request into a strict, hash-bound contribution preview and, only after human confirmation, append the corresponding local contribution entry/event to SQLite without adding GitHub write authority or hiring inference.

**Architecture:** Keep contribution intake as a sibling of the relationship-oriented Operator Bridge. A GET-only `GitHubPublicContributionProvider` produces allowlisted transient snapshots; a deterministic normalizer selects one public fact and proposes either one immutable `PublicContributionEntry` or zero/one `ContributionEvent`; `ContributionObservationBridge` binds that proposal to current local state with a preview hash. Import revalidates the embedded typed preview against SQLite and never re-fetches GitHub. `ContributionContext` remains a pure projection.

**Tech Stack:** Python 3.12+, Pydantic v2, stdlib `sqlite3`, existing `httpx`, stdlib `argparse`, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-04-contribution-observation-bridge-v1-design.md`

## Global Constraints

- Preserve `OBSERVE != CLAIM`, `OBSERVE != COMMENT`, `OBSERVE != OPEN_PR`, and `IMPORT != EXTERNAL_ACTION`.
- Preserve `PUBLIC_CONTRIBUTION_ENTRY != JOB_OPENING`, `PR_OPENED != EMPLOYMENT_INTEREST`, and `PR_MERGED != EMPLOYMENT_INTEREST`.
- Support exactly one explicitly selected public GitHub issue or pull request per preview; no search/radar/discovery endpoints.
- GitHub provider authority is GET-only. No POST, PUT, PATCH, DELETE, assignment, comment, review submission, PR mutation, merge, or repository mutation code belongs in V1.
- Do not add HTTP API routes. Do not modify `app/main.py`, `app/operator_bridge`, `app/relationships`, `app/outreach`, `app/process_email`, `app/cv`, or opportunity models.
- Do not add project dependencies; `httpx` already exists in `pyproject.toml`.
- Raw GitHub issue/PR bodies, review text, check logs, auth headers, and tokens remain transient and are never persisted or serialized into domain models.
- All typed timestamps are timezone-aware and normalized to UTC. Tests inject explicit wall-clock values; no domain hash or event identity depends on hidden `datetime.now()` calls.
- One preview proposes at most one new entry or one candidate event.
- PR lineage always requires an explicit existing contribution entry. PR body text such as `Closes #25` is ignored for lineage.
- Existing issue lineage requires exact repository identity and exact `task_ref` equality.
- Generic CI failure is not an external blocker. Only `ACTION_REQUIRED` or allowlisted explicit authorization/access evidence can create `BLOCKED`.
- Preview is read-only and must not initialize or mutate SQLite. Import requires the exact serialized `IMPORTABLE` preview the operator reviewed.
- Import performs no GitHub call. It revalidates the embedded typed observation/proposal against current local SQLite state and rejects stale previews.
- Default local persistence path is `state/contributions.local.sqlite3`; reads against a missing DB are side-effect free; initialization is explicit and occurs only on the confirmed import path.
- `ContributionContext` is projected and never stored as independent truth.
- Contribution outcomes never mutate Relationship Memory and never imply hiring/contact permission.

---

## File Structure

### Existing files to modify

- `app/contributions/models.py` — add `TASK_CLOSED` to the core event contract.
- `app/contributions/projector.py` — fix initial `CLAIMED_SELF -> TASK_READY` and project `TASK_CLOSED` without erasing PR/review work.
- `app/contributions/__init__.py` — export stable public contribution intake contracts after their defining tasks are green.
- `.gitignore` — explicitly ignore `state/contributions.local.sqlite3` and sidecars.
- `.github/workflows/tests.yml` — add `state/contributions.local.sqlite3*` to the private/generated-file guard.

### New runtime files

- `app/contributions/observations.py` — selection, snapshot, observation, preview, import, receipt/result models and canonical hashes.
- `app/contributions/repository.py` — immutable entries, append-only events, receipts, ordering validation, atomic entry/event + receipt transactions.
- `app/contributions/github_provider.py` — GitHub URL parsing plus GET-only REST adapter using `httpx` and strict snapshot normalization.
- `app/contributions/normalizer.py` — deterministic issue/PR public-fact selection and mapping to entry/event candidates.
- `app/contributions/bridge.py` — preview/import orchestration, state hashes, stale-preview protection, idempotency, receipts.
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
- Consumes existing `PublicContributionEntry`, `ContributionEvent`, and `ContributionProjector`.
- Produces `ContributionEventKind` with `TASK_CLOSED` plus projector semantics required by all later intake tasks.

- [ ] **Step 1: Write failing compatibility tests**

Create `tests/test_contribution_core_compatibility.py` with fixed aware datetimes and these exact core cases:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contributions.models import ContributionEvent, PublicContributionEntry
from app.contributions.projector import ContributionProjector

NOW = datetime(2026, 9, 4, 6, 30, tzinfo=timezone.utc)
TASK = "https://github.com/WesleyHanauer/moracarta/issues/25"
PR = "https://github.com/WesleyHanauer/moracarta/pull/42"


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


def task_closed_event(*, observed_at: datetime) -> ContributionEvent:
    return ContributionEvent(
        event_id=f"event-task-close-{observed_at.timestamp()}",
        entry_id="contrib-moracarta-25",
        kind="TASK_CLOSED",
        source_type="PUBLIC_GITHUB",
        source_ref=TASK,
        observed_at=observed_at,
        task_ref=TASK,
    )


def test_claimed_self_entry_initializes_task_ready():
    context = ContributionProjector().project(entry=claimed_self_entry(), events=[])
    assert context.stage == "TASK_READY"
    assert context.task_claim_state == "CLAIMED_SELF"


def test_task_closed_closes_task_ready_entry():
    context = ContributionProjector().project(
        entry=claimed_self_entry(),
        events=[task_closed_event(observed_at=NOW)],
    )
    assert context.stage == "CLOSED"
    assert context.task_claim_state == "CLOSED"


def test_task_closed_does_not_erase_open_pr_review_stage():
    events = [
        ContributionEvent(
            event_id="event-pr-open",
            entry_id="contrib-moracarta-25",
            kind="PR_OPENED",
            source_type="PUBLIC_GITHUB",
            source_ref=PR,
            observed_at=NOW,
            work_ref=PR,
        ),
        task_closed_event(observed_at=NOW.replace(second=1)),
    ]
    context = ContributionProjector().project(entry=claimed_self_entry(), events=events)
    assert context.stage == "IN_REVIEW"
    assert context.task_claim_state == "CLOSED"
    assert context.active_work_ref == PR


def test_task_closed_requires_task_ref():
    with pytest.raises(ValidationError):
        ContributionEvent(
            event_id="event-invalid-close",
            entry_id="contrib-moracarta-25",
            kind="TASK_CLOSED",
            source_type="PUBLIC_GITHUB",
            source_ref=TASK,
            observed_at=NOW,
        )
```

Add one more test that projects `TASK_CLOSED` followed by `TASK_RELEASED` and asserts `stage == "TASK_READY"` and `task_claim_state == "AVAILABLE"`.

- [ ] **Step 2: Run the focused tests and verify RED**

```bash
python -m pytest tests/test_contribution_core_compatibility.py -v
```

Expected RED reasons: initial `CLAIMED_SELF` currently projects as `DISCOVERED`; `TASK_CLOSED` is not a valid core kind.

- [ ] **Step 3: Implement the minimal core corrections**

In `app/contributions/models.py`, add the exact string `"TASK_CLOSED"` to `ContributionEventKind` immediately after `"TASK_RELEASED"`, and add `"TASK_CLOSED"` to `_TASK_EVENTS_REQUIRING_REF`.

In `app/contributions/projector.py`, replace initial-stage selection with:

```python
stage = (
    "TASK_READY"
    if entry.task_claim_state in {"AVAILABLE", "CLAIMED_SELF"}
    else "DISCOVERED"
)
```

Add:

```python
elif kind == "TASK_CLOSED":
    task_claim_state = "CLOSED"
    if stage in {"DISCOVERED", "CONTACTED", "ENGAGED", "TASK_READY", "PAUSED"}:
        stage = "CLOSED"
```

Do not alter stage for `IN_PROGRESS`, `IN_REVIEW`, `COMPLETED`, `CLOSED`, or `DISCARDED`.

- [ ] **Step 4: Run compatibility plus existing contribution suites**

```bash
python -m pytest \
  tests/test_contribution_core_compatibility.py \
  tests/test_contribution_models.py \
  tests/test_contribution_projection.py \
  tests/test_contribution_dogfood.py \
  tests/test_proof_of_work.py \
  tests/test_contribution_release_contract.py -v
```

Expected: 0 failures.

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
- Produces `GitHubContributionSelection`, `GitHubIssueSnapshot`, `GitHubReviewSnapshot`, `GitHubCheckSnapshot`, `GitHubPullRequestSnapshot`, `ContributionObservation`, `ContributionPreview`, `ContributionImportRequest`, `ContributionImportReceipt`, `ContributionImportResult`, `canonical_sha256`, and `observation_sha256`.

- [ ] **Step 1: Write strict-model RED tests**

Freeze unknown-field rejection, aware-UTC requirements, kind-specific references, preview shape, confirmation time, and privacy.

Use an actual minimal observation/preview for the privacy assertion:

```python
NOW = datetime(2026, 9, 4, 6, 45, tzinfo=timezone.utc)
ISSUE = "https://github.com/trixocom/odoo-argentina-trx-ce/issues/1"

observation = ContributionObservation(
    observation_id="obs-issue-1",
    source_type="PUBLIC_GITHUB",
    source_name="github",
    source_ref=ISSUE,
    kind="ISSUE_AVAILABLE",
    entry_id=None,
    repository_full_name="trixocom/odoo-argentina-trx-ce",
    public_title="Invalid language code: es_419 en l10n_ar_edi_base",
    fact_at=NOW,
    captured_at=NOW,
    task_ref=ISSUE,
    work_ref=None,
    actor_ref=None,
    reason_code=None,
    source_fact_identity="issue:1:open:unassigned:2026-09-04T06:45:00Z",
)
preview = ContributionPreview(
    preview_version=PREVIEW_VERSION,
    status="NO_CHANGE",
    observation=observation,
    observation_sha256=observation_sha256(observation),
    preview_sha256="a" * 64,
    entry_id="contrib-example",
    source_ref=ISSUE,
    proposed_entry=None,
    candidate_event=None,
    context_before=None,
    context_after=None,
    errors=[],
    external_actions=[],
)
payload = preview.model_dump_json().lower()
for forbidden in [
    "bearer ", "github_token", "authorization_header", "raw_body",
    "review_text", "check_log", "salary", "employment_interest",
]:
    assert forbidden not in payload
```

Also test:

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

Add a selection validator test where repository/number/kind fields do not match `source_url`; it must fail closed at construction rather than create an ambiguous selection.

Freeze that issue observations require `task_ref` + `public_title`; PR/review observations require `work_ref`; `EXTERNAL_BLOCKER` requires bounded reason code `EXTERNAL_AUTHORIZATION_REQUIRED`; `external_actions` rejects any non-empty list.

- [ ] **Step 2: Run model tests and verify RED**

```bash
python -m pytest tests/test_contribution_observation_models.py -v
```

Expected: module import failure because `app.contributions.observations` does not exist.

- [ ] **Step 3: Implement exact strict contracts**

Use `ConfigDict(extra="forbid")` and shared aware-UTC normalization. Define:

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
ReceiptStatus = Literal["IMPORTED", "ALREADY_IMPORTED"]
ReasonCode = Literal["EXTERNAL_AUTHORIZATION_REQUIRED"]
PREVIEW_VERSION = "contribution-preview-v1"
```

Implement these exact field sets:

```text
GitHubContributionSelection:
resource_kind, repository_full_name, number, source_url, operator_github_login, entry_id?

GitHubIssueSnapshot:
repository_full_name, issue_number, issue_url, title, state, assignee_logins[], author_login?, created_at, updated_at, closed_at?, captured_at

GitHubReviewSnapshot:
review_ref, reviewer_login?, state, submitted_at

GitHubCheckSnapshot:
check_ref, name, state_or_conclusion, description_code?, fact_at

GitHubPullRequestSnapshot:
repository_full_name, pr_number, pr_url, state, merged, draft, author_login?, created_at, updated_at, closed_at?, merged_at?, head_sha, reviews[], checks[], captured_at

ContributionObservation:
observation_id, source_type="PUBLIC_GITHUB", source_name="github", source_ref, kind, entry_id?, repository_full_name, public_title?, fact_at, captured_at, task_ref?, work_ref?, actor_ref?, reason_code?, source_fact_identity

ContributionPreview:
preview_version, status, observation, observation_sha256, preview_sha256, entry_id, source_ref, proposed_entry?, candidate_event?, context_before?, context_after?, errors[], external_actions[]

ContributionImportRequest:
preview, confirmed_by, confirmed_at

ContributionImportReceipt:
receipt_id, observation_id, observation_sha256, preview_sha256, entry_id, contribution_event_id?, source_ref, confirmed_by, confirmed_at, processed_at, status

ContributionImportResult:
status, receipt?, errors[]
```

`GitHubContributionSelection` validates canonical GitHub path identity against its repository/kind/number fields. `ContributionPreview` enforces empty `external_actions`; `IMPORTABLE` contains exactly one mutable proposal (`proposed_entry` XOR `candidate_event`); `NO_CHANGE`, `ALREADY_IMPORTED`, and `BLOCKED` contain neither. `BLOCKED` requires at least one bounded error code.

`ContributionImportRequest` rejects any preview whose status is not `IMPORTABLE` and rejects `confirmed_at < preview.observation.captured_at`.

Canonical hashing:

```python
def canonical_sha256(value: BaseModel | dict[str, object]) -> str:
    payload = value.model_dump(mode="json", exclude_none=False) if isinstance(value, BaseModel) else value
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def observation_sha256(observation: ContributionObservation) -> str:
    return canonical_sha256(observation)
```

`ContributionImportResult` requires a receipt for `IMPORTED`/`ALREADY_IMPORTED` and forbids receipts for blocked/conflict statuses.

- [ ] **Step 4: Run strict-model tests GREEN**

```bash
python -m pytest tests/test_contribution_observation_models.py -v
```

- [ ] **Step 5: Export contracts and commit**

Add the stable Task 2 contract names to `app/contributions/__init__.py`.

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

`SQLiteContributionRepository` exposes these exact signatures:

```text
initialize() -> None
get_entry(entry_id: str) -> PublicContributionEntry | None
list_events(entry_id: str) -> list[ContributionEvent]
get_event(event_id: str) -> ContributionEvent | None
get_receipt_for_observation(observation_id: str) -> ContributionImportReceipt | None
insert_entry_with_receipt(entry: PublicContributionEntry, receipt: ContributionImportReceipt) -> tuple[PublicContributionEntry, ContributionImportReceipt, bool]
append_event_with_receipt(event: ContributionEvent, receipt: ContributionImportReceipt, projector: ContributionProjector) -> tuple[ContributionEvent, ContributionImportReceipt, bool]
```

- [ ] **Step 1: Write repository RED tests**

Test independently:

1. missing DB reads return `None`/`[]` and do not create file or parent directory;
2. `initialize()` creates exactly three durable tables;
3. identical entry replay is idempotent;
4. same `entry_id` with different canonical payload raises `ValueError("contribution entry_id conflict")`;
5. events list in `(observed_at, event_id)` order;
6. out-of-order event append is rejected;
7. identical event replay is idempotent;
8. same event id with changed payload conflicts;
9. same observation id with changed receipt payload conflicts;
10. pre-existing conflicting receipt causes entry+receipt rollback and entry remains absent;
11. pre-existing conflicting receipt causes event+receipt rollback and event remains absent;
12. full existing+candidate sequence is validated through `ContributionProjector` before commit.

Use direct `sqlite3` only inside the two conflict/rollback test helpers to seed the deliberately conflicting receipt row; production repository exposes no receipt-only write method.

- [ ] **Step 2: Run repository tests RED**

```bash
python -m pytest tests/test_contribution_repository.py -v
```

- [ ] **Step 3: Implement explicit initialization and schema**

Use exactly:

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

Every read method checks `self.path.exists()` before opening SQLite. Transactional write methods require an initialized DB and raise `RuntimeError("contribution repository is not initialized")` when it does not exist; they do not initialize implicitly.

For event insertion, load immutable entry + all existing events, reject `(event.observed_at, event.event_id)` less than or equal to the latest order unless the exact event already exists, run `projector.project(entry=entry, events=events + [event])`, then insert event and receipt in one transaction.

- [ ] **Step 4: Run repository tests GREEN**

```bash
python -m pytest tests/test_contribution_repository.py -v
```

- [ ] **Step 5: Lock private-file handling**

Append explicit ignore lines:

```text
state/contributions.local.sqlite3
state/contributions.local.sqlite3-*
```

Add this glob to the workflow forbidden-file list:

```text
'state/contributions.local.sqlite3*'
```

Do not alter other CI commands.

- [ ] **Step 6: Verify repository and syntax**

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

```text
GitHubContributionProvider.fetch(selection: GitHubContributionSelection, *, captured_at: datetime) -> GitHubIssueSnapshot | GitHubPullRequestSnapshot
GitHubPublicContributionProvider(client: httpx.Client, *, token: str | None = None)
GitHubPublicContributionProvider.fetch(selection: GitHubContributionSelection, *, captured_at: datetime) -> GitHubIssueSnapshot | GitHubPullRequestSnapshot
selection_from_github_url(url: str, *, operator_github_login: str, entry_id: str | None = None) -> GitHubContributionSelection
```

- [ ] **Step 1: Write provider RED tests using `httpx.MockTransport`**

Create a request recorder whose handler starts with:

```python
assert request.method == "GET"
requests_seen.append((request.method, request.url.path))
```

Test:

- parse Trixo issue URL into `ISSUE`, canonical repo, number `1`;
- parse Moracarta PR URL into `PULL_REQUEST`, canonical repo, number `42`;
- malformed/non-GitHub URLs fail closed;
- manually constructed selection with mismatched URL/repo/number/kind is rejected by Task 2 model validation;
- optional token appears only as outbound `Authorization: Bearer <token>` and never appears in snapshot JSON or exception messages;
- issue fetch ignores body and returns only allowlisted snapshot fields;
- PR fetch uses only PR metadata, PR reviews, selected-head check runs, and selected-head combined status;
- review body/check output text is absent from snapshot models;
- generic `failure` produces `description_code is None`;
- `ACTION_REQUIRED` produces `description_code == "EXTERNAL_AUTHORIZATION_REQUIRED"`;
- allowlisted phrase `team authorization required` produces the same bounded code.

- [ ] **Step 2: Run provider tests RED**

```bash
python -m pytest tests/test_contribution_github_provider.py -v
```

- [ ] **Step 3: Implement URL parsing and GET-only reads**

Use `urllib.parse.urlparse` for URL parsing and existing `httpx` for HTTP.

Issue endpoint:

```text
GET /repos/{owner}/{repo}/issues/{number}
```

Reject issue payloads containing `pull_request`.

PR endpoints:

```text
GET /repos/{owner}/{repo}/pulls/{number}
GET /repos/{owner}/{repo}/pulls/{number}/reviews
GET /repos/{owner}/{repo}/commits/{head_sha}/check-runs
GET /repos/{owner}/{repo}/commits/{head_sha}/status
```

Normalize timestamps to aware UTC. Convert raw external-gate evidence to bounded `description_code`; do not preserve raw descriptions. Keep the token only in transient request headers.

`GitHubPublicContributionProvider` must define only constructor + `fetch` as its public operations; no mutating GitHub method is added.

- [ ] **Step 4: Run provider tests GREEN and prove authority surface**

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

### Task 5: Normalize public GitHub facts into zero/one local transition

**Files:**
- Create: `app/contributions/normalizer.py`
- Test: `tests/test_contribution_normalizer.py`

**Interfaces:**

Create immutable result type:

```python
@dataclass(frozen=True)
class ContributionNormalization:
    observation: ContributionObservation
    status: Literal["IMPORTABLE", "NO_CHANGE", "BLOCKED"]
    proposed_entry: PublicContributionEntry | None = None
    candidate_event: ContributionEvent | None = None
    errors: tuple[str, ...] = ()
```

Expose exact call signatures:

```text
deterministic_issue_entry_id(repository_full_name: str, issue_number: int) -> str
normalize_snapshot(*, selection: GitHubContributionSelection, snapshot: GitHubIssueSnapshot | GitHubPullRequestSnapshot, entry: PublicContributionEntry | None, events: list[ContributionEvent], projector: ContributionProjector) -> ContributionNormalization
normalize_embedded_observation(*, observation: ContributionObservation, entry: PublicContributionEntry | None, events: list[ContributionEvent], projector: ContributionProjector) -> ContributionNormalization
```

`normalize_embedded_observation` is the no-network import revalidation seam.

- [ ] **Step 1: Write issue-normalization RED tests**

Freeze:

- open/unassigned new issue -> deterministic proposed entry with `AVAILABLE` and no event;
- open/self-assigned new issue, case-insensitive login -> `CLAIMED_SELF` and projected `TASK_READY`;
- open/other-assigned new issue -> `CLAIMED_OTHER` and projected `DISCOVERED`;
- closed issue without existing entry -> `BLOCKED` + `closed_issue_requires_existing_entry`;
- existing repository mismatch -> `BLOCKED` + `repository_mismatch`;
- existing missing/wrong `task_ref` -> `BLOCKED` + `task_ref_mismatch`;
- unchanged claim state -> `NO_CHANGE` even when public `updated_at` changes;
- `CLAIMED_OTHER -> unassigned` -> `TASK_RELEASED`;
- open -> closed -> `TASK_CLOSED`;
- `TASK_CLOSED` + reopened/unassigned -> `TASK_RELEASED`.

- [ ] **Step 2: Write PR chronology/blocker RED tests**

Freeze:

- PR without entry id -> `BLOCKED` + `pr_requires_entry_id`;
- selected PR repository mismatch -> `BLOCKED` + `repository_mismatch`;
- PR text cannot create lineage because raw body never enters typed snapshot/normalizer;
- absent local `PR_OPENED` always proposes `PR_OPENED` first, even when snapshot also contains reviews/merge;
- after PR open, unseen admissible facts sort by `(fact_at, deterministic_kind_order, source_fact_identity)`;
- equal timestamp order is exactly `CHANGES_REQUESTED`, `REVIEW_RECEIVED`, `EXTERNAL_BLOCKER`, `BLOCKER_CLEARED`, `PR_MERGED`, `PR_CLOSED`;
- older review is selected before later merge;
- `DISMISSED` review is ignored;
- generic failed checks create no blocker;
- explicit authorization gate creates `ContributionEvent(kind="BLOCKED", reason="EXTERNAL_AUTHORIZATION_REQUIRED")`;
- later successful same `check_ref` can create `UNBLOCKED` only while a blocker is active;
- every normalization result has at most one candidate event;
- event ids are deterministic hashes of observation identity.

- [ ] **Step 3: Run normalizer tests RED**

```bash
python -m pytest tests/test_contribution_normalizer.py -v
```

- [ ] **Step 4: Implement deterministic issue identity/intake**

Use:

```python
identity = f"PUBLIC_GITHUB|{repository_full_name}|ISSUE|{issue_number}"
entry_id = f"contrib-{hashlib.sha256(identity.encode("utf-8")).hexdigest()}"
```

Issue observation identity contains canonical state, sorted case-folded assignee logins, and public `updated_at`; closure identity uses `closed_at`.

Sanitize title by collapsing whitespace, stripping control characters, and truncating to 500 characters. Never inspect issue body.

- [ ] **Step 5: Implement chronological PR fact selection**

Represent `PR_OPENED` from `created_at`, reviews from `review_ref`, terminal facts from `merged_at`/`closed_at`, blockers from `check_ref`.

Equal-time order:

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

Before returning an event, project the full candidate sequence through `ContributionProjector`. Return `BLOCKED` + `invalid_contribution_transition` when the chosen public fact cannot form a valid core sequence.

- [ ] **Step 6: Run normalizer + core suites GREEN**

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

```text
ContributionObservationBridge(provider: GitHubContributionProvider, repository: SQLiteContributionRepository, projector: ContributionProjector, clock: Callable[[], datetime])
ContributionObservationBridge.preview(selection: GitHubContributionSelection) -> ContributionPreview
ContributionObservationBridge.import_preview(request: ContributionImportRequest) -> ContributionImportResult
```

- [ ] **Step 1: Write preview RED tests**

Use a fake provider with call counter. Assert:

1. preview calls provider exactly once;
2. preview against a missing DB does not create the DB file/directory;
3. proposed new entry -> `IMPORTABLE`, event `None`, projected `context_after`;
4. existing transition -> one event and before/after contexts;
5. unchanged state -> `NO_CHANGE`;
6. exact observation with existing identical receipt -> `ALREADY_IMPORTED`;
7. same observation + same local state -> same `preview_sha256`;
8. local history change -> different preview hash;
9. external actions stays empty.

State hash canonicalizes existing entry payload or null plus the complete ordered event payload list.

Preview hash binds preview version, observation hash, proposed/existing entry, candidate event, history hash, context before, and context after.

- [ ] **Step 2: Write import RED tests**

Initialize the temp repository explicitly before confirmed imports. Assert:

- provider call count is unchanged during import;
- new entry + receipt commits atomically;
- event + receipt commits atomically;
- exact repeated import -> `ALREADY_IMPORTED`;
- changed local state after preview -> `BLOCKED_STALE_PREVIEW`, no write;
- same observation id with different hash -> `CONFLICT`;
- embedded-observation domain revalidation failure -> `BLOCKED_DOMAIN`;
- `processed_at` comes from injected aware-UTC clock;
- receipt id equals `contrib-receipt-` + SHA-256 of `observation_id`.

- [ ] **Step 3: Run bridge tests RED**

```bash
python -m pytest tests/test_contribution_bridge.py -v
```

- [ ] **Step 4: Implement preview orchestration**

Call provider once with `captured_at=self.clock()`, then load local entry/events using side-effect-free reads. Call `normalize_snapshot` and project before/after in memory.

For exact prior receipt:

- same observation id + different observation hash -> `BLOCKED` + `observation_identity_conflict`;
- identical receipt identity -> `ALREADY_IMPORTED`.

Compute preview hash only from canonical typed/local state; no provider raw payload participates.

- [ ] **Step 5: Implement no-network import revalidation**

`import_preview` must never call `self.provider.fetch`. Re-load local state, call `normalize_embedded_observation` with `request.preview.observation`, rebuild candidate/context/history hash, and compare against the confirmed preview hash.

Stale result:

```python
return ContributionImportResult(
    status="BLOCKED_STALE_PREVIEW",
    receipt=None,
    errors=["stale_preview"],
)
```

On an exact current preview, build deterministic receipt and call exactly one repository atomic transaction.

- [ ] **Step 6: Run bridge tests GREEN and prove no-network import**

```bash
python -m pytest tests/test_contribution_bridge.py -v
```

The test fake provider changes its `fetch` implementation after preview to raise `AssertionError("provider called during import")`; import must still pass.

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

```text
python -m app.contributions.intake_cli preview --url <url> --operator-login <login> [--entry-id <id>] [--db <path>] --out <preview.json>
python -m app.contributions.intake_cli import --preview-file <preview.json> --confirmed-by <operator-id> [--db <path>]
```

`main(argv: list[str] | None = None) -> int` is the testable CLI entrypoint.

- [ ] **Step 1: Write CLI RED tests**

Monkeypatch provider construction so no test uses live GitHub. Freeze:

- `preview` parses URL, constructs repository without calling `initialize()`, calls bridge preview, writes exact `ContributionPreview.model_dump_json(indent=2)` to `--out`, prints only bounded identifiers/status;
- preview against missing default DB leaves the DB absent;
- `preview` never imports;
- `import` reads exact preview JSON, constructs `ContributionImportRequest`, calls `repository.initialize()` only after the preview validates as `IMPORTABLE` and explicit `--confirmed-by` is present, then calls bridge import;
- `import` makes zero provider/network calls and prints receipt JSON on success;
- non-importable preview files are rejected before repository initialization;
- neither command has an auto-confirm flag/default.

Use stdlib `argparse` subparsers.

- [ ] **Step 2: Add five sanitized fixture cases + dogfood RED tests**

Create `tests/fixtures/contributions/github_intake_v1.json` using only Task 2 snapshot fields:

1. Trixo `trixocom/odoo-argentina-trx-ce#1`: open/unassigned -> `AVAILABLE` -> `TASK_READY`.
2. Moracarta `WesleyHanauer/moracarta#25`: open/assigned to `juanmanueltorres-creator` -> `CLAIMED_SELF` -> `TASK_READY`.
3. Public claimed-other issue: open/different assignee -> `CLAIMED_OTHER` -> `DISCOVERED`.
4. Moracarta PR #42 with explicit existing entry -> first `PR_OPENED` -> `IN_REVIEW`.
5. SUNAT PR #115 with explicit existing entry and `GitHubCheckSnapshot(description_code="EXTERNAL_AUTHORIZATION_REQUIRED")` -> first `PR_OPENED`; later chronological `BLOCKED` while stage remains `IN_REVIEW`.

Privacy test:

```python
serialized = json.dumps(payload).lower()
for forbidden in [
    "email", "token", "authorization_header", "raw_body", "review_body",
    "check_log", "private_message", "employment_interest",
]:
    assert forbidden not in serialized
```

The bounded string `EXTERNAL_AUTHORIZATION_REQUIRED` is allowed because it is a typed reason code, not a credential/header/raw message.

- [ ] **Step 3: Write release-contract RED tests**

Freeze FastAPI surface:

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

- contribution intake runtime files contain no imports from `app.relationships`, `app.operator_bridge`, `app.outreach`, `app.process_email`, or `app.cv`;
- observation/receipt field names contain none of `employment`, `salary`, `hiring`, `contact_permission`;
- provider exposes no GitHub mutation methods;
- `pyproject.toml` is unchanged in the feature diff;
- workflow private guard contains `state/contributions.local.sqlite3*`.

- [ ] **Step 4: Run CLI/dogfood/release tests RED**

```bash
python -m pytest \
  tests/test_contribution_intake_cli.py \
  tests/test_contribution_intake_dogfood.py \
  tests/test_contribution_intake_release_contract.py -v
```

- [ ] **Step 5: Implement thin CLI**

Preview path:

```python
repository = SQLiteContributionRepository(Path(args.db))
selection = selection_from_github_url(
    args.url,
    operator_github_login=args.operator_login,
    entry_id=args.entry_id,
)
preview = bridge.preview(selection)
Path(args.out).write_text(preview.model_dump_json(indent=2), encoding="utf-8")
```

Do not call `repository.initialize()` in preview.

Import path:

```python
preview = ContributionPreview.model_validate_json(
    Path(args.preview_file).read_text(encoding="utf-8")
)
request = ContributionImportRequest(
    preview=preview,
    confirmed_by=args.confirmed_by,
    confirmed_at=clock(),
)
repository.initialize()
result = bridge.import_preview(request)
```

Construct the provider/client normally or with a test fake; `import_preview` never calls it. Return nonzero exit code for blocked/conflict results.

- [ ] **Step 6: Add public boundary document**

Create `docs/PUBLIC_CONTRIBUTION_INTAKE_V1.md` with these exact statements:

```text
GitHub reads are explicit and read-only.
Preview is local and non-mutating.
Import mutates only local contribution state after confirmation.
No GitHub write authority is added.
Contribution outcomes do not imply employment interest.
V1 is explicit-resource intake, not discovery/radar.
```

Document both CLI commands and `state/contributions.local.sqlite3`. Do not claim background monitoring, search, Gmail classification, automatic proof-of-work promotion, or GitHub mutation.

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

- [ ] **Step 8: Run full repository release gate**

```bash
python -m pytest -v
python -m compileall app
git diff --check origin/main...HEAD
```

Run the exact private-file guard from `.github/workflows/tests.yml`, now containing `state/contributions.local.sqlite3*`, then:

```bash
python scripts/render_recruiter_previews.py
```

Push implementation branch and require GitHub Actions `success` for:

```text
pytest
build-offline-runtime (3.12)
build-offline-runtime (3.13)
verify-offline-runtime (3.12)
verify-offline-runtime (3.13)
```

Do not mark implementation PR ready while any gate is pending/failing.

- [ ] **Step 9: Verify changed-file scope**

Allowed implementation diff:

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

Fail review if `app/main.py`, relationships, Operator Bridge, Outreach, Process Email, CV, opportunity models, or `pyproject.toml` changed.

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

PR body must state:

- explicit public GitHub issue/PR intake only;
- GET-only provider authority;
- preview-before-import human boundary;
- local SQLite mutation only;
- one candidate event per preview;
- exact repository + task lineage rules;
- chronology-before-terminal-state rule;
- evidence-aware external blocker rule;
- no GitHub writes, search/radar, Gmail classifier, Relationship mutation, CV/outreach changes, HTTP routes, or hiring inference;
- full CI evidence from exact head SHA.

Keep PR draft until every release gate is green. Request code review before merge. Do not merge to `main` without explicit operator approval.

## Self-Review Checklist

- Sections 5.1–5.2 -> Task 1.
- Sections 6, 8–10, 15–18 -> Task 2.
- Section 19 -> Task 3.
- Sections 6–8 and 14 -> Task 4.
- Sections 11–14 -> Task 5.
- Sections 15–20 -> Task 6.
- Sections 21–24 -> Task 7.
- Section 25 stays deferred: no radar, Gmail contribution classifier, proof-of-work promotion, or background polling task exists.

No task authorizes GitHub mutation or hiring inference. No new dependency is required. Preview remains non-mutating; import is the only path that initializes/writes contribution SQLite state after confirmation.