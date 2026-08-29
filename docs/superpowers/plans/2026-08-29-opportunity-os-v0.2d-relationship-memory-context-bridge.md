# Opportunity OS V0.2D — Relationship Memory + Context Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist private company/contact relationship state plus append-only history, expose a redacted context projection, and let Target Accounts use that memory for cooldown, open-process, held-contact, and follow-up decisions without gaining any external side effects.

**Architecture:** Add a focused `app/relationships/` subsystem with strict Pydantic contracts, a local SQLite repository, a transactional service that owns state transitions, and a deterministic redacted Context Bridge. Target Accounts reads a `RelationshipMemory` protocol only; FastAPI exposes redacted read-only context endpoints. Gmail, Apollo, vault import, web research, drafts, sends, applications, and background scheduling remain outside this slice.

**Tech Stack:** Python 3.12+, Pydantic, stdlib `sqlite3`, FastAPI, pytest, existing Opportunity OS CI.

**Spec:** `docs/superpowers/specs/2026-08-29-opportunity-os-v0.2d-relationship-memory-context-bridge-design.md`

## Global Constraints

- Real database path defaults to `state/relationships.local.sqlite3` and must remain private/gitignored.
- Public repository contains only contracts, implementation code, and fictional fixtures/tests.
- Relationship events are append-only and idempotent by `event_id`.
- Reusing an `event_id` with a conflicting payload is an integrity error.
- All stored datetimes are timezone-aware and normalized to UTC.
- `UNVERIFIED` and `STALE` contacts are never counted as usable outbound contacts.
- `HELD` means known but intentionally not recommended; it is distinct from `INACTIVE`.
- Relationship Memory may recommend/suppress actions but must never create drafts, send email, submit applications, consume enrichment credits, search the web, or mutate external providers.
- The Context Bridge is redacted by default: no names, email addresses, provider message IDs, mailbox bodies, free-form private notes, or raw source payloads.
- `FOLLOW_UP` is only a recommendation; it requires prior relationship history, an explicit current reason, and the configured timing gate.
- Missing relationship storage must degrade to empty memory rather than break ordinary radar/health routes.
- Existing V0.2C hard boundary remains intact: approval is not a send command.

---

## File Structure

Create:

```text
app/relationships/__init__.py
app/relationships/models.py
app/relationships/repository.py
app/relationships/service.py
app/relationships/context.py

tests/test_relationship_models.py
tests/test_relationship_repository.py
tests/test_relationship_service.py
tests/test_relationship_context.py
tests/test_target_relationship_integration.py
tests/test_api_relationship_context.py
```

Modify:

```text
app/targets/models.py
app/targets/selector.py
app/targets/service.py
app/api/routes.py
app/main.py
.env.example
.gitignore
README.md
ROADMAP.md
```

Responsibilities:

- `models.py`: strict public contracts/enums only.
- `repository.py`: SQLite schema, private current-state persistence, append-only events, atomic transaction primitive.
- `service.py`: validated transition rules and projection updates; callers do not orchestrate multi-table writes themselves.
- `context.py`: redacted `RelationshipContext` construction and compact snapshot rendering.
- `targets/*`: consume relationship context and add `FOLLOW_UP`; never read private contact fields directly.
- `api/routes.py`: read-only redacted context endpoints only.
- `main.py`: optional default relationship repository/service wiring with empty-memory fallback.

---

### Task 1: Strict relationship domain contracts

**Files:**
- Create: `app/relationships/__init__.py`
- Create: `app/relationships/models.py`
- Test: `tests/test_relationship_models.py`

**Interfaces:**
- Produces: `CareerContact`, `RelationshipAccount`, `RelationshipEvent`, `RelationshipPolicy`, `RelationshipContext`, `RelationshipContextSnapshot`.
- Produces literals: `ContactType`, `VerificationStatus`, `ContactDisposition`, `RelationshipState`, `RelationshipEventKind`, `RelationshipAction`.
- Later tasks import these contracts without redefining them.

- [ ] **Step 1: Write failing strict-model tests**

