# V0.2E Operator Observation Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provider-neutral preview→confirm→import bridge that converts authorized external facts into existing `RelationshipEvent` state without granting draft, send, enrichment, or application authority.

**Architecture:** Add `app/operator_bridge` for strict observation contracts, deterministic normalization, preview hashing, and import orchestration. Refactor Relationship Memory so dry-run preview and real record share the same transition projector and chronological validator. Register the two operator mutation routes only when explicitly enabled; keep provider SDKs, network I/O, credentials, and Outreach Core send logic outside this slice.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite, `hashlib`, canonical JSON, pytest.

**Spec:** `docs/superpowers/specs/2026-08-29-opportunity-os-v0.2e-operator-observation-bridge-design.md`

**Normative amendment:** `docs/superpowers/specs/2026-08-29-opportunity-os-v0.2e-operator-observation-bridge-approval-amendment.md`

## Global Constraints

- Supported observation kinds: `CONTACT_VERIFIED`, `MESSAGE_SENT`, `REPLY_RECEIVED`, `PROCESS_OPENED`, `PROCESS_UPDATED`, `PROCESS_CLOSED`.
- `OperatorObservation` has no free-form `metadata`, email body, raw payload, mailbox dump, or conversation-history field.
- `MESSAGE_SENT` may normalize only to `RelationshipEvent(kind="CONTACTED")`; it must never create `SendReceipt` or call the outreach send path.
- Preview performs zero writes.
- Existing identical event ID + identical payload is recognized before chronology validation and returns idempotent `ALREADY_IMPORTED` semantics.
- Existing identical event ID + different payload fails closed as `observation_identity_conflict`.
- A not-yet-imported observation with a changed relevant relationship state fails as stale preview.
- Existing relationship chronology remains authoritative.
- Existing `/api/v1/relationships/...` endpoints remain GET-only.
- `/api/v1/operator/...` routes are absent by default.
- Enabling operator routes without writable existing relationship storage returns sanitized `503 relationship_storage_unavailable` and does not create a missing database.
- `app/operator_bridge` has no Gmail, Apollo, `httpx`, `requests`, provider connector, `SendGate`, `SQLiteOutreachRepository`, `record_successful_send`, or `SendReceipt` dependency.
- Preserve these exact README boundary strings: `CV Factory does not send email and does not submit applications`, `Opportunity OS does not create Gmail drafts automatically`, `Approval is not a send command`.

---

## File Map

Create:

- `app/operator_bridge/__init__.py`
- `app/operator_bridge/models.py`
- `app/operator_bridge/normalizer.py`
- `app/operator_bridge/service.py`
- `app/operator_bridge/api.py`
- `tests/test_operator_models.py`
- `tests/test_operator_normalizer.py`
- `tests/test_operator_service.py`
- `tests/test_api_operator_bridge.py`
- `tests/test_operator_release_contract.py`

Modify:

- `app/relationships/repository.py`
- `app/relationships/service.py`
- `app/main.py`
- `.env.example`
- `README.md`
- `ROADMAP.md`
- `docs/superpowers/specs/2026-08-29-opportunity-os-v0.2e-operator-observation-bridge-design.md`

Do not modify provider connectors or any file under the Outreach Core send path.

---

### Task 1: Shared relationship dry-run projection

**Files:**
- Modify: `app/relationships/repository.py`
- Modify: `app/relationships/service.py`
- Test: `tests/test_relationship_repository.py`
- Test: `tests/test_relationship_service.py`

**Interfaces:**
- Add `EventDisposition = Literal["NEW", "IDENTICAL"]`.
- Add `SQLiteRelationshipRepository.validate_event(event: RelationshipEvent) -> EventDisposition`.
- Add `RelationshipProjection` with `account: RelationshipAccount` and `contacts: tuple[CareerContact, ...]`.
- Add `RelationshipService.preview(event: RelationshipEvent) -> RelationshipProjection`.
- Keep `RelationshipService.record(event: RelationshipEvent) -> RelationshipAccount`.
- Extract all event-kind transition logic into one `_project()` method used by both preview and record.

- [ ] **Step 1: Add repository tests first**

Add these concrete tests:

