# Opportunity OS V0.2D — Relationship Memory + Context Bridge Design

Date: 2026-08-29
Status: approved
Applies to: V0.2A2 Target Accounts + V0.2C Email Outreach Core

## 1. Decision

Opportunity OS adds a private relationship-memory subsystem that remembers account-level and contact-level career interactions across runs without giving that memory authority to send email, submit applications, consume enrichment credits, or mutate any external provider.

The subsystem uses a hybrid SQLite design:

1. current-state records for fast operational reads;
2. append-only relationship events for history and auditability;
3. a redacted Context Bridge projection for Target Accounts and operator-facing reasoning.

The real database lives outside the public repository:

```text
state/relationships.local.sqlite3
```

The public repository contains contracts, implementation code, tests, schema initialization and documentation. Real names, contact channels and relationship history remain local/private.

## 2. Why this exists

Target Accounts can tell us that a company is interesting. That is not enough to decide what to do next.

The system must distinguish situations such as:

- the company has never been contacted;
- a recruiter was contacted recently and a cooldown is active;
- the recruiter replied;
- an active selection process exists;
- a second technical contact is known but intentionally held back;
- a previous process closed;
- a materially new reason exists to prepare a follow-up;
- no trustworthy contact path is known.

Without this memory, each run can start from zero and repeat outreach that should have been suppressed.

## 3. Design principles

### 3.1 Memory informs; it does not authorize

Relationship Memory may recommend or suppress an action. It must never:

- create a Gmail draft;
- send email;
- submit an application;
- consume Apollo/enrichment credits;
- search the web;
- mutate an external provider.

No relationship action named `SEND` exists in V0.2D.

### 3.2 Account, contact and event are different things

A company can have an open process while one specific contact is held, stale or inactive.

The system therefore separates:

```text
RelationshipAccount
CareerContact
RelationshipEvent
```

### 3.3 Real contact data is private

Names, emails, provider IDs, message bodies, source payloads and private notes never appear in the default Context Bridge projection and must not be committed to the public repository.

### 3.4 Events are the audit trail

Relationship events are append-only. Corrections are represented by later events rather than rewriting earlier history.

Current-state account/contact rows are mutable projections optimized for reads.

### 3.5 Idempotency is mandatory

A repeated `event_id` with identical payload returns the stored event unchanged.

A repeated `event_id` with conflicting payload is an integrity error.

## 4. Domain contracts

All public contracts are strict Pydantic models with `extra="forbid"`. Stored datetimes must be timezone-aware and normalize to UTC.

### 4.1 Contact type

```text
RECRUITER
HIRING_MANAGER
TECHNICAL
OTHER
```

### 4.2 Verification status

```text
VERIFIED
PUBLIC_SOURCE
STALE
UNVERIFIED
```

A usable contact requires:

```text
active == true
and disposition == AVAILABLE
and verification_status in {VERIFIED, PUBLIC_SOURCE}
```

`STALE` and `UNVERIFIED` are never considered usable outbound channels.

### 4.3 Contact disposition

```text
AVAILABLE
HELD
INACTIVE
```

`HELD` means: known and intentionally preserved, but not recommended now.

This supports the real operating case where one recruiter channel is active while a valuable technical contact should remain in memory without creating parallel outreach.

### 4.4 Persisted relationship states

```text
UNTOUCHED
CONTACTED
REPLIED
PROCESS_OPEN
PROCESS_CLOSED
```

Semantics:

- `UNTOUCHED`: no recorded outbound relationship history;
- `CONTACTED`: outbound contact recorded, no reply/process state supersedes it;
- `REPLIED`: reply recorded but no structured process is open;
- `PROCESS_OPEN`: an active recruiting/hiring process exists;
- `PROCESS_CLOSED`: a known process finished, was rejected, withdrawn or otherwise closed.

### 4.5 Derived context state

`DORMANT` is **not persisted**.

It is produced only by the Context Bridge when historical relationship state exists but there is no active process, no active cooldown and no currently qualifying follow-up reason.

A read operation must never write `DORMANT` or mutate relationship state merely because time passed.

### 4.6 Event kinds

```text
CONTACT_VERIFIED
CONTACT_HELD
CONTACT_RELEASED
CONTACTED
REPLIED
PROCESS_OPENED
PROCESS_UPDATED
PROCESS_CLOSED
COOLDOWN_SET
COOLDOWN_CLEARED
NOTE_RECORDED
```

`NOTE_RECORDED` remains private and has no direct redacted-state effect.

## 5. Core models

### CareerContact