Create tests covering timezone normalization, forbidden extra fields, preferred-contact invariants, and forbidden PII fields in `RelationshipContext`.

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.relationships.models import (
    CareerContact,
    RelationshipAccount,
    RelationshipContext,
    RelationshipEvent,
)

NOW = datetime(2026, 8, 29, 4, 30, tzinfo=timezone.utc)


def test_contact_normalizes_observed_at_and_rejects_extra_fields() -> None:
    contact = CareerContact(
        contact_id="contact-1",
        account_id="account-1",
        person="Example Person",
        role="Recruiter",
        contact_type="RECRUITER",
        verification_status="VERIFIED",
        observed_at=NOW,
        disposition="AVAILABLE",
        active=True,
    )
    assert contact.observed_at.tzinfo is timezone.utc

    with pytest.raises(ValidationError):
        CareerContact(
            **contact.model_dump(),
            invented=True,
        )


def test_relationship_event_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        RelationshipEvent(
            event_id="event-1",
            account_id="account-1",
            kind="CONTACTED",
            occurred_at=datetime(2026, 8, 29, 4, 30),
        )


def test_redacted_context_has_no_contact_pii_fields() -> None:
    assert "person" not in RelationshipContext.model_fields
    assert "email" not in RelationshipContext.model_fields
    assert "channel_value" not in RelationshipContext.model_fields
    assert "notes" not in RelationshipContext.model_fields
