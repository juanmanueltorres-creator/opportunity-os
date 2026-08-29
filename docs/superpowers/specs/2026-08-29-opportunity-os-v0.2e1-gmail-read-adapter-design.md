# Opportunity OS V0.2E1 — Gmail Read Adapter

Date: 2026-08-29
Status: design approved in chat; written spec awaiting review
Base: `main` after V0.2E Operator Observation Bridge

## 1. Purpose

V0.2E1 gives Opportunity OS read-only eyes into explicitly selected Gmail messages or threads without changing the safety boundary established by V0.2E.

Target flow:

```text
explicit Gmail selection
        ↓
Gmail read-only provider client
        ↓
minimal normalized metadata
        ↓
GmailReadAdapter
        ↓
OperatorObservation
        ↓
STOP

V0.2E preview
→ human confirm
→ import
→ Relationship Memory
```

Invariant:

> Gmail may provide evidence about what happened; Gmail evidence does not authorize Opportunity OS to make something happen.

## 2. Scope

V0.2E1 includes:

- provider-specific Gmail read code isolated from `app/operator_bridge`;
- Gmail REST reads using existing `httpx`;
- explicit message/thread selection only;
- caller-supplied `account_id` and optional `contact_id`;
- minimal allowlisted Gmail metadata;
- strong-evidence classification for `MESSAGE_SENT` and `REPLY_RECEIVED` only;
- deterministic observation identity and bounded Gmail provenance;
- a local read-only observation endpoint, disabled by default;
- fail-closed provider/error handling;
- privacy/release tests proving no draft/send/import authority;
- README/ROADMAP updates.

V0.2E1 excludes:

- mailbox-wide sync or background polling;
- Gmail drafts, sends, replies, archive/delete/label mutation;
- application submission;
- automatic V0.2E preview confirmation or import;
- Apollo integration;
- full bodies, raw MIME, attachments or raw provider-payload persistence;
- automatic company/account inference from arbitrary mail content;
- automatic `PROCESS_OPENED`, `PROCESS_UPDATED` or `PROCESS_CLOSED` classification;
- OAuth consent UX, refresh-token persistence or a secrets vault.

## 3. Architecture

Create:

```text
app/adapters/gmail_read/
    __init__.py
    models.py
    provider.py
    normalizer.py
    service.py
    api.py
```

Dependency direction is one-way:

```text
app/adapters/gmail_read
        ↓
app/operator_bridge.models.OperatorObservation

app/operator_bridge
        ✗ must not import gmail_read
```

`GmailReadAdapter` may construct `OperatorObservation`. Only V0.2E may preview/import it.

Use Gmail REST through `httpx`, not `google-api-python-client`, because the required provider surface is narrow/read-only and `httpx` is already a project dependency.

OAuth token acquisition/storage is external to this slice. Runtime credentials are injected and never persisted by Opportunity OS.

## 4. Explicit selection contract

Every provider read must come from an explicit selection. No default inbox crawl exists.

```text
GmailReadSelection
- account_id: required
- contact_id: optional
- message_id: optional
- thread_id: optional
- selected_by: required bounded operator identifier
```

Exactly one of `message_id` or `thread_id` is required.

The caller supplies canonical `account_id`. The adapter must not infer account identity from sender domain, subject or body.

## 5. Provider contract

Define a narrow provider protocol:

```python
class GmailReadProvider(Protocol):
    async def get_message(self, message_id: str) -> GmailMessageEnvelope: ...
    async def get_thread(self, thread_id: str) -> GmailThreadEnvelope: ...
```

No provider interface may expose methods equivalent to:

```text
send
reply
create_draft
update_draft
delete
trash
archive
modify_labels
mark_read
```

The network implementation uses only documented Gmail read endpoints.

## 6. Minimal normalized envelope

The domain-facing adapter never receives a raw mailbox archive. Provider JSON is immediately normalized into an allowlist.

```text
GmailMessageEnvelope
- message_id
- thread_id
- internal_date
- label_ids
- from_address
- to_addresses
- cc_addresses
- subject: optional and bounded, diagnostic only
- in_reply_to: optional
- references: optional bounded IDs
```

Forbidden in domain-facing models:

```text
body
snippet archive
raw MIME
attachments
full header map
raw payload
token
arbitrary metadata dict
```

The adapter also receives a normalized set of operator-owned Gmail addresses/aliases. Direction is derived from actual addresses, never display names.

## 7. Classification rules

V0.2E1 is intentionally conservative.

### 7.1 `MESSAGE_SENT`

Produce `MESSAGE_SENT` only when all are true:

1. stable Gmail message provenance exists;
2. provider metadata confirms the message is in `SENT`;
3. `from_address` belongs to the configured owned-address set;
4. at least one recipient is outside that set;
5. caller supplied `account_id`;
6. timestamp is valid and UTC-normalizable.

Output:

```text
source_type = EMAIL_PROVIDER
source_name = gmail
source_ref = gmail:message:<message_id>
kind = MESSAGE_SENT
account_id = caller supplied
contact_id = caller supplied optional
reason = selected Gmail message is confirmed in Sent
```

Recommended deterministic ID:

```text
gmail-message:<message_id>:message-sent
```

### 7.2 `REPLY_RECEIVED`

Produce `REPLY_RECEIVED` only from a selected Gmail thread when all are true:

1. the thread contains an earlier outbound message from an owned address to a non-owned participant;
2. the thread contains a later inbound message from a non-owned participant to an owned address;
3. both belong to the same Gmail thread;
4. inbound timestamp is strictly later than the prior outbound timestamp;
5. caller supplied `account_id`;
6. provider metadata is internally consistent.

No semantic body analysis is required to establish that a reply occurred; thread membership, direction and chronology are sufficient.

Output provenance:

```text
source_ref = gmail:thread:<thread_id>:message:<reply_message_id>
reason = selected Gmail thread contains inbound reply after prior outbound message
```

Recommended deterministic ID:

```text
gmail-message:<reply_message_id>:reply-received
```

### 7.3 Ambiguous evidence

Produce no `OperatorObservation` when evidence is ambiguous, including:

- direction cannot be established;
- all participants are operator-owned addresses;
- inbound mail exists with no prior outbound message in the selected thread;
- chronology is inconsistent;
- relationship identity is missing;
- required Gmail metadata is malformed/missing;
- subject starts with `Re:` but thread evidence is insufficient;
- an automated notification cannot defensibly be treated as a human reply.

Ambiguity fails closed.

## 8. Process-status emails are deferred

Emails such as application receipts, interview invitations, advancement notices and rejection messages are useful, but their semantics depend on content and process context.

V0.2E1 therefore does not automatically emit:

```text
PROCESS_OPENED
PROCESS_UPDATED
PROCESS_CLOSED
```

A later slice may add a classifier with an explicit evidence/confidence policy. Until then, Gmail transport metadata cannot silently become process state.

## 9. Result contract

The Gmail layer distinguishes provider read success from observation eligibility.

```text
GmailObservationResult
- status: OBSERVATION_READY | AMBIGUOUS | PROVIDER_ERROR | INVALID_SELECTION
- observation: OperatorObservation | None
- provider: gmail
- source_ref: optional bounded provenance
- errors: bounded machine-readable codes
- external_actions: []
```

`external_actions` is always empty.

No result contains bodies, raw payloads, credentials or unrestricted metadata.

## 10. API boundary

V0.2E1 includes one local endpoint:

```text
POST /api/v1/adapters/gmail/observe
```

POST is used because the caller supplies a structured selection; the operation remains externally read-only and locally non-mutating.

The route is absent/disabled by default and requires explicit configuration such as:

```text
OPPORTUNITY_GMAIL_READ_ENABLED=false
```

When enabled, it may:

- read the explicitly selected Gmail message/thread;
- return `GmailObservationResult` and, when defensible, an `OperatorObservation`.

It must not:

- call `OperatorBridgeService.import_observation()`;
- write Relationship Memory;
- create Relationship Events;
- create drafts;
- send/reply;
- mutate Gmail state.

The caller must separately submit the returned observation to the existing V0.2E preview endpoint.

## 11. Authentication and secret handling

V0.2E1 assumes an authorized Gmail OAuth access token or equivalent authorization dependency is supplied at runtime.