```python
def test_validate_event_identical_replay_precedes_chronology(tmp_path: Path) -> None:
    repo = _relationship_repo(tmp_path)
    event = RelationshipEvent(
        event_id="event-1",
        account_id="account-1",
        kind="CONTACTED",
        occurred_at=NOW,
        metadata={"official_channel": "manual"},
    )
    repo.append_event(event)

    assert repo.validate_event(event) == "IDENTICAL"
    assert repo.list_events("account-1") == [event]


def test_validate_event_rejects_new_out_of_order_event_without_write(tmp_path: Path) -> None:
    repo = _relationship_repo(tmp_path)
    newer = RelationshipEvent(
        event_id="event-new",
        account_id="account-1",
        kind="CONTACTED",
        occurred_at=NOW,
        metadata={"official_channel": "manual"},
    )
    older = RelationshipEvent(
        event_id="event-old",
        account_id="account-1",
        kind="CONTACTED",
        occurred_at=NOW - timedelta(days=1),
        metadata={"official_channel": "manual"},
    )
    repo.append_event(newer)

    with pytest.raises(ValueError, match="out-of-order relationship event"):
        repo.validate_event(older)

    assert repo.get_event("event-old") is None
    assert repo.list_events("account-1") == [newer]
```

- [ ] **Step 2: Run repository tests and confirm RED**

```bash
python -m pytest tests/test_relationship_repository.py -v
```

Expected: the new tests fail because `validate_event` is missing.

- [ ] **Step 3: Implement one read-only event validator**

Add:

```python
from typing import Literal

EventDisposition = Literal["NEW", "IDENTICAL"]


def _validate_event_conn(
    self,
    conn: sqlite3.Connection,
    event: RelationshipEvent,
) -> EventDisposition:
    existing = self._get_event_conn(conn, event.event_id)
    if existing is not None:
        if existing != event:
            raise ValueError("relationship event_id conflict")
        return "IDENTICAL"

    latest_order = self._latest_event_order_conn(conn, event.account_id)
    if latest_order is not None and (event.occurred_at, event.event_id) <= latest_order:
        raise ValueError("out-of-order relationship event")
    return "NEW"


def validate_event(self, event: RelationshipEvent) -> EventDisposition:
    with self._connect() as conn:
        return self._validate_event_conn(conn, event)
```

Replace the duplicate existing-ID/chronology checks inside `_append_event_conn()` with a call to `_validate_event_conn()`. Insert only for `NEW`; return existing event with `inserted=False` for `IDENTICAL`.

- [ ] **Step 4: Add service preview tests first**

Add:

```python
def test_preview_projects_same_account_as_record_without_writing(tmp_path: Path) -> None:
    repo = _relationship_repo(tmp_path)
    service = RelationshipService(repo)
    original = RelationshipAccount(
        account_id="account-1",
        company="Example Co",
        updated_at=NOW - timedelta(days=1),
    )
    service.register_account(original)
    event = RelationshipEvent(
        event_id="event-1",
        account_id="account-1",
        kind="CONTACTED",
        occurred_at=NOW,
        reason="authorized observation",
        metadata={"official_channel": "manual"},
    )

    projection = service.preview(event)

    assert projection.account.relationship_state == "CONTACTED"
    assert repo.get_event("event-1") is None
    assert repo.get_account("account-1") == original

    recorded = service.record(event)
    assert recorded == projection.account


def test_preview_rejects_process_close_without_open_process(tmp_path: Path) -> None:
    repo = _relationship_repo(tmp_path)
    service = RelationshipService(repo)
    service.register_account(
        RelationshipAccount(
            account_id="account-1",
            company="Example Co",
            updated_at=NOW - timedelta(days=1),
        )
    )
    event = RelationshipEvent(
        event_id="event-close",
        account_id="account-1",
        kind="PROCESS_CLOSED",
        occurred_at=NOW,
    )

    with pytest.raises(ValueError, match="PROCESS_CLOSED requires open process"):
        service.preview(event)

    assert repo.get_event("event-close") is None
```

- [ ] **Step 5: Run service tests and confirm RED**

```bash
python -m pytest tests/test_relationship_service.py -v
```

Expected: new tests fail because `preview` and `RelationshipProjection` are missing.

- [ ] **Step 6: Extract the existing nested projector without changing its event semantics**

Add:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class RelationshipProjection:
    account: RelationshipAccount
    contacts: tuple[CareerContact, ...]
```

Create this method on `RelationshipService`:

```python
def _project(
    self,
    event: RelationshipEvent,
    account: RelationshipAccount | None,
    contacts: list[CareerContact],
) -> tuple[RelationshipAccount, list[CareerContact]]:
```

Move the complete current event-kind branch from the nested `projector()` inside `record()` into `_project()` unchanged in behavior. The method must preserve every current guard for `CONTACT_VERIFIED`, `CONTACT_HELD`, `CONTACT_RELEASED`, `CONTACTED`, `REPLIED`, `PROCESS_OPENED`, `PROCESS_UPDATED`, `PROCESS_CLOSED`, `COOLDOWN_SET`, `COOLDOWN_CLEARED`, and `NOTE_RECORDED`.

Then implement preview exactly as:

```python
def preview(self, event: RelationshipEvent) -> RelationshipProjection:
    disposition = self.repository.validate_event(event)
    account = self.repository.get_account(event.account_id)
    contacts = self.repository.list_contacts(event.account_id)

    if disposition == "IDENTICAL":
        if account is None:
            raise ValueError("idempotent event has no relationship account projection")
        return RelationshipProjection(account=account, contacts=tuple(contacts))

    next_account, next_contacts = self._project(event, account, contacts)
    return RelationshipProjection(account=next_account, contacts=tuple(next_contacts))