```text
contact_id
account_id
person
role
contact_type
verification_status
verification_source optional
observed_at
disposition
channel_kind optional
channel_value optional
active
```

`person`, `channel_value` and private source details never enter the redacted Context Bridge.

### RelationshipAccount

```text
account_id
company
relationship_state
last_contacted_at optional
last_reply_at optional
cooldown_until optional
open_process
process_label optional
last_reason optional
preferred_next_contact_id optional
updated_at
```

`preferred_next_contact_id` may point only to an active, available contact belonging to the same account.

### RelationshipEvent

```text
event_id
account_id
contact_id optional
kind
occurred_at
reason optional
source_ref optional
metadata map<string,string>
```

### RelationshipContext

```text
account_id
relationship_state
last_contacted_at optional
last_reply_at optional
cooldown_until optional
cooldown_active
open_process
usable_contact_count
held_contact_count
preferred_contact_type optional
last_reason optional
recommended_relationship_action
reason
generated_at
```

This model is the public/redacted boundary.

### RelationshipContextSnapshot

```text
generated_at
accounts[]
```

## 6. Storage architecture

V0.2D uses stdlib `sqlite3`; no new database dependency is required.

Default path:

```text
OPPORTUNITY_RELATIONSHIPS_PATH=state/relationships.local.sqlite3
```

Tables:

### `relationship_accounts`

Current account projection keyed by `account_id`.

### `relationship_contacts`

Current private contact directory keyed by `contact_id`, indexed by account/disposition.

### `relationship_events`

Append-only event history keyed by `event_id`, indexed by account/time and contact/time.

## 7. Transaction model

Relationship writes go through `RelationshipService`.

For an accepted event:

```text
validate event
→ append event idempotently
→ update contact projection if needed
→ update account projection
→ commit
```

If any projection step fails, the transaction rolls back, including the newly inserted event.

## 8. Transition semantics

### PROCESS_OPEN protection

While `open_process=true`, later `CONTACTED` and `REPLIED` events may update timestamps/history but cannot downgrade the account out of `PROCESS_OPEN`.

### CONTACT_VERIFIED

Requires an existing account/contact relationship and updates verification metadata without changing account relationship state.

### CONTACT_HELD

Requires a contact belonging to the account, sets it to `HELD`, and clears `preferred_next_contact_id` if necessary.

### CONTACT_RELEASED

Requires an active held contact with usable verification and returns it to `AVAILABLE`.

### CONTACTED

Requires a usable contact or an explicitly documented official account-level channel. Updates `last_contacted_at` and applies the relationship cooldown policy.

### REPLIED

Updates `last_reply_at`; preserves `PROCESS_OPEN` when a process is active.

### PROCESS_OPENED / PROCESS_UPDATED / PROCESS_CLOSED

- `PROCESS_OPENED` sets `PROCESS_OPEN` and `open_process=true`;
- `PROCESS_UPDATED` requires an open process and preserves it;
- `PROCESS_CLOSED` requires an open process and sets `PROCESS_CLOSED`, `open_process=false`.

### COOLDOWN_SET / COOLDOWN_CLEARED

A set cooldown must be timezone-aware and not earlier than the event timestamp. Explicit stored cooldowns are authoritative until replaced or cleared.

## 9. Relationship policy

Defaults:

```text
spontaneous_contact_cooldown_days = 30
follow_up_min_days = 5
stale_contact_days = 180
```

These values guide recommendations only. They are not automated schedules.

## 10. Context Bridge recommendation precedence

The Context Bridge computes relationship-level action before Target Accounts applies ordinary affinity thresholds.

```text
open process
    -> WATCH

cooldown active
    -> WATCH

historical relationship + explicit new reason + follow-up timing satisfied
    -> FOLLOW_UP

no usable contact + one or more HELD contacts
    -> WATCH

no usable contact
    -> RESEARCH_CONTACT

usable contact + no relationship blocker
    -> PREPARE_SPECULATIVE
```

`FOLLOW_UP` means “there is enough context to prepare a follow-up.” It does not create or send one.

## 11. New-reason rule

Time alone never creates a follow-up recommendation.

A `FOLLOW_UP` candidate needs historical context, the minimum timing gate and a concrete current reason, such as:

- a newly published relevant role;
- a meaningful hiring signal change;
- a prior reply explicitly inviting future contact;
- a materially new capability/evidence point;
- a process-state change that creates a legitimate next step.

A generated justification is not evidence by itself.

## 12. Target Accounts integration

V0.2D replaces the narrow historical interface:

```python
last_contacted_at(account_id)
```

with:

```python
RelationshipMemory.context_for(account_id, *, now, current_reason=None)
```

