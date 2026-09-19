# Curation Change Brief v1

## Purpose

Render the latest curation run delta as a short deterministic operator-facing
brief without adding another source of truth.

Core boundaries:

`BRIEF = RENDER(DELTA)`
`BRIEF != NEW EVIDENCE`
`MEMBERSHIP CHANGE != CAUSAL EXPLANATION`

The feature is read-only.

## Endpoint

`GET /api/v1/curation/history/delta/brief?format=markdown`

Supported formats:

- `markdown`
- `plain`

## Response

The response preserves:

- delta status: `EMPTY`, `BASELINE_ONLY`, or `READY`;
- current and previous run IDs when available;
- deterministic structured highlights;
- rendered text;
- an empty `external_actions` list.

## Language rules

The brief deliberately uses evidence-bounded language.

Examples:

- "entered publishable set"
- "exited publishable set"
- "sources newly failing in current snapshot"
- "checkpointed only against current run"
- "current run created opportunity count"

It does not say:

- an item moved for a particular reason;
- an item was published "since" the previous run;
- an opportunity was newly created by ID when Source Refresh v1 only preserves
  the created count.

## Baseline behavior

With no recorded runs, the brief reports `EMPTY`.

With one recorded run, it reports `BASELINE_ONLY` and explicitly states that no
run-to-run transition is claimed.

## Authority boundary

The brief performs no external reads, writes, verification, publication,
messaging, scoring, or opportunity status mutation.

It is a deterministic presentation layer over the recorded delta from #74.