```

Replace the nested `projector()` in `record()` with:

```python
def projector(
    account: RelationshipAccount | None,
    contacts: list[CareerContact],
) -> tuple[RelationshipAccount, list[CareerContact]]:
    return self._project(event, account, contacts)
```

- [ ] **Step 7: Run focused relationship tests**

```bash
python -m pytest tests/test_relationship_repository.py tests/test_relationship_service.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/relationships/repository.py app/relationships/service.py tests/test_relationship_repository.py tests/test_relationship_service.py
git commit -m "refactor: add relationship dry-run projection"
```

---

### Task 2: Strict operator contracts and deterministic hashes

**Files:**
- Create: `app/operator_bridge/__init__.py`
- Create: `app/operator_bridge/models.py`
- Test: `tests/test_operator_models.py`

**Interfaces:**
- Add literals `ObservationSourceType`, `ObservationKind`, `PreviewStatus`, `ObservationImportStatus`.
- Add models `OperatorObservation`, `ObservationPreview`, `ObservationImportRequest`, `ObservationImportReceipt`, `ObservationImportResult`.
- Add `canonical_sha256(value: BaseModel | dict[str, object]) -> str`.
- Add `observation_sha256(observation: OperatorObservation) -> str`.
- Add constants `PREVIEW_VERSION = "operator-preview-v1"` and `STATE_VERSION = "relationship-state-v1"`.

- [ ] **Step 1: Write model tests first**

Create tests with these exact assertions:

```python
def test_operator_observation_is_strict_and_normalizes_time() -> None:
    observation = OperatorObservation(
        observation_id="gmail-message-1",
        source_type="EMAIL_PROVIDER",
        source_name="gmail",
        source_ref="message:gmail-message-1",
        kind="REPLY_RECEIVED",
        account_id="example-co",
        observed_at=datetime(2026, 8, 29, 9, 0, tzinfo=timezone(timedelta(hours=-3))),
        reason="recruiter replied",
    )
    assert observation.observed_at == datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def test_operator_observation_rejects_raw_body_and_metadata() -> None:
    base = {
        "observation_id": "obs-1",
        "source_type": "MANUAL",
        "source_name": "manual",
        "source_ref": "manual:obs-1",
        "kind": "PROCESS_OPENED",
        "account_id": "example-co",
        "observed_at": datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
    }
    with pytest.raises(ValidationError):
        OperatorObservation(**base, body="secret")
    with pytest.raises(ValidationError):
        OperatorObservation(**base, metadata={"raw_payload": "secret"})


def test_same_observation_has_stable_hash() -> None:
    observation = _observation()
    assert observation_sha256(observation) == observation_sha256(observation.model_copy())
```

Also add one test proving `ObservationImportRequest` rejects `confirmed_at < observation.observed_at`, and one proving `ObservationPreview` rejects non-empty `external_actions`.

- [ ] **Step 2: Run tests and confirm RED**

```bash
python -m pytest tests/test_operator_models.py -v
```

Expected: import failure for `app.operator_bridge.models`.

- [ ] **Step 3: Implement the exact model surface**

Use one strict base:

```python
class StrictOperatorModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

Define:

```python
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
```

`OperatorObservation` fields are exactly: `observation_id`, `source_type`, `source_name`, `source_ref`, `kind`, `account_id`, `contact_id`, `observed_at`, `reason`, `process_label`.

`ObservationPreview` fields are exactly: `preview_version`, `status`, `observation_id`, `observation_sha256`, `preview_sha256`, `account_id`, `contact_id`, `event_kind`, `state_before`, `state_after`, `open_process_before`, `open_process_after`, `source_type`, `source_name`, `source_ref`, `reason`, `errors`, `external_actions`.

`ObservationImportRequest` fields are `observation`, `preview_sha256`, `confirmed_by`, `confirmed_at`.