Target Accounts then combines relationship action with account affinity/confidence.

Allowed final actions:

```text
WATCH
FOLLOW_UP
RESEARCH_CONTACT
PREPARE_SPECULATIVE
```

The selector never returns `SEND`.

When Relationship Memory is not configured, `EmptyRelationshipMemory` is neutral and preserves the pre-V0.2D Target Accounts behavior.

## 13. API boundary

Read-only local endpoints:

```text
GET /api/v1/relationships/context
GET /api/v1/relationships/{account_id}/context
```

They expose only redacted `RelationshipContext` data.

V0.2D exposes no relationship `POST`, `PUT`, `PATCH` or `DELETE` endpoint.

## 14. Missing-storage behavior

If `OPPORTUNITY_RELATIONSHIPS_PATH` does not exist:

- health and ordinary radar routes continue working;
- the app uses `EmptyRelationshipMemory`;
- the missing DB is not created merely by startup or read-only API access.

If an existing relationship database is configured, the SQLite repository may initialize its schema before use.

## 15. Context Bridge privacy

The redacted projection must not contain:

- contact names;
- email addresses/contact channel values;
- provider message/thread IDs;
- mailbox bodies;
- private notes;
- raw external payloads.

Human-readable rendering is likewise redacted.

## 16. Import boundary

V0.2D does **not** automatically import:

- the existing private Markdown CRM;
- Gmail;
- Apollo;
- GitHub vault data;
- web research.

Those systems are product-research inputs and future operator sources, not runtime dependencies of Relationship Memory.

A later authorized adapter may translate external observations into `CareerContact`/`RelationshipEvent` writes.

## 17. Public/private separation

Public repository:

- strict contracts;
- SQLite repository/service implementation;
- Context Bridge implementation;
- tests and fictitious examples;
- read-only API contracts;
- design/plan documents.

Private runtime:

- `state/relationships.local.sqlite3` and sidecars;
- real contact names/channels;
- private source references;
- provider IDs;
- mailbox-derived history;
- private notes.

`.gitignore` and CI guards must cover the relationship database and generated relationship artifacts.

## 18. Failure behavior

Fail closed for:

- naive datetimes;
- cross-account contact references;
- unusable preferred contacts;
- invalid process transitions;
- past cooldown timestamps;
- duplicate event IDs with conflicting payload;
- malformed existing private relationship state.

Errors must not expose raw private payloads.

## 19. Testing strategy

Required coverage:

1. strict models and timezone rules;
2. SQLite initialization and persistence;
3. contact/account guards;
4. append-only idempotency/conflicting event IDs;
5. transaction rollback;
6. verification/contact/reply/process/cooldown/held transitions;
7. `PROCESS_OPEN` downgrade protection;
8. `DORMANT` derivation without mutation;
9. Context Bridge redaction;
10. `FOLLOW_UP` history + reason + timing gate;
11. Target Accounts relationship precedence;
12. read-only API and missing-DB fallback;
13. release/privacy/docs contracts;
14. full regression suite, compile, whitespace and private-file guards.

## 20. Explicit non-goals

V0.2D does not:

- send email;
- create Gmail drafts;
- submit applications;
- search the web;
- consume Apollo credits;
- discover contacts automatically;
- scrape mailbox history;
- auto-import a private CRM;
- schedule follow-ups;
- notify users in the background;
- rank humans by relationship value;
- publish real contacts.

## 21. Success criteria

The slice is complete when:

1. private account/contact relationship state persists locally;
2. every accepted relationship change has append-only event history;
3. known-but-held contacts are represented explicitly;
4. open processes cannot be accidentally downgraded;
5. `DORMANT` is derived without writes;
6. `FOLLOW_UP` requires history, timing and a concrete reason;
7. Target Accounts uses Relationship Context without gaining external side effects;
8. the read-only Context Bridge exposes no contact PII;
9. missing memory degrades safely;
10. the full existing suite stays green.

## 22. Dependency direction

```text
Target Accounts
      ↓ reads
RelationshipMemory / RelationshipContext
      ↑
RelationshipService
      ↑
SQLiteRelationshipRepository

Operator Integration (later)
      ↓ writes authorized observations
RelationshipService
```

`app/relationships/` must not import Gmail/Apollo SDKs or depend on operator tooling.

## 23. Roadmap after V0.2D

The next architectural block is **Operator Integration**:

```text
core deterministic state
↕
authorized operator adapters
↕
Gmail / contact discovery / public research / private workspaces
```

Only that later slice should translate authorized external provider observations into the contracts defined here. External action authorization remains separate.
