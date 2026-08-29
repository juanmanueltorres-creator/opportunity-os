# V0.2E Operator Observation Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provider-neutral, explicit preview→confirm→import bridge that turns authorized external facts into existing `RelationshipEvent` state without granting any draft/send/application authority.

**Architecture:** Add a small `app/operator_bridge` package that owns strict observation contracts, deterministic normalization, preview hashing and import orchestration. Refactor Relationship Memory so preview and record share one pure projector and one chronology validator; keep `RelationshipService` as the sole state-transition owner. Register operator write routes only when explicitly enabled, and never add provider SDK/network dependencies in V0.2E.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite, hashlib/JSON canonicalization, pytest.

**Spec:** `docs/superpowers/specs/2026-08-29-opportunity-os-v0.2e-operator-observation-bridge-design.md`

**Normative amendment:** `docs/superpowers/specs/2026-08-29-opportunity-os-v0.2e-operator-observation-bridge-approval-amendment.md`

## Global Constraints

- `OperatorObservation` is provider-neutral; no Gmail/Apollo SDK or HTTP/network call belongs in `app/operator_bridge`.
- V0.2E supports only `CONTACT_VERIFIED`, `MESSAGE_SENT`, `REPLY_RECEIVED`, `PROCESS_OPENED`, `PROCESS_UPDATED`, `PROCESS_CLOSED`.
- No raw email body, raw provider payload, mailbox dump or free-form observation metadata field.
- `MESSAGE_SENT` may only create relationship history (`CONTACTED`); it must never create `SendReceipt` or call the outreach send path.
- Preview performs zero writes.
- Import requires the exact deterministic preview hash unless the exact deterministic event is already stored; exact retries return `ALREADY_IMPORTED` before stale-preview evaluation.
- Same observation identity with changed semantics fails closed.
- Existing V0.2D chronological ordering remains authoritative.
- Existing `/api/v1/relationships/...` routes remain GET-only.
- `/api/v1/operator/...` routes are absent by default and are registered only when `OPPORTUNITY_OPERATOR_IMPORT_ENABLED=true` or an explicit test injection enables them.
- Enabling operator routes without writable relationship storage returns sanitized `503 relationship_storage_unavailable`.
- Preserve hard product boundaries: `CV Factory does not send email and does not submit applications.`, `Opportunity OS does not create Gmail drafts automatically.`, and `Approval is not a send command.`

---

## File Structure

Create:

- `app/operator_bridge/__init__.py` — package marker only.
- `app/operator_bridge/models.py` — strict observation/preview/import contracts plus canonical hashing helpers.
- `app/operator_bridge/normalizer.py` — pure `OperatorObservation -> RelationshipEvent` translation.
- `app/operator_bridge/service.py` — preview/import orchestration and stable domain-error mapping.
- `app/operator_bridge/api.py` — isolated FastAPI router for the two operator endpoints.
- `tests/test_operator_models.py`
- `tests/test_operator_normalizer.py`
- `tests/test_operator_service.py`
- `tests/test_api_operator_bridge.py`
- `tests/test_operator_release_contract.py`

Modify:

- `app/relationships/repository.py` — expose read-only event disposition/chronology validation used by preview and append.
- `app/relationships/service.py` — extract one pure projector and add `preview(event)`.
- `app/main.py` — resolve optional writable relationship service/operator bridge and conditionally register operator routes.
- `.env.example` — add `OPPORTUNITY_OPERATOR_IMPORT_ENABLED=false`.
- `README.md` — document Observe→preview→confirm→import and operator boundary.
- `ROADMAP.md` — mark V0.2E complete only after implementation and move NEXT to Gmail read adapter or monitoring per approved roadmap.

Do not modify `app/outreach/send.py`, `app/outreach/repository.py`, or provider connectors for this slice.

---

### Task 1: Make RelationshipService previewable without duplicating transition rules

**Files:**
- Modify: `app/relationships/repository.py`
- Modify: `app/relationships/service.py`
- Test: `tests/test_relationship_repository.py`
- Test: `tests/test_relationship_service.py`

**Interfaces:**
- Produces: `EventDisposition = Literal["NEW", "IDENTICAL"]` in `app.relationships.repository`.
- Produces: `SQLiteRelationshipRepository.validate_event(event: RelationshipEvent) -> EventDisposition`.
- Produces: `RelationshipProjection` in `app.relationships.service` with `account: RelationshipAccount` and `contacts: tuple[CareerContact, ...]`.
- Produces: `RelationshipService.preview(event: RelationshipEvent) -> RelationshipProjection`.
- Keeps: `RelationshipService.record(event: RelationshipEvent) -> RelationshipAccount`.
- Both `preview()` and `record()` must call one `_project(event, account, contacts)` transition implementation.

- [ ] **Step 1: Add repository RED tests for read-only event validation**

Add tests proving:

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


def test_validate_event_rejects_new_out_of_order_event_without_write(tmp_path: Path) -> None:
    repo = _relationship_repo(tmp_path)
    newer = RelationshipEvent(
        event_id="event-new",
        account_id="account-1",
        kind="CONTACTED",
        occurred_at=NOW,
        metadata={"official_channel": "manual"},
    )
    older = newer.model_copy(update={"event_id": "event-old", "occurred_at": NOW - timedelta(days=1)})
    repo.append_event(newer)
    with pytest.raises(ValueError, match="out-of-order"):
        repo.validate_event(older)
    assert repo.get_event("event-old") is None
```

- [ ] **Step 2: Run the two tests and confirm RED**

Run:

```bash
python -m pytest tests/test_relationship_repository.py -v
```

Expected: new tests fail because `validate_event` does not exist.

- [ ] **Step 3: Extract one repository validation primitive**

Implement:

```python
from typing import Literal

EventDisposition = Literal["NEW", "IDENTICAL"]


def _validate_event_conn(self, conn: sqlite3.Connection, event: RelationshipEvent) -> EventDisposition:
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

Change `_append_event_conn()` to call `_validate_event_conn()` and insert only when it returns `NEW`.

- [ ] **Step 4: Add RelationshipService RED tests for dry-run parity/no writes**

Add representative tests:

```python
def test_preview_projects_same_account_as_record_without_writing(tmp_path: Path) -> None:
    repo = _relationship_repo(tmp_path)
    service = RelationshipService(repo)
    service.register_account(RelationshipAccount(account_id="account-1", company="Example Co", updated_at=NOW - timedelta(days=1)))
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
    assert repo.get_account("account-1").relationship_state == "UNTOUCHED"

    recorded = service.record(event)
    assert recorded == projection.account
```

Also add preview failures for `PROCESS_CLOSED` without open process and an out-of-order event.

- [ ] **Step 5: Run RelationshipService tests and confirm RED**

```bash
python -m pytest tests/test_relationship_service.py -v
```

Expected: fail because `RelationshipService.preview` / `RelationshipProjection` do not exist.

- [ ] **Step 6: Extract a pure projector and implement preview**

Use:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class RelationshipProjection:
    account: RelationshipAccount
    contacts: tuple[CareerContact, ...]
```

Move the existing event-kind branching from the nested `record()` projector into:

```python
def _project(
    self,
    event: RelationshipEvent,
    account: RelationshipAccount | None,
    contacts: list[CareerContact],
) -> tuple[RelationshipAccount, list[CareerContact]]:
    ...
```

`preview()` must:

1. call `repository.validate_event(event)`;
2. require `NEW` for a new projection; if `IDENTICAL`, return the currently stored account/contacts unchanged;
3. load account + contacts;
4. call `_project()`;
5. return `RelationshipProjection` without saving anything.

`record()` passes a thin projector closure to `apply_event_transaction()` that delegates to `_project()`.

- [ ] **Step 7: Run relationship tests**

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

### Task 2: Add strict operator contracts and deterministic identity

**Files:**
- Create: `app/operator_bridge/__init__.py`
- Create: `app/operator_bridge/models.py`
- Create: `tests/test_operator_models.py`

**Interfaces:**
- Produces: `ObservationSourceType`, `ObservationKind`, `PreviewStatus`, `ObservationImportStatus`.
- Produces: `OperatorObservation`, `ObservationPreview`, `ObservationImportRequest`, `ObservationImportReceipt`, `ObservationImportResult`.
- Produces: `canonical_sha256(value: BaseModel | dict) -> str`.
- Produces: `observation_sha256(observation: OperatorObservation) -> str`.
- Produces: constants `PREVIEW_VERSION = "operator-preview-v1"`, `STATE_VERSION = "relationship-state-v1"`.

- [ ] **Step 1: Write model RED tests**

Cover:

```python
def test_operator_observation_is_strict_and_normalizes_time() -> None: ...
def test_operator_observation_rejects_raw_body_and_free_form_metadata() -> None: ...
def test_import_request_requires_confirmed_at_not_before_observed_at() -> None: ...
def test_same_observation_produces_same_semantic_hash() -> None: ...
def test_preview_external_actions_must_be_empty() -> None: ...
def test_import_result_requires_receipt_only_for_imported_statuses() -> None: ...
```

The raw-body test should attempt construction with `body="secret"` and `metadata={"raw_payload": "secret"}` and expect Pydantic validation errors due to `extra="forbid"`.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_operator_models.py -v
```

Expected: import failure because `app.operator_bridge.models` does not exist.

- [ ] **Step 3: Implement exact contracts**

Define literals exactly from the approved spec. Use one strict base model:

```python
class StrictOperatorModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

Normalize all datetimes to UTC with an aware-datetime validator. `ObservationImportRequest` validates `confirmed_at >= observation.observed_at`.

Use canonical hashing:

```python
def canonical_sha256(value: BaseModel | dict) -> str:
    payload = value.model_dump(mode="json", exclude_none=False) if isinstance(value, BaseModel) else value
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

`ObservationPreview.external_actions` must default to `[]` and reject non-empty values in a model validator.

`ObservationImportResult` rules:

- `IMPORTED` and `ALREADY_IMPORTED` require `receipt` and no errors;
- blocked/conflict statuses forbid `receipt` and require at least one stable error code.

- [ ] **Step 4: Run models tests**

```bash
python -m pytest tests/test_operator_models.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/operator_bridge tests/test_operator_models.py
git commit -m "feat: add operator observation contracts"
```

---

### Task 3: Normalize observations into minimal RelationshipEvents

**Files:**
- Create: `app/operator_bridge/normalizer.py`
- Create: `tests/test_operator_normalizer.py`

**Interfaces:**
- Consumes: `OperatorObservation`, `observation_sha256()`.
- Produces: `relationship_event_id(observation: OperatorObservation) -> str`.
- Produces: `normalize_observation(observation: OperatorObservation) -> RelationshipEvent`.

- [ ] **Step 1: Write table-driven RED mapping tests**

Use a parameterized table:

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
def test_normalizer_maps_supported_kinds(kind, expected_event_kind): ...
```

Add tests that:

- same source identity produces same `event_id`;
- changed observation semantics keep same `event_id` but change event payload via `operator_observation_sha256`, causing repository conflict later;
- `source_ref` is copied exactly;
- metadata keys are exactly the allowlist;
- `CONTACT_VERIFIED` without contact ID raises `ValueError("CONTACT_VERIFIED requires contact_id")`;
- `process_label` only maps for process observations;
- account-level `MESSAGE_SENT` adds `official_channel="operator_observation"`;
- no symbol from `app.outreach.send` / `SendReceipt` is imported or returned.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_operator_normalizer.py -v
```

Expected: fail because normalizer does not exist.

- [ ] **Step 3: Implement deterministic event identity**

```python
def relationship_event_id(observation: OperatorObservation) -> str:
    identity = f"{observation.source_type}|{observation.source_name}|{observation.observation_id}"
    return "opobs-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Implement pure mapping**

Metadata must start as:

```python
metadata = {
    "operator_source_type": observation.source_type,
    "operator_source_name": observation.source_name,
    "operator_observation_id": observation.observation_id,
    "operator_observation_sha256": observation_sha256(observation),
}
```

Add `process_label` only when supplied for a process event. Add `official_channel="operator_observation"` only for account-level `MESSAGE_SENT`.

Return `RelationshipEvent` with deterministic `event_id`, copied `account_id`, `contact_id`, `observed_at -> occurred_at`, `reason`, and `source_ref`.

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

### Task 4: Implement preview hashing, stale-state protection and idempotent import

**Files:**
- Create: `app/operator_bridge/service.py`
- Create: `tests/test_operator_service.py`

**Interfaces:**
- Consumes: `RelationshipService`, `SQLiteRelationshipRepository`, Task 2 models, Task 3 normalizer.
- Produces: `OperatorBridgeService(repository: SQLiteRelationshipRepository, relationships: RelationshipService)`.
- Produces: `OperatorBridgeService.preview(observation: OperatorObservation) -> ObservationPreview`.
- Produces: `OperatorBridgeService.import_observation(request: ObservationImportRequest, *, processed_at: datetime) -> ObservationImportResult`.

- [ ] **Step 1: Write RED tests for preview**

Cover:

```python
def test_preview_is_read_only_and_returns_importable_projection(tmp_path: Path) -> None: ...
def test_same_observation_and_state_produce_same_preview_hash(tmp_path: Path) -> None: ...
def test_changed_reason_changes_preview_hash(tmp_path: Path) -> None: ...
def test_changed_account_state_changes_preview_hash(tmp_path: Path) -> None: ...
def test_changed_referenced_contact_changes_preview_hash(tmp_path: Path) -> None: ...
def test_preview_identity_conflict_is_blocked(tmp_path: Path) -> None: ...
def test_preview_out_of_order_observation_is_blocked(tmp_path: Path) -> None: ...
```

For the read-only test snapshot `repo.list_events()`, `repo.get_account()` and referenced `repo.get_contact()` before/after preview and assert equality.

- [ ] **Step 2: Run preview tests and confirm RED**

```bash
python -m pytest tests/test_operator_service.py -k preview -v
```

- [ ] **Step 3: Implement state fingerprint and preview**

State fingerprint payload:

```python
{
    "state_version": STATE_VERSION,
    "account": account.model_dump(mode="json"),
    "contact": contact.model_dump(mode="json") if contact is not None else None,
}
```

Preview order:

1. normalize observation;
2. fetch existing deterministic event;
3. identical -> `ALREADY_IMPORTED`;
4. different -> `BLOCKED` with `observation_identity_conflict`;
5. require account;
6. require referenced contact when contact_id supplied;
7. call `RelationshipService.preview(event)`;
8. map domain errors to stable codes;
9. hash `{preview_version, observation_sha256, normalized_event, state_sha256}`;
10. expose only redacted account-level before/after fields and `external_actions=[]`.

Use exact error mapping helper:

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

Do not return raw exception strings through API-facing models.

- [ ] **Step 4: Write RED tests for import**

Cover exact normative ordering:

```python
def test_exact_preview_imports_once(tmp_path: Path) -> None: ...
def test_retry_same_import_request_returns_already_imported_before_stale_check(tmp_path: Path) -> None: ...
def test_same_identity_changed_semantics_returns_conflict(tmp_path: Path) -> None: ...
def test_state_change_before_first_import_returns_blocked_stale_preview(tmp_path: Path) -> None: ...
def test_domain_block_returns_no_receipt(tmp_path: Path) -> None: ...
def test_receipt_id_is_stable_across_identical_retries(tmp_path: Path) -> None: ...
```

The retry test must perform a successful first import and then call `import_observation()` again with the exact same request; expect `ALREADY_IMPORTED`, same `receipt_id`, and no second event.

- [ ] **Step 5: Implement import ordering exactly**

Pseudo-code to implement literally:

```python
def import_observation(self, request: ObservationImportRequest, *, processed_at: datetime) -> ObservationImportResult:
    event = normalize_observation(request.observation)
    existing = self.repository.get_event(event.event_id)
    if existing is not None:
        if existing != event:
            return ObservationImportResult(status="CONFLICT", errors=["observation_identity_conflict"])
        return ObservationImportResult(
            status="ALREADY_IMPORTED",
            receipt=self._receipt(request, event, processed_at=processed_at, status="ALREADY_IMPORTED"),
        )

    preview = self.preview(request.observation)
    if preview.preview_sha256 != request.preview_sha256:
        return ObservationImportResult(status="BLOCKED_STALE_PREVIEW", errors=["stale_preview"])
    if preview.status == "BLOCKED":
        return ObservationImportResult(status="BLOCKED_DOMAIN", errors=list(preview.errors))

    try:
        self.relationships.record(event)
    except ValueError as exc:
        return ObservationImportResult(status="BLOCKED_DOMAIN", errors=[_domain_error_code(exc)])

    return ObservationImportResult(
        status="IMPORTED",
        receipt=self._receipt(request, event, processed_at=processed_at, status="IMPORTED"),
    )
```

`receipt_id = "opreceipt-" + sha256(event.event_id.encode()).hexdigest()`.

Normalize `processed_at` to aware UTC and reject naive values.

- [ ] **Step 6: Run operator service tests**

```bash
python -m pytest tests/test_operator_service.py -v
```

Expected: PASS.

- [ ] **Step 7: Run Task 1–4 focused suite**

```bash
python -m pytest tests/test_relationship_repository.py tests/test_relationship_service.py tests/test_operator_models.py tests/test_operator_normalizer.py tests/test_operator_service.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/operator_bridge/service.py tests/test_operator_service.py
git commit -m "feat: add observation preview and confirmed import"
```

---

### Task 5: Add disabled-by-default operator API without weakening relationship read boundaries

**Files:**
- Create: `app/operator_bridge/api.py`
- Modify: `app/main.py`
- Modify: `.env.example`
- Create: `tests/test_api_operator_bridge.py`
- Keep existing: `tests/test_relationship_release_contract.py`

**Interfaces:**
- Produces: `create_operator_router(service: OperatorBridgeService | None) -> APIRouter`.
- `POST /api/v1/operator/observations/preview` accepts `OperatorObservation`.
- `POST /api/v1/operator/observations/import` accepts `ObservationImportRequest`.
- `create_app(..., operator_bridge_service: OperatorBridgeService | None = None, enable_operator_import: bool | None = None)`.
- `enable_operator_import=None` reads `OPPORTUNITY_OPERATOR_IMPORT_ENABLED`, default false.

- [ ] **Step 1: Write API RED tests for disabled/default behavior**

```python
def test_operator_routes_are_absent_by_default() -> None:
    app = create_app(enable_default_radar=False, enable_default_targets=False, enable_default_relationships=False)
    assert not any(path.startswith("/api/v1/operator/") for path in app.openapi()["paths"])


def test_existing_relationship_routes_remain_get_only() -> None:
    ... # assert exactly the two existing GET routes and no POST/PUT/PATCH/DELETE
```

- [ ] **Step 2: Write API RED tests for enabled behavior**

Create a real temporary relationship repository, seed a fictional account, construct `RelationshipService` + `OperatorBridgeService`, inject it into `create_app(..., enable_operator_import=True)` and assert:

- preview returns 200 + redacted `ObservationPreview`;
- preview writes no event;
- import with correct hash returns `IMPORTED`;
- retry returns `ALREADY_IMPORTED`;
- responses contain no contact `person`, `channel_value`, body, raw payload;
- enabled routes with `operator_bridge_service=None` return `503` detail exactly `relationship_storage_unavailable`.

- [ ] **Step 3: Run RED**

```bash
python -m pytest tests/test_api_operator_bridge.py -v
```

Expected: fail because operator router/create_app options do not exist.

- [ ] **Step 4: Implement isolated operator router**

In `app/operator_bridge/api.py`:

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
        return service.import_observation(request, processed_at=datetime.now(timezone.utc))

    return router
```

- [ ] **Step 5: Wire explicit enablement in `create_app`**

Add strict env parsing:

```python
def _operator_import_enabled() -> bool:
    raw = os.getenv("OPPORTUNITY_OPERATOR_IMPORT_ENABLED", "false").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("OPPORTUNITY_OPERATOR_IMPORT_ENABLED must be boolean")
```

Resolve `enabled = _operator_import_enabled() if enable_operator_import is None else enable_operator_import`.

When enabled and no injected service exists, try to load the existing configured relationships SQLite file **only if the file already exists**. Do not create a missing DB just because routes are enabled. If present, initialize repository schema safely and construct `RelationshipService` + `OperatorBridgeService`. If absent, keep service `None` so routes return sanitized 503.

Include the operator router only when `enabled is True`.

- [ ] **Step 6: Add config example**

Append exactly:

```text
OPPORTUNITY_OPERATOR_IMPORT_ENABLED=false
```

to `.env.example` without reformatting unrelated lines.

- [ ] **Step 7: Run API + existing release boundary tests**

```bash
python -m pytest tests/test_api_operator_bridge.py tests/test_relationship_release_contract.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/operator_bridge/api.py app/main.py .env.example tests/test_api_operator_bridge.py
git commit -m "feat: expose explicit operator observation import"
```

---

### Task 6: Lock privacy/release contracts, docs and full verification

**Files:**
- Create: `tests/test_operator_release_contract.py`
- Modify: `README.md`
- Modify: `ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-08-29-opportunity-os-v0.2e-operator-observation-bridge-design.md` (`Status: approved` if the implementation branch carries the original proposed file)
- Keep: `.github/workflows/tests.yml` unless a new static guard is genuinely required by a failing release-contract test.

**Interfaces:**
- No new runtime interface.
- Release contract freezes the provider-neutral/no-send boundary.

- [ ] **Step 1: Write release/privacy RED tests**

Tests must assert:

```python
def test_operator_bridge_has_no_provider_or_network_dependency() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in Path("app/operator_bridge").glob("*.py"))
    for forbidden in (
        "import gmail", "from gmail", "import apollo", "from apollo",
        "import httpx", "from httpx", "requests", "sqliteoutreachrepository",
        "sendgate", "record_successful_send", "sendreceipt",
    ):
        assert forbidden not in combined


def test_operator_observation_contract_has_no_raw_message_fields() -> None:
    fields = set(OperatorObservation.model_fields)
    assert fields.isdisjoint({"body", "raw_body", "message_body", "raw_payload", "provider_payload", "mailbox_dump", "conversation_history", "metadata"})
```

Also assert:

- default OpenAPI has no `/api/v1/operator/...` routes;
- relationship routes remain read-only;
- README contains `Observe → preview → confirm → import local fact`;
- README contains `An imported observation is evidence about what happened; it is not authority to make something happen.`;
- README preserves the three existing hard boundary strings;
- ROADMAP contains `### ✅ V0.2E — Operator Observation Bridge`;
- ROADMAP leaves Gmail adapter/provider integration as later work, not completed work;
- approved spec/amendment is present.

- [ ] **Step 2: Run release-contract tests and confirm RED**

```bash
python -m pytest tests/test_operator_release_contract.py -v
```

Expected: documentation/state assertions fail until docs are updated.

- [ ] **Step 3: Update README in plain language**

Add a compact section explaining:

```text
Observe → preview → confirm → import local fact
```

Explain that preview is a dry-run, confirmation is bound to exact hash/state, import changes only local relationship state, and provider adapters are not part of V0.2E.

Include exactly:

```text
An imported observation is evidence about what happened; it is not authority to make something happen.
```

Do not claim Gmail integration exists.

- [ ] **Step 4: Update ROADMAP**

Move V0.2E from NEXT to completed with the implemented facts:

- provider-neutral observations;
- exact preview hash;
- explicit confirmed import;
- idempotent retry/conflict semantics;
- relationship-only `MESSAGE_SENT` history;
- disabled-by-default operator routes;
- no provider SDK/network integration.

Set NEXT to V0.2E1 Gmail read adapter if still desired, while keeping monitoring/follow-up after the adapter bridge.

- [ ] **Step 5: Mark the design approved on the implementation branch**

Change the design header from:

```text
Status: proposed
```

to:

```text
Status: approved
```

Keep the approval/idempotent-retry amendment alongside it.

- [ ] **Step 6: Run full tests**

```bash
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Compile application**

```bash
python -m compileall app
```

Expected: exit 0.

- [ ] **Step 8: Whitespace verification**

```bash
git diff --check origin/main...HEAD
```

Expected: no output, exit 0.

- [ ] **Step 9: Privacy/import-boundary grep**

```bash
python - <<'PY'
from pathlib import Path
text = "\n".join(p.read_text(encoding="utf-8").lower() for p in Path("app/operator_bridge").glob("*.py"))
forbidden = [
    "import gmail", "from gmail", "import apollo", "from apollo",
    "import httpx", "from httpx", "sqliteoutreachrepository",
    "sendgate", "record_successful_send", "sendreceipt",
]
found = [token for token in forbidden if token in text]
assert not found, found
print("operator bridge boundary: OK")
PY
```

Expected: `operator bridge boundary: OK`.

- [ ] **Step 10: Verify branch contains no private/generated data**

```bash
git ls-files | grep -E '(^|/)(relationships\.local\.sqlite3|outreach\.local\.sqlite3|profile\.local\.yaml|targets\.local\.yaml)$' && exit 1 || true
```

Expected: no private file paths printed.

- [ ] **Step 11: Run the release-contract test again**

```bash
python -m pytest tests/test_operator_release_contract.py tests/test_relationship_release_contract.py tests/test_outreach_release_contract.py tests/test_cv_release_contract.py -v
```

Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add README.md ROADMAP.md docs/superpowers/specs/2026-08-29-opportunity-os-v0.2e-operator-observation-bridge-design.md tests/test_operator_release_contract.py
git commit -m "docs: release v0.2e operator observation bridge"
```

---

## Final Review Checklist

Before opening a PR, verify all of these explicitly:

- [ ] `RelationshipService.preview()` and `.record()` share one transition implementation.
- [ ] Repository identical-event detection happens before chronology rejection.
- [ ] Preview creates no relationship event, account change or contact change.
- [ ] Preview hash includes observation semantics + normalized event + relevant relationship state.
- [ ] Exact already-imported retry is recognized before stale-preview evaluation.
- [ ] Same identity with changed semantics is a conflict.
- [ ] No provider/network dependency exists in `app/operator_bridge`.
- [ ] No outreach send/receipt dependency exists in `app/operator_bridge`.
- [ ] `MESSAGE_SENT` only produces `RelationshipEvent(kind="CONTACTED")`.
- [ ] Operator routes are absent by default.
- [ ] Enabled bridge with no writable relationship DB fails sanitized 503 and does not create a DB.
- [ ] Relationship endpoints remain GET-only.
- [ ] No body/raw-payload fields exist in observation contracts.
- [ ] README does not claim Gmail/Apollo integration is implemented.
- [ ] Full tests, compile, whitespace and privacy checks are green.

## Expected implementation outcome

After V0.2E, Opportunity OS can safely accept an already-authorized fact from any future operator/provider adapter, show the exact local state change it would cause, require explicit confirmation of that exact preview, and import it idempotently into Relationship Memory. It still cannot read Gmail by itself, discover contacts automatically, create drafts automatically, send email, submit applications or fabricate Outreach Core receipts.