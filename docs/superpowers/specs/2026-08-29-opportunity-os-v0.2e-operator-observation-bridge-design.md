# Opportunity OS V0.2E — Operator Observation Bridge

Date: 2026-08-29
Status: proposed
Base: `main` after V0.2D Relationship Memory / Context Bridge

## 1. Purpose

V0.2E adds the first provider-neutral operator integration boundary.

Opportunity OS already knows how to represent and validate opportunities, target accounts, CV evidence, outreach approvals/receipts and relationship state. The missing piece is a safe way to bring authorized facts observed outside the core into that deterministic state without giving external tools authority over the domain.

The first slice is deliberately **not** a Gmail adapter, Apollo adapter, polling agent or autopilot. It is an explicit observation import bridge:

```text
external authorized fact
        ↓
OperatorObservation
        ↓
normalize + validate
        ↓
ObservationPreview
        ↓
explicit human confirmation bound to exact preview hash
        ↓
RelationshipService
        ↓
RelationshipEvent
        ↓
ObservationImportReceipt
```

The system must preserve the existing principle:

> external observations may inform deterministic local state; they do not authorize irreversible external actions.

## 2. Scope

V0.2E includes:

- strict provider-neutral observation contracts;
- deterministic normalization into existing `RelationshipEvent` semantics;
- read-only dry-run validation against the same relationship projector used by real imports;
- exact preview identity using canonical SHA-256;
- explicit confirmation bound to the exact preview;
- deterministic observation/event identity and idempotent re-import behavior;
- provenance on every imported event;
- local `ObservationImportReceipt` returned after success/already-imported detection;
- two operator API endpoints: preview and confirmed import;
- operator mutation endpoints disabled by default;
- privacy/release contracts proving no provider SDK/network dependency and no full-message storage;
- documentation and roadmap update.

V0.2E does **not** include:

- Gmail read/write integration;
- Apollo integration;
- public web research automation;
- automatic contact discovery;
- automatic mailbox synchronization;
- automatic process classification from free text;
- background polling or monitoring;
- scheduled follow-ups;
- draft creation;
- send authorization;
- email sending;
- application submission;
- synthetic `SendReceipt` creation;
- persistence of full email bodies, mailbox dumps or raw provider payloads.

## 3. Architectural decision

### 3.1 New subsystem

Add a focused package:

```text
app/operator_bridge/
    __init__.py
    models.py
    normalizer.py
    service.py
```

Do **not** add a provider-specific adapter in V0.2E.

Do **not** add a separate operator SQLite database in this slice.

The canonical audit record of an accepted observation is the existing append-only `RelationshipEvent` ledger. Deterministic event IDs and source provenance are sufficient to provide idempotency and auditability without introducing a second event store.

### 3.2 Existing domain ownership stays intact

`app/operator_bridge` may translate and preview observations, but it must not reimplement relationship transitions.

`RelationshipService` remains the sole owner of relationship state transitions.

The required refactor is:

```text
RelationshipService.preview(event)
RelationshipService.record(event)
             ↓
      shared pure projector
```

`preview(event)` performs the same domain validation/projection as `record(event)` but writes nothing.

This prevents preview/import drift.

### 3.3 No outreach-core mutation

V0.2E must not import or call the outreach send path.

In particular:

```text
MESSAGE_SENT observation
        ↓
RelationshipEvent(kind="CONTACTED")
        ✅ allowed

MESSAGE_SENT observation
        ↓
SendReceipt
        ❌ forbidden
```

A `SendReceipt` proves a stronger chain:

```text
exact draft
→ exact approval
→ SendRequest
→ SendGate authorization
→ provider-confirmed success
→ SendReceipt
```

An external observation that “a message exists in Sent” is useful relationship history, but it is not equivalent to that chain.

Historical outreach reconciliation is a later slice.

## 4. Observation contract

### 4.1 Source categories

Provider-neutral source categories:

```python
ObservationSourceType = Literal[
    "EMAIL_PROVIDER",
    "CONTACT_DISCOVERY",
    "PUBLIC_RESEARCH",
    "PRIVATE_WORKSPACE",
    "MANUAL",
]
```

