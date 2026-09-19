# Explicit Availability Verification Workflow V1

Availability verification is a human-confirmed write workflow for recording explicit
evidence that an opportunity is open or closed.

It is intentionally separate from source ingestion.

## Core boundary

```text
SEEN != VERIFIED_OPEN
MISSING != VERIFIED_CLOSED
PREVIEW != WRITE
CONFIRM != SEND
```

Automatic ingestion continues to record only `SEEN`.

A verification observation can be appended only through an explicit
preview-confirm workflow.

## Feature flag

The API write surface is disabled by default.

```text
OPPORTUNITY_AVAILABILITY_VERIFICATION_ENABLED=false
```

Set it to `true` only when an operator intentionally wants to enable explicit
verification writes.

Providing a verification service directly to `create_app` is also an explicit
application-level opt-in.

## Evidence contract

A verification request contains:

- opportunity ID;
- decision: `OPEN` or `CLOSED`;
- evidence observation time;
- evidence kind;
- bounded evidence source identifier;
- HTTP/HTTPS evidence URL;
- optional note.

V1 evidence kinds are:

- `OFFICIAL_COMPANY_PAGE`;
- `DIRECT_ATS`;
- `DIRECT_PLATFORM`;
- `MANUAL_REVIEW`.

The workflow does not crawl or inspect the URL. The operator is asserting that the
supplied evidence was reviewed.

## Preview

`POST /api/v1/availability/verification/preview`

Preview is read-only.

It returns:

- current availability state;
- proposed availability state;
- evidence hash;
- preview hash;
- current observation count;
- latest observation timestamp;
- stable errors when blocked.

The preview hash binds:

- the evidence payload;
- the immutable opportunity snapshot;
- the current availability projection;
- the preview policy version.

## Confirm

`POST /api/v1/availability/verification/confirm`

Confirm must repeat the exact evidence plus:

- the preview hash;
- `confirmed_by`;
- `confirmed_at`.

A valid confirm appends one explicit `VERIFIED_OPEN` or `VERIFIED_CLOSED`
observation.

The base `Opportunity.status` remains unchanged.

## Concurrency and stale previews

The final append uses an SQLite `BEGIN IMMEDIATE` transaction and checks:

- expected observation count;
- expected latest observation timestamp.

If availability history changed after preview, confirm returns:

`BLOCKED_STALE_PREVIEW`

instead of writing over newer evidence.

This includes a concurrent `SEEN` observation.

## Idempotency

The same evidence can be confirmed only once through the workflow.

An exact retry returns:

`ALREADY_RECORDED`

with the same stable receipt identity and the original confirmation provenance.

If an identical verification already exists outside this workflow and has no workflow
receipt metadata, V1 fails closed rather than silently claiming ownership of it.

## Stored provenance

Workflow-created verification observations preserve:

- evidence kind;
- evidence source;
- evidence URL;
- evidence note;
- confirmer;
- confirmation time;
- preview hash.

This metadata is append-only.

## Authority boundary

V1 does not:

- fetch evidence URLs;
- infer open/closed from source absence;
- auto-confirm crawler results;
- mutate `Opportunity.status`;
- send messages;
- apply to opportunities;
- publish a Community Digest automatically.

The Community Digest may consume the resulting explicit availability state, but it does
not create that state.
