# Contribution Intake / Observation Bridge V1 — Design

Date: 2026-09-04
Status: proposed design
Base: `main` at `c1ee646e5797d5e06ca6139cf17924d2029991d1`

## 1. Purpose

Public Contribution Core V1 can represent contribution surfaces, contribution events, projected contribution context, and public proof of work. It does not yet provide a safe path from an explicitly selected public GitHub issue or pull request into those domain objects.

Contribution Intake / Observation Bridge V1 adds that path while preserving the authority boundary already established by Public Contribution Core.

The intended flow is:

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
local ContributionEvent or new PublicContributionEntry
        ↓
ContributionContext
```

The bridge observes public repository facts. It does not claim tasks, comment, open pull requests, merge, contact maintainers, or infer employment interest.

## 2. Hard invariants

The following invariants are normative:

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

The bridge may convert an explicit public GitHub fact into local contribution state only after an operator previews and confirms the exact observation.

The bridge must never convert repository activity into hiring, recruiting, endorsement, or contact permission semantics.

## 3. Scope

V1 supports one explicitly selected public GitHub issue or pull request at a time.

It supports:

- public issue availability and assignment state;
- public issue closure for an already-known contribution entry;
- public pull request open, review, changes-requested, merge, and close facts;
- narrowly evidenced external authorization/permission blockers;
- deterministic preview and import;
- local SQLite persistence of entries, events, and import receipts;
- a thin local CLI for explicit preview/import dogfood;
- optional read-only GitHub authentication through an environment token.

V1 does not support:

- repository discovery or scanning;
- contribution ranking or radar;
- automatic issue assignment;
- issue comments;
- pull-request creation or mutation;
- merge authority;
- Gmail collaboration-response classification;
- maintainer conversation interpretation;
- Relationship Memory mutation;
- Outreach integration;
- CV changes;
- automatic `EvidenceItem` or `ProofOfWork` promotion;
- employment inference;
- background polling;
- HTTP API routes;
- autonomous follow-up.

## 4. Architectural position

The bridge is a sibling of the existing Operator Observation Bridge, not an extension of it.

The existing `OperatorObservation` contract is relationship/hiring-oriented: it requires `account_id` and normalizes into `RelationshipEvent`. Contribution observations must not be pushed through that contract.

V1 introduces contribution-specific bridge components under the contribution subsystem:

```text
app/contributions/
  models.py                 # existing core + small compatibility amendments
  projector.py              # existing core + small compatibility amendments
  repository.py             # new local persistence
  observations.py           # new observation/preview/import models
  github_provider.py        # explicit public GitHub read adapter
  normalizer.py             # observation -> entry/event candidate
  bridge.py                 # preview/import service
  intake_cli.py             # explicit local operator surface
```

No contribution model is added to `app.operator_bridge`, `app.relationships`, `app.outreach`, or `app.process_email`.

## 5. Required Public Contribution Core compatibility amendments

Real intake exposes two gaps in the just-merged core. These are treated as compatibility corrections required by this bridge, not as unrelated refactoring.

### 5.1 Initial `CLAIMED_SELF` projection

The approved Public Contribution Core design specifies:

```text
task_claim_state = AVAILABLE      -> TASK_READY
task_claim_state = CLAIMED_SELF   -> TASK_READY
otherwise                         -> DISCOVERED
```

The current implementation only initializes `AVAILABLE` as `TASK_READY`.

V1 must correct the projector so:

```text
AVAILABLE     -> TASK_READY
CLAIMED_SELF  -> TASK_READY
CLAIMED_OTHER -> DISCOVERED
```

This is required for the Moracarta issue #25 dogfood case: a public issue already assigned to the operator is an actionable task, not merely a discovered surface.

A regression test must freeze this behavior.

### 5.2 Public issue closure requires a task-close event

The current core has no event that means "the public task/issue itself closed". Mapping issue closure to `PR_CLOSED`, `DISCARDED`, or `PAUSED` would fabricate semantics.

V1 adds:

```text
ContributionEventKind += TASK_CLOSED
```

`TASK_CLOSED` requires `task_ref` and sets:

```text
task_claim_state = CLOSED
```

Stage behavior is conservative:

```text
if current stage in {DISCOVERED, CONTACTED, ENGAGED, TASK_READY, PAUSED}:
    stage = CLOSED
