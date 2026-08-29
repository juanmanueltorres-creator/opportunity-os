# V0.2E1 Gmail Read Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a selective, read-only Gmail adapter that converts explicitly selected Gmail messages/threads into defensible `OperatorObservation` candidates without importing relationship state or gaining Gmail mutation authority.

**Architecture:** Add `app/adapters/gmail_read` as a provider-specific layer that owns Gmail REST reading, payload normalization and conservative message/thread classification. It may depend on `app.operator_bridge.models.OperatorObservation`, but `app/operator_bridge` must remain provider-neutral. The API returns a candidate observation and stops; V0.2E remains the only preview → confirm → import boundary.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, `httpx`, standard-library email address parsing, pytest/pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-08-29-opportunity-os-v0.2e1-gmail-read-adapter-design.md`

## Global Constraints

- Gmail reads are explicit: exactly one `message_id` or `thread_id` per request.
- Caller supplies canonical `account_id`; Gmail content never invents the Opportunity OS account identity.
- Initial observation kinds are only `MESSAGE_SENT` and `REPLY_RECEIVED`.
- No body, raw MIME, raw provider payload, attachment, token or unrestricted metadata enters domain-facing models.
- Gmail provider code exposes only read operations.
- No Gmail draft/send/reply/archive/delete/label mutation.
- Adapter never calls `OperatorBridgeService.import_observation()` and never writes Relationship Memory.
- `external_actions=[]` is invariant.
- Route `/api/v1/adapters/gmail/observe` is absent by default and enabled only explicitly.
- Provider failures fail closed with bounded error codes.
- `app/operator_bridge` must not import `app.adapters.gmail_read`.
- Do not add Apollo, mailbox polling, process-email semantic classification or OAuth token persistence in this slice.

---

## File Map

Create:
- `app/adapters/__init__.py`
- `app/adapters/gmail_read/__init__.py`
- `app/adapters/gmail_read/models.py`
- `app/adapters/gmail_read/provider.py`
- `app/adapters/gmail_read/normalizer.py`
- `app/adapters/gmail_read/service.py`
- `app/adapters/gmail_read/api.py`
- `tests/test_gmail_read_models.py`
- `tests/test_gmail_read_provider.py`
- `tests/test_gmail_read_normalizer.py`
- `tests/test_gmail_read_service.py`
- `tests/test_api_gmail_read.py`
- `tests/test_gmail_read_release_contract.py`

Modify:
- `app/main.py`
- `.env.example`
- `README.md`
- `ROADMAP.md`

Do not modify Outreach Core or Relationship Memory transition code.

---

### Task 1: Strict Gmail adapter contracts

**Files:**
- Create: `app/adapters/__init__.py`
- Create: `app/adapters/gmail_read/__init__.py`
- Create: `app/adapters/gmail_read/models.py`
- Test: `tests/test_gmail_read_models.py`

**Interfaces:**
- `GmailReadSelection(account_id, selected_by, contact_id=None, message_id=None, thread_id=None)` with exactly one provider ID.
- `GmailMessageEnvelope(message_id, thread_id, internal_date, label_ids, from_address, to_addresses, cc_addresses=(), subject=None, in_reply_to=None, references=())`.
- `GmailThreadEnvelope(thread_id, messages)`.
- `GmailObservationResult(status, observation=None, provider="gmail", source_ref=None, errors=[], external_actions=[])`.
- Status literal: `OBSERVATION_READY | AMBIGUOUS | PROVIDER_ERROR | INVALID_SELECTION`.

- [ ] **Step 1: Write failing model tests**

Create `tests/test_gmail_read_models.py` covering:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.adapters.gmail_read.models import (
    GmailMessageEnvelope,
    GmailObservationResult,
    GmailReadSelection,
)

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def test_selection_requires_exactly_one_provider_id() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        GmailReadSelection(account_id="example-co", selected_by="operator")
    with pytest.raises(ValidationError, match="exactly one"):
        GmailReadSelection(
            account_id="example-co",
            selected_by="operator",
            message_id="m1",
            thread_id="t1",
        )


def test_envelope_rejects_raw_body_fields() -> None:
    with pytest.raises(ValidationError):
        GmailMessageEnvelope(
            message_id="m1",
            thread_id="t1",
            internal_date=NOW,
            label_ids=("SENT",),
            from_address="owner@example.test",
            to_addresses=("person@example.test",),
            body="secret",
        )


def test_result_rejects_external_actions() -> None:
    with pytest.raises(ValidationError, match="external_actions"):
        GmailObservationResult(
            status="AMBIGUOUS",
            errors=["ambiguous_message_direction"],
            external_actions=["send_email"],
        )
```

