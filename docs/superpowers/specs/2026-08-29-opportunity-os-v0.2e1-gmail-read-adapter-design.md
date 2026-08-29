# Opportunity OS V0.2E1 — Gmail Read Adapter

Date: 2026-08-29
Status: design approved in chat; written spec awaiting review
Base: `main` after V0.2E Operator Observation Bridge

## 1. Purpose

V0.2E1 gives Opportunity OS read-only eyes into explicitly selected Gmail messages or threads without changing the safety boundary established by V0.2E.

The adapter may observe evidence from Gmail and normalize only defensible facts into `OperatorObservation`. It must not import those facts into Relationship Memory itself and must never gain draft, send, reply, delete, archive, label-mutation or application authority.

Target flow:

```text
explicit Gmail selection
        ↓
Gmail read-only provider client
        ↓
minimal normalized message/thread metadata
        ↓
GmailReadAdapter
        ↓
OperatorObservation
        ↓
V0.2E preview
        ↓
explicit human confirmation
        ↓
V0.2E import
        ↓
Relationship Memory
```

The invariant remains:

> Gmail can provide evidence about what happened; Gmail evidence does not authorize Opportunity OS to make something happen.

## 2. Scope

V0.2E1 includes:

- a provider-specific Gmail read package isolated from `app/operator_bridge`;
- a minimal provider protocol so normalization can be tested without network access;
- Gmail REST reads using the project's existing `httpx` dependency;
- explicit message/thread selection only;
- caller-supplied relationship identity (`account_id`, optional `contact_id`);
- minimal message/thread metadata normalization;
- deterministic mapping of strong outbound evidence to `MESSAGE_SENT`;
- deterministic mapping of strong reply evidence to `REPLY_RECEIVED`;
- provider provenance based on stable Gmail message/thread IDs;
- fail-closed behavior for ambiguous direction, missing relationship identity, malformed provider responses and provider failures;
- read-only API/service surface that returns observations/candidates but performs no import;
- release/privacy tests proving the adapter has no Gmail mutation authority and cannot bypass V0.2E;
- documentation/roadmap updates.

V0.2E1 does **not** include:

- automatic mailbox synchronization;
- inbox crawling by default;
- background polling;
- Gmail drafts;
- Gmail sends or replies;
- Gmail label/archive/delete mutations;
- application submission;
- automatic import into Relationship Memory;
- automatic confirmation of V0.2E previews;
- Apollo integration;
- full email-body storage;
- raw MIME/provider-payload persistence;
- attachment ingestion;
- automatic extraction of company/account identity from arbitrary email text;
- automatic `PROCESS_OPENED`, `PROCESS_UPDATED` or `PROCESS_CLOSED` classification from subject/body text;
- OAuth authorization UX, refresh-token storage or a secrets vault.

## 3. Architectural decision

### 3.1 Provider-specific package

Add a focused package separate from the provider-neutral bridge:

```text
app/adapters/gmail_read/
    __init__.py
    models.py
    provider.py
    normalizer.py
    service.py
    api.py          # only if exposing the local operator endpoint is useful
```

`app/operator_bridge` must remain free of Gmail SDKs, Gmail URLs and provider-specific parsing.

Dependency direction:

```text
app/adapters/gmail_read
        ↓
app/operator_bridge.models.OperatorObservation

app/operator_bridge
        ✗ must not import gmail_read
```

The Gmail adapter may create an `OperatorObservation`; only V0.2E may preview/import it.

### 3.2 HTTP strategy

Use Gmail REST via `httpx` instead of `google-api-python-client`.

Reasons:

- `httpx` already exists in project dependencies;
- the required surface is small and read-only;
- fewer transitive dependencies and less provider coupling;
- easier deterministic mocking in tests;
- OAuth token acquisition/storage remains outside the adapter.

The provider client accepts an access token or authorization-provider dependency at runtime. Tokens are never committed, logged, hashed into observations or persisted by Opportunity OS.

### 3.3 Explicit selection, never implicit mailbox sweep