elif current stage in {IN_PROGRESS, IN_REVIEW, COMPLETED, CLOSED, DISCARDED}:
    preserve current stage
```

Rationale:

- a closed issue with no work underway is no longer actionable;
- closing the issue must not erase an already-open PR or completed contribution;
- a reopened issue can later emit `TASK_RELEASED`, returning it to `TASK_READY`.

A new already-closed issue is not imported as a new entry in V1. `ISSUE_CLOSED` is accepted only for an existing contribution entry.

## 6. Explicit GitHub selection

The bridge never scans GitHub. The operator supplies one exact public resource.

```text
GitHubContributionSelection
  resource_kind            # ISSUE | PULL_REQUEST
  repository_full_name
  number
  source_url
  operator_github_login
  entry_id?                # optional for ISSUE; required for PULL_REQUEST
```

Rules:

- `repository_full_name` is canonical `owner/repo`.
- `number` is positive.
- `source_url` must match the selected repository/resource identity.
- `operator_github_login` is explicit input used only to distinguish self-assignment from assignment to another contributor.
- GitHub login comparison is case-insensitive after canonical normalization.
- `entry_id` is optional for an issue because a new public issue may create a proposed entry.
- `entry_id` is mandatory for a pull request.

### 6.1 No automatic PR-to-issue linkage

The bridge must not infer contribution lineage from PR body text such as:

```text
Closes #25
Fixes #106
Related to #1
```

For a pull request, the operator must explicitly identify the existing contribution entry.

This prevents textual cross-links from silently becoming authoritative task lineage.

## 7. Read-only GitHub provider

`GitHubPublicContributionProvider` may issue public GitHub GET requests only for the explicitly selected resource and the minimum public subresources needed to classify it.

Allowed reads in V1:

- selected issue metadata;
- selected pull request metadata;
- reviews for the selected pull request;
- commit/check/status metadata needed for bounded blocker detection.

Forbidden provider actions:

- POST, PUT, PATCH, DELETE;
- search endpoints for repository discovery;
- issue assignment;
- comments;
- review submission;
- pull-request mutation;
- merge;
- repository mutation.

The provider exposes a protocol so tests use fixtures/fakes rather than live GitHub.

### 7.1 Authentication

Public unauthenticated reads are valid.

An optional `GITHUB_TOKEN` may be used only as a bearer credential for read requests and rate-limit relief.

The token:

- is never persisted;
- is never serialized into an observation;
- is never logged;
- is never included in error messages;
- does not expand V1 action authority.

### 7.2 Transient source material

GitHub responses may contain fields not needed by the domain, including issue/PR bodies and verbose check descriptions.

V1 persists only the allowlisted typed facts required by the observation, entry, event, and receipt contracts.

Raw issue bodies, raw PR bodies, raw review text, raw check logs, HTTP headers, and provider credentials are not persisted.

## 8. GitHub snapshot models

Provider payloads are normalized immediately into strict transient snapshots.

### 8.1 Issue snapshot

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
```

The issue body is not part of this model.

### 8.2 Pull request snapshot

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
  latest_relevant_review?
  relevant_check_snapshot?
```

Review snapshot:

```text
GitHubReviewSnapshot
  review_ref
  reviewer_login?
  state                    # APPROVED | COMMENTED | CHANGES_REQUESTED | DISMISSED
  submitted_at
```

Check snapshot:

```text
GitHubCheckSnapshot
  check_ref
  name
  state_or_conclusion
  description_code?
  observed_at
```

No raw review body or check log is stored.

## 9. Contribution observation

A `ContributionObservation` is a typed statement about one public GitHub fact.

```text
ContributionObservation
  observation_id
  source_type               # PUBLIC_GITHUB
  source_name               # github
  source_ref
  kind
  entry_id?
  repository_full_name
  observed_at
  task_ref?
  work_ref?
  actor_ref?
  reason_code?
