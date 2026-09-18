# Community Digest Availability V1

Community Digest now consumes explicit opportunity availability memory when it is
available.

## Precedence

```text
VERIFIED_CLOSED > base Opportunity.status=open
VERIFIED_OPEN   -> publishable if all other digest rules pass
UNVERIFIED      -> existing digest behavior
NO HISTORY      -> existing digest behavior
```

A `VERIFIED_CLOSED` observation is explicit evidence and excludes the item from the
digest even when the immutable base opportunity still carries `status=open`.

A later plain `SEEN` observation does not resurrect that item because Availability
Memory preserves the latest explicit verification state.

A later `VERIFIED_OPEN` observation can supersede the prior explicit close state.

## Public evidence

For a `VERIFIED_OPEN` item the structured digest exposes:

- `availability_state`;
- `last_verified_at`;
- `verification_source`.

The text renderer may show:

`✅ Verificada abierta: <verification_source> · DD/MM/YYYY`

No such claim is rendered for `UNVERIFIED` items.

## Ranking

Explicit open verification does not alter the numerical Community Digest selection
score in V1.

It is used as a deterministic tie-breaker only after selection score and freshness are
equal. This avoids silently rewriting the established 55/30/15 scoring formula.

## Digest identity

Because availability evidence can change the public output, the digest ID incorporates:

- opportunity ID;
- availability state;
- last verification timestamp;
- verification source.

The same opportunity list with changed public verification evidence therefore produces
a different digest ID.

## Integrity

`CommunityDigestCandidate` fails closed when an attached availability projection refers
to a different opportunity ID.

```text
availability.opportunity_id != opportunity.id -> invalid candidate
```

This prevents verification evidence from being accidentally attached to the wrong
opportunity.

## Preview integration

The default Community Digest Preview service receives the same
`SQLiteAvailabilityRepository` used by Opportunity OS ingestion.

The preview remains read-only:

- it reads availability projections;
- it does not create verification observations;
- it does not convert sightings into verification;
- it does not mutate `Opportunity.status`;
- it does not send or publish anything externally.
