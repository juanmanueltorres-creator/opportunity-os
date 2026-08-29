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

The public repository contains only contracts, repository/service code, migrations created by `initialize()`, and fictional fixtures.

## 2. Why this exists

Target Accounts can already decide that a company is worth watching or approaching, but V0.2A2 only knows one historical fact:

```text
last_contacted_at(account_id)
```

That is not enough for real outreach decisions.

The operating system needs to distinguish situations such as:

- the company has never been contacted;
- a recruiter was contacted recently and the cooldown is active;
- the recruiter replied and there is an open process;
- a second technical contact is known but intentionally held back;
- the prior process closed and a new concrete reason now exists to reconnect;
- the company is worth watching but no trustworthy contact path exists yet.

Without this memory, every run risks starting from zero, duplicating outreach, contradicting prior context, or treating a valuable long-term contact as a disposable lead.

## 3. Design principles

### 3.1 Memory informs; it does not authorize

Relationship Memory may recommend or suppress an action. It must never create a Gmail draft, send email, apply to a role, enrich a contact, or mutate an external system.

No relationship action named `SEND` exists in this slice.

### 3.2 Company state and person state are different

A company can have an open relationship while one particular contact is held, inactive, stale, or no longer verified.

The system therefore models:

```text
Account relationship
Contact directory
Interaction/event history
```

as separate concerns.

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

`UNVERIFIED` may be stored for research context but must never be treated as a usable outbound channel.

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
- `PROCESS_CLOSED`: a known process finished or was rejected/withdrawn/closed;
- `DORMANT`: historical relationship exists but no current process and no active cooldown-driven expectation.

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

`channel_value` can contain an email or other private contact detail. It is private-state data and is excluded from the default Context Bridge projection.

A contact with `verification_status=UNVERIFIED` or `STALE` cannot be considered a usable verified outbound contact.

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

`preferred_next_contact_id` may point only to an active `AVAILABLE` contact belonging to the same account.

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

It must not contain:

- contact names;
- email addresses;
- provider message IDs;
- mailbox bodies;
- private free-form notes;
- raw source payloads.

## 6. Storage architecture

V0.2D uses SQLite via stdlib `sqlite3`; no new runtime dependency is required.

Default private path:

```text
OPPORTUNITY_RELATIONSHIPS_PATH=state/relationships.local.sqlite3
```

The repository creates three logical stores.

### 6.1 `relationship_accounts`

Current account-level operational state.

Primary key: `account_id`.

Stores the strict serialized `RelationshipAccount` plus indexed fields needed for common reads such as `relationship_state`, `last_contacted_at`, `cooldown_until` and `open_process`.

### 6.2 `relationship_contacts`

Current private contact directory.

Primary key: `contact_id`.

Index by `account_id` and disposition.

### 6.3 `relationship_events`

Append-only history.

Primary key: `event_id`.

Index by:

```text
(account_id, occurred_at, event_id)
(contact_id, occurred_at, event_id)
```

The repository must return an existing event unchanged when the same `event_id` is appended again.

## 7. Update model and consistency

Relationship writes go through a `RelationshipService`; callers should not directly coordinate account/contact/event mutations.

For every accepted relationship event, the service performs one logical transaction:

```text
validate event
→ append event idempotently
→ update contact state if the event affects a contact
→ update account projection
→ commit
```

If any step fails, the transaction rolls back.

The append-only event remains the audit record; current state is the operational projection.

### 7.1 Required transition effects

Minimum behavior:

- `CONTACTED`
  - set `relationship_state=CONTACTED` unless a stronger open-process state already exists;
  - update `last_contacted_at`;
  - set or refresh cooldown according to policy when supplied by the service;
- `REPLIED`
  - update `last_reply_at`;
  - set `relationship_state=REPLIED` unless `PROCESS_OPEN` is already active;
- `PROCESS_OPENED`
  - set `relationship_state=PROCESS_OPEN` and `open_process=true`;
- `PROCESS_UPDATED`
  - requires an open process and preserves `PROCESS_OPEN`;
- `PROCESS_CLOSED`
  - requires an open process;
  - set `relationship_state=PROCESS_CLOSED` and `open_process=false`;
- `CONTACT_HELD`
  - set the referenced contact disposition to `HELD`;
  - clear `preferred_next_contact_id` if it points to that contact;
- `CONTACT_RELEASED`
  - move a valid active held contact back to `AVAILABLE`;
- `COOLDOWN_SET`
  - set a timezone-aware `cooldown_until` later than or equal to `occurred_at`;
- `COOLDOWN_CLEARED`
  - clear the account cooldown.