```

Observation kinds:

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

- models use `extra="forbid"`;
- timestamps must be timezone-aware and normalize to UTC;
- `source_ref` is the exact public GitHub resource supporting the observation;
- issue observations require `task_ref`;
- PR/review observations require `work_ref`;
- `EXTERNAL_BLOCKER` requires a bounded allowlisted `reason_code`;
- observations contain no employment, recruiting, salary, hiring, or contact-permission fields.

## 10. Observation identity and canonical hashes

Observation identity must be stable across repeated reads of the same public fact.

The canonical identity basis is:

```text
PUBLIC_GITHUB
repository_full_name
resource_kind
resource_number
fact_kind
source_fact_identity
```

Examples:

- issue assignment state may use the issue update identity relevant to the observed state;
- PR open uses PR identity + created timestamp;
- review uses the public review identifier;
- merge uses PR identity + merged timestamp;
- check blocker uses check/status identity.

`observation_id` is derived from a SHA-256 digest of canonical identity fields.

`observation_sha256` hashes the complete typed observation in canonical JSON form.

The bridge reuses the semantic pattern of the Operator Bridge but not its relationship-specific models.

## 11. New issue intake

An issue selection without `entry_id` may propose a new `PublicContributionEntry` only when the issue is open.

The proposed entry is deterministic:

```text
entry_id
  = contrib-<sha256(PUBLIC_GITHUB|repository_full_name|ISSUE|issue_number)>

repository_full_name
  = issue repository

repository_url
  = canonical repository URL

origin
  = PUBLIC_ISSUE

need_basis
  = OBSERVED

need_statement
  = sanitized public issue title

evidence_refs
  = [issue_url]

task_ref
  = issue_url

bounded_task
  = sanitized issue title

discovered_at
  = operator observation time
```

Initial `task_claim_state` derives only from public issue state/assignees:

```text
open + no assignees
  -> AVAILABLE

open + operator login in assignees
  -> CLAIMED_SELF

open + assignee(s) and operator absent
  -> CLAIMED_OTHER
```

No issue body interpretation is required to create the entry.

A closed issue without an existing `entry_id` is blocked with:

```text
closed_issue_requires_existing_entry
```

V1 does not create historical closed entries from arbitrary GitHub URLs.

## 12. Existing issue normalization

For an issue tied to an existing entry, the current public issue snapshot is compared to the local contribution state.

Mapping:

```text
ISSUE_AVAILABLE
  -> TASK_RELEASED

ISSUE_CLAIMED_SELF
  -> TASK_CLAIMED_SELF

ISSUE_CLAIMED_OTHER
  -> TASK_CLAIMED_OTHER

ISSUE_CLOSED
  -> TASK_CLOSED
```

A candidate event is emitted only when it would represent a real change from the currently projected local state.

Examples:

- local `AVAILABLE`, GitHub still open/unassigned -> `NO_CHANGE`;
- local `CLAIMED_SELF`, GitHub still assigned to operator -> `NO_CHANGE`;
- local `CLAIMED_OTHER`, assignment removed -> `TASK_RELEASED`;
- local `AVAILABLE`, issue closes -> `TASK_CLOSED`.

The normalizer never emits an event solely to refresh a timestamp.

## 13. Pull request normalization

A pull request selection always requires an explicit existing `entry_id`.

The selected PR repository must match the contribution entry's `repository_full_name` as the upstream/base repository identity.

The normalizer emits at most one candidate `ContributionEvent` per preview.

This one-event rule keeps every imported fact individually reviewable and makes replay/idempotency straightforward.

### 13.1 Deterministic PR priority

If multiple public facts are visible in one PR snapshot, choose the first not-yet-represented fact in this order:

```text
1. PR_OPENED
2. PR_MERGED or PR_CLOSED
3. CHANGES_REQUESTED or REVIEW_RECEIVED
4. EXTERNAL_BLOCKER or BLOCKER_CLEARED
5. NO_CHANGE
```

Consequences:

- selecting an already-merged PR with no local `PR_OPENED` first proposes `PR_OPENED`; a subsequent preview may propose `PR_MERGED`;
- selecting an open PR with an authorization blocker first establishes `PR_OPENED`; a subsequent preview may propose `BLOCKED`;
- invalid core sequences are never bypassed merely because GitHub currently shows a later terminal state.

### 13.2 Review mapping

The latest relevant unseen public review maps as:

```text
CHANGES_REQUESTED -> CHANGES_REQUESTED
APPROVED           -> REVIEW_RECEIVED
COMMENTED          -> REVIEW_RECEIVED
DISMISSED          -> no event in V1
```

A review before local `PR_OPENED` is never imported first because `PR_OPENED` has higher normalization priority.

## 14. Bounded external blocker detection

A failed CI/check is not automatically a contribution blocker. Generic test failure may simply indicate that the submitted code is failing and must not be mislabeled as an external dependency.

V1 emits `EXTERNAL_BLOCKER` only when public structured evidence explicitly indicates authorization, permission, access, or action-required gating outside normal code-test failure.

Accepted evidence classes:

```text
GitHub check conclusion = ACTION_REQUIRED
```

or an allowlisted deterministic public status description match such as:

```text
authorization required
permission required
must have access
deployment access required
team authorization required
```

The persisted event reason is a bounded code, not raw provider text. Example:

```text
EXTERNAL_AUTHORIZATION_REQUIRED
```

Generic states such as these do not create `BLOCKED` by themselves:

```text
failure
error
tests failed
build failed
lint failed
```

If an active blocker exists and the same gating condition is demonstrably cleared, the bridge may propose `BLOCKER_CLEARED -> UNBLOCKED`.

## 15. Contribution preview

`ContributionPreview` is the human-review surface.

```text
ContributionPreview
  preview_version
  status                    # IMPORTABLE | NO_CHANGE | ALREADY_IMPORTED | BLOCKED
  observation_id
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