- [ ] **Step 2: Push the test-only commit and verify GitHub Actions RED**

Expected failure: import/module missing for `app.adapters.gmail_read.models`.

- [ ] **Step 3: Implement minimal strict models**

Use `ConfigDict(extra="forbid")`. Normalize `internal_date` to UTC and reject naive datetimes. Bound `subject` to 200 chars, `selected_by` to 120 chars, provider IDs to non-empty strings. Store list-like metadata as tuples. Enforce exactly one of `message_id` or `thread_id` with a model validator. `GmailObservationResult` must reject any non-empty `external_actions` and require `observation` only for `OBSERVATION_READY`.

- [ ] **Step 4: Verify GREEN in GitHub Actions**

Expected: full suite passes.

- [ ] **Step 5: Commit**

Commit message: `feat: add Gmail read contracts`.

---

### Task 2: Read-only Gmail REST provider

**Files:**
- Create: `app/adapters/gmail_read/provider.py`
- Create: `app/adapters/gmail_read/normalizer.py`
- Test: `tests/test_gmail_read_provider.py`
- Test: `tests/test_gmail_read_normalizer.py`

**Interfaces:**

```python
class GmailReadProvider(Protocol):
    async def get_message(self, message_id: str) -> GmailMessageEnvelope: ...
    async def get_thread(self, thread_id: str) -> GmailThreadEnvelope: ...
```

```python
class GmailProviderError(Exception):
    code: str
```

```python
class GmailRestReadProvider:
    def __init__(self, client: httpx.AsyncClient, access_token: str, timeout_seconds: float = 10.0): ...
```

Provider URLs:
- `GET https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}`
- `GET https://gmail.googleapis.com/gmail/v1/users/me/threads/{thread_id}`

Use `format=metadata` and request only these headers: `From`, `To`, `Cc`, `Subject`, `In-Reply-To`, `References`.

- [ ] **Step 1: Write provider/normalizer tests first**

Use `httpx.MockTransport`. Assert:
- Authorization header is `Bearer <token>` but token never appears in returned models/errors.
- message success normalizes only allowlisted fields;
- thread success normalizes each message;
- `internalDate` milliseconds become UTC datetime;
- address headers are parsed to normalized lowercase email addresses;
- 401 → `gmail_unauthorized`;
- 403 → `gmail_forbidden`;
- 404 → `gmail_not_found`;
- 429 → `gmail_rate_limited`;
- timeout → `gmail_timeout`;
- malformed provider JSON → `gmail_payload_invalid`.

- [ ] **Step 2: Push tests and verify RED**

Expected failure: provider/normalizer modules missing.

- [ ] **Step 3: Implement payload normalization**

`normalizer.py` must:
- parse header names case-insensitively;
- use `email.utils.getaddresses()` for From/To/Cc;
- require exactly one usable `From` address;
- normalize addresses to lowercase/trimmed form;
- parse `internalDate` from milliseconds since epoch;
- copy only `message_id`, `thread_id`, time, labels and allowlisted headers into `GmailMessageEnvelope`;
- reject malformed structures with `ValueError` consumed by provider as `gmail_payload_invalid`.

- [ ] **Step 4: Implement provider**

