# Curation Publication Coverage v1

## Purpose

Show which opportunity IDs from the latest recorded publishable digest have an
explicit publication checkpoint and which do not.

Core boundary:

`UNCHECKPOINTED != UNPUBLISHED`

Absence of a checkpoint proves only that Opportunity OS has no recorded
publication confirmation for that run/item. It does not prove that an operator
did not publish the item externally.

## Endpoint

`GET /api/v1/curation/history/publication-coverage`

The endpoint is read-only and always evaluates the latest recorded curation run.

## Statuses

- `EMPTY`: no recorded curation run exists.
- `NO_PUBLISHABLE`: the latest recorded run has no publishable items.
- `NONE_CHECKPOINTED`: publishable items exist but none have a publication
  checkpoint.
- `PARTIAL`: some publishable IDs have checkpoints and some do not.
- `COMPLETE`: every publishable ID in the latest recorded run has a checkpoint.

## Exact fields

The response includes:

- exact publishable opportunity IDs from the recorded run;
- exact checkpointed opportunity IDs from explicit publication checkpoints;
- exact `uncheckpointed_publishable_ids` as the set difference;
- counts for each set;
- latest checkpoint timestamp when present;
- `external_actions=[]`.

## Integrity boundary

Publication confirmation already requires an opportunity ID to belong to the
recorded publishable digest. Coverage fails closed if the ledger ever contains a
checkpoint for an ID outside that run's publishable set.

## Authority boundary

This endpoint does not:

- send or publish anything;
- infer whether an external WhatsApp message exists;
- modify publication checkpoints;
- change opportunity status;
- refresh or verify sources.

It is an audit/coverage view over recorded evidence only.