`external_actions` must always be empty and is validator-enforced.

`context_after` is projected in memory only. Preview performs no local mutation.

### 15.1 Preview state hash

`preview_sha256` binds:

```text
preview_version
observation_sha256
proposed_entry or existing canonical entry
candidate_event or null
canonical existing event history hash
projected context before
projected context after
```

This prevents confirmation of a preview after local contribution state has changed.

## 16. Preview statuses

```text
IMPORTABLE
  = exact observation can create one new entry or append one new event

NO_CHANGE
  = public fact is valid but local state already represents it; no import needed

ALREADY_IMPORTED
  = the exact deterministic observation/import identity already has a receipt

BLOCKED
  = source identity, entry lineage, domain sequence, or evidence rule is invalid
```

Representative bounded errors:

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

Errors must not include provider response bodies, credentials, raw review text, or raw check logs.

## 17. Import confirmation

```text
ContributionImportRequest
  observation
  preview_sha256
  confirmed_by
  confirmed_at
```

Rules:

- `confirmed_at >= observation.observed_at`;
- confirmation is explicit and local;
- import never executes a GitHub write;
- import does not re-fetch GitHub.

The preview represents an exact observed public snapshot. If GitHub changes afterward, that is a new observation, not a reason to rewrite history.

Import re-evaluates the current local contribution state and recomputes the preview hash. If local state changed, import returns `BLOCKED_STALE_PREVIEW`.

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

A new-entry intake may have no `contribution_event_id` because the immutable entry itself represents the initial observed task state.

Receipts do not contain source bodies or hiring semantics.

## 19. Local SQLite repository

V1 introduces:

```text
state/contributions.local.sqlite3
```

The path is private/local and must be gitignored and covered by the private-file CI guard.

The repository stores exactly three durable surfaces:

```text
contribution_entries
contribution_events
contribution_import_receipts
```

`ContributionContext` remains a projection and is not an independent source of truth.

### 19.1 Entry persistence

`PublicContributionEntry` is immutable after creation in V1.

Rules:

- new `entry_id` -> insert;
- identical replay -> idempotent;
- same `entry_id` with different canonical payload -> conflict;
- no update-in-place API exists.

### 19.2 Event persistence

`ContributionEvent` is append-only.

Rules:

- deterministic event identity;
- identical replay is idempotent;
- same event id with different payload is conflict;
- event order is validated by `(observed_at, event_id)`;
- the complete projected sequence must validate before commit;
- event append and receipt persistence are atomic.

### 19.3 Read behavior

Reading a missing default contribution database must not create the database or parent directory.

Initialization is explicit.

This preserves the repo's established no-side-effect read behavior.

## 20. Bridge service

`ContributionObservationBridge` owns preview/import orchestration.

Dependencies:

```text
ContributionObservationBridge
  -> GitHubPublicContributionProvider
  -> SQLiteContributionRepository
  -> ContributionProjector
  -> deterministic contribution normalizer
```

It does not depend on:

```text
OperatorBridgeService
RelationshipService
OutreachService
ProcessEmailService
CVPreparationService
```

