# Availability Memory V1

Availability Memory adds append-only temporal evidence for opportunities without
overloading the base `Opportunity` record.

## Core rule

```text
NOT SEEN != CLOSED
```

A source returning no result does not create an observation and does not mutate
availability state.

## Observation types

V1 supports three explicit observation types:

- `SEEN`: the opportunity appeared in a source fetch or was imported manually.
- `VERIFIED_OPEN`: a deliberate verification confirmed that the opportunity is open.
- `VERIFIED_CLOSED`: a deliberate verification confirmed that the opportunity is closed.

Automatic ingestion records only `SEEN`.

It never records `VERIFIED_OPEN` merely because an aggregator returned a row, and it
never records `VERIFIED_CLOSED` because a row disappeared from a later fetch.

## Projection

The append-only observation history is projected into:

- `first_seen_at`
- `last_seen_at`
- `last_verified_at`
- `verification_source`
- `availability_state`
- `observation_count`
- `latest_observation_at`

Availability state is determined only by the latest explicit verification observation:

```text
no explicit verification -> UNVERIFIED
latest verification open -> VERIFIED_OPEN
latest verification closed -> VERIFIED_CLOSED
```

A later plain `SEEN` observation does not silently override an earlier explicit
verification. A later explicit verification can change the verified state.

## Storage

Observations live in a separate SQLite table:

`opportunity_availability_observations`

The base `opportunities` schema is unchanged.

This keeps source facts and temporal verification evidence separate and makes every
availability transition auditable.

## Ingestion behavior

When availability memory is enabled, each fetched opportunity records one `SEEN`
observation at the ingestion run timestamp.

If the fetched row deduplicates onto an existing canonical opportunity, the observation
is attached to the canonical opportunity ID while preserving the source that produced
the sighting.

An empty source result records nothing.

## Manual imports

The default RadarService records a `SEEN` observation when a manual opportunity import
is persisted.

Manual import is not equivalent to explicit verification.

## Read API

`GET /api/v1/opportunities/{opportunity_id}/availability`

returns the current projected availability memory.

The endpoint does not fabricate history. An existing opportunity with no observations
returns `404 Availability history not found`.

## Verification authority

V1 provides the repository primitive for explicit verification, but does not expose a
public verification mutation endpoint yet.

A future verification adapter must require an explicit evidence source and must never
derive closure from source absence alone.

## Authority boundary

Availability Memory V1 does not:

- delete opportunities;
- mutate `Opportunity.status` from source absence;
- poll sources by itself;
- auto-close listings;
- send messages;
- apply to jobs;
- convert aggregator sightings into explicit verification.