`ObservationImportReceipt` fields are `receipt_id`, `observation_id`, `observation_sha256`, `preview_sha256`, `relationship_event_id`, `account_id`, `contact_id`, `source_type`, `source_name`, `source_ref`, `confirmed_by`, `confirmed_at`, `processed_at`, `status` where receipt status is `Literal["IMPORTED", "ALREADY_IMPORTED"]`.

`ObservationImportResult` fields are `status`, `receipt`, `errors`.

Normalize every datetime to UTC and reject naive datetimes. Validate `confirmed_at >= observation.observed_at`. Validate non-empty identifiers/refs with `Field(min_length=1)`. Validate SHA fields with `min_length=64, max_length=64`.

- [ ] **Step 4: Implement canonical hashing**

```python
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
```

- [ ] **Step 5: Run model tests**

```bash
python -m pytest tests/test_operator_models.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/operator_bridge/__init__.py app/operator_bridge/models.py tests/test_operator_models.py
git commit -m "feat: add operator observation contracts"
```

---

### Task 3: Deterministic observation normalizer

**Files:**
- Create: `app/operator_bridge/normalizer.py`
- Test: `tests/test_operator_normalizer.py`

**Interfaces:**
- Add `relationship_event_id(observation: OperatorObservation) -> str`.
- Add `normalize_observation(observation: OperatorObservation) -> RelationshipEvent`.

- [ ] **Step 1: Write mapping tests first**

Create a parameterized test with this full mapping:

```python
@pytest.mark.parametrize(
    ("kind", "expected_event_kind"),
    [
        ("CONTACT_VERIFIED", "CONTACT_VERIFIED"),
        ("MESSAGE_SENT", "CONTACTED"),
        ("REPLY_RECEIVED", "REPLIED"),
        ("PROCESS_OPENED", "PROCESS_OPENED"),
        ("PROCESS_UPDATED", "PROCESS_UPDATED"),
        ("PROCESS_CLOSED", "PROCESS_CLOSED"),
    ],
)
def test_normalizer_maps_supported_kinds(kind: str, expected_event_kind: str) -> None:
    observation = _observation(kind=kind)
    if kind == "CONTACT_VERIFIED":
        observation = observation.model_copy(update={"contact_id": "contact-1"})
    event = normalize_observation(observation)
    assert event.kind == expected_event_kind
    assert event.account_id == observation.account_id
    assert event.source_ref == observation.source_ref
    assert event.occurred_at == observation.observed_at
```

Add tests proving:

```python
def test_same_source_identity_produces_same_event_id_even_if_semantics_change() -> None:
    first = _observation(reason="first")
    second = first.model_copy(update={"reason": "second"})
    assert relationship_event_id(first) == relationship_event_id(second)
    assert normalize_observation(first) != normalize_observation(second)


def test_account_level_message_sent_adds_only_official_channel_bridge_metadata() -> None:
    event = normalize_observation(_observation(kind="MESSAGE_SENT", contact_id=None))
    assert event.metadata["official_channel"] == "operator_observation"
    assert set(event.metadata) == {
        "operator_source_type",
        "operator_source_name",
        "operator_observation_id",
        "operator_observation_sha256",
        "official_channel",
    }
```

Also assert `CONTACT_VERIFIED` without `contact_id` raises `ValueError("CONTACT_VERIFIED requires contact_id")` and process labels only appear as `process_label` metadata for process events.

- [ ] **Step 2: Run tests and confirm RED**

```bash
python -m pytest tests/test_operator_normalizer.py -v
```

Expected: import failure for `app.operator_bridge.normalizer`.

- [ ] **Step 3: Implement deterministic event ID**

```python
def relationship_event_id(observation: OperatorObservation) -> str:
    identity = f"{observation.source_type}|{observation.source_name}|{observation.observation_id}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"opobs-{digest}"
```

- [ ] **Step 4: Implement pure normalization**

Use this mapping dictionary:

```python
_EVENT_KIND = {
    "CONTACT_VERIFIED": "CONTACT_VERIFIED",
    "MESSAGE_SENT": "CONTACTED",
    "REPLY_RECEIVED": "REPLIED",
    "PROCESS_OPENED": "PROCESS_OPENED",
    "PROCESS_UPDATED": "PROCESS_UPDATED",
    "PROCESS_CLOSED": "PROCESS_CLOSED",
}
```

Build metadata from only these keys:

```python
metadata = {
    "operator_source_type": observation.source_type,
    "operator_source_name": observation.source_name,
    "operator_observation_id": observation.observation_id,
    "operator_observation_sha256": observation_sha256(observation),
}
```

Add `process_label` only for the three process kinds when supplied. Add `official_channel="operator_observation"` only for `MESSAGE_SENT` with `contact_id is None`.