### 20.1 Preview flow

```text
selection
  ↓
provider read
  ↓
strict transient snapshot
  ↓
build deterministic observation
  ↓
load existing entry/events if applicable
  ↓
normalize to proposed entry OR zero/one event
  ↓
project context before/after
  ↓
return hash-bound preview
```

### 20.2 Import flow

```text
confirmed request
  ↓
normalize same typed observation
  ↓
check identical prior receipt
  ↓
recompute current local preview hash
  ↓
reject stale/conflicting/domain-invalid state
  ↓
atomic entry/event + receipt transaction
  ↓
return receipt
```

## 21. Thin local CLI

V1 includes a local CLI only to make the bridge dogfoodable without adding an HTTP API.

Illustrative commands:

```text
python -m app.contributions.intake_cli preview \
  --url https://github.com/trixocom/odoo-argentina-trx-ce/issues/1 \
  --operator-login juanmanueltorres-creator
```

For an existing contribution / PR:

```text
python -m app.contributions.intake_cli preview \
  --url https://github.com/WesleyHanauer/moracarta/pull/42 \
  --entry-id <entry-id> \
  --operator-login juanmanueltorres-creator
```

Import requires an exact serialized preview plus explicit confirmation metadata.

The CLI:

- prints typed JSON;
- never asks GitHub to mutate anything;
- never auto-confirms;
- never imports on `preview`;
- does not expose tokens;
- defaults to the private local contribution DB path.

Exact CLI argument names may be adjusted during implementation to match existing CLI conventions without changing the domain contract.

## 22. Dogfood fixtures

Tests use sanitized public snapshots, not live GitHub network calls.

Public identities/URLs may remain because they are already public, but fixtures must contain no personal email addresses, private messages, access tokens, or inferred hiring intent.

### Fixture A — Trixo issue #1

Public pattern:

```text
open issue
no assignee
```

Expected new-entry preview:

```text
status = IMPORTABLE
proposed_entry.need_basis = OBSERVED
proposed_entry.task_claim_state = AVAILABLE
context_after.stage = TASK_READY
candidate_event = null
```

### Fixture B — Moracarta issue #25

Public pattern:

```text
open issue
assigned to operator
```

Expected new-entry preview:

```text
proposed_entry.task_claim_state = CLAIMED_SELF
context_after.stage = TASK_READY
```

This fixture freezes the compatibility correction from section 5.1.

### Fixture C — Crafter issue #106-like claimed-other case

Public pattern:

```text
open useful issue
assigned to another contributor
```

Expected:

```text
proposed_entry.task_claim_state = CLAIMED_OTHER
context_after.stage = DISCOVERED
```

The bridge must not mark it actionable merely because the problem is good.

### Fixture D — Moracarta PR #42

Given the explicit Moracarta contribution entry:

```text
open PR
not merged
```

Expected first PR preview:

```text
candidate_event.kind = PR_OPENED
context_after.stage = IN_REVIEW
```

### Fixture E — SUNAT PR #115 authorization blocker

Given an explicit SUNAT contribution entry and a public PR snapshot whose public check description explicitly indicates team/deployment authorization gating:

First preview/import:

```text
PR_OPENED
-> IN_REVIEW
```

Second preview/import:

```text
BLOCKED(reason=EXTERNAL_AUTHORIZATION_REQUIRED)
-> stage remains IN_REVIEW
-> blocking_reason is non-null
```

Generic CI failure without explicit authorization evidence must not produce this blocker.

## 23. Determinism and fail-closed rules

At minimum, regression tests must prove:

1. strict observation/snapshot models reject unknown fields;
2. naive datetimes fail;
3. GitHub token never enters typed models;
4. selected URL identity must match repo/kind/number;
5. new open unassigned issue proposes `AVAILABLE` entry;
6. new open self-assigned issue proposes `CLAIMED_SELF` entry;
7. `CLAIMED_SELF` initial projection is `TASK_READY`;
8. new other-assigned issue stays non-actionable;
9. new closed issue without entry is blocked;
10. existing issue closure maps to `TASK_CLOSED`;
11. `TASK_CLOSED` updates task state without erasing `IN_REVIEW`;
12. reopened issue can map to `TASK_RELEASED`;
13. PR selection without entry id is blocked;
14. PR repository mismatch is blocked;
15. PR body cross-link text never creates lineage;
16. PR open is imported before later visible merge/close facts;
17. review is never imported before PR open;
18. merge/close sequence remains valid under core projector rules;
19. exact review identity is idempotent;
20. generic CI failure does not create external blocker;
21. explicit auth/action-required evidence can create blocker;
22. blocker remains orthogonal to `IN_REVIEW`;
23. blocker clear maps to `UNBLOCKED` only when blocker is active;
24. one preview emits at most one candidate event;
25. repeated same source/local state returns `NO_CHANGE` or `ALREADY_IMPORTED` deterministically;
26. same observation + same local state yields identical preview hash;
27. local state change invalidates old preview hash;
28. import never calls a GitHub mutation method;
29. identical import is idempotent;
30. conflicting observation identity fails closed;
31. entry/event/receipt persistence is atomic;
32. reading missing DB creates no file;
33. public fixtures contain no private mail bodies or credentials;
34. contribution models still contain no employment authority fields;
35. default FastAPI/OpenAPI surface remains unchanged.

## 24. Privacy and logging

Logs may include bounded operational identifiers:

```text
repository_full_name
resource_kind
resource_number
observation_id
entry_id
status/error_code
```

Logs must not include:

```text
GitHub token
Authorization header
raw issue body
raw PR body
raw review body
raw check logs
private email address
private message content
```

Public URLs are acceptable provenance, but no system may reinterpret their existence as permission for outreach.

## 25. Release contract

Public documentation for this slice must state:

```text
GitHub reads are explicit and read-only.
Preview is local and non-mutating.
Import mutates only local contribution state after confirmation.
No GitHub write authority is added.
Contribution outcomes do not imply employment interest.
```

The release contract must also state that V1 is intake for explicitly selected resources, not repository discovery/radar.

## 26. Acceptance criteria

Contribution Intake / Observation Bridge V1 is complete only when:

- the `CLAIMED_SELF -> TASK_READY` compatibility bug is fixed and regression-tested;
- `TASK_CLOSED` exists with the conservative projection semantics defined here;
- strict GitHub issue/PR/review/check snapshot models exist;
- strict contribution observation/preview/import/receipt models exist;
- a read-only explicit GitHub provider exists;
- no provider mutation method exists in the V1 adapter surface;
- new open issues can be previewed as proposed immutable entries;
- PRs require explicit existing entry lineage;
- PR-to-issue linkage is never inferred from PR text;
- existing issue/PR state can normalize to zero or one contribution event;
- blocker classification is evidence-aware and generic CI failure does not become an external blocker;
- preview is deterministic and state-hash bound;
- import requires explicit human confirmation and rejects stale previews;
- SQLite persistence is append-only/idempotent/conflict-safe and atomic;
- missing-database reads are side-effect free;
- thin CLI preview/import dogfood works without adding HTTP routes;
- five public/sanitized dogfood cases pass;
- no existing hiring, relationship, outreach, CV, Process Email, or default API contract changes;
- full repository tests, compile gate, diff check, private-file guard, recruiter regressions, and offline runtime verification remain green.

## 27. Future seams

Explicitly deferred:

### Contribution Radar

```text
GitHub search/discovery
  -> ranked contribution candidates
  -> explicit operator selection
  -> this intake bridge
```

### Contribution Conversation Classifier

```text
explicit Gmail/public conversation
  -> contribution-response classification
  -> contribution observation preview
  -> human confirmation
```

This must remain separate from hiring Process Email.

### Proof-of-work promotion

```text
ContributionEvent / public PR state
  -> ProofOfWork preview
  -> human confirmation
  -> optional candidate evidence preview
```

No automatic promotion is authorized by this design.

### Monitoring

Background GitHub polling, notifications, and change watches require a separate design because they introduce scheduling, external freshness policy, and repeated network reads.

## 28. Design summary

V1 deliberately implements the narrow bridge:

```text
one selected public GitHub resource
        ↓
read-only factual snapshot
        ↓
strict contribution observation
        ↓
zero/one deterministic local transition
        ↓
hash-bound preview
        ↓
human confirmation
        ↓
append-only local contribution history
```

It makes Public Contribution Core operational without turning Opportunity OS into a GitHub bot, a recruiter inference engine, or an autonomous collaboration agent.