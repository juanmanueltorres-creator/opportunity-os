# Daily Curation Run V1

Daily Curation Run is a read-only orchestration surface for the daily community
opportunity workflow.

It combines existing verification and digest components without creating a new source
of truth.

## Core output

One run returns three operational blocks:

1. `review` — the top human review session;
2. `publishable` — the Community Digest after excluding the full verification hold;
3. `held` — opportunities that still require verification work.

```text
stored opportunities
        |
        +-> Verification Queue -> full hold set
        |          |
        |          +-> Review Session -> top N work cards
        |
        +-> Community Digest Preview
                   |
                   +-> exclude full hold set before digest selection
                   |
                   +-> publishable digest
```

## Publishable semantics

`publishable` means:

- the opportunity passed Community Digest rules;
- it is not currently present in Verification Queue;
- it is not explicitly closed;
- it is not a discovery-only signal;
- it satisfies the configured freshness and digest selection policy.

It does **not** mean:

- the item was sent or published;
- the item is personally recommended to any candidate;
- the item is guaranteed to remain open indefinitely;
- the system applied to it.

```text
PUBLISHABLE != PUBLISHED
PUBLISHABLE != PERSONAL_RECOMMENDATION
```

## Verification hold

The full Verification Queue is used internally as the exclusion set.

This is important: `held_items_limit` only controls how many held items are displayed
in the response. It does not weaken publication gating.

For example:

```text
held total = 40
held shown = 20

all 40 are excluded from publishable selection
```

## Selection before caps

Held opportunity IDs are removed before Community Digest selection.

This preserves correct backfilling and diversity caps. A held LinkedIn item does not
consume the source cap and prevent a later verified LinkedIn opportunity from becoming
publishable.

## Review block

The review block reuses `VerificationReviewSessionService`.

It is always the prefix of the same Verification Queue ordering used for the full hold
set.

If those snapshots disagree during a run, the orchestration fails closed rather than
returning internally inconsistent review work.

## Held block

The held block exposes:

- total held count;
- displayed count;
- omitted count;
- displayed queue items;
- reason counts across the full hold set.

The default display limit is 20.

## Endpoint

`POST /api/v1/curation/daily`

Default behavior:

- review batch: 5;
- held display: 20;
- digest max items: 10;
- WhatsApp renderer;
- queue/digest policies inherit their existing defaults.

The endpoint supports the existing queue timing controls and digest diversity/freshness
controls, plus Markdown/WhatsApp rendering options.

## Profile independence

Daily Curation Run does not use:

- CandidateProfile;
- CAREER score;
- INCOME_NOW score;
- personal eligibility;
- personal tier;
- selected intent.

It is a community curation surface.

## Read-only boundary

A Daily Curation Run does not:

- ingest or refresh external sources;
- record `SEEN`;
- record availability verification;
- create evidence drafts;
- invoke verification confirm;
- mutate `Opportunity.status`;
- send WhatsApp/email;
- publish Community Digest externally;
- apply to opportunities.

It only reads current stored state and composes existing projections.

## Dependency boundary

The default Daily Curation service is available only when all three default read
services exist:

- Verification Queue;
- Verification Review Session;
- Community Digest Preview.

If a required dependency is disabled, the daily run returns unavailable instead of
reconstructing hidden alternate logic.

## Run identity

The deterministic run ID binds:

- generated time;
- curation policy;
- review session ID;
- publishable digest ID;
- displayed held IDs;
- total held count;
- full held reason counts.

The same snapshot and policy produce the same run ID.

A new verification, source sighting, or policy change can produce a different run
identity.

## Authority boundary

Daily Curation V1 coordinates existing evidence-aware components.

It does not expand authority beyond those components.

```text
CURATION RUN != DISCOVERY FETCH
CURATION RUN != VERIFICATION
CURATION RUN != SEND
CURATION RUN != APPLY
```