Requirements:

- use read-only Gmail authorization;
- credentials come from environment/injected dependency only;
- no real credential appears in repo fixtures or docs;
- credentials are never returned, logged, hashed into observations or written to Relationship Memory;
- provider exceptions are mapped to bounded errors without credential-bearing headers/URLs.

If a runtime token happens to have broader privileges, the adapter still exposes only read operations in code.

## 12. Failure behavior

Provider/network errors never mutate local relationship state.

Bounded error codes include:

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

No provider failure falls back to guessed or stale state.

## 13. Determinism and provenance

For fixed normalized Gmail evidence plus fixed selection/account identity, adapter output must be deterministic.

Do not use request time, random UUIDs or credentials in `observation_id`.

V0.2E remains responsible for canonical observation hashing, preview hashing, event identity, stale-preview protection and import idempotency.

## 14. Privacy/release contracts

Tests must prove:

1. `app/operator_bridge` still contains no Gmail provider dependency;
2. Gmail domain-facing models expose no body/raw-payload/token fields;
3. provider protocol exposes no mutation methods;
4. default startup requires no Gmail credential;
5. Gmail route is disabled by default;
6. observe calls create no relationship storage/events;
7. observe calls never invoke V0.2E import;
8. provider failure leaves relationship state unchanged;
9. `external_actions=[]` is invariant;
10. deterministic fixtures produce deterministic observations;
11. ambiguous fixtures fail closed;
12. fixtures contain no real email addresses/tokens/provider IDs.

## 15. TDD strategy

### Unit

- strict selection validation;
- normalized envelope allowlist;
- owned-address normalization;
- outbound classification;
- reply chronology/direction;
- ambiguity rejection;
- deterministic IDs/provenance;
- provider-error mapping.

### Provider

Mock `httpx` for:

- message success;
- thread success;
- 401/403;
- 404;
- 429;
- timeout;
- malformed payload.

Assert only Gmail read endpoints are called.

### API/integration

- route absent by default;
- explicit enablement works with injected fake provider;
- response may contain `OperatorObservation` but no import side effect;
- Relationship Memory event count/state is unchanged after observe;
- V0.2E preview remains a separate call.

### Release contract

Static tests prohibit future introduction of Gmail mutation methods, raw body storage or an import shortcut.

## 16. Expected files

```text
app/adapters/gmail_read/__init__.py
app/adapters/gmail_read/models.py
app/adapters/gmail_read/provider.py
app/adapters/gmail_read/normalizer.py
app/adapters/gmail_read/service.py
app/adapters/gmail_read/api.py
app/main.py
.env.example
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

## 17. Acceptance criteria

V0.2E1 is complete when:

1. caller can explicitly select exactly one Gmail message/thread and bind it to a known `account_id`;
2. strong sent evidence yields deterministic `MESSAGE_SENT`;
3. strong thread evidence yields deterministic `REPLY_RECEIVED`;
4. ambiguous evidence yields no observation;
5. no full body/raw MIME/raw payload/credential enters domain-facing storage or response;
6. adapter has no Gmail mutation authority;
7. adapter never writes Relationship Memory or imports observations;
8. V0.2E remains the sole preview/confirm/import boundary;
9. provider failures fail closed with no local mutation;
10. full tests, compile check, diff check and privacy/generated-file guards pass;
11. README/ROADMAP state Gmail read is selective and process semantic classification remains future work.

## 18. Future work

After real operator validation:

1. process-email classifier with explicit confidence/evidence policy;
2. bounded Gmail query helper rather than mailbox-wide sync;
3. authorized contact/public-research adapters, including Apollo with explicit cumulative cost/contact limits;
4. historical outreach reconciliation without fabricating `SendReceipt`;
5. monitoring/follow-up notifications.

None are part of V0.2E1.

## 19. Final boundary

```text
Gmail READ
→ selected evidence
→ GmailReadAdapter
→ OperatorObservation
→ STOP

then separately:

PREVIEW
→ HUMAN CONFIRM
→ IMPORT MEMORY
```

Still true:

```text
IMPORT MEMORY ≠ SEND
READ ≠ APPLY
OBSERVED ≠ AUTHORIZED
```