Catch `httpx.TimeoutException` separately. Map HTTP status before returning sanitized `GmailProviderError(code)`. Never expose response body or Authorization header in exception strings. Validate non-empty token at construction but do not persist it anywhere except the in-memory provider instance.

- [ ] **Step 5: Verify GREEN**

Expected: full suite passes.

- [ ] **Step 6: Commit**

Commit message: `feat: add read-only Gmail provider`.

---

### Task 3: Conservative observation classification

**Files:**
- Create: `app/adapters/gmail_read/service.py`
- Test: `tests/test_gmail_read_service.py`

**Interfaces:**

```python
class GmailReadService:
    def __init__(self, provider: GmailReadProvider, owned_addresses: set[str] | frozenset[str]): ...
    async def observe(self, selection: GmailReadSelection) -> GmailObservationResult: ...
```

Owned addresses are normalized lowercase and the set must be non-empty.

- [ ] **Step 1: Write failing service tests**

Use an in-memory fake provider and prove:

**MESSAGE_SENT ready**
- message has `SENT` label;
- sender is owned;
- at least one To/Cc recipient is external;
- result observation has:
  - `observation_id="gmail-message:m1:message-sent"`
  - `source_type="EMAIL_PROVIDER"`
  - `source_name="gmail"`
  - `source_ref="gmail:message:m1"`
  - `kind="MESSAGE_SENT"`
  - caller-supplied account/contact IDs;
  - fixed reason `selected Gmail message is confirmed in Sent`.

**MESSAGE_SENT ambiguous**
- not SENT;
- sender not owned;
- only owned recipients;
- missing usable direction.

**REPLY_RECEIVED ready**
- selected thread contains an earlier outbound owned→external message and later inbound external→owned message;
- choose the latest inbound message that has a prior outbound in the same thread;
- result uses `observation_id="gmail-message:<reply_id>:reply-received"` and `source_ref="gmail:thread:<thread_id>:message:<reply_id>"`.

**REPLY_RECEIVED ambiguous**
- inbound-only thread → `reply_without_prior_outbound`;
- same-time or backwards chronology → no observation;
- all-owned thread → no observation.

**Provider failure**
- maps `GmailProviderError.code` into `status="PROVIDER_ERROR"` with no observation and `external_actions=[]`.

- [ ] **Step 2: Push tests and verify RED**

Expected failure: `GmailReadService` missing.

- [ ] **Step 3: Implement minimal classifier**

Message selection only attempts `MESSAGE_SENT`. Thread selection only attempts `REPLY_RECEIVED`. Do not inspect subject semantics for process state. Do not create process observations.

Direction helpers:

```python
def _is_owned(address: str, owned: frozenset[str]) -> bool: ...
def _has_external_recipient(message: GmailMessageEnvelope, owned: frozenset[str]) -> bool: ...
def _is_outbound(message: GmailMessageEnvelope, owned: frozenset[str]) -> bool: ...
def _is_inbound(message: GmailMessageEnvelope, owned: frozenset[str]) -> bool: ...
```

For thread reply detection, sort by `(internal_date, message_id)` and for each inbound candidate require a strictly earlier outbound message. Return the latest qualifying inbound candidate.

- [ ] **Step 4: Verify GREEN**

Expected: full suite passes.

- [ ] **Step 5: Commit**

Commit message: `feat: classify Gmail relationship observations`.

---

### Task 4: Guarded local API wiring

**Files:**
- Create: `app/adapters/gmail_read/api.py`
- Modify: `app/main.py`
- Modify: `.env.example`
- Test: `tests/test_api_gmail_read.py`

**Interfaces:**

```python
def create_gmail_read_router(service: GmailReadService | None) -> APIRouter: ...
```

Route:

```text
POST /api/v1/adapters/gmail/observe
```

Add to `create_app`:

```python
gmail_read_service: GmailReadService | None = None
enable_gmail_read: bool | None = None
```

Add boolean env flag:

```text
OPPORTUNITY_GMAIL_READ_ENABLED=false
```

This slice does not persist OAuth credentials and does not require credentials at default startup. Runtime hosts may inject a real `GmailReadService`; enabling the route without one returns `503 gmail_read_unavailable`.

- [ ] **Step 1: Write failing API tests**

Prove:
- route absent by default;
- route appears only with `enable_gmail_read=True`;
- enabled route with `service=None` returns sanitized 503;
- injected fake service returns `GmailObservationResult`;
- endpoint result contains no body/raw payload/token;
- observation endpoint does not alter an existing Relationship Memory repository event count.

- [ ] **Step 2: Push tests and verify RED**

Expected: route/wiring missing.

- [ ] **Step 3: Implement router and guarded wiring**

Router calls only `await service.observe(selection)`. It has no bridge/repository dependency. Add `_gmail_read_enabled()` mirroring the existing boolean parser style. Include the router only when explicitly enabled.

- [ ] **Step 4: Verify GREEN**

Expected: full suite passes.

- [ ] **Step 5: Commit**

Commit message: `feat: expose guarded Gmail read endpoint`.

---

### Task 5: Release/privacy contracts and documentation

**Files:**
- Create: `tests/test_gmail_read_release_contract.py`
- Modify: `README.md`
- Modify: `ROADMAP.md`
- Modify: `.env.example` if not already committed in Task 4

- [ ] **Step 1: Write release-contract tests first**

Static/runtime assertions must prove:
- `app/operator_bridge/*.py` does not import `gmail_read`;
- Gmail provider protocol/source contains no mutation methods (`send`, `reply`, `create_draft`, `update_draft`, `trash`, `archive`, `modify_labels`, `mark_read`);
- Gmail domain models have none of `body`, `raw_body`, `raw_payload`, `provider_payload`, `token`, `attachments`, `metadata`;
- Gmail adapter source does not reference `OperatorBridgeService.import_observation`, `SQLiteRelationshipRepository`, `RelationshipService.record`, `SendGate`, `SendReceipt`, or `record_successful_send`;
- `.env.example` documents `OPPORTUNITY_GMAIL_READ_ENABLED=false` and contains no Gmail token value;
- README keeps the existing hard boundaries and documents selective Gmail read;
- ROADMAP marks V0.2E1 implemented and moves `NEXT` to the next validated adapter/classifier decision without claiming WhatsApp or Apollo implementation exists.

- [ ] **Step 2: Push tests and verify RED**

Expected: docs/release contract not yet satisfied.

- [ ] **Step 3: Update README/ROADMAP**

Document:

```text
selected Gmail message/thread
→ Gmail read-only adapter
→ OperatorObservation candidate
→ STOP
→ V0.2E preview/confirm/import separately
```

State explicitly that process-status classification remains future work and Gmail writes are absent.

For roadmap, mark:

```text
✅ V0.2E1 — Gmail Read Adapter
```

Set the next product decision to provider expansion / process classification; mention WhatsApp only as a candidate adapter, not an implemented capability.

- [ ] **Step 4: Run final verification**

Required commands/equivalent CI checks:

```bash
python -m pytest -v
python -m compileall app
git diff --check origin/main...HEAD
```

Also require the existing private/generated-file guard to pass.

- [ ] **Step 5: Commit**

Commit message: `docs: complete V0.2E1 Gmail read release`.

---

## Final Review Checklist

Before opening/merging a PR:

- [ ] All tests are green.
- [ ] Compile check is green.
- [ ] Diff whitespace check is green.
- [ ] Private/generated-file guard is green.
- [ ] No token, real email, Gmail body or raw payload is tracked.
- [ ] `app/operator_bridge` remains provider-neutral.
- [ ] Gmail adapter has no mutation method.
- [ ] `observe` never imports relationship state.
- [ ] Ambiguous evidence produces no observation.
- [ ] README/ROADMAP match actual code.
