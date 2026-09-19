# Curation Run History v1

## Purpose

Provide a read-only operational history over curation runs that were explicitly
recorded in the curation ledger.

Core boundaries:

`HISTORY != SOURCE REFRESH`
`HISTORY != PUBLICATION`
`CREATED COUNT != CREATED IDS`

The history view does not call external sources, verify opportunities, publish,
send messages, mutate opportunity status, or infer closure.

## Evidence source

History is projected only from:

1. exact recorded `RefreshCurationOperatorRun` snapshots;
2. explicit publication checkpoints attached to each recorded run.

No WhatsApp or Markdown text is parsed to reconstruct publication state.

## Endpoint

`GET /api/v1/curation/history?limit=20`

`limit` accepts 1..100 and defaults to 20.

Runs are returned newest first.

## Per-run fields

The view includes:

- generated and recorded timestamps;
- source refresh counts;
- exact failed source names from recorded diagnostics;
- fetched / created / existing counts;
- review / publishable / held counts;
- exact review, publishable and displayed-held IDs preserved by the recorded run;
- publication checkpoint count;
- exact opportunity IDs explicitly checkpointed as published;
- publication channels and latest publication time;
- partial-source-failure flag.

## Important provenance limitation

Source refresh v1 records `created_count`, but does not record the exact IDs of
the opportunities created during ingestion.

Therefore history exposes `new_opportunity_count` only. It does not fabricate
or retrospectively infer a list of new opportunity IDs.

Published opportunity IDs are different: they are available exactly because
publication checkpoints store them explicitly.

## Authority boundary

This feature is read-only. `external_actions` is always empty.
