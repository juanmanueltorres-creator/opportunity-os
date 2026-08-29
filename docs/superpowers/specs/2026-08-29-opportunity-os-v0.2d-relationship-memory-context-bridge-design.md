# Opportunity OS V0.2D — Relationship Memory + Context Bridge Design

Date: 2026-08-29
Status: review
Applies to: V0.2A2 Target Accounts + V0.2C Email Outreach Core

## 1. Decision

Opportunity OS will add a private relationship-memory subsystem that remembers account-level and contact-level career interactions across runs without giving that memory authority to send email, submit applications, consume enrichment credits, or contact anyone automatically.

The subsystem uses a hybrid SQLite design:

1. private current-state records for fast operational reads;
2. append-only relationship events for auditability and history;
3. a redacted Context Bridge projection for safe downstream reasoning.

The real database lives outside the public repository:

```text
state/relationships.local.sqlite3
```

The public repository contains only contracts, repository/service code, schema initialization, redacted renderers and fictional fixtures.

## 2. Why this exists

Target Accounts can already decide that a company is worth watching or approaching, but V0.2A2 only knows one historical fact:

```text
last_contacted_at(account_id)
```

That is not enough for real outreach decisions. The operating system must distinguish situations such as:

- the company has never been contacted;
- a recruiter was contacted recently and the cooldown is active;
- the recruiter replied and there is an open process;
- a second technical contact is known but intentionally held back;
- the prior process closed and a new concrete reason now exists to reconnect;
- the company is worth watching but no trustworthy contact path exists yet.

Without this memory, each run can start from zero, duplicate outreach, contradict prior context, or treat a valuable long-term contact as a disposable lead.

## 3. Design principles

### 3.1 Memory informs; it does not authorize

Relationship Memory may recommend or suppress an action. It must never create a Gmail draft, send email, apply to a role, enrich a contact, or mutate an external system.

No relationship action named `SEND` exists in this slice.

### 3.2 Company state and person state are different

A company can have an open relationship while one particular contact is held, inactive, stale, or no longer verified.

The system therefore models account relationship, contact directory, and interaction/event history as separate concerns.

### 3.3 Real contact data is private

Names, emails, provider message IDs, mailbox bodies, free-form private notes, recruiter histories and private source records must never be committed to the public repository.

The Context Bridge is redacted by default and exposes operational facts, not contact PII.

### 3.4 Append-only history is the audit trail

Relationship events are immutable once recorded. Corrections are represented by later events, not by editing old history.

Current-state tables may change because they are projections used for fast reads.

### 3.5 Idempotency is required

Replaying the same external observation or operator action must not create duplicate relationship history when the same `event_id` is supplied.

## 4. Public domain contracts

The public core defines strict Pydantic contracts with `extra="forbid"` and timezone-aware datetimes.

### 4.1 Contact types

```text
RECRUITER
HIRING_MANAGER
TECHNICAL
OTHER
```

### 4.2 Contact verification status

```text
VERIFIED
PUBLIC_SOURCE
STALE
UNVERIFIED
```

`UNVERIFIED` may be stored for research context but must never be treated as a usable outbound channel. `STALE` is also non-usable until revalidated.

### 4.3 Contact disposition

```text
AVAILABLE
HELD
INACTIVE
```

`HELD` means the contact is intentionally known but should not be recommended now. This is different from `INACTIVE`.

Example: a company already has an active recruiting conversation, while a senior technical manager is valuable to retain for a future concrete reason. The technical manager is `HELD`, not deleted and not recommended.

### 4.4 Relationship states

```text
UNTOUCHED
CONTACTED
REPLIED
PROCESS_OPEN
PROCESS_CLOSED
DORMANT
```

Semantics:

- `UNTOUCHED`: no recorded outbound contact;
- `CONTACTED`: outbound contact recorded, no reply yet;
- `REPLIED`: reply received but no structured open process recorded;
- `PROCESS_OPEN`: an active recruiting/hiring process exists;
- `PROCESS_CLOSED`: a known process finished, was rejected, withdrawn or otherwise closed;
- `DORMANT`: historical relationship exists but no current process and no active expectation of immediate contact.

