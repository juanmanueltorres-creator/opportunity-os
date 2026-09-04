# Contribution Intake / Observation Bridge V1 — Design

Date: 2026-09-04
Status: proposed design
Base: `main` at `c1ee646e5797d5e06ca6139cf17924d2029991d1`

## 1. Purpose

Public Contribution Core V1 can represent contribution surfaces, append-only contribution events, projected context, and public proof of work. It does not yet provide a safe path from an explicitly selected public GitHub issue or pull request into those domain objects.

Contribution Intake / Observation Bridge V1 adds that path:

```text
explicit public GitHub issue / PR
        ↓
read-only GitHub adapter
        ↓
typed ContributionObservation
        ↓
deterministic normalization
        ↓
ContributionPreview
        ↓
explicit human confirmation
        ↓
local PublicContributionEntry or ContributionEvent
        ↓
ContributionContext
```

The bridge observes public repository facts. It does not claim tasks, comment, open or mutate pull requests, merge, contact maintainers, or infer employment interest.

## 2. Hard invariants

```text
OBSERVE != CLAIM
OBSERVE != COMMENT
OBSERVE != OPEN_PR
IMPORT != EXTERNAL_ACTION
PUBLIC_CONTRIBUTION_ENTRY != JOB_OPENING
PR_OPENED != EMPLOYMENT_INTEREST
PR_MERGED != EMPLOYMENT_INTEREST
GOOD_PROBLEM != AVAILABLE_PROBLEM
PUBLIC_GITHUB_FACT != MAINTAINER_INTENT
```

The bridge may convert an explicit public GitHub fact into local contribution state only after the operator previews and confirms the exact observation.

## 3. V1 scope

V1 supports one explicitly selected public GitHub issue or pull request at a time.

Included:

- issue availability and assignment state;
- issue closure for an already-known entry;
- PR open, review, changes-requested, merge, and close facts;
- narrowly evidenced external authorization/permission blockers;
- deterministic preview/import;
- local SQLite persistence for entries, events, and import receipts;
- a thin local CLI for explicit dogfood;
- optional read-only GitHub authentication.

Excluded:

- GitHub search/radar/discovery;
- automatic issue assignment;
- comments or review submission;
- PR creation, update, close, or merge;
- background polling;
- Gmail collaboration classification;
- Relationship Memory mutation;
- Outreach/CV/Process Email integration;
- automatic `ProofOfWork` or `EvidenceItem` promotion;
- hiring or contact-permission inference;
- HTTP API routes.

## 4. Architectural position

This is a sibling of the existing Operator Observation Bridge, not an extension of it.

`OperatorObservation` is relationship/hiring-oriented: it requires `account_id` and normalizes into `RelationshipEvent`. Contribution observations must not enter that contract.

Proposed layout:

```text
app/contributions/
  models.py                 # existing core + compatibility amendments
  projector.py              # existing core + compatibility amendments
  repository.py             # local persistence
  observations.py           # observation/preview/import contracts
  github_provider.py        # explicit public GitHub GET adapter
  normalizer.py             # snapshot -> observation -> entry/event candidate
  bridge.py                 # preview/import orchestration
  intake_cli.py             # explicit local operator surface
```

No contribution model is added to `app.operator_bridge`, `app.relationships`, `app.outreach`, or `app.process_email`.

## 5. Required core compatibility corrections

Real intake exposes two gaps in the merged core. They are required corrections for this bridge, not unrelated refactoring.

### 5.1 `CLAIMED_SELF` must initialize as `TASK_READY`

The approved core design says:

```text
AVAILABLE     -> TASK_READY
CLAIMED_SELF  -> TASK_READY
otherwise     -> DISCOVERED
```

The current implementation only initializes `AVAILABLE` as `TASK_READY`.

V1 must correct that behavior and add a regression test. This is required for Moracarta issue #25: an issue already assigned to the operator is actionable, not merely discovered.

### 5.2 Add `TASK_CLOSED`

The core currently has no event for "the public issue/task closed". Mapping that fact to `PR_CLOSED`, `PAUSED`, or `DISCARDED` would fabricate semantics.