`source_name` is a short operator/provider label such as `gmail`, `manual`, or another authorized source. It is data, not an SDK dependency.

### 4.2 Initial observation kinds

YAGNI: V0.2E supports only facts that map cleanly to existing Relationship Memory semantics.

```python
ObservationKind = Literal[
    "CONTACT_VERIFIED",
    "MESSAGE_SENT",
    "REPLY_RECEIVED",
    "PROCESS_OPENED",
    "PROCESS_UPDATED",
    "PROCESS_CLOSED",
]
```

Cooldown mutation is intentionally excluded. A cooldown is local policy/state, not normally an external provider fact. Existing `RelationshipService` remains responsible for cooldown behavior.

### 4.3 `OperatorObservation`

Strict Pydantic model with `extra="forbid"`:

```text
OperatorObservation
- observation_id: non-empty stable external/local identity
- source_type: ObservationSourceType
- source_name: non-empty short source label
- source_ref: non-empty provenance reference
- kind: ObservationKind
- account_id: non-empty
- contact_id: optional
- observed_at: timezone-aware UTC-normalized datetime
- reason: optional short normalized fact/reason
- process_label: optional
```

No free-form `metadata` field is allowed in the public observation contract.

This is deliberate. An arbitrary dictionary would make it too easy to smuggle raw email bodies, provider responses or private notes into Opportunity OS.

The source adapter/operator must normalize the fact before creating `OperatorObservation`.

### 4.4 Privacy constraints

The observation model must not have fields named or semantically equivalent to:

- `body`;
- `raw_body`;
- `message_body`;
- `raw_payload`;
- `provider_payload`;
- `mailbox_dump`;
- `conversation_history`.

A short `reason` may contain a concise normalized fact such as `recruiter replied with interview availability`, but it must not be used as a mailbox/body archive.

## 5. Deterministic identity and provenance

### 5.1 Observation semantic hash

Compute a canonical SHA-256 over the complete normalized `OperatorObservation` payload.

```text
observation_sha256
= sha256(canonical_json(observation))
```

Canonical JSON requirements:

- UTF-8;
- keys sorted;
- compact separators;
- timezone-normalized datetimes;
- no nondeterministic timestamps added during hashing.

### 5.2 Relationship event ID

The relationship event ID is deterministic from source identity, not from import time:

```text
event_identity =
    source_type + "|" + source_name + "|" + observation_id

event_id = "opobs-" + sha256(event_identity)
```

Consequences:

- importing the same observation twice produces the same `event_id`;
- an identical re-import is idempotent;
- reusing the same observation identity with different semantic content conflicts fail-closed through the relationship event ledger;
- no random UUID is introduced by the bridge.

### 5.3 Relationship event provenance

Every normalized `RelationshipEvent` must copy:

```text
source_ref = observation.source_ref
```

and include only minimal bridge metadata:

```text
operator_source_type
operator_source_name
operator_observation_id
operator_observation_sha256
```

For `MESSAGE_SENT` without a `contact_id`, the normalizer also supplies an `official_channel` metadata value so the existing relationship `CONTACTED` rule can validate an account-level official channel.

No raw provider body or payload may enter event metadata.

## 6. Normalization rules

The normalizer is deterministic and performs no I/O.

```text
CONTACT_VERIFIED -> RelationshipEvent.CONTACT_VERIFIED
MESSAGE_SENT      -> RelationshipEvent.CONTACTED
REPLY_RECEIVED    -> RelationshipEvent.REPLIED
PROCESS_OPENED    -> RelationshipEvent.PROCESS_OPENED
PROCESS_UPDATED   -> RelationshipEvent.PROCESS_UPDATED
PROCESS_CLOSED    -> RelationshipEvent.PROCESS_CLOSED
```

### 6.1 Contact rules

`CONTACT_VERIFIED` requires `contact_id`.

V0.2E does not create a brand-new `CareerContact` from an observation. The contact must already exist in the private relationship directory and belong to the same account.

This preserves the V0.2D contract that directory seeding is explicit and verification events update existing contacts.

`MESSAGE_SENT` may be account-level when the observation proves an official account channel and no specific stored contact is referenced.

