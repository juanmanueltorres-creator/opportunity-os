# Verification Queue V1

Verification Queue is a read-only review inbox for deciding which stored opportunities
deserve human availability verification next.

It prioritizes verification work, not candidate fit.

## Core boundary

```text
REVIEW_PRIORITY != CANDIDATE_FIT
QUEUE != VERIFICATION
QUEUE != CLOSE
QUEUE != SEND
```

The queue does not consume:

- career match;
- income viability;
- personal eligibility;
- personal tier;
- selected intent.

## Endpoint

`POST /api/v1/availability/verification/queue`

The queue is read-only and is available independently from the explicit verification
write feature.

The confirm workflow may remain disabled while the queue is still used for inspection.

## Priority reasons

V1 exposes bounded reason codes:

- `DISCOVERY_ONLY_NEEDS_OFFICIAL_SOURCE`
- `DEADLINE_SOON_UNVERIFIED`
- `FAST_MARKET_UNVERIFIED`
- `SOURCE_REQUIRES_VERIFICATION`
- `VERIFICATION_STALE`

Priority is the strongest active reason:

```text
100 discovery-only needs official source
 95 deadline soon and still unverified
 90 fast-market project still unverified
 80 source requires verification
 70 explicit open verification is stale
```

Scores are operational review priority only. They are not opportunity quality scores.

## Suggested actions

Each queue item emits one bounded action:

- `FIND_OFFICIAL_SOURCE`
- `VERIFY_CURRENT_SOURCE`
- `REVERIFY_CURRENT_SOURCE`

The action is advisory and does not execute anything.

## Source authority

Source Catalog controls whether manual verification work is required.

Direct official/ATS sources with `verification_required=false` do not enter the queue
merely because Availability Memory is unverified.

Unknown sources fail conservatively into the queue.

Discovery-only sources receive the strongest priority because their current URL is not
sufficient publication authority. Their action is to find an official source, not to
promote the discovery URL.

## Availability memory

`VERIFIED_CLOSED` items never enter the queue.

Recently `VERIFIED_OPEN` items remain out until their re-verification window expires.

Default windows:

- standard opportunity: 7 days;
- fast-market project: 2 days.

These windows are configurable review policy, not closure policy.

A stale verification means "review again", never "closed".

## Freshness workload control

Fast-market projects older than 14 days are omitted from verification work by default.

This does not mutate their status. It only avoids spending human review effort on
projects already below the fast-market publication horizon.

Expired explicit deadlines are also omitted.

## Ordering

Within priority, deterministic ordering prefers:

1. earlier explicit deadlines;
2. more recently seen opportunities;
3. opportunity ID as final stable tie-break.

No weak item is promoted merely to fill queue capacity.

## Authority boundary

Verification Queue V1 does not:

- record verification observations;
- mutate `Opportunity.status`;
- infer closure from source absence;
- fetch evidence URLs;
- publish Community Digest;
- send messages;
- apply to opportunities;
- infer community or personal candidate fit.