V1 adds:

```text
ContributionEventKind += TASK_CLOSED
```

`TASK_CLOSED` requires `task_ref` and sets:

```text
task_claim_state = CLOSED
```

Stage semantics:

```text
if stage in {DISCOVERED, CONTACTED, ENGAGED, TASK_READY, PAUSED}:
    stage = CLOSED
elif stage in {IN_PROGRESS, IN_REVIEW, COMPLETED, CLOSED, DISCARDED}:
    preserve stage
```

Closing an issue must not erase an open PR or a completed contribution. A later reopened issue may emit `TASK_RELEASED` and return to `TASK_READY`.

A newly selected already-closed issue cannot create a new entry in V1; `ISSUE_CLOSED` is accepted only for an existing contribution entry.

## 6. Explicit GitHub selection

```text
GitHubContributionSelection
  resource_kind             # ISSUE | PULL_REQUEST
  repository_full_name
  number
  source_url
  operator_github_login
  entry_id?                 # optional for ISSUE; required for PULL_REQUEST
```

Rules:

- repository identity is canonical `owner/repo`;
- resource number is positive;
- URL must match repository, kind, and number;
- operator login is explicit and used only for self-vs-other assignment;
- login comparison is case-insensitive after normalization;
- PR selection always requires explicit `entry_id`.

For an issue without `entry_id`, the bridge computes the deterministic issue entry id first. If that entry already exists, the issue is treated as an existing entry rather than as a new intake.

### 6.1 No automatic PR-to-issue lineage

PR text such as `Closes #25`, `Fixes #106`, or `Related to #1` is not authoritative lineage.

The operator must explicitly select the existing contribution entry for every PR preview.

## 7. Read-only GitHub provider

`GitHubPublicContributionProvider` performs only GET requests for the explicitly selected public resource and the minimum subresources needed to classify it.

Allowed reads:

- selected issue metadata;
- selected PR metadata;
- selected PR reviews;
- selected PR commit/check/status metadata required for bounded blocker detection.

Forbidden:

```text
POST
PUT
PATCH
DELETE
search/discovery endpoints
assignment
comments
review submission
PR mutation
merge
repository mutation
```

The provider exposes a protocol so tests use fakes/fixtures rather than live GitHub.

An optional `GITHUB_TOKEN` may be used only for read requests/rate-limit relief. It is never persisted, serialized, logged, or included in errors.

## 8. Transient GitHub snapshots

Raw GitHub responses normalize immediately into strict allowlisted snapshots. Raw issue/PR bodies, review text, check logs, headers, and credentials are not persisted.

### Issue

```text
GitHubIssueSnapshot
  repository_full_name
  issue_number
  issue_url
  title
  state                    # OPEN | CLOSED
  assignee_logins[]
  author_login?
  created_at
  updated_at
  closed_at?
  captured_at
```

### Pull request

```text
GitHubPullRequestSnapshot
  repository_full_name
  pr_number
  pr_url
  state                    # OPEN | CLOSED
  merged
  draft
  author_login?
  created_at
  updated_at
  closed_at?
  merged_at?
  head_sha
  reviews[]
  checks[]
  captured_at
```

Review:

```text
GitHubReviewSnapshot
  review_ref
  reviewer_login?
  state                    # APPROVED | COMMENTED | CHANGES_REQUESTED | DISMISSED
  submitted_at
```

Check:

```text
GitHubCheckSnapshot
  check_ref
  name
  state_or_conclusion
  description_code?
  fact_at
```

All timestamps are timezone-aware UTC after normalization.

## 9. Contribution observation

A `ContributionObservation` is one typed public fact.

```text
ContributionObservation
  observation_id
  source_type               # PUBLIC_GITHUB
  source_name               # github
  source_ref
  kind
  entry_id?
  repository_full_name
  public_title?             # bounded public issue title; required for issue intake
  fact_at                   # public fact occurrence time
  captured_at               # time Opportunity OS read the fact
  task_ref?
  work_ref?
  actor_ref?
  reason_code?
  source_fact_identity
```

Kinds:

```text
ISSUE_AVAILABLE
ISSUE_CLAIMED_SELF
ISSUE_CLAIMED_OTHER
ISSUE_CLOSED
PR_OPENED
REVIEW_RECEIVED
CHANGES_REQUESTED
PR_MERGED
PR_CLOSED
EXTERNAL_BLOCKER
BLOCKER_CLEARED
```

Rules:

- strict `extra="forbid"` models;
- issue observations require `task_ref` and bounded `public_title`;
- PR/review observations require `work_ref`;
- blocker observation requires an allowlisted `reason_code`;
- `captured_at >= fact_at` is not required because provider clocks/source timestamps may differ slightly, but both must be aware UTC;
- no employment, recruiting, salary, or contact-permission fields exist.

`fact_at` becomes the candidate `ContributionEvent.observed_at`. `captured_at` becomes a new entry's `discovered_at`.

## 10. Stable observation identity

Identity basis:

```text
PUBLIC_GITHUB
repository_full_name
resource_kind
resource_number
fact_kind
source_fact_identity
```

Examples:

- PR open: PR identity + created timestamp;
- review: public review id/ref;
- merge: PR identity + merged timestamp;
- issue closure: issue identity + closed timestamp;
- blocker: check/status identity.

`observation_id` is derived from a SHA-256 digest of canonical identity fields. `observation_sha256` hashes the full typed observation as canonical JSON.

## 11. New issue intake

An issue without an existing entry may propose a new immutable `PublicContributionEntry` only when the issue is open.

Deterministic identity:

```text
entry_id = contrib-<sha256(PUBLIC_GITHUB|repository_full_name|ISSUE|issue_number)>
```

Proposed fields:

```text
repository_full_name = issue repository
repository_url       = canonical repository URL
origin               = PUBLIC_ISSUE
need_basis           = OBSERVED
need_statement       = sanitized bounded public issue title
evidence_refs        = [issue_url]
task_ref             = issue_url
bounded_task          = sanitized bounded public issue title
discovered_at         = observation.captured_at
```

Initial claim state derives only from public state/assignees:

```text
open + no assignees                         -> AVAILABLE
open + operator login among assignees       -> CLAIMED_SELF
open + assignee(s), operator not among them -> CLAIMED_OTHER
```

No issue body interpretation is required.

Closed issue + no existing entry returns `BLOCKED` with `closed_issue_requires_existing_entry`.

New-entry import persists the entry and receipt atomically; no synthetic `ContributionEvent` is required because initial task state is already carried by the immutable entry.

## 12. Existing issue normalization

Mapping when a deterministic/existing entry is present:

```text
ISSUE_AVAILABLE       -> TASK_RELEASED
ISSUE_CLAIMED_SELF    -> TASK_CLAIMED_SELF
ISSUE_CLAIMED_OTHER   -> TASK_CLAIMED_OTHER
ISSUE_CLOSED          -> TASK_CLOSED
```

An event is emitted only if it represents a real change from projected local state.

Examples:

```text
local AVAILABLE + still open/unassigned -> NO_CHANGE
local CLAIMED_SELF + still self-assigned -> NO_CHANGE
local CLAIMED_OTHER + assignee removed   -> TASK_RELEASED
local AVAILABLE + issue closes           -> TASK_CLOSED
```

No event exists only to refresh a timestamp.

## 13. Pull request normalization

PR selection always requires an explicit existing entry. The selected PR's upstream/base repository identity must equal the entry's `repository_full_name`.

The normalizer emits at most one candidate event per preview.

### 13.1 Chronology, not semantic priority

A merged/closed PR may already contain older reviews or older blocker facts. Importing the terminal state before those older facts would make later append-only history impossible.

Therefore normalization works as follows:

1. If local history lacks `PR_OPENED`, propose `PR_OPENED` first using PR `created_at`.
2. Otherwise build the set of unseen admissible PR facts:
   - relevant reviews;
   - blocker/blocker-cleared facts;
   - merge or close fact.
3. Sort unseen facts by:

```text
(fact_at, deterministic_kind_order, source_fact_identity)
```

