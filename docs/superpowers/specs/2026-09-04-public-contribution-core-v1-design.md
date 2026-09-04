# Public Contribution Core V1 — Design

Date: 2026-09-04
Status: proposed design
Scope: domain-only contribution lifecycle for public repositories
Base: `main@6b90552e3417e54ddfbe98031e806edfe4c971fd`

## 1. Purpose

Opportunity OS currently models real job postings, target companies, relationship context, verified candidate evidence, and hiring-process observations. It does not yet have a truthful domain model for a different path that has appeared during real dogfood:

```text
public repository
    ↓
observable need or bounded contribution hypothesis
    ↓
maintainer/project contact
    ↓
concrete task or permission to contribute
    ↓
work
    ↓
PR / review / merge
    ↓
verifiable proof of work
```

The goal of V1 is to represent that path without pretending that a contribution is a vacancy, that a maintainer reply is hiring interest, or that a merged PR implies employment interest.

The invariant is:

```text
PUBLIC_CONTRIBUTION_ENTRY != JOB_OPENING
PR_OPENED != EMPLOYMENT_INTEREST
PR_MERGED != EMPLOYMENT_INTEREST
```

A public contribution can later become candidate evidence, relationship context, or a precursor to a paid opportunity, but those transitions require separate evidence and are out of scope for V1.

## 2. Why a separate domain

`Opportunity` represents a published requisition. `TargetAccount` represents an organization worth following or researching. `RelationshipMemory` represents what has already happened with a contact or organization.

A repository issue, a maintainer-stated need, and a scoped PR are none of those things.

Reusing `Opportunity` would fabricate a job opening. Reusing `TargetAccount` would collapse an organization-level research object with a repository/task-level work surface. Reusing `RelationshipMemory` as the canonical contribution store would turn relationship events into project-management state.

V1 therefore adds a new isolated package:

```text
app/contributions/
```

No existing job, target-account, outreach, process-email, or relationship contract is changed.

## 3. Design principles

1. Evidence before inference.
2. Public need and contribution hypothesis remain distinct.
3. Task quality and task availability remain distinct.
4. Contribution lifecycle and hiring lifecycle remain distinct.
5. Current state is projected from append-only events.
6. Blocking is orthogonal to lifecycle stage.
7. Repository identity is canonical; `TargetAccount` linkage is optional.
8. No private email bodies or provider payloads are persisted in public fixtures.
9. No external action authority is introduced.
10. V1 stays domain-only: no DB, API, GitHub mutation, Gmail integration, background worker, or autonomous outreach.

## 4. Core models

### 4.1 `PublicContributionEntry`

Represents why a public repository or task is worth considering as a contribution surface.

Proposed fields:

```text
entry_id
repository_full_name
repository_url
account_id?                 # optional TargetAccount linkage
origin
need_basis
need_statement
evidence_refs[]
task_ref?
bounded_task?
task_claim_state
expected_effort
risk_level
discovered_at
```

Enums:

```text
origin:
  PUBLIC_ISSUE
  HELP_WANTED
  REPOSITORY_RESEARCH
  MAINTAINER_PROPOSAL
  COLLABORATION_CALL

need_basis:
  OBSERVED
  MAINTAINER_STATED
  HYPOTHESIZED

task_claim_state:
  NONE
  AVAILABLE
  CLAIMED_SELF
  CLAIMED_OTHER
  CLOSED
  UNKNOWN

expected_effort:
  XS
  S
  M
  L
  UNKNOWN

risk_level:
  LOW
  MEDIUM
  HIGH
  UNKNOWN
```

Rules:

- `repository_full_name` and `repository_url` are required.
- `account_id` is optional. A legitimate public contribution may belong to an individual or project that is not a `TargetAccount`.
- `OBSERVED` and `MAINTAINER_STATED` require at least one evidence reference.
- `HYPOTHESIZED` may describe a bounded contribution idea but must not claim that the maintainer requested it.
- `CLAIMED_SELF` and `CLAIMED_OTHER` require `task_ref`.
- `AVAILABLE` requires `task_ref`.
- `bounded_task` is a scoped work description, not a promise that the work is available.
- Unknown extra fields fail closed.
- All timestamps are timezone-aware and normalized to UTC.

### 4.2 `ContributionEvent`

Represents one evidenced event in the contribution lifecycle.

Proposed fields:

```text
event_id
entry_id
kind
source_type
source_ref
observed_at
actor_ref?
work_ref?
reason?
```

Event kinds:

```text
DISCOVERED
OUTREACH_SENT
MAINTAINER_REPLIED
COLLABORATION_WELCOMED
WORK_PROPOSED
TASK_SELECTED
TASK_CLAIMED
WORK_STARTED
PR_OPENED
REVIEW_RECEIVED
CHANGES_REQUESTED
BLOCKED
UNBLOCKED
PR_MERGED
PR_CLOSED
PAUSED
RESUMED
DISCARDED
```

Source types:

```text
PUBLIC_GITHUB
PUBLIC_RESEARCH
EMAIL_PROVIDER
MANUAL
```

Rules:

- Every event has a provenance-bearing `source_ref`.
- V1 may model an event whose source is private (`EMAIL_PROVIDER`) but public dogfood fixtures must not contain private body text, email addresses, or provider payloads.
- `PR_OPENED`, `PR_MERGED`, and `PR_CLOSED` require `work_ref`.
- `BLOCKED` requires a bounded `reason`.
- `UNBLOCKED` clears the active blocker during projection.
- Events are immutable values; correction is represented by later evidence, not mutation of history.

## 5. Deterministic projection

### 5.1 Primary stage

`ContributionContext` is derived from an entry plus its ordered events.

The primary stage is exclusive:

```text
DISCOVERED
CONTACTED
ENGAGED
TASK_READY
IN_PROGRESS
IN_REVIEW
COMPLETED
PAUSED
DISCARDED
```

The projected context contains:

```text
entry_id
stage
blocking_reason?
last_event_kind?
last_observed_at?
task_claim_state
active_work_ref?
event_count
```

Projection intent:

```text
DISCOVERED                 -> DISCOVERED
OUTREACH_SENT              -> CONTACTED
MAINTAINER_REPLIED         -> ENGAGED
COLLABORATION_WELCOMED     -> ENGAGED
WORK_PROPOSED              -> ENGAGED
TASK_SELECTED              -> TASK_READY
TASK_CLAIMED               -> TASK_READY
WORK_STARTED               -> IN_PROGRESS
PR_OPENED                  -> IN_REVIEW
REVIEW_RECEIVED            -> IN_REVIEW
CHANGES_REQUESTED          -> IN_REVIEW
PR_MERGED                  -> COMPLETED
PR_CLOSED                  -> COMPLETED
PAUSED                     -> PAUSED
RESUMED                    -> recompute from last substantive non-pause event
DISCARDED                   -> DISCARDED
```

`BLOCKED` and `UNBLOCKED` do not replace the primary stage.

Example:

```text
PR_OPENED
→ stage = IN_REVIEW

BLOCKED: external deployment authorization required
→ stage = IN_REVIEW
→ blocking_reason = external deployment authorization required

UNBLOCKED
→ stage = IN_REVIEW
→ blocking_reason = null
```

This prevents a real PR from disappearing from review state merely because an external dependency is blocked.

### 5.2 Ordering and determinism

Events are ordered by:

```text
(observed_at, event_id)
```

The explicit `event_id` tie-breaker makes projection deterministic for equal timestamps.

A repeated projection over the same canonical entry and event sequence must produce byte-equivalent model output.

Invalid event sequences fail closed where semantics would otherwise be fabricated. At minimum:

- `PR_MERGED` without prior `PR_OPENED` is invalid in V1.
- `REVIEW_RECEIVED` or `CHANGES_REQUESTED` without prior `PR_OPENED` is invalid.
- `UNBLOCKED` without an active blocker is invalid.
- `TASK_CLAIMED` without a task reference is invalid.

V1 does not attempt a complete project-management state machine. The projector enforces only invariants needed by the dogfood cases.

## 6. `ProofOfWork`

Represents a public artifact produced by the operator that can be independently inspected.

V1 intentionally supports pull requests only.

```text
proof_id
entry_id
artifact_kind              # PULL_REQUEST
repository_full_name
artifact_ref
artifact_url
status
observed_at
evidence_refs[]
```

Status:

```text
OPEN
MERGED
CLOSED_UNMERGED
```

Rules:

- `artifact_ref` must identify the public PR.
- `evidence_refs` must contain public provenance.
- `MERGED` is stronger proof that work was accepted upstream, but it does not imply employment interest, endorsement beyond the contribution, or permission to contact anyone.
- V1 does not automatically promote `ProofOfWork` into the existing candidate `EvidenceItem` model.
- Future evidence promotion must remain behind an explicit preview/confirmation boundary.

## 7. Dogfood fixtures

V1 uses five sanitized/public-evidence fixtures. The repository may retain public GitHub identities and public issue/PR URLs, but it must not commit private Gmail bodies, personal email addresses, private notes, or inferred hiring intent.

### Fixture A — hypothetical contribution surface

Pattern based on a public geospatial SDK repository with no explicit issue available.

Expected:

```text
need_basis = HYPOTHESIZED
task_claim_state = NONE
stage = DISCOVERED
```