`REPLY_RECEIVED` may be account-level or reference an existing contact. When a `contact_id` is supplied, existing relationship validation applies.

### 6.2 Process rules

`PROCESS_OPENED`, `PROCESS_UPDATED`, and `PROCESS_CLOSED` may carry `process_label`.

The label is translated to existing relationship event metadata only; no new process state machine is introduced.

Existing V0.2D guards continue to apply:

- `PROCESS_UPDATED` requires an open process;
- `PROCESS_CLOSED` requires an open process;
- event chronology is monotonic;
- old delayed events cannot regress the projection.

## 7. Shared dry-run projection

### 7.1 `RelationshipService.preview()`

Refactor the V0.2D transition logic so both preview and record call one pure projector.

Conceptually:

```python
class RelationshipProjection(...):
    account: RelationshipAccount
    contacts: list[CareerContact]

class RelationshipService:
    def preview(self, event: RelationshipEvent) -> RelationshipProjection:
        ... # no writes

    def record(self, event: RelationshipEvent) -> RelationshipAccount:
        ... # transaction + same projector
```

The exact internal return type may remain private to the relationship package, but there must be only one transition implementation.

### 7.2 Preview validates current state

Preview must validate against the current relationship account/contact projection.

Examples that must be blocked during preview:

- unknown account;
- `CONTACT_VERIFIED` for missing/wrong-account contact;
- `PROCESS_CLOSED` without open process;
- unusable contact for a contact-specific `MESSAGE_SENT`;
- chronologically stale/out-of-order event;
- observation identity conflict with an already-stored different event.

Preview performs zero writes.

## 8. State fingerprint and optimistic confirmation

The exact preview must be tied to the relationship state it was evaluated against.

### 8.1 State fingerprint

Compute a deterministic state fingerprint over:

- the current `RelationshipAccount` for `account_id`;
- the referenced `CareerContact` when `contact_id` is present;
- a bridge schema/version identifier.

```text
state_sha256 = sha256(canonical_current_state)
```

No names/emails need to be exposed by the API for this hash to work.

### 8.2 Preview hash

```text
preview_sha256 = sha256(canonical_json({
    preview_version,
    observation_sha256,
    normalized_event,
    state_sha256,
}))
```

No `generated_at` timestamp participates in preview identity.

Therefore the same observation against the same state produces the same preview hash.

If relationship state changes before confirmation, recomputation produces a different hash and the old confirmation is rejected.

## 9. Preview contract

```python
PreviewStatus = Literal[
    "IMPORTABLE",
    "ALREADY_IMPORTED",
    "BLOCKED",
]
```

`ObservationPreview`:

```text
preview_version
status
observation_id
observation_sha256
preview_sha256
account_id
contact_id optional
event_kind optional
state_before optional
state_after optional
open_process_before optional
open_process_after optional
source_type
source_name
source_ref
reason optional
errors[]
external_actions = []
```

The preview API must never expose contact person names, contact emails, message bodies, draft bodies, credentials or raw provider payloads.

`external_actions` is always an empty list in V0.2E.

### 9.1 Already imported

If the deterministic event already exists and is semantically identical:

```text
status = ALREADY_IMPORTED
```

The preview remains side-effect free.

### 9.2 Conflict

If the deterministic event ID already exists but its stored semantic payload differs:

```text
status = BLOCKED
errors = ["observation_identity_conflict"]
```

Fail closed.

## 10. Confirmation and import

### 10.1 Confirmation request

`ObservationImportRequest`:

```text
observation: OperatorObservation
preview_sha256: exact 64-char SHA-256
confirmed_by: non-empty local operator identity
confirmed_at: timezone-aware datetime
```

`confirmed_at` must be at or after `observation.observed_at`.

Confirmation is permission to import one normalized local observation. It is **not**:

- outreach approval;
- send approval;
- a `SendRequest`;
- provider authorization;
- permission to consume paid enrichment;
- permission to submit an application.

### 10.2 Import algorithm

On import:

1. normalize the supplied observation again;
2. read current relationship state again;
3. recompute preview using the same code path;
4. compare recomputed `preview_sha256` with the submitted hash;
5. reject if the hash differs;
6. reject if preview status is `BLOCKED`;
7. return `ALREADY_IMPORTED` without a second write when the existing event is identical;
8. otherwise call `RelationshipService.record(event)`;
9. return an import receipt only after the relationship transaction succeeds.

No external provider call occurs anywhere in this algorithm.

## 11. Import result and receipt

```python
ObservationImportStatus = Literal[
    "IMPORTED",
    "ALREADY_IMPORTED",
    "BLOCKED_STALE_PREVIEW",
    "BLOCKED_DOMAIN",
    "CONFLICT",
]
```

`ObservationImportReceipt`:

```text
receipt_id
observation_id
observation_sha256
preview_sha256
relationship_event_id
account_id
contact_id optional
source_type
source_name
source_ref
confirmed_by
confirmed_at
imported_at
status = IMPORTED | ALREADY_IMPORTED
```

The receipt is returned to the operator. V0.2E does not introduce a second receipt database: the persisted canonical audit fact is the append-only relationship event.

`receipt_id` is deterministic from the imported event identity plus preview hash so repeated identical imports return a stable receipt identity.

`ObservationImportResult` contains:

```text
status
receipt optional
errors[]
```

Blocked/conflicting imports return no receipt.

## 12. API surface

Existing relationship endpoints remain read-only and unchanged:

```text
GET /api/v1/relationships/context
GET /api/v1/relationships/{account_id}/context
```

New operator namespace:

```text
POST /api/v1/operator/observations/preview
POST /api/v1/operator/observations/import
```

These endpoints mutate only local Opportunity OS state after confirmation; they perform no provider writes.

### 12.1 Disabled by default

Operator mutation endpoints must be disabled by default.

Recommended configuration:

```text
OPPORTUNITY_OPERATOR_IMPORT_ENABLED=false
```

When disabled, the operator routes are not exposed or return a stable unavailable response; implementation must choose one behavior and test it consistently.

Enabling the bridge does not automatically enable Gmail, Apollo, web research or any provider adapter.

### 12.2 Relationship storage prerequisite

The bridge requires a writable Relationship Memory repository/service.

A preview or import must not silently create relationship accounts or contacts.

If writable relationship storage is unavailable, return a sanitized `503`-class API error.

The existing guarantee remains true: read-only relationship queries do not create the SQLite file merely by reading.

## 13. Error semantics

Internal details and provider payloads must not leak through API errors.

Stable error concepts:

```text
operator_bridge_disabled
relationship_storage_unavailable
unknown_relationship_account
unknown_or_invalid_contact
invalid_relationship_transition
out_of_order_observation
observation_identity_conflict
stale_preview
already_imported
```

Map internal `ValueError`/repository details to these public-safe concepts.

No raw SQLite error, email content or external provider response may be returned.

## 14. Security and privacy invariants

V0.2E must preserve all existing release boundaries and add these invariants:

1. `app/operator_bridge` contains no Gmail/Apollo/provider SDK dependency.
2. `app/operator_bridge` performs no HTTP/network calls.
3. `app/operator_bridge` does not import `app.outreach.send`, `SendGate`, `SQLiteOutreachRepository`, or `record_successful_send`.
4. `MESSAGE_SENT` can only become relationship history (`CONTACTED`) in this slice.
5. Preview performs no writes.
6. Import requires an exact preview hash.
7. Import never creates draft/send/application authority.
8. Raw message bodies/provider payloads are not part of observation contracts.
9. Source provenance is mandatory.
10. Re-import is idempotent and conflicting identities fail closed.
11. Existing relationship chronology guards remain authoritative.
12. Real provider credentials remain outside the core repository.

## 15. Testing strategy

### 15.1 Models

Test:

- strict extra-field rejection;
- aware datetime enforcement;
- required provenance fields;
- no raw-body/payload fields;
- confirmation timestamp rules;
- stable canonical hashes.

### 15.2 Normalizer

Table-driven mapping tests for every initial observation kind.

Verify:

- deterministic event ID;
- source provenance copied;
- only allowlisted metadata emitted;
- `MESSAGE_SENT` never creates outreach objects;
- `CONTACT_VERIFIED` requires contact ID;
- process label mapping.