Invalid transitions fail closed with sanitized errors.

## 8. Relationship policy

Defaults:

```text
spontaneous_contact_cooldown_days = 30
follow_up_min_days = 5
stale_contact_days = 180
```

These defaults guide recommendations only. They are not automated send schedules.

A manually stored `cooldown_until` always overrides a calculated default.

## 9. Target Accounts integration

V0.2A2 currently depends on:

```python
OutreachHistory.last_contacted_at(account_id) -> datetime | None
```

V0.2D replaces this narrow dependency with a richer read protocol:

```python
RelationshipMemory.context_for(account_id, *, now) -> RelationshipContext
```

Target selection remains deterministic and side-effect free.

### 9.1 Recommended action precedence

Relationship state is applied before ordinary target-account affinity/action rules.

```text
open process
    -> WATCH

cooldown active
    -> WATCH

PROCESS_CLOSED or DORMANT + explicit new reason
    -> FOLLOW_UP

usable contact count == 0
    -> RESEARCH_CONTACT

usable contacts exist but all relevant contacts are HELD
    -> WATCH

high affinity + confidence + no blocking history
    -> PREPARE_SPECULATIVE

otherwise
    -> WATCH
```

`FOLLOW_UP` is introduced as a recommendation state in V0.2D. It means “there is history and a defensible reason to prepare a follow-up.” It does not create or send one.

The selector must never return `SEND`.

## 10. New-reason rule

A prior relationship does not become eligible for `FOLLOW_UP` simply because time passed.

A follow-up candidate requires at least one explicit current reason, for example:

- a newly published relevant role;
- a meaningful new company hiring signal;
- a recruiter reply requesting future contact;
- cooldown expiry plus a materially new capability/evidence point;
- a previously open process changing state in a way that invites follow-up.

The reason is represented as a short structured/operator-provided string and stored as `last_reason`/event reason with provenance when available.

No LLM-generated justification is treated as evidence by itself.

## 11. Context Bridge

The bridge produces a compact, deterministic summary for operator/ChatGPT use without requiring the full private database to be loaded into context.

### 11.1 Snapshot contract

```text
RelationshipContextSnapshot
- generated_at
- accounts[]
```

Each account item contains only the redacted `RelationshipContext` fields.

### 11.2 Human-readable rendering

A renderer may produce:

```text
TARGET RELATIONSHIPS
- example-co: PROCESS_OPEN | last contact 2026-08-20 | cooldown active | WATCH
- sample-labs: DORMANT | verified contact available | new reason: backend role | FOLLOW_UP
- demo-industrial: UNTOUCHED | no verified contact | RESEARCH_CONTACT
```

The renderer must not include private contact names or addresses by default.

## 12. API boundary

V0.2D may expose read-only local API endpoints:

```text
GET /api/v1/relationships/{account_id}/context
GET /api/v1/relationships/context
```

Responses use redacted context models only.

The public API does not expose contact channels, emails, notes or event metadata containing private payloads.

Relationship mutations remain internal/local service calls in this slice. External connector ingestion belongs to Operator Integration.

## 13. Import and migration boundary

V0.2D does not automatically import the existing private Markdown CRM, Gmail, Apollo, or GitHub vault data.

The current CRM is a product-research source used to validate the domain model.

A later operator/import adapter may translate authorized external observations into `RelationshipEvent` and `CareerContact` writes.

This keeps the core deterministic and testable without provider access.

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

- missing relationship DB/config: Target Accounts continues to work with an empty-memory implementation rather than breaking health or ordinary radar routes;
- malformed private data: fail closed for the affected relationship read/write and return sanitized local/API errors;
- naive datetimes: reject;
- contact belonging to another account: reject;
- preferred contact not active/available: reject;
- duplicate event ID with identical stored event: return stored event idempotently;
- duplicate event ID with conflicting payload: reject as integrity conflict;
- context generation must never silently expose raw private payloads during errors.

## 16. Testing strategy

All implementation tasks follow TDD.

Required test groups:

1. strict model validation and timezone rules;
2. SQLite initialization and private path behavior;
3. contact/account CRUD with cross-account guards;
4. append-only event idempotency and conflicting-ID rejection;
5. transition semantics for contact/reply/process/cooldown/held states;
6. transaction rollback on invalid projection update;
7. redacted Context Bridge output;
8. Target Accounts integration and action precedence;
9. `FOLLOW_UP` requiring an explicit new reason;
10. API privacy tests proving no email/contact name/private note fields leak;
11. full regression suite, compile, whitespace check and private-file guard.

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
5. `FOLLOW_UP` is recommended only when both historical context and a concrete new reason exist;
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
