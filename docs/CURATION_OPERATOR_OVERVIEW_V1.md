# Curation Operator Overview v1

## Purpose

Provide one read-only operator entry point for the latest recorded curation state.

The overview composes, from one history read:

- the latest recorded run;
- the structured run delta;
- the deterministic change brief;
- publication checkpoint coverage;
- exact visible review, publishable, and displayed-held IDs;
- exact uncheckpointed publishable IDs.

Core boundary:

`OVERVIEW = COMPOSE(RECORDED HISTORY)`

`OVERVIEW != REFRESH`

`OVERVIEW != NEW EVIDENCE`

## Endpoint

`GET /api/v1/curation/operator/overview?format=markdown`

Supported brief formats:

- `markdown`
- `plain`

## Consistency rule

The service performs one `history(limit=2)` read and derives delta, brief, and
coverage from that same in-memory snapshot.

This avoids a composite response whose components could observe different
publication checkpoint states if separate ledger reads occurred between them.

## Status

The overview reuses the run-delta status:

- `EMPTY`
- `BASELINE_ONLY`
- `READY`

All nested components must reference the same current run when one exists.

## Evidence boundaries

The overview preserves the semantics of its components:

- membership changes do not imply cause;
- uncheckpointed does not mean unpublished;
- publication checkpoints are human assertions recorded in the ledger;
- no exact new-opportunity IDs are invented from a count-only source refresh.

## Authority boundary

The endpoint performs no:

- source refresh;
- verification;
- scoring;
- publication;
- email or WhatsApp send;
- opportunity mutation;
- checkpoint creation.

`external_actions` is always empty.