Return a `RelationshipEvent` with deterministic `event_id`, copied account/contact/time/reason/source_ref, mapped kind, and allowlisted metadata.

- [ ] **Step 5: Run normalizer tests**

```bash
python -m pytest tests/test_operator_normalizer.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/operator_bridge/normalizer.py tests/test_operator_normalizer.py
git commit -m "feat: normalize operator observations"
```

---

### Task 4: Preview hashing and confirmed idempotent import

**Files:**
- Create: `app/operator_bridge/service.py`
- Test: `tests/test_operator_service.py`

**Interfaces:**
- Add `OperatorBridgeService(repository: SQLiteRelationshipRepository, relationships: RelationshipService)`.
- Add `OperatorBridgeService.preview(observation: OperatorObservation) -> ObservationPreview`.
- Add `OperatorBridgeService.import_observation(request: ObservationImportRequest, *, processed_at: datetime) -> ObservationImportResult`.

- [ ] **Step 1: Write preview tests first**

Seed a fictional account and optional contact through existing relationship services. Add tests with these exact behavioral assertions:

```python
def test_preview_is_read_only_and_returns_importable_projection(tmp_path: Path) -> None:
    repo, relationships, bridge = _bridge(tmp_path)
    original = repo.get_account("example-co")
    before_events = repo.list_events("example-co")

    preview = bridge.preview(_observation(kind="MESSAGE_SENT"))

    assert preview.status == "IMPORTABLE"
    assert preview.event_kind == "CONTACTED"
    assert preview.state_before == "UNTOUCHED"
    assert preview.state_after == "CONTACTED"
    assert preview.external_actions == []
    assert repo.get_account("example-co") == original
    assert repo.list_events("example-co") == before_events


def test_same_observation_and_same_state_produce_same_preview_hash(tmp_path: Path) -> None:
    _, _, bridge = _bridge(tmp_path)
    observation = _observation(kind="MESSAGE_SENT")
    assert bridge.preview(observation).preview_sha256 == bridge.preview(observation).preview_sha256
```

Add separate tests asserting changed observation reason, changed account state, and changed referenced contact state each change `preview_sha256`.

Add a conflict test by inserting an event with the same deterministic event ID but a different event payload and asserting preview returns `BLOCKED` with `errors == ["observation_identity_conflict"]`.

Add an out-of-order test asserting preview returns `BLOCKED` with `errors == ["out_of_order_observation"]` and no write.

- [ ] **Step 2: Run preview tests and confirm RED**

```bash
python -m pytest tests/test_operator_service.py -k preview -v
```

Expected: import failure for `app.operator_bridge.service`.

- [ ] **Step 3: Implement stable public error mapping**

```python
def _domain_error_code(exc: ValueError) -> str:
    text = str(exc)
    if "out-of-order" in text:
        return "out_of_order_observation"
    if "contact" in text:
        return "unknown_or_invalid_contact"
    if "account must be registered" in text:
        return "unknown_relationship_account"
    return "invalid_relationship_transition"
```

Do not expose `str(exc)` in `ObservationPreview.errors` or API responses.

- [ ] **Step 4: Implement state fingerprint**

Use:

```python
def _state_sha256(
    account: RelationshipAccount,
    contact: CareerContact | None,
) -> str:
    return canonical_sha256(
        {
            "state_version": STATE_VERSION,
            "account": account.model_dump(mode="json", exclude_none=False),
            "contact": (
                contact.model_dump(mode="json", exclude_none=False)
                if contact is not None
                else None
            ),
        }
    )
```

- [ ] **Step 5: Implement preview in the required order**

The method must perform these concrete steps in this order:

1. `event = normalize_observation(observation)`.
2. `existing = repository.get_event(event.event_id)`.
3. Existing equal event → build redacted `ALREADY_IMPORTED` preview without projecting a new transition.
4. Existing different event → return `BLOCKED` with `observation_identity_conflict`.
5. Load account; missing account → `BLOCKED` with `unknown_relationship_account`.
6. If `contact_id` exists, load contact and require `contact.account_id == observation.account_id`; otherwise return `BLOCKED` with `unknown_or_invalid_contact`.
7. Call `relationships.preview(event)`; map any `ValueError` to one stable code.
8. Compute `state_sha256` from current account and referenced contact.
9. Compute preview hash from exactly `{preview_version, observation_sha256, normalized_event, state_sha256}` using `canonical_sha256`.
10. Return redacted before/after account state, open-process flags, source fields, reason, errors, and `external_actions=[]`.

- [ ] **Step 6: Write import tests before import implementation**

Add:

```python
def test_exact_confirmed_preview_imports_once(tmp_path: Path) -> None:
    repo, _, bridge = _bridge(tmp_path)
    observation = _observation(kind="MESSAGE_SENT")
    preview = bridge.preview(observation)
    request = ObservationImportRequest(
        observation=observation,
        preview_sha256=preview.preview_sha256,
        confirmed_by="operator",
        confirmed_at=NOW,
    )

    result = bridge.import_observation(request, processed_at=NOW)

    assert result.status == "IMPORTED"
    assert result.receipt is not None
    assert len(repo.list_events("example-co")) == 1


def test_exact_retry_returns_already_imported_before_stale_check(tmp_path: Path) -> None:
    repo, _, bridge = _bridge(tmp_path)
    observation = _observation(kind="MESSAGE_SENT")
    preview = bridge.preview(observation)
    request = ObservationImportRequest(
        observation=observation,
        preview_sha256=preview.preview_sha256,
        confirmed_by="operator",
        confirmed_at=NOW,
    )

    first = bridge.import_observation(request, processed_at=NOW)
    second = bridge.import_observation(request, processed_at=NOW + timedelta(seconds=1))

    assert first.status == "IMPORTED"
    assert second.status == "ALREADY_IMPORTED"
    assert first.receipt is not None
    assert second.receipt is not None
    assert first.receipt.receipt_id == second.receipt.receipt_id
    assert len(repo.list_events("example-co")) == 1
```

Add tests for identity conflict, stale state before first import, blocked domain transition, stable receipt ID, and naive `processed_at` rejection.

- [ ] **Step 7: Implement receipt construction**

Receipt identity:

```python
def _receipt_id(event: RelationshipEvent) -> str:
    digest = hashlib.sha256(event.event_id.encode("utf-8")).hexdigest()
    return f"opreceipt-{digest}"
```

`processed_at` must be timezone-aware and normalized to UTC. Receipt status is exactly `IMPORTED` or `ALREADY_IMPORTED`.

- [ ] **Step 8: Implement import with idempotent retry precedence**

Use this exact control flow:

```python
def import_observation(
    self,
    request: ObservationImportRequest,
    *,
    processed_at: datetime,
) -> ObservationImportResult:
    processed_at = _aware_utc(processed_at)
    event = normalize_observation(request.observation)
    existing = self.repository.get_event(event.event_id)

    if existing is not None:
        if existing != event:
            return ObservationImportResult(
                status="CONFLICT",
                errors=["observation_identity_conflict"],
            )
        return ObservationImportResult(
            status="ALREADY_IMPORTED",
            receipt=self._build_receipt(
                request=request,
                event=event,
                processed_at=processed_at,
                status="ALREADY_IMPORTED",
            ),
        )

    preview = self.preview(request.observation)
    if preview.preview_sha256 != request.preview_sha256:
        return ObservationImportResult(
            status="BLOCKED_STALE_PREVIEW",
            errors=["stale_preview"],
        )
    if preview.status == "BLOCKED":
        return ObservationImportResult(
            status="BLOCKED_DOMAIN",
            errors=list(preview.errors),
        )

    try:
        self.relationships.record(event)
    except ValueError as exc:
        return ObservationImportResult(
            status="BLOCKED_DOMAIN",
            errors=[_domain_error_code(exc)],
        )

    return ObservationImportResult(
        status="IMPORTED",
        receipt=self._build_receipt(
            request=request,
            event=event,
            processed_at=processed_at,
            status="IMPORTED",
        ),
    )
```

- [ ] **Step 9: Run operator service tests**

```bash
python -m pytest tests/test_operator_service.py -v
```

Expected: PASS.

- [ ] **Step 10: Run Tasks 1–4 together**

```bash
python -m pytest tests/test_relationship_repository.py tests/test_relationship_service.py tests/test_operator_models.py tests/test_operator_normalizer.py tests/test_operator_service.py -v
```

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add app/operator_bridge/service.py tests/test_operator_service.py
git commit -m "feat: add observation preview and confirmed import"
```

---

### Task 5: Disabled-by-default operator API and release boundaries

**Files:**
- Create: `app/operator_bridge/api.py`
- Modify: `app/main.py`
- Modify: `.env.example`
- Create: `tests/test_api_operator_bridge.py`
- Create: `tests/test_operator_release_contract.py`
- Modify: `README.md`
- Modify: `ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-08-29-opportunity-os-v0.2e-operator-observation-bridge-design.md`

**Interfaces:**
- Add `create_operator_router(service: OperatorBridgeService | None) -> APIRouter`.
- Add `POST /api/v1/operator/observations/preview`.
- Add `POST /api/v1/operator/observations/import`.
- Extend `create_app()` with `operator_bridge_service: OperatorBridgeService | None = None` and `enable_operator_import: bool | None = None`.

- [ ] **Step 1: Write disabled/default API tests first**

```python
def test_operator_routes_are_absent_by_default() -> None:
    app = create_app(
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )
    assert not any(
        path.startswith("/api/v1/operator/")
        for path in app.openapi()["paths"]
    )