```

- [ ] **Step 2: Run model tests and verify RED**

Run:

```bash
python -m pytest tests/test_relationship_models.py -v
```

Expected: collection/import failure because `app.relationships.models` does not exist.

- [ ] **Step 3: Implement minimal strict models**

Use `ConfigDict(extra="forbid")`, timezone validators equivalent to existing `TargetSignal`/outreach models, and these exact public values:

```python
ContactType = Literal["RECRUITER", "HIRING_MANAGER", "TECHNICAL", "OTHER"]
VerificationStatus = Literal["VERIFIED", "PUBLIC_SOURCE", "STALE", "UNVERIFIED"]
ContactDisposition = Literal["AVAILABLE", "HELD", "INACTIVE"]
RelationshipState = Literal[
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
```

Required defaults:

```python
class RelationshipPolicy(StrictRelationshipModel):
    spontaneous_contact_cooldown_days: int = Field(default=30, ge=0)
    follow_up_min_days: int = Field(default=5, ge=0)
    stale_contact_days: int = Field(default=180, ge=1)
```

`RelationshipContext` must contain only redacted account-level fields specified by the design.

- [ ] **Step 4: Run tests and verify GREEN**

```bash
python -m pytest tests/test_relationship_models.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/relationships/__init__.py app/relationships/models.py tests/test_relationship_models.py
git commit -m "feat: define relationship memory contracts"
```

---

### Task 2: SQLite relationship repository and integrity rules

**Files:**
- Create: `app/relationships/repository.py`
- Test: `tests/test_relationship_repository.py`

**Interfaces:**
- Consumes: Task 1 models.
- Produces: `SQLiteRelationshipRepository(path)`.
- Produces methods:
  - `initialize() -> None`
  - `get_account(account_id: str) -> RelationshipAccount | None`
  - `save_account(account: RelationshipAccount) -> RelationshipAccount`
  - `get_contact(contact_id: str) -> CareerContact | None`
  - `list_contacts(account_id: str) -> list[CareerContact]`
  - `save_contact(contact: CareerContact) -> CareerContact`
  - `get_event(event_id: str) -> RelationshipEvent | None`
  - `list_events(account_id: str) -> list[RelationshipEvent]`
  - `apply_event_transaction(event, projector) -> tuple[RelationshipEvent, RelationshipAccount]`
- `projector` is an injected callback used by Task 3 inside one SQLite transaction; repository owns commit/rollback.

- [ ] **Step 1: Write failing repository tests**

Cover schema initialization, account/contact round-trip, cross-account preferred-contact rejection, idempotent identical events, conflicting duplicate event IDs, and rollback.

```python
from pathlib import Path

import pytest

from app.relationships.models import CareerContact, RelationshipEvent
from app.relationships.repository import SQLiteRelationshipRepository


def test_duplicate_event_id_with_conflicting_payload_is_rejected(tmp_path: Path) -> None:
    repo = SQLiteRelationshipRepository(tmp_path / "relationships.sqlite3")
    repo.initialize()
    first = RelationshipEvent(
        event_id="event-1",
        account_id="account-1",
        kind="CONTACTED",
        occurred_at=NOW,
    )
    repo.append_event(first)

    conflicting = first.model_copy(update={"kind": "REPLIED"})
    with pytest.raises(ValueError, match="event_id conflict"):
        repo.append_event(conflicting)
```

- [ ] **Step 2: Run repository tests and verify RED**

```bash
python -m pytest tests/test_relationship_repository.py -v
```

Expected: import failure for missing repository.

- [ ] **Step 3: Implement SQLite schema and deterministic serialization**

Create tables:

```sql
relationship_accounts(account_id PRIMARY KEY, relationship_state, last_contacted_at, cooldown_until, open_process, payload_json, updated_at)
relationship_contacts(contact_id PRIMARY KEY, account_id, disposition, verification_status, payload_json, updated_at)
relationship_events(event_id PRIMARY KEY, account_id, contact_id, kind, payload_json, occurred_at)
```

Indexes:

```sql
CREATE INDEX idx_relationship_contacts_account ON relationship_contacts(account_id, disposition, contact_id);
CREATE INDEX idx_relationship_events_account ON relationship_events(account_id, occurred_at, event_id);
CREATE INDEX idx_relationship_events_contact ON relationship_events(contact_id, occurred_at, event_id);
```

When an existing `event_id` is found:

```python
stored = RelationshipEvent.model_validate_json(row["payload_json"])
if stored != value:
    raise ValueError("relationship event_id conflict")
return stored
```

Validate that `preferred_next_contact_id`, when set, resolves to the same account and is `active=True`, `disposition="AVAILABLE"`.

- [ ] **Step 4: Run repository tests and verify GREEN**

```bash
python -m pytest tests/test_relationship_repository.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/relationships/repository.py tests/test_relationship_repository.py
git commit -m "feat: add private relationship sqlite repository"
```

---

### Task 3: Transactional relationship transition service

**Files:**
- Create: `app/relationships/service.py`
- Test: `tests/test_relationship_service.py`

**Interfaces:**
- Consumes: `SQLiteRelationshipRepository`, Task 1 models.
- Produces: `RelationshipService(repository, policy=None)`.
- Produces:
  - `register_contact(contact: CareerContact) -> CareerContact`
  - `record(event: RelationshipEvent) -> RelationshipAccount`
  - `context_source_account(account_id: str) -> RelationshipAccount | None`
- All event mutation is owned by `record`; external callers must not manually coordinate account/contact/event writes.

- [ ] **Step 1: Write failing transition tests**

Test at minimum:

```python
def test_process_open_is_not_downgraded_by_later_contacted_event(...): ...
def test_replied_preserves_process_open(...): ...
def test_process_updated_requires_open_process(...): ...
def test_process_closed_requires_open_process(...): ...
def test_contact_held_clears_preferred_contact(...): ...
def test_contact_released_requires_active_held_contact(...): ...
def test_cooldown_set_requires_aware_future_or_equal_timestamp(...): ...
def test_invalid_projection_rolls_back_event_and_state(...): ...
```

Representative assertion:

```python
service.record(process_opened)
account = service.record(contacted_later)
assert account.relationship_state == "PROCESS_OPEN"
assert account.open_process is True
assert account.last_contacted_at == contacted_later.occurred_at
```

- [ ] **Step 2: Run service tests and verify RED**

```bash
python -m pytest tests/test_relationship_service.py -v
```

Expected: import failure for missing service.

- [ ] **Step 3: Implement transition projector and atomic record path**

Define an explicit state-strength guard rather than relying on enum ordering:

```python
def _apply_account_event(account: RelationshipAccount, event: RelationshipEvent) -> RelationshipAccount:
    if event.kind == "CONTACTED":
        next_state = account.relationship_state
        if next_state not in {"PROCESS_OPEN"}:
            next_state = "CONTACTED"
        return account.model_copy(update={
            "relationship_state": next_state,
            "last_contacted_at": event.occurred_at,
            "updated_at": event.occurred_at,
        })
    ...
```

For `CONTACT_VERIFIED`, require `contact_id`, require the contact exists under the same account, set `verification_status="VERIFIED"`, and refresh `observed_at` to the event time unless an explicit newer observation already exists.

For `CONTACT_HELD`, set disposition `HELD` and clear the account preferred contact when it points to that contact.

For `COOLDOWN_SET`, require a timestamp in `metadata["cooldown_until"]`, parse it as aware UTC, and reject values before `occurred_at`.

The repository transaction must append the event and update projections atomically; an invalid projection leaves neither the event nor state persisted.

- [ ] **Step 4: Run service tests and verify GREEN**

```bash
python -m pytest tests/test_relationship_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/relationships/service.py tests/test_relationship_service.py
git commit -m "feat: apply transactional relationship events"
```

---

### Task 4: Redacted Context Bridge and relationship recommendations

**Files:**
- Create: `app/relationships/context.py`
- Test: `tests/test_relationship_context.py`

**Interfaces:**
- Consumes: repository/service read models.
- Produces protocol:

```python
class RelationshipMemory(Protocol):
    def context_for(
        self,
        account_id: str,
        *,
        now: datetime,
        current_reason: str | None = None,
    ) -> RelationshipContext: ...
```

- Produces `SQLiteRelationshipMemory` and `EmptyRelationshipMemory`.
- Produces `build_context_snapshot(account_ids, *, now) -> RelationshipContextSnapshot`.
- Produces `render_context_snapshot(snapshot) -> str` with no PII.

- [ ] **Step 1: Write failing redaction/recommendation tests**

Cover:

```python
def test_empty_memory_returns_untouched_context(...): ...
def test_open_process_is_watch(...): ...
def test_active_cooldown_is_watch(...): ...
def test_no_usable_contacts_is_research_contact(...): ...
def test_held_contacts_are_counted_but_not_usable(...): ...
def test_follow_up_requires_history_new_reason_and_min_days(...): ...
def test_rendered_snapshot_contains_no_person_email_or_notes(...): ...
```

Example:

```python
context = memory.context_for(
    "account-1",
    now=NOW,
    current_reason="new backend role published",
)
assert context.recommended_relationship_action == "FOLLOW_UP"
assert context.reason == "new backend role published"
```

- [ ] **Step 2: Run context tests and verify RED**

```bash
python -m pytest tests/test_relationship_context.py -v
```

Expected: import failure for missing context module.

- [ ] **Step 3: Implement deterministic context precedence**

Use this order exactly:

```python
if account.open_process:
    action = "WATCH"
elif cooldown_active:
    action = "WATCH"
elif historical and current_reason and follow_up_age_ok:
    action = "FOLLOW_UP"
elif usable_contact_count == 0:
    action = "RESEARCH_CONTACT"
elif usable_contact_count == 0 and held_contact_count > 0:
    action = "WATCH"  # normalize this by evaluating held-only before generic no-contact branch
else:
    action = "PREPARE_SPECULATIVE"
```

Implement the held-only branch before the generic zero-usable-contact branch so the effective precedence is:

```text
open process -> WATCH
cooldown -> WATCH
history + new reason + timing -> FOLLOW_UP
held-only contacts -> WATCH
no usable contacts -> RESEARCH_CONTACT
otherwise -> PREPARE_SPECULATIVE
```

Usable contact definition:

```python
contact.active
and contact.disposition == "AVAILABLE"
and contact.verification_status in {"VERIFIED", "PUBLIC_SOURCE"}
```

Never put `person`, `channel_value`, `verification_source`, raw metadata, or notes into `RelationshipContext`.

- [ ] **Step 4: Run context tests and verify GREEN**

```bash
python -m pytest tests/test_relationship_context.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/relationships/context.py tests/test_relationship_context.py
git commit -m "feat: add redacted relationship context bridge"
```

---

### Task 5: Integrate Relationship Memory into Target Accounts

**Files:**
- Modify: `app/targets/models.py`
- Modify: `app/targets/selector.py`
- Modify: `app/targets/service.py`
- Test: `tests/test_target_relationship_integration.py`
- Update existing tests as required: `tests/test_target_selector.py`, `tests/test_target_service.py`

**Interfaces:**
- Consumes: `RelationshipMemory.context_for(...)` from Task 4.
- Produces: `TargetAction = Literal["PREPARE_SPECULATIVE", "FOLLOW_UP", "RESEARCH_CONTACT", "WATCH"]`.
- `TargetRadarService(..., relationship_memory: RelationshipMemory | None = None)` replaces the old `OutreachHistory` dependency.

- [ ] **Step 1: Write failing integration tests**

Test that Target Accounts honors relationship precedence before affinity action logic:

```python
def test_open_process_forces_watch_even_for_high_affinity(...): ...
def test_follow_up_propagates_when_relationship_context_allows_it(...): ...
def test_held_only_contact_forces_watch(...): ...
def test_missing_memory_preserves_existing_target_behavior(...): ...
def test_selector_never_returns_send(...): ...
```

- [ ] **Step 2: Run integration tests and verify RED**

```bash
python -m pytest tests/test_target_relationship_integration.py -v
```

Expected: failure because `FOLLOW_UP` and relationship-memory integration do not exist.

- [ ] **Step 3: Replace narrow history protocol**

Remove `OutreachHistory.last_contacted_at()` from the target selector path. The target service obtains `RelationshipContext` per account and passes it into selector materialization.

Keep target-account scoring unchanged.

Action merge rule:

```python
if relationship_action in {"WATCH", "FOLLOW_UP", "RESEARCH_CONTACT"}:
    action = relationship_action
else:
    action = _affinity_action(item, policy)
```

`PREPARE_SPECULATIVE` from relationship context means “no relationship blocker”; final affinity/confidence/contactability thresholds still apply.

Sort order becomes:

```python
_ACTION_ORDER = {
    "FOLLOW_UP": 0,
    "PREPARE_SPECULATIVE": 1,
    "RESEARCH_CONTACT": 2,
    "WATCH": 3,
}
```

- [ ] **Step 4: Run target tests and verify GREEN**

```bash
python -m pytest \
  tests/test_target_relationship_integration.py \
  tests/test_target_selector.py \
  tests/test_target_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/targets/models.py app/targets/selector.py app/targets/service.py tests/test_target_relationship_integration.py tests/test_target_selector.py tests/test_target_service.py
git commit -m "feat: make target radar relationship aware"
```

---

### Task 6: Read-only API wiring and empty-memory fallback

**Files:**
- Modify: `app/api/routes.py`
- Modify: `app/main.py`
- Test: `tests/test_api_relationship_context.py`
- Modify: `.env.example`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `RelationshipMemory` from Task 4.
- API produces redacted responses only:
  - `GET /api/v1/relationships/{account_id}/context`
  - `GET /api/v1/relationships/context`
- `create_app(..., relationship_memory: RelationshipMemory | None = None, enable_default_relationships: bool = True)`.

- [ ] **Step 1: Write failing API/privacy tests**

```python
def test_relationship_context_endpoint_is_redacted(...):
    response = client.get("/api/v1/relationships/example/context")
    payload = response.json()
    serialized = json.dumps(payload).lower()
    assert "email" not in serialized
    assert "person" not in serialized
    assert "channel_value" not in serialized


def test_missing_relationship_db_does_not_break_health_or_target_radar(...): ...
```

Also test that there are no POST/PATCH/DELETE relationship routes in V0.2D.

- [ ] **Step 2: Run API tests and verify RED**

```bash
python -m pytest tests/test_api_relationship_context.py -v
```

Expected: 404/missing protocol before implementation.

- [ ] **Step 3: Wire optional default storage**

Environment:

```text
OPPORTUNITY_RELATIONSHIPS_PATH=state/relationships.local.sqlite3
```

Behavior:

```python
path = Path(os.getenv("OPPORTUNITY_RELATIONSHIPS_PATH", "state/relationships.local.sqlite3"))
if path.exists():
    repository = SQLiteRelationshipRepository(path)
    repository.initialize()
    memory = SQLiteRelationshipMemory(repository)
else:
    memory = EmptyRelationshipMemory()
```

Do not auto-create the real default DB merely by importing/running an app with no relationship configuration; this keeps missing storage equivalent to empty memory. Tests may inject a temp initialized repository explicitly.

Add to `.gitignore` exactly:

```text
state/relationships.local.sqlite3
state/relationships.local.sqlite3-*
artifacts/relationships/*.local.*
```

- [ ] **Step 4: Run API + target regression tests**

```bash
python -m pytest tests/test_api_relationship_context.py tests/test_api_target_radar.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py app/main.py tests/test_api_relationship_context.py .env.example .gitignore
git commit -m "feat: expose redacted relationship context API"
```

---

### Task 7: Privacy guard, documentation, and release verification

**Files:**
- Modify: `README.md`
- Modify: `ROADMAP.md`
- Modify CI/private guard only if current guard does not already reject `state/relationships.local.sqlite3` and relationship local artifacts.
- Test existing README/release-contract tests plus full suite.

**Interfaces:**
- Documents V0.2D as implemented only after all code/tests in Tasks 1–6 are green.
- Advances roadmap NEXT to Operator Integration.

- [ ] **Step 1: Inspect the existing privacy guard before editing it**

Run/search the repository for the current private-file check. If `.gitignore` patterns plus current guard already cover `*.sqlite3` and local artifacts, do not add redundant CI logic. If they do not, add the narrowest test/guard necessary for:

```text
state/relationships.local.sqlite3
state/relationships.local.sqlite3-*
artifacts/relationships/*.local.*
```

- [ ] **Step 2: Update README in human-first language**

Add Relationship Memory to the implemented-state table and describe it before technical details:

```text
empresa detectada
→ memoria privada de relación
→ ¿proceso abierto / cooldown / contacto held?
→ WATCH / FOLLOW_UP / RESEARCH_CONTACT / PREPARE_SPECULATIVE
```

Keep the existing tested hard-boundary phrases unchanged, including:

```text
CV Factory does not send email and does not submit applications.
Opportunity OS does not create Gmail drafts automatically.
Approval is not a send command.
```

State explicitly that real CRM/contact data remains local and is not imported automatically from Gmail/Apollo/the vault in V0.2D.

- [ ] **Step 3: Advance ROADMAP**

Mark `V0.2D — Relationship Memory / Context Bridge` implemented and move `Operator integration` from AFTER to NEXT. Do not claim Gmail/Apollo/vault synchronization exists.

- [ ] **Step 4: Run focused release-contract tests**

Use repository search to identify README/privacy tests, then run them explicitly together with all relationship/target tests.

Minimum:

```bash
python -m pytest \
  tests/test_relationship_models.py \
  tests/test_relationship_repository.py \
  tests/test_relationship_service.py \
  tests/test_relationship_context.py \
  tests/test_target_relationship_integration.py \
  tests/test_api_relationship_context.py \
  tests/test_target_selector.py \
  tests/test_target_service.py \
  tests/test_api_target_radar.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full verification**

```bash
python -m pytest -v
python -m compileall app
git diff --check main...HEAD
```

Then run the repository's private-file guard exactly as CI runs it.

Expected: all PASS, no tracked private relationship DB/artifact.

- [ ] **Step 6: Commit docs/release boundary**

```bash
git add README.md ROADMAP.md .github tests
git commit -m "docs: document V0.2D relationship memory"
```

Do not add `.github` if it was not changed.

- [ ] **Step 7: Final branch review**

Check:

```bash
git diff --stat main...HEAD
git diff --check main...HEAD
git status --short
```

Confirm:

- no real names/emails/contact CRM content is present;
- no Gmail/Apollo SDK dependency was introduced;
- no relationship mutation HTTP endpoint exists;
- no `SEND` relationship action exists;
- `FOLLOW_UP` requires prior history + new reason + timing gate;
- Target Accounts still works with empty memory;
- full CI is green before opening the PR.