These states describe operational history, not relationship quality.

### 4.5 Relationship event kinds

V0.2D minimum event vocabulary:

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

`NOTE_RECORDED` is allowed only for private storage and must not be copied into the redacted Context Bridge payload.

## 5. Core models

### 5.1 CareerContact

```text
CareerContact
- contact_id
- account_id
- person
- role
- contact_type
- verification_status
- verification_source optional
- observed_at
- disposition: AVAILABLE | HELD | INACTIVE
- channel_kind optional
- channel_value optional
- active
```

`channel_value` can contain an email or other private contact detail. It is excluded from the default Context Bridge projection.

A contact is usable only when:

```text
active == true
and disposition == AVAILABLE
and verification_status in {VERIFIED, PUBLIC_SOURCE}
```

### 5.2 RelationshipAccount

```text
RelationshipAccount
- account_id
- company
- relationship_state
- last_contacted_at optional
- last_reply_at optional
- cooldown_until optional
- open_process
- process_label optional
- last_reason optional
- preferred_next_contact_id optional
- updated_at
```

`preferred_next_contact_id` may point only to a usable contact belonging to the same account.

### 5.3 RelationshipEvent

```text
RelationshipEvent
- event_id
- account_id
- contact_id optional
- kind
- occurred_at
- reason optional
- source_ref optional
- metadata map<string,string>
```

Events are append-only and idempotent by `event_id`.

### 5.4 RelationshipContext

This is the redacted account-level projection consumed by Target Accounts and operator-facing context summaries.

```text
RelationshipContext
- account_id
- relationship_state
- last_contacted_at optional
- last_reply_at optional
- cooldown_until optional
- cooldown_active
- open_process
- usable_contact_count
- held_contact_count
- preferred_contact_type optional
- last_reason optional
- recommended_relationship_action
- reason
- generated_at
```

It must not contain contact names, email addresses, provider message IDs, mailbox bodies, private free-form notes or raw source payloads.

## 6. Storage architecture

V0.2D uses SQLite via stdlib `sqlite3`; no new runtime dependency is required.

Default private path:

```text
OPPORTUNITY_RELATIONSHIPS_PATH=state/relationships.local.sqlite3
```

The repository creates three logical stores.

### 6.1 `relationship_accounts`

Current account-level operational state. Primary key: `account_id`.

It stores the strict serialized `RelationshipAccount` plus indexed fields needed for common reads such as `relationship_state`, `last_contacted_at`, `cooldown_until` and `open_process`.

### 6.2 `relationship_contacts`

Current private contact directory. Primary key: `contact_id`.

Index by `account_id` and disposition.

### 6.3 `relationship_events`

Append-only history. Primary key: `event_id`.

Indexes:

```text
(account_id, occurred_at, event_id)
(contact_id, occurred_at, event_id)
```

A repeated `event_id` with identical payload returns the stored event unchanged. A repeated `event_id` with conflicting payload is an integrity error.

## 7. Update model and consistency

Relationship writes go through a `RelationshipService`; callers do not directly coordinate account/contact/event mutations.

For every accepted relationship event, the service performs one logical SQLite transaction:

```text
validate event
→ append event idempotently
→ update contact state if needed
→ update account projection
→ commit
```

If any step fails, the transaction rolls back.

The append-only event is the audit record; current state is the operational projection.

### 7.1 State transition precedence

`PROCESS_OPEN` is protected while `open_process=true`: ordinary `CONTACTED` or `REPLIED` events update timestamps/history but cannot downgrade the account out of `PROCESS_OPEN`.

Once `PROCESS_CLOSED` is recorded, a later `CONTACTED` event may begin a new outreach cycle and move the account to `CONTACTED`. A later `PROCESS_OPENED` begins a new process and moves it to `PROCESS_OPEN`.

`DORMANT` is a derived/explicit resting state for historical relationships and is never created merely because a timer elapsed inside a read operation; a service transition or explicit maintenance action records it.

### 7.2 Required event effects

- `CONTACT_VERIFIED`
  - requires `contact_id`;
  - inserts or updates that contact with current verification metadata;
  - does not change account relationship state by itself.
