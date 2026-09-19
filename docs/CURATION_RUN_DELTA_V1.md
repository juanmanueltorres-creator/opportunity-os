# Curation Run Delta v1

## Purpose

Compare the two most recent explicitly recorded curation runs and answer a
narrow operational question: what changed between the latest two snapshots?

Core boundaries:

`DELTA != CAUSAL EXPLANATION`
`SNAPSHOT MEMBERSHIP CHANGE != VERIFIED STATE TRANSITION`
`NEW OPPORTUNITY COUNT != NEW OPPORTUNITY IDS`

The delta is read-only and performs no source refresh, verification, publication
or opportunity mutation.

## Endpoint

`GET /api/v1/curation/history/delta`

The response status is:

- `EMPTY`: no recorded runs exist;
- `BASELINE_ONLY`: one recorded run exists, so no comparison is possible;
- `READY`: the two newest recorded runs are compared.

## Exact set comparisons

When two runs exist, the response reports deterministic set differences for:

- sources that started failing or recovered;
- opportunities entering or leaving the recorded review set;
- opportunities entering or leaving the recorded publishable set;
- opportunities entering or leaving the displayed-held subset;
- opportunity IDs checkpointed only against the current run or only against the
  previous run.

These are snapshot membership differences. They do not claim why an item moved.

## Count comparisons

The response also exposes explicit previous/current/change values for:

- source errors;
- fetched opportunities;
- newly created opportunity count;
- existing opportunity count;
- review count;
- publishable count;
- held count;
- publication checkpoint count;
- published opportunity ID count.

A change in `new_opportunity_count` compares two counters. Source Refresh v1
still does not preserve the exact IDs created during each ingestion run, so this
feature does not fabricate `new_opportunity_ids`.

## Held provenance

`held_count` is the full held count from each recorded operator snapshot.

Exact held ID transitions use only `held_displayed_opportunity_ids`, because
that is the exact ID subset persisted by the run ledger. The API names these
fields `entered_displayed_held_ids` and `exited_displayed_held_ids` to keep
that limitation explicit.

## Publication provenance

`published_only_in_current_run_ids` means publication checkpoints are attached
to the current run but not the previous run at query time. It does not mean the
publication necessarily occurred inside the wall-clock interval between the two
run generation timestamps.

Publication checkpoints are append-only, so a later checkpoint can change a
future read of the delta while preserving the underlying audit history.

## Authority boundary

The endpoint has no external actions and `external_actions` is always empty.