4. Select the earliest fact whose resulting core sequence is valid.
5. Emit at most that one event.
6. If none exists, return `NO_CHANGE`.

This preserves public chronology and append-only event ordering.

A deterministic tie order is frozen only for equal timestamps:

```text
CHANGES_REQUESTED
REVIEW_RECEIVED
EXTERNAL_BLOCKER
BLOCKER_CLEARED
PR_MERGED
PR_CLOSED
```

The tie order does not override actual timestamps.

### 13.2 Review mapping

```text
CHANGES_REQUESTED -> CHANGES_REQUESTED
APPROVED           -> REVIEW_RECEIVED
COMMENTED          -> REVIEW_RECEIVED
DISMISSED          -> ignored in V1
```

No review can import before local `PR_OPENED`.

## 14. Evidence-aware blocker detection

A generic failing CI check is not automatically an external blocker.

V1 emits `EXTERNAL_BLOCKER` only when structured public evidence explicitly indicates authorization, permission, access, or action-required gating outside ordinary code-test failure.

Accepted evidence:

```text
check conclusion = ACTION_REQUIRED
```

or an allowlisted deterministic status-description match such as:

```text
authorization required
permission required
must have access
deployment access required
team authorization required
```

Persisted reason is a bounded code, for example:

```text
EXTERNAL_AUTHORIZATION_REQUIRED
```

These alone do not create `BLOCKED`:

```text
failure
error
tests failed
build failed
lint failed
```

If an active blocker exists and the same gate is demonstrably cleared, the bridge may produce `BLOCKER_CLEARED -> UNBLOCKED`.

## 15. Contribution preview

```text
ContributionPreview
  preview_version
  status                    # IMPORTABLE | NO_CHANGE | ALREADY_IMPORTED | BLOCKED
  observation               # complete typed ContributionObservation
  observation_sha256
  preview_sha256
  entry_id
  source_ref
  proposed_entry?
  candidate_event?
  context_before?
  context_after?
  errors[]
  external_actions[]
```

`external_actions` must always be empty and validator-enforced.

Preview is read-only. `context_after` is projected in memory.

### 15.1 Preview hash

`preview_sha256` binds:

```text
preview_version
observation_sha256
proposed_entry or existing canonical entry
candidate_event or null
canonical current event-history hash
context_before
context_after
```

Same observation + same local state yields the same preview hash.

## 16. Preview statuses

```text
IMPORTABLE
  exact preview can insert one new entry or append one event

NO_CHANGE
  valid public fact is already represented by local state, but no exact prior receipt is required

ALREADY_IMPORTED
  exact deterministic observation/import identity already has a receipt

BLOCKED
  source identity, lineage, sequence, or evidence rule is invalid
```

Bounded errors include:

```text
unknown_contribution_entry
repository_mismatch
pr_requires_entry_id
closed_issue_requires_existing_entry
observation_identity_conflict
invalid_contribution_transition
stale_preview
unsupported_github_fact
external_blocker_not_evidenced
```

Errors never contain raw provider bodies, tokens, review text, or check logs.

## 17. Import contract

Import uses the exact serialized preview that the operator reviewed:

```text
ContributionImportRequest
  preview
  confirmed_by
  confirmed_at
```

Rules:

- `preview.status` must be `IMPORTABLE`;
- `confirmed_at >= preview.observation.captured_at`;
- import performs no GitHub read or write;
- import recomputes normalization/hash against current local state using the typed observation embedded in the preview;
- if local state changed, return `BLOCKED_STALE_PREVIEW`;
- the bridge never silently refreshes the external fact during import.

A later GitHub change becomes a new observation/preview rather than a rewrite of confirmed history.

## 18. Import receipt

```text
ContributionImportReceipt
  receipt_id
  observation_id
  observation_sha256
  preview_sha256
  entry_id
  contribution_event_id?
  source_ref
  confirmed_by
  confirmed_at
  processed_at
  status                    # IMPORTED | ALREADY_IMPORTED
```

New-entry intake can have no `contribution_event_id` because the immutable entry carries the initial state.

## 19. SQLite contribution repository