Every read must be caused by an explicit selection/query supplied to the adapter.

Initial selector contract:

```text
GmailReadSelection
- account_id: required
- contact_id: optional
- message_id: optional
- thread_id: optional
- selected_by: required short operator identity
```

Exactly one of `message_id` or `thread_id` is required.

The adapter must not infer `account_id` from sender domain, subject text or body text. The caller/operator provides the canonical relationship account identity.

This is deliberate: provider identity and Opportunity OS domain identity are different concerns.

## 4. Provider contracts

### 4.1 Read-only provider protocol

Define a narrow protocol conceptually equivalent to:

```python
class GmailReadProvider(Protocol):
    async def get_message(self, message_id: str) -> GmailMessageEnvelope: ...
    async def get_thread(self, thread_id: str) -> GmailThreadEnvelope: ...
```

No provider interface method may be named or semantically equivalent to:

- `send`;
- `reply`;
- `create_draft`;
- `update_draft`;
- `delete`;
- `trash`;
- `archive`;
- `modify_labels`;
- `mark_read`.

### 4.2 Minimal normalized envelope

The core adapter works from normalized metadata, not the raw Gmail response.

A message envelope should contain only fields needed to establish provenance and direction:

```text
GmailMessageEnvelope
- message_id
- thread_id
- internal_date
- label_ids
- from_address
- to_addresses
- cc_addresses (optional, if needed for direction)
- subject (optional, bounded; diagnostic only)
- in_reply_to (optional)
- references (bounded IDs if useful)
```

No `body`, snippet archive, raw MIME, attachments, full header map or arbitrary metadata dictionary is retained in the domain-facing model.

The network client may transiently receive provider JSON, but it must immediately normalize and discard fields outside the allowlist.

### 4.3 User identity

The adapter requires one or more configured Gmail-owned addresses/aliases to determine direction.

```text
owned_addresses = normalized set of addresses controlled by the operator
```

Direction is not inferred from display names.

## 5. Observation classification

V0.2E1 is intentionally conservative.

### 5.1 `MESSAGE_SENT`

A selected message may become `MESSAGE_SENT` only when all are true:

1. Gmail provenance is valid and stable;
2. the message contains Gmail's `SENT` label or equivalent provider evidence;
3. `from_address` belongs to `owned_addresses`;
4. at least one recipient is outside `owned_addresses`;
5. `account_id` is explicitly supplied by the caller;
6. if `contact_id` is supplied, it is passed through unchanged for V0.2E/domain validation;
7. timestamp is valid and timezone-aware after normalization.

Output:

```text
OperatorObservation
- source_type = EMAIL_PROVIDER
- source_name = gmail
- source_ref = gmail:message:<message_id>
- kind = MESSAGE_SENT
- account_id = caller supplied
- contact_id = caller supplied optional
- observed_at = normalized Gmail timestamp
- reason = concise fixed-format fact, not email content
```

Example reason:

```text
selected Gmail message is confirmed in Sent
```

### 5.2 `REPLY_RECEIVED`

A selected thread may become `REPLY_RECEIVED` only when the thread provides strong conversation evidence.

Minimum evidence:

1. at least one earlier message is outbound from an owned address to a non-owned participant;
2. a later selected/relevant message is inbound from a non-owned address to an owned address;
3. both messages belong to the same Gmail thread;
4. inbound timestamp is strictly later than the outbound timestamp;
5. `account_id` is explicitly supplied;
6. provider metadata is internally consistent.

The adapter does not need semantic body analysis to call this a reply. Thread chronology + direction is sufficient evidence that a response occurred.

Output source provenance:

```text
source_ref = gmail:thread:<thread_id>:message:<reply_message_id>
```

Reason remains content-free, for example:

```text
selected Gmail thread contains inbound reply after prior outbound message
```

### 5.3 Ambiguous cases

Return a non-importable adapter result/candidate status instead of fabricating an observation when:

- sender/recipient direction is ambiguous;
- all participants are owned addresses;
- selected thread has inbound mail but no prior outbound message;
- chronology is inconsistent;
- required relationship identity is absent;
- Gmail metadata is incomplete;
- a message looks like an automated notification but there is no defensible reply relationship;
- provider response cannot be normalized safely.

Ambiguity must not be converted into `REPLY_RECEIVED` by subject keywords such as `Re:` alone.

## 6. Process-status emails are deferred

Emails such as:

- “we received your application”;
- “your application moved forward”;
- interview invitations;
- rejection notices;
- ATS status notifications;

may be highly useful, but V0.2E1 does not automatically convert them to:

```text
PROCESS_OPENED
PROCESS_UPDATED
PROCESS_CLOSED
```

Those require a separate classifier/evidence policy because semantics live in content, sender type and process context rather than simple transport metadata.

V0.2E1 may expose enough bounded diagnostic metadata for a later classifier, but it must not silently elevate ambiguous content into relationship state.

## 7. Adapter result contract

The Gmail layer should distinguish provider read success from observation eligibility.

Conceptual result:

```text
GmailObservationResult
- status: OBSERVATION_READY | AMBIGUOUS | PROVIDER_ERROR | INVALID_SELECTION
- observation: OperatorObservation | None
- provider: gmail
- source_ref: stable bounded provenance when available
- errors: bounded machine-readable codes
- external_actions: []
```

`external_actions` must always be empty.

No result object may contain a body, raw provider payload, OAuth token or unrestricted metadata dictionary.

## 8. API boundary

If an HTTP endpoint is added, use a local operator/read endpoint conceptually like:

```text
POST /api/v1/adapters/gmail/observe
```

The verb is POST only because the caller supplies a structured selection; the operation remains externally read-only and locally non-mutating.

The endpoint:

- may call Gmail read-only provider methods;
- may return a normalized observation candidate;
- must not call `OperatorBridgeService.import_observation()`;
- must not call RelationshipRepository/RelationshipService mutation methods;
- must not create drafts or sends;
- must fail safely when Gmail authorization/provider access is unavailable.

A later operator action explicitly submits the returned `OperatorObservation` to the existing V0.2E preview endpoint.

## 9. Authentication and secret handling

V0.2E1 assumes an authorized Gmail OAuth access token or equivalent authorization dependency is supplied at runtime.

Out of scope:

- browser OAuth consent flow;
- refresh-token lifecycle;
- credential database;
- multi-user OAuth tenancy.

Security requirements:

- credentials only from environment/injected runtime dependency;
- never in repository fixtures;
- never returned in API models;
- never logged;
- never stored in Relationship Memory;
- provider exceptions must redact credential-bearing headers/URLs.

The implementation should request/use read-only Gmail authorization. If the runtime token has broader privileges, the adapter still exposes only the read-only code path.

## 10. Failure behavior

Provider/network failures must not change local relationship state.

Normalize failures into bounded adapter errors such as:

```text
gmail_unauthorized
gmail_forbidden
gmail_not_found
gmail_timeout
gmail_rate_limited
gmail_payload_invalid
gmail_provider_error
ambiguous_message_direction
reply_without_prior_outbound
invalid_selection
```

No retry may create domain events because the adapter never imports events.

A provider failure must not fall back to guessing from stale local data.

## 11. Determinism and provenance

For a fixed normalized Gmail message/thread plus fixed selection/account identity, the produced `OperatorObservation` must be deterministic.

Recommended observation identity:

```text
message sent:
gmail-message:<message_id>:message-sent

reply received:
gmail-message:<reply_message_id>:reply-received
```

Do not include access token, request time or random UUID in `observation_id`.

`source_ref` preserves stable Gmail provenance while remaining bounded and body-free.

V0.2E remains responsible for canonical observation hashing, preview hashing, event identity and import idempotency.

## 12. Privacy and release contracts

Tests must prove:

1. `app/operator_bridge` still contains no Gmail provider dependency;
2. Gmail adapter domain-facing models expose no body/raw payload/token fields;
3. provider protocol exposes no mutation methods;
4. default application startup does not require Gmail credentials;
5. Gmail routes, if any, are disabled unless explicitly configured;
6. observe calls do not create Relationship Memory storage or relationship events;
7. observe calls do not call V0.2E import;
8. provider failure leaves state unchanged;
9. `external_actions=[]` is invariant;
10. deterministic provider fixtures produce deterministic observations;
11. ambiguous fixtures fail closed;
12. no test fixture contains real emails, tokens or personal provider IDs.

## 13. Testing strategy

Implementation follows TDD.

### Unit tests

- strict selection validation;
- normalized envelope allowlist;
- owned-address normalization;
- outbound direction classification;
- reply chronology classification;
- ambiguous direction rejection;
- deterministic IDs/provenance;
- provider-error mapping.

### Provider tests

Mock `httpx` responses for:

- selected message success;
- selected thread success;
- 401/403;
- 404;
- 429;
- timeout;
- malformed JSON/payload.

Assert only documented Gmail read endpoints are called.

### Integration/API tests

- endpoint absent/disabled by default if endpoint is exposed;
- explicit enablement works with injected fake provider;
- response contains `OperatorObservation` but no import side effect;
- Relationship Memory remains byte-for-byte/event-count unchanged after observe;
- V0.2E preview must be called separately.

### Release-contract tests

Static boundary tests prevent future accidental introduction of send/draft/mutation methods or raw body storage.

## 14. Files expected to change

Likely implementation surface:

```text
app/adapters/gmail_read/__init__.py
app/adapters/gmail_read/models.py
app/adapters/gmail_read/provider.py
app/adapters/gmail_read/normalizer.py
app/adapters/gmail_read/service.py
app/adapters/gmail_read/api.py          # if endpoint retained
app/main.py                             # guarded dependency wiring only
.env.example                           # enable flag / optional runtime config, never secrets
README.md
ROADMAP.md
tests/test_gmail_read_models.py
tests/test_gmail_read_normalizer.py
tests/test_gmail_read_provider.py
tests/test_gmail_read_service.py
tests/test_api_gmail_read.py
tests/test_gmail_read_release_contract.py
```

Avoid unrelated refactors.

## 15. Acceptance criteria

V0.2E1 is complete when all of the following are true:

1. A caller can explicitly select one Gmail message or thread and associate it with a known Opportunity OS `account_id`.
2. Strong sent-mail evidence yields a deterministic `MESSAGE_SENT` `OperatorObservation`.
3. Strong thread reply evidence yields a deterministic `REPLY_RECEIVED` `OperatorObservation`.
4. Ambiguous evidence produces no observation.
5. No full body, raw MIME, raw provider payload or credential is persisted/exposed in domain-facing contracts.
6. The adapter has no Gmail mutation method and no send/draft authority.
7. The adapter never writes Relationship Memory and never imports observations.
8. V0.2E remains the only preview/confirm/import boundary.
9. Gmail/provider failures are fail-closed and cause no local mutation.
10. The test suite, compile check, diff check and privacy/generated-file guards are green.
11. README/ROADMAP accurately state that Gmail read is selective and that process semantic classification remains future work.

## 16. Explicit future work

After V0.2E1 is validated in real operator use, candidate follow-up slices are:

1. process-email classifier with explicit confidence/evidence policy;
2. Gmail query helper for bounded candidate discovery rather than mailbox-wide sync;
3. authorized contact/public-research adapters including Apollo with explicit cumulative cost/contact limits;
4. historical outreach reconciliation without fabricating `SendReceipt`;
5. monitoring/follow-up notifications.

None of those are implicitly included in V0.2E1.

## 17. Final boundary

```text
Gmail READ
   ↓
selected evidence
   ↓
GmailReadAdapter
   ↓
OperatorObservation
   ↓
STOP
```

From there the existing V0.2E boundary takes over:

```text
PREVIEW
→ HUMAN CONFIRM
→ IMPORT MEMORY
```

And still:

```text
IMPORT MEMORY ≠ SEND
READ ≠ APPLY
OBSERVED ≠ AUTHORIZED
```