- `CONTACT_HELD`
  - requires an existing contact belonging to the account;
  - sets disposition to `HELD`;
  - clears `preferred_next_contact_id` when it points to that contact.
- `CONTACT_RELEASED`
  - requires an active held contact belonging to the account;
  - moves it back to `AVAILABLE` only if its verification state is usable.
- `CONTACTED`
  - requires a usable contact or an explicitly documented official account-level channel;
  - updates `last_contacted_at`;
  - sets `CONTACTED` unless an open process is already active;
  - may set/refresh cooldown through policy.
- `REPLIED`
  - updates `last_reply_at`;
  - sets `REPLIED` unless an open process is already active.
- `PROCESS_OPENED`
  - sets `relationship_state=PROCESS_OPEN` and `open_process=true`.
- `PROCESS_UPDATED`
  - requires `open_process=true` and preserves `PROCESS_OPEN`.
- `PROCESS_CLOSED`
  - requires `open_process=true`;
  - sets `relationship_state=PROCESS_CLOSED` and `open_process=false`.
- `COOLDOWN_SET`
  - sets a timezone-aware `cooldown_until >= occurred_at`.
- `COOLDOWN_CLEARED`
  - clears the account cooldown.
- `NOTE_RECORDED`
  - changes no public/redacted state by itself.

Invalid transitions fail closed with sanitized errors.

## 8. Relationship policy

Defaults:

```text
spontaneous_contact_cooldown_days = 30
follow_up_min_days = 5
stale_contact_days = 180
```

These values guide recommendations only. They are not automated send schedules.

An explicitly stored `cooldown_until` is authoritative over a newly calculated default until cleared or replaced by a later `COOLDOWN_SET` event.

## 9. Target Accounts integration

V0.2A2 currently depends on:

```python
OutreachHistory.last_contacted_at(account_id) -> datetime | None
```

V0.2D replaces this narrow dependency with:

```python
RelationshipMemory.context_for(account_id, *, now) -> RelationshipContext
```

Target selection remains deterministic and side-effect free.

### 9.1 Recommended action precedence

Relationship state is applied before ordinary target-account affinity/action rules:

```text
open process
    -> WATCH

cooldown active
    -> WATCH

PROCESS_CLOSED or DORMANT + explicit new reason + follow-up age satisfied
    -> FOLLOW_UP

usable_contact_count == 0
    -> RESEARCH_CONTACT

usable contacts exist but relevant candidates are intentionally HELD
    -> WATCH

high affinity + confidence + no blocking history
    -> PREPARE_SPECULATIVE

otherwise
    -> WATCH
```

`FOLLOW_UP` means “history exists and there is a defensible reason to prepare a follow-up.” It does not create or send one.

The selector must never return `SEND`.

## 10. New-reason rule

A prior relationship does not become eligible for `FOLLOW_UP` simply because time passed.

A follow-up candidate requires at least one explicit current reason, for example:

- a newly published relevant role;
- a meaningful new company hiring signal;
- a recruiter reply requesting future contact;
- cooldown expiry plus a materially new capability/evidence point;
- a previously open process changing state in a way that invites follow-up.

The reason is a short structured/operator-provided string stored as `last_reason` and/or event reason with provenance when available.

No LLM-generated justification is treated as evidence by itself.

## 11. Context Bridge

The bridge produces a compact, deterministic summary for operator/ChatGPT use without loading the full private database into context.

### 11.1 Snapshot contract

```text
RelationshipContextSnapshot
- generated_at
- accounts[]
```

Each account item contains only redacted `RelationshipContext` fields.

### 11.2 Human-readable rendering

A renderer may produce:

```text
TARGET RELATIONSHIPS
- example-co: PROCESS_OPEN | last contact 2026-08-20 | cooldown active | WATCH
- sample-labs: DORMANT | verified contact available | new reason: backend role | FOLLOW_UP
- demo-industrial: UNTOUCHED | no verified contact | RESEARCH_CONTACT
```

The renderer must not include private contact names or addresses by default.

