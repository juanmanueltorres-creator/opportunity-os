# Refresh Curation Operator Run V1

Refresh Curation Operator Run is the explicit one-command operator workflow that
refreshes configured external sources and then builds the Daily Curation Operator View
from the newly updated local state.

## Core sequence

```text
external sources
      |
      v
Source Refresh
      |
      +-> Opportunity upsert/dedup
      +-> SEEN observations
      |
      v
Daily Curation Operator View
      |
      +-> Review
      +-> Held
      +-> Publishable
```

The ordering is strict:

```text
REFRESH BEFORE CURATION
```

The curation view is never built first and patched afterward.

## Endpoint

`POST /api/v1/curation/daily/refresh-view`

This endpoint is available only when:

- Source Refresh is available;
- Daily Curation Operator View is available.

Because Source Refresh is disabled by default, this combined endpoint is also unavailable
by default unless refresh authority is explicitly enabled or injected.

## Authority boundary

This combined run inherits the Source Refresh authority boundary.

It may:

- read configured external sources;
- upsert opportunities;
- record internal `SEEN` observations;
- build the read-only operator view.

It does not:

- infer OPEN/CLOSED;
- record verification decisions;
- invoke verification confirm;
- publish/send the digest;
- apply to opportunities.

```text
REFRESH + CURATION != VERIFICATION
REFRESH + CURATION != SEND
REFRESH + CURATION != APPLY
```

## Source policy still applies

A newly fetched opportunity is not automatically publishable.

Examples:

```text
Greenhouse / direct ATS
  -> source does not require manual verification
  -> may enter Publishable immediately if digest rules pass

Remotive / job board
  -> source requires verification
  -> enters Held / Review
  -> does not enter Publishable
```

Fresh acquisition does not upgrade source authority.

## Partial source failure

Source failures remain isolated.

If one configured source fails and another succeeds:

- successful source data is ingested;
- the failed source remains in Source Refresh diagnostics;
- `partial_source_failure=true`;
- Daily Curation still runs against the resulting stored state.

The upstream exception text remains hidden.

If every refreshed source fails, the operator view may still be built from previously
stored opportunities. The response therefore distinguishes refresh health from the
current local curation snapshot.

## Exact source subset

The request can select an exact source subset:

```json
{
  "sources": ["greenhouse:example-gis"]
}
```

Subset validation occurs before source reads.

Unknown, empty, blank or duplicate source requests fail closed through the Source
Refresh contract.

## Shared timestamp

The orchestration uses one timezone-aware UTC timestamp for:

- Source Refresh;
- SEEN observations created by that refresh;
- Daily Curation;
- Operator View.

This makes the combined response one coherent operational snapshot.

## Response

The response contains:

- combined run ID;
- generated timestamp;
- full `SourceRefreshRun`;
- full `DailyCurationOperatorView`;
- `partial_source_failure`;
- external source reads;
- empty downstream external actions.

The combined run ID is bound to the effective component snapshots rather than raw request
spelling.

## Intended operator workflow

```text
POST /api/v1/curation/daily/refresh-view
        |
        +-> source diagnostics
        |
        +-> Review now
        |      |
        |      +-> inspect source
        |      +-> Evidence Draft
        |      +-> Verification Preview
        |      +-> Human Confirm
        |
        +-> Publishable digest
        |
        +-> Held backlog
```

This is the V1 "run today's round" entry point.

The final publication step remains explicitly human-controlled.