Default private path:

```text
state/contributions.local.sqlite3
```

It must be gitignored and added to the private/generated-file CI guard.

Durable tables:

```text
contribution_entries
contribution_events
contribution_import_receipts
```

`ContributionContext` remains a projection, not stored truth.

### Entries

- immutable after creation;
- new id inserts;
- identical replay is idempotent;
- same id with different canonical payload is conflict;
- no update-in-place API.

### Events

- append-only;
- deterministic identity;
- identical replay idempotent;
- identity conflict rejected;
- `(observed_at, event_id)` ordering enforced;
- complete projected sequence validates before commit.

### Transactions

New-entry import:

```text
entry + receipt
```

Existing-entry transition:

```text
event + receipt
```

Each pair is atomic.

Reading a missing default DB must not create the DB or parent directory. Initialization is explicit.

## 20. Bridge service

```text
ContributionObservationBridge
  -> GitHubPublicContributionProvider
  -> SQLiteContributionRepository
  -> ContributionProjector
  -> deterministic normalizer
```

It does not depend on Operator Bridge, Relationships, Outreach, Process Email, or CV services.

Preview flow:

```text
selection
  -> provider GET
  -> strict transient snapshot
  -> deterministic observation
  -> load current entry/events
  -> normalize to proposed entry OR zero/one event
  -> project before/after
  -> return hash-bound preview
```

Import flow:

```text
confirmed serialized preview
  -> check exact prior receipt
  -> recompute against current local state
  -> reject stale/conflicting/invalid state
  -> atomic local insert
  -> receipt
```

## 21. Thin local CLI

No HTTP route is added in V1.

Exact preview command:

```text
python -m app.contributions.intake_cli preview \
  --url <public-github-issue-or-pr-url> \
  --operator-login <github-login> \
  [--entry-id <existing-entry-id>] \
  [--db state/contributions.local.sqlite3] \
  --out <preview.json>
```

Behavior:

- performs explicit public GET read;
- writes the exact typed preview JSON to `--out`;
- also prints a compact human-readable summary;
- does not import;
- does not mutate GitHub.

Exact import command:

```text
python -m app.contributions.intake_cli import \
  --preview-file <preview.json> \
  --confirmed-by <operator-id> \
  [--db state/contributions.local.sqlite3]
```

Behavior:

- performs no GitHub network call;
- validates exact preview and local-state hash;
- imports only if `IMPORTABLE` and still current;
- prints typed receipt JSON;
- never auto-confirms.

## 22. Dogfood fixtures

Tests use sanitized public snapshots, not live network calls. Public repository identities/URLs are acceptable; fixtures contain no personal emails, private messages, tokens, or inferred hiring intent.

### A — Trixo issue #1

```text
open + unassigned
-> proposed entry AVAILABLE
-> context_after TASK_READY
-> candidate_event null
```

### B — Moracarta issue #25

```text
open + assigned to operator
-> proposed entry CLAIMED_SELF
-> context_after TASK_READY
```

This freezes the `CLAIMED_SELF` compatibility correction.

### C — claimed-other public issue

```text
open + assigned to another contributor
-> proposed entry CLAIMED_OTHER
-> context_after DISCOVERED
```

A good problem does not become available merely because it is relevant.

### D — Moracarta PR #42

Given an explicit Moracarta entry:

```text
open PR
-> PR_OPENED
-> IN_REVIEW
```

### E — SUNAT PR #115 authorization blocker

Given an explicit SUNAT entry and a sanitized public check snapshot with explicit authorization gating:

```text
first preview/import:
PR_OPENED -> IN_REVIEW

later chronological preview/import:
BLOCKED(reason=EXTERNAL_AUTHORIZATION_REQUIRED)
-> stage remains IN_REVIEW
-> blocking_reason non-null
```

A generic failing check must not produce the blocker.

## 23. Required regression coverage

At minimum:

1. strict models reject unknown fields;
2. naive datetimes fail;
3. token/authorization data cannot enter typed models;
4. URL identity mismatch is blocked;
5. new unassigned issue -> `AVAILABLE`;
6. new self-assigned issue -> `CLAIMED_SELF`;
7. initial `CLAIMED_SELF` -> `TASK_READY`;
8. other-assigned issue remains non-actionable;
9. closed new issue without entry is blocked;
10. existing closure -> `TASK_CLOSED`;
11. `TASK_CLOSED` does not erase `IN_REVIEW`;
12. reopened issue -> `TASK_RELEASED`;
13. PR without entry id is blocked;
14. PR repository mismatch is blocked;
15. PR body text never creates lineage;
16. `PR_OPENED` precedes all later PR facts;
17. unseen PR facts are selected chronologically;
18. equal timestamps use deterministic tie order;
19. older review is not stranded behind a later merge import;
20. review cannot precede PR open;
21. merge/close sequence respects core projector rules;
22. exact review identity is idempotent;
23. generic CI failure does not create external blocker;
24. explicit action-required/auth evidence can create blocker;
25. blocker remains orthogonal to `IN_REVIEW`;
26. blocker clear requires active blocker;
27. one preview emits at most one candidate event;
28. repeated represented state -> deterministic `NO_CHANGE`/`ALREADY_IMPORTED`;
29. same observation + local state -> same preview hash;
30. local state change invalidates old preview;
31. import uses embedded typed preview and does not re-fetch GitHub;
32. import never calls a GitHub mutation method;
33. identical import is idempotent;
34. identity conflict fails closed;
35. entry/receipt transaction is atomic;
36. event/receipt transaction is atomic;
37. missing DB read has no side effect;
38. fixtures contain no private payloads or credentials;
39. contribution models retain no employment-authority fields;
40. default FastAPI/OpenAPI surface remains unchanged.

## 24. Privacy, release boundary, and acceptance

Logs may include bounded identifiers only:

```text
repository_full_name
resource_kind
resource_number
observation_id
entry_id
status/error_code
```

Logs exclude tokens, auth headers, raw bodies, raw reviews, raw check logs, private emails, and private messages.

Public docs must state:

```text
GitHub reads are explicit and read-only.
Preview is local and non-mutating.
Import mutates only local contribution state after confirmation.
No GitHub write authority is added.
Contribution outcomes do not imply employment interest.
V1 is explicit-resource intake, not discovery/radar.
```

V1 is accepted only when:

- both core compatibility corrections are implemented and tested;
- strict snapshot and observation bridge contracts exist;
- the provider surface is GET-only;
- new open issues can preview deterministic immutable entries;
- PRs require explicit lineage;
- PR text cannot infer lineage;
- existing state normalizes to zero/one event in public chronology;
- blocker classification is evidence-aware;
- preview is deterministic and state-hash bound;
- import uses the exact confirmed serialized preview and rejects stale state;
- SQLite persistence is append-only/idempotent/conflict-safe/atomic;
- missing-DB reads are side-effect free;
- CLI preview/import works without HTTP API routes or GitHub writes;
- all five dogfood cases pass;
- hiring/relationship/outreach/CV/Process Email contracts remain unchanged;
- full repo tests, compile, diff check, private-file guard, recruiter regressions, and offline runtime gates remain green.

## 25. Future seams

Deferred designs:

```text
Contribution Radar
GitHub search -> ranked candidates -> explicit selection -> this bridge
```

```text
Contribution Conversation Classifier
explicit Gmail/public conversation -> contribution observation preview -> human confirmation
```

This remains separate from hiring Process Email.

```text
Proof-of-work promotion
ContributionEvent/public PR -> ProofOfWork preview -> human confirmation -> optional candidate evidence preview
```

No automatic promotion is authorized.

Background monitoring/polling is also deferred because it introduces scheduling and external freshness policy.

## 26. Summary

```text
one selected public GitHub resource
        ↓
read-only factual snapshot
        ↓
strict contribution observation
        ↓
zero/one chronological local transition
        ↓
hash-bound preview
        ↓
human confirmation
        ↓
append-only local contribution history
```

This makes Public Contribution Core operational without turning Opportunity OS into a GitHub bot, recruiter inference engine, or autonomous collaboration agent.