# Curation Run Ledger / Publication Checkpoint V1

This increment adds explicit operational memory around Daily Curation.

It records what a specific refresh-curation run contained and lets an operator explicitly
checkpoint what was actually published.

The ledger does not send or publish anything by itself.

## Core boundary

```text
RUN GENERATED != RUN RECORDED
PUBLISHABLE != PUBLISHED
CHECKPOINT != SEND
PUBLICATION MEMORY != CLOSED
```

## Run ledger

A Refresh Curation Operator Run may be explicitly recorded through:

`POST /api/v1/curation/ledger/runs`

The stored record binds:

- combined run ID;
- generated timestamp;
- recorded timestamp;
- canonical payload SHA-256;
- digest ID;
- publishable opportunity IDs;
- review opportunity IDs;
- displayed held opportunity IDs;
- full structured run payload.

Recording the same exact snapshot is idempotent and returns `IDENTICAL`.

A conflicting payload for the same persisted run ID fails closed.

Before recording, the service also validates derived run invariants:

- the run ID matches Source Refresh + Operator View;
- combined/source/operator timestamps agree;
- `partial_source_failure` matches Source Refresh diagnostics;
- external reads match Source Refresh;
- record time is not before run generation.

## Publication checkpoint workflow

Publication memory uses explicit preview-confirm semantics.

### Preview

`POST /api/v1/curation/publication/preview`

The request contains:

- recorded run ID;
- exact digest ID;
- one or more opportunity IDs;
- publication channel.

V1 channels:

- `WHATSAPP`;
- `MANUAL_OTHER`.

The preview only becomes `READY` when:

- the run was recorded;
- the digest ID matches;
- every requested opportunity was part of that recorded publishable digest;
- those opportunity IDs were not already checkpointed for that same run.

The preview hash binds:

- evidence;
- recorded run payload hash;
- current publication-ledger count.

### Confirm

`POST /api/v1/curation/publication/confirm`

Confirm requires the exact preview plus:

- `confirmed_by`;
- `confirmed_at`;
- optional note.

The confirm records an internal publication checkpoint only.

It does not call WhatsApp, email, or any external publishing provider.

Exact retries return `ALREADY_RECORDED` with the original checkpoint.

If another publication checkpoint changes the ledger after preview, the stale confirm
fails closed with `publication_ledger_changed`.

## Repeat semantics

Publication duplication is scoped to one recorded run.

The same opportunity cannot be checkpointed twice from the same run.

It may appear in a new future run after the publication cooldown expires and may then
be checkpointed again as a new publication event.

This preserves both:

- duplicate protection for one daily round;
- intentional future resurfacing.

## Publication Memory

Daily Curation reads recent publication checkpoints and removes those opportunity IDs
before Community Digest selection.

Default cooldown:

`30 days`

Configurable field:

`publication_cooldown_days`

Allowed V1 range:

`1..365`

Publication exclusion happens before digest source/bucket caps, so recently published
items do not consume editorial diversity capacity.

The response makes this filtering visible:

- cooldown days;
- excluded opportunity IDs;
- exclusion count;
- `counts.recently_published`.

Operator View also displays a separate:

`Ya publicados recientemente`

section.

## Cooldown behavior

Example:

```text
Day 1
  greenhouse:1 -> publishable
  operator manually posts it
  publication checkpoint recorded

Day 2
  greenhouse:1 still exists and is still open
  -> excluded by Publication Memory
  -> not repeated in Publishable

Day 31
  default 30-day cooldown expired
  -> may return to Publishable if all other rules still pass
```

The opportunity is never marked closed because of publication memory.

## Persistence

V1 adds SQLite tables:

- `curation_runs`;
- `publication_checkpoints`;
- `publication_checkpoint_items`.

The ledger shares the Opportunity OS SQLite path by default.

No existing opportunity or availability rows are mutated by run recording.

Publication checkpointing writes only ledger tables.

## Authority boundary

The ledger may:

- persist a curation snapshot;
- persist an operator-confirmed publication event;
- suppress recently published opportunities from future digest selection.

It does not:

- fetch external sources;
- verify an opportunity open/closed;
- mutate `Opportunity.status`;
- send WhatsApp messages;
- send email;
- apply to opportunities.

```text
PUBLICATION CHECKPOINT = OPERATOR MEMORY
PUBLICATION CHECKPOINT != DELIVERY AUTHORITY
```

## Intended daily workflow

```text
Refresh -> Curation Operator Run
        |
        +-> explicitly record run snapshot
        |
        +-> Review / verification workflow
        |
        +-> Publishable digest
                |
                +-> operator manually posts selected items
                |
                +-> publication preview
                +-> human confirm
                +-> Publication Memory
                        |
                        +-> next Daily Curation suppresses recent repeats
```

This closes the daily historical loop without granting automatic publishing authority.