The system must not rewrite the hypothesis as a maintainer-stated need.

### Fixture B — open unassigned issue

Pattern based on an explicit reproducible public bug with no assignee.

Expected:

```text
need_basis = OBSERVED
task_claim_state = AVAILABLE
stage = TASK_READY
```

### Fixture C — good issue already claimed by another contributor

Pattern based on a well-scoped public issue with strong acceptance criteria but another assignee.

Expected:

```text
task_claim_state = CLAIMED_OTHER
```

The model must preserve that distinction; issue quality must not imply availability.

### Fixture D — self-claimed issue with open PR

Pattern based on the Moracarta testing contribution, using only public GitHub evidence.

Expected event sequence:

```text
DISCOVERED
TASK_SELECTED
TASK_CLAIMED
WORK_STARTED
PR_OPENED
```

Expected projection:

```text
stage = IN_REVIEW
task_claim_state = CLAIMED_SELF
blocking_reason = null
```

Expected proof:

```text
artifact_kind = PULL_REQUEST
status = OPEN
```

### Fixture E — draft PR blocked by external authorization

Pattern based on a public draft PR whose deployment preview requires external team authorization.

Expected event sequence:

```text
PR_OPENED
BLOCKED
```

Expected projection:

```text
stage = IN_REVIEW
blocking_reason != null
```

This fixture protects the orthogonality of lifecycle stage and blocking state.

## 8. Package layout

Proposed minimum layout:

```text
app/contributions/
  __init__.py
  models.py
  projector.py

examples/contributions/
  public_contribution_dogfood.json

tests/
  test_contribution_models.py
  test_contribution_projection.py
  test_contribution_dogfood.py
  test_proof_of_work.py
```

If the repository's existing fixture conventions make another public path more consistent, implementation may use that existing convention without changing the domain contract.

## 9. Testing strategy

Implementation follows TDD.

Required regression coverage:

1. strict models reject unknown fields;
2. timezone-naive timestamps fail closed;
3. observed/maintainer-stated needs require provenance;
4. hypotheses cannot silently become observed needs;
5. task availability and task quality are independent;
6. claimed task requires a task ref;
7. deterministic event ordering produces stable projection;
8. outreach without reply projects `CONTACTED`, not `ENGAGED`;
9. maintainer reply projects `ENGAGED` without fabricating a task;
10. task selection/claim projects `TASK_READY`;
11. work start projects `IN_PROGRESS`;
12. PR open projects `IN_REVIEW`;
13. blocker preserves the current primary stage;
14. unblock clears only the blocker;
15. review before PR fails closed;
16. merge before PR fails closed;
17. merged PR projects `COMPLETED`;
18. `ProofOfWork(MERGED)` never creates employment semantics;
19. all five dogfood fixtures project the expected result;
20. no fixture contains private email body text or personal email addresses.

The final implementation gate must include the focused contribution suite plus the repository's existing full pytest/compile/private-file checks.

## 10. Explicit non-goals

V1 does not add:

- a GitHub search/radar adapter;
- GitHub issue assignment or PR creation authority;
- Gmail collaboration-response classification;
- mailbox sync;
- target-account scoring changes;
- CV generation changes;
- automatic `EvidenceItem` promotion;
- automatic relationship mutation;
- delivery-failure handling;
- hiring-process deadlines/actions;
- DB persistence;
- HTTP API routes;
- background jobs;
- autonomous outreach or follow-up;
- an employment-opportunity inference from public contribution activity.

Those remain separate future slices.

## 11. Future seams

The V1 domain should leave clean seams for later work without implementing them now:

```text
Contribution Radar
  public GitHub evidence
  → PublicContributionEntry preview

Contribution Engagement
  selected email/public event
  → ContributionEvent preview
  → human import

Proof promotion
  ProofOfWork
  → evidence preview
  → human confirmation
  → candidate EvidenceItem

Search Health
  discovered
  → maintainer replied
  → task claimed
  → PR opened
  → PR merged
```

The contribution funnel must remain separate from the hiring funnel:

```text
applications → interviews → offers
```

## 12. Acceptance boundary

Public Contribution Core V1 is complete when:

- the four strict domain objects exist (`PublicContributionEntry`, `ContributionEvent`, `ContributionContext`, `ProofOfWork`);
- contribution stage is deterministically projected from append-only events;
- blocker state is orthogonal to lifecycle stage;
- optional `TargetAccount` linkage is supported without being required;
- the five public/sanitized dogfood cases pass;
- no existing `Opportunity`, `TargetAccount`, `RelationshipMemory`, Process Email, Outreach Core, DB, or API contract is modified;
- the full existing repository test gate remains green;
- no new external action authority exists.