def test_relationship_routes_remain_get_only() -> None:
    app = create_app(
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )
    relationship_paths = {
        path: operations
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/v1/relationships")
    }
    assert set(relationship_paths) == {
        "/api/v1/relationships/context",
        "/api/v1/relationships/{account_id}/context",
    }
    for operations in relationship_paths.values():
        assert set(operations).isdisjoint({"post", "put", "patch", "delete"})
```

Add enabled tests using a temporary real relationship DB and injected bridge service. Assert preview is 200 and no write; import is 200 and creates one event; retry is `ALREADY_IMPORTED`; response JSON has none of `person`, `channel_value`, `body`, `raw_payload`.

Add an enabled-without-service test asserting both operator routes return HTTP 503 with `detail == "relationship_storage_unavailable"`.

- [ ] **Step 2: Run API tests and confirm RED**

```bash
python -m pytest tests/test_api_operator_bridge.py -v
```

Expected: fail because operator API wiring does not exist.

- [ ] **Step 3: Implement isolated router**

```python
def create_operator_router(service: OperatorBridgeService | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/operator")

    @router.post("/observations/preview", response_model=ObservationPreview)
    def preview_observation(observation: OperatorObservation) -> ObservationPreview:
        if service is None:
            raise HTTPException(status_code=503, detail="relationship_storage_unavailable")
        return service.preview(observation)

    @router.post("/observations/import", response_model=ObservationImportResult)
    def import_observation(request: ObservationImportRequest) -> ObservationImportResult:
        if service is None:
            raise HTTPException(status_code=503, detail="relationship_storage_unavailable")
        return service.import_observation(
            request,
            processed_at=datetime.now(timezone.utc),
        )

    return router
```

- [ ] **Step 4: Add strict enablement parsing to `app/main.py`**

```python
def _operator_import_enabled() -> bool:
    raw = os.getenv("OPPORTUNITY_OPERATOR_IMPORT_ENABLED", "false").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("OPPORTUNITY_OPERATOR_IMPORT_ENABLED must be boolean")
```

Extend `create_app()` with the two operator parameters. Resolve enablement from the explicit argument when non-`None`, otherwise from the env parser.

If enabled and no injected bridge service exists, read the configured `OPPORTUNITY_RELATIONSHIPS_PATH`. If the file does not exist, leave the bridge service as `None`; do not call `initialize()` and do not create the file. If the file exists, construct `SQLiteRelationshipRepository`, initialize schema, then construct `RelationshipService` and `OperatorBridgeService`.

Include `create_operator_router()` only when operator import is enabled.

- [ ] **Step 5: Add environment example**

Append exactly:

```text
OPPORTUNITY_OPERATOR_IMPORT_ENABLED=false
```

Do not reformat unrelated `.env.example` lines.

- [ ] **Step 6: Run API tests**

```bash
python -m pytest tests/test_api_operator_bridge.py tests/test_relationship_release_contract.py -v
```

Expected: PASS.

- [ ] **Step 7: Write release/privacy tests before docs**

Create tests that read all `app/operator_bridge/*.py` and assert none of these lowercase tokens exist:

```python
forbidden = {
    "import gmail",
    "from gmail",
    "import apollo",
    "from apollo",
    "import httpx",
    "from httpx",
    "import requests",
    "from requests",
    "sqliteoutreachrepository",
    "sendgate",
    "record_successful_send",
    "sendreceipt",
}
```

Also assert `OperatorObservation.model_fields` is disjoint from:

```python
{
    "body",
    "raw_body",
    "message_body",
    "raw_payload",
    "provider_payload",
    "mailbox_dump",
    "conversation_history",
    "metadata",
}
```

Add README assertions for `Observe → preview → confirm → import local fact`, `An imported observation is evidence about what happened; it is not authority to make something happen.`, and the three existing hard boundary strings.

Add ROADMAP assertion for `### ✅ V0.2E — Operator Observation Bridge` and a statement that Gmail/provider adapters remain future work.

- [ ] **Step 8: Run release tests and confirm RED on docs**

```bash
python -m pytest tests/test_operator_release_contract.py -v
```

Expected: runtime/static boundary assertions pass; README/ROADMAP/status assertions fail until documentation is updated.

- [ ] **Step 9: Update README**

Add a concise section with exactly:

```text
Observe → preview → confirm → import local fact
```

Explain that preview is a dry-run against current relationship state, confirmation is bound to an exact hash, import changes only local Relationship Memory, and V0.2E does not read Gmail or call providers by itself.

Include exactly:

```text
An imported observation is evidence about what happened; it is not authority to make something happen.
```

Preserve the existing CV Factory, Gmail draft, and approval/send boundary strings unchanged.

- [ ] **Step 10: Update ROADMAP**

Mark V0.2E complete with these implemented facts: provider-neutral observation contract; deterministic event IDs; dry-run preview; exact preview hash; explicit confirmed import; idempotent retry; identity conflicts; disabled-by-default operator routes; relationship-only `MESSAGE_SENT`; no provider SDK/network integration.

Set NEXT to `V0.2E1 — Gmail read adapter` and keep monitoring/follow-up after provider observation adapters.

- [ ] **Step 11: Mark the main design status approved**

Change only the header line:

```text
Status: proposed
```

to:

```text
Status: approved
```

Keep the approval/idempotent-retry amendment unchanged.

- [ ] **Step 12: Run the full test suite**

```bash
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 13: Compile application**

```bash
python -m compileall app
```

Expected: exit 0.

- [ ] **Step 14: Verify whitespace**

```bash
git diff --check origin/main...HEAD
```

Expected: no output and exit 0.

- [ ] **Step 15: Verify provider/send boundary statically**

```bash
python - <<'PY'
from pathlib import Path
text = "\n".join(
    path.read_text(encoding="utf-8").lower()
    for path in Path("app/operator_bridge").glob("*.py")
)
forbidden = [
    "import gmail",
    "from gmail",
    "import apollo",
    "from apollo",
    "import httpx",
    "from httpx",
    "import requests",
    "from requests",
    "sqliteoutreachrepository",
    "sendgate",
    "record_successful_send",
    "sendreceipt",
]
found = [token for token in forbidden if token in text]
assert found == [], found
print("operator bridge boundary: OK")
PY
```

Expected: `operator bridge boundary: OK`.

- [ ] **Step 16: Verify no private local data is tracked**

```bash
set -euo pipefail
forbidden="$(git ls-files -- \
  'state/relationships.local.sqlite3*' \
  'state/outreach.local.sqlite3' \
  'profile.local.yaml' \
  'targets.local.yaml')"
test -z "$forbidden"
```

Expected: exit 0 and no printed private paths.

- [ ] **Step 17: Run release-contract suites together**

```bash
python -m pytest tests/test_operator_release_contract.py tests/test_relationship_release_contract.py tests/test_outreach_release_contract.py tests/test_cv_release_contract.py -v
```

Expected: PASS.

- [ ] **Step 18: Commit final release/docs block**

```bash
git add app/operator_bridge/api.py app/main.py .env.example tests/test_api_operator_bridge.py tests/test_operator_release_contract.py README.md ROADMAP.md docs/superpowers/specs/2026-08-29-opportunity-os-v0.2e-operator-observation-bridge-design.md
git commit -m "feat: release v0.2e operator observation bridge"
```

---

## Final Review Checklist

- [ ] `RelationshipService.preview()` and `record()` share one `_project()` implementation.
- [ ] Identical event detection precedes chronology validation.
- [ ] Preview changes no account, contact, event, or external provider state.
- [ ] Preview hash includes observation semantics, normalized event, and relevant relationship state.
- [ ] Exact retry after successful import returns `ALREADY_IMPORTED` before stale-preview evaluation.
- [ ] Same identity with changed semantics returns conflict.
- [ ] `MESSAGE_SENT` produces only relationship `CONTACTED` history.
- [ ] No provider/network or Outreach Core send dependency exists in `app/operator_bridge`.
- [ ] Operator routes are absent by default.
- [ ] Enabled bridge with missing relationship DB returns sanitized 503 and does not create the DB.
- [ ] Relationship API remains GET-only.
- [ ] Observation contracts have no raw-body/raw-payload/free-form metadata field.
- [ ] README does not claim Gmail/Apollo integration exists.
- [ ] Full tests, compile, whitespace, privacy, and release-contract checks pass.

## Expected Outcome

After V0.2E, an authorized future adapter or human operator can supply one normalized fact, see the exact local Relationship Memory transition it would cause, explicitly confirm the exact preview, and import that fact idempotently. Opportunity OS still cannot read Gmail by itself, consume Apollo credits, create Gmail drafts automatically, send email, submit applications, or fabricate Outreach Core receipts.