### 15.3 Relationship preview parity

Test that `RelationshipService.preview(event)` and `record(event)` use identical transition rules.

Representative cases:

- process open preservation;
- held/unusable contacts;
- process close precondition;
- out-of-order event rejection;
- contact verification update;
- preview writes nothing.

### 15.4 Preview hash

Test:

- same observation + same state => same hash;
- change observation reason => different hash;
- change relationship state => different hash;
- change referenced contact state => different hash;
- generated clock time alone does not alter hash.

### 15.5 Import

Test:

- exact confirmed preview imports once;
- second identical import returns `ALREADY_IMPORTED`;
- same identity/different semantics => `CONFLICT`;
- stale preview after relationship state changes => `BLOCKED_STALE_PREVIEW`;
- invalid transition => `BLOCKED_DOMAIN`;
- failed import leaves no partial relationship event/state;
- receipt only exists after successful/already-imported resolution.

### 15.6 API

Test:

- operator routes disabled by default;
- enabled preview returns redacted result;
- preview performs no mutation;
- enabled import requires exact hash;
- relationship API remains read-only;
- missing writable relationship storage is sanitized;
- no provider side effects.

### 15.7 Release/privacy contract

CI/static tests must prove:

- no provider SDK/network imports in `app/operator_bridge`;
- no outreach-send imports in `app/operator_bridge`;
- no raw body/payload fields in observation models;
- README describes explicit preview/confirm boundary;
- ROADMAP marks V0.2E done only after implementation;
- provider adapters remain future work.

## 16. Public documentation language

README should explain the operator boundary in plain language:

```text
Observe → preview → confirm → import local fact
```

and preserve existing statements:

- `CV Factory does not send email and does not submit applications.`
- `Opportunity OS does not create Gmail drafts automatically.`
- `Approval is not a send command.`

Add a new boundary sentence:

> An imported observation is evidence about what happened; it is not authority to make something happen.

## 17. Roadmap after V0.2E

After this bridge is implemented and validated, candidate slices are:

### V0.2E1 — Gmail read adapter

Authorized read-only translation of selected Gmail message/thread facts into `OperatorObservation`.

No automatic import; still preview + confirm.

### V0.2E2 — Contact/public-research adapter

Authorized translation of verified public/contact-discovery facts into observations/contact candidates, with cost controls for any paid source.

### V0.2E3 — Outreach reconciliation

Explicit reconciliation of provider history with the stronger Outreach Core ledger. This is where historical provider evidence may be compared against drafts/approvals/send requests; V0.2E must not fake this.

### AFTER — Monitoring / follow-up

Once real observations can enter safely, monitoring can detect meaningful changes and recommend follow-up without turning elapsed time into send authority.

## 18. Acceptance criteria

V0.2E is complete only if all are true:

1. A provider-neutral `OperatorObservation` can be normalized deterministically.
2. Preview validates against current relationship state using the same projector as import.
3. Preview produces no writes.
4. Preview hash changes when either the observation or relevant relationship state changes.
5. Import requires explicit confirmation of that exact hash.
6. Same observation is idempotent across repeated imports.
7. Same observation identity with changed semantics conflicts fail-closed.
8. Imported relationship events preserve provenance.
9. `MESSAGE_SENT` updates Relationship Memory only and cannot create `SendReceipt`.
10. Operator bridge has no provider/network dependency.
11. No full message bodies/raw provider payloads are stored by the bridge.
12. Existing relationship read API remains read-only.
13. Operator mutation routes are disabled by default.
14. Full test suite, compile, diff whitespace and privacy guards pass.

## 19. Explicit non-goals

The following are not implementation shortcuts; they are intentionally excluded product behavior:

- scraping inboxes;
- auto-reading every email;
- classifying every conversation with an LLM;
- bulk importing CRM data without review;
- generating guessed contacts;
- silently consuming Apollo credits;
- automatic drafts;
- automatic sends;
- automatic applications;
- bypassing existing outreach approval/send gates;
- treating provider history as equivalent to a verified Outreach Core receipt.
