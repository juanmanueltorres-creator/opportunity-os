# Source Refresh Run V1

Source Refresh Run is the profile-independent ingestion step that updates Opportunity OS
from configured external job sources before curation.

It is the first V1 component in this stack that intentionally performs network reads and
writes internal source observations.

## Core boundary

```text
SOURCE REFRESH != VERIFICATION
SOURCE REFRESH != CLOSURE
SOURCE REFRESH != CURATION
SOURCE REFRESH != PUBLISH
```

A successful source fetch proves only that an opportunity was seen in that source at the
refresh timestamp.

```text
SEEN != VERIFIED_OPEN
MISSING_FROM_REFRESH != VERIFIED_CLOSED
```

## Endpoint

`POST /api/v1/sources/refresh`

The API is disabled by default.

```text
OPPORTUNITY_SOURCE_REFRESH_ENABLED=false
```

Enable it explicitly when the operator intends to perform external source reads and
internal ingestion writes.

Injecting a `SourceRefreshService` directly into `create_app` is also treated as an
explicit application-level opt-in.

## Source registry

Default connectors are built only from enabled entries in:

`OPPORTUNITY_SOURCES_PATH` (default: `sources.local.yaml`)

V1 reuses the existing connector registry:

- Remotive;
- Greenhouse;
- Lever;
- Ashby.

The refresh service and default Radar service share the same configured connector
objects/client when both are enabled.

This avoids two independent source configurations.

## Exact source subset

Without a request body, all configured connectors are refreshed.

A caller may request an exact subset:

```json
{
  "sources": [
    "greenhouse:example-gis",
    "remotive"
  ]
}
```

Source names are exact connector identities.

Unknown, blank, duplicated, or empty requested source sets fail before any source fetch.

No fuzzy source matching is performed.

## Ingestion

For each fetched opportunity, the existing ingestion path:

1. normalizes through the connector;
2. upserts into `SQLiteOpportunityRepository`;
3. records a `SEEN` observation in Availability Memory.

A duplicate payload within one connector response may still count as an existing
upsert, but it records at most one `SEEN` observation for the resulting stored
opportunity during that refresh batch.

This prevents duplicate upstream rows from artificially inflating sighting history.

## Refresh report

Each source diagnostic contains:

- source identity;
- status;
- fetched count;
- created count;
- existing count;
- unique sightings recorded;
- bounded public-safe code/message.

The run also returns aggregate counts plus:

- configured source names;
- requested source names;
- external source reads performed;
- `closure_inference=false`.

## Failure isolation

A `ConnectorError` from one source produces a bounded diagnostic:

```text
status: error
code: source_unavailable
message: Source unavailable
```

The original upstream exception text is not exposed.

Other configured sources continue processing.

A run may therefore complete with both successful and failed source diagnostics.

## No closure inference

V1 never closes an opportunity because it disappeared from a later fetch.

Example:

```text
Day 1: opportunity seen
Day 1: human VERIFIED_OPEN
Day 2: source returns zero rows for that opportunity

result:
- no new SEEN
- base status unchanged
- VERIFIED_OPEN unchanged
- no VERIFIED_CLOSED observation
```

This rule applies even if the source refresh itself completed successfully.

Future support for authoritative full-snapshot disappearance would require a separate
source-specific contract and explicit lifecycle policy.

## External authority

Source Refresh performs:

- external **reads** from configured sources;
- internal opportunity upserts;
- internal `SEEN` observations.

It does not perform downstream external actions.

The run exposes `external_reads` and keeps `external_actions=[]`.

## Profile independence

Source Refresh does not require or inspect:

- CandidateProfile;
- CAREER score;
- INCOME_NOW score;
- eligibility;
- personal tier.

Its job is source acquisition only.

## Intended flow

```text
Source Refresh
      |
      +-> new/stored opportunities
      +-> SEEN observations
      |
      v
Daily Curation Run
      |
      +-> Review
      +-> Held
      +-> Publishable
```

V1 keeps these as separate calls so network/write authority remains explicit.

A later orchestration layer may offer a single operator command for
`refresh -> curation`, but it must preserve this authority boundary.