Company display names may be joined from the target registry; the relationship context itself remains keyed by stable `account_id`.

## 12. API boundary

V0.2D may expose read-only local API endpoints:

```text
GET /api/v1/relationships/{account_id}/context
GET /api/v1/relationships/context
```

Responses use redacted context models only.

The API does not expose contact channels, emails, notes or event metadata containing private payloads.

Relationship mutations remain internal/local service calls in this slice. External connector ingestion belongs to Operator Integration.

## 13. Import boundary

V0.2D does not automatically import the existing private Markdown CRM, Gmail, Apollo, or GitHub vault data.

The current CRM is a product-research source used to validate the domain model.

A later operator/import adapter may translate authorized external observations into `RelationshipEvent` and `CareerContact` writes.

## 14. Privacy and public/private separation

Public repo:

- strict models;
- SQLite repository/service implementation;
- fictional fixtures;
- tests;
- redacted context rendering;
- API contracts.

Private runtime:

- `state/relationships.local.sqlite3`;
- real contact names and channels;
- source references that reveal personal data;
- private notes;
- provider IDs;
- imported CRM/Gmail history.

`.gitignore` and CI privacy guards must cover the relationship database and any generated private snapshot artifact.

## 15. Failure behavior

- missing relationship DB/config: Target Accounts continues with an empty-memory implementation rather than breaking health or ordinary radar routes;
- malformed private data: fail closed for the affected relationship read/write and return sanitized local/API errors;
- naive datetimes: reject;
- contact belonging to another account: reject;
- preferred contact not usable: reject;
- duplicate event ID with identical stored event: return stored event idempotently;
- duplicate event ID with conflicting payload: reject as integrity conflict;
- context generation must never expose raw private payloads during errors.

## 16. Testing strategy

All implementation tasks follow TDD.

Required test groups:

1. strict model validation and timezone rules;
2. SQLite initialization and private path behavior;
3. contact/account CRUD with cross-account guards;
4. append-only event idempotency and conflicting-ID rejection;
5. transition semantics for verification/contact/reply/process/cooldown/held states;
6. protection against accidental `PROCESS_OPEN` downgrade;
7. transaction rollback on invalid projection update;
8. redacted Context Bridge output;
9. Target Accounts integration and action precedence;
10. `FOLLOW_UP` requiring explicit new reason plus minimum age;
11. API privacy tests proving no email/contact name/private note fields leak;
12. full regression suite, compile, whitespace check and private-file guard.

## 17. Explicit non-goals

V0.2D does not:

- send email;
- create Gmail drafts;
- submit applications;
- search the web;
- consume Apollo credits;
- discover contacts automatically;
- scrape mailbox history;
- import the private Markdown CRM automatically;
- schedule follow-ups;
- notify users in the background;
- rank humans by relationship value;
- publish real contacts in the repository.

## 18. Success criteria

The slice is complete when:

1. Opportunity OS can persist and retrieve a private company/contact relationship without publishing PII;
2. every relationship change can be represented by an append-only auditable event;
3. the system can represent “known but held” contacts explicitly;
4. Target Accounts can distinguish untouched, cooldown, replied/open-process, held-contact, dormant and closed-process situations;
5. `FOLLOW_UP` is recommended only when historical context, minimum timing and a concrete new reason all allow it;
6. redacted context can be consumed without loading full CRM history;
7. no relationship-memory path can draft, send, apply, enrich, or mutate an external provider;
8. the full existing suite remains green.

## 19. Dependency direction

```text
Target Accounts
      ↓ reads
Relationship Context protocol
      ↑
Relationship Service
      ↑
SQLite Relationship Repository

Operator Integration (later)
      ↓ writes authorized observations
Relationship Service
```

Relationship Memory must not import Gmail/Apollo connector SDKs or depend on operator tooling.

## 20. Roadmap after V0.2D

After Relationship Memory + Context Bridge is implemented, the next architectural block remains Operator Integration:

```text
core deterministic state
↕
authorized operator adapters
↕
Gmail / contact discovery / public research
```

Only that later slice should automate translating external provider observations into the relationship-memory contracts defined here.
