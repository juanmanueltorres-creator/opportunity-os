# Community Digest V1

Community Digest is a deterministic, read-only projection for publishing a useful
cross-profile opportunity roundup without turning one person's radar into a proxy for
the whole community.

## Epistemic boundary

```text
PERSONAL_FIT != COMMUNITY_RELEVANCE
DISCOVERY_SIGNAL != PUBLISHABLE_OPPORTUNITY
OLD != CLOSED
BUCKET != QUOTA
DIGEST != SEND_AUTHORITY
```

The projection may receive already-ranked radar assessments for transport convenience,
but it must ignore personal ranking state when deciding community relevance.

The following personal fields must not affect Community Digest output:

- career match;
- income viability;
- personal tier;
- selected intent;
- profile-specific eligibility.

Community Digest uses only opportunity facts and enrichment facts such as source
category, channel tags, dates, canonical URL, source quality, title and description.

## V1 buckets

V1 assigns multiple descriptive bucket tags and one deterministic primary bucket:

- `FREELANCE`
- `ENTRY_LEVEL`
- `GEOSCIENCE_MINING`
- `GEOAI_DATA`
- `GEO_CORE`
- `SENIOR`
- `GENERAL`

A single item can carry several tags. For example, a junior geology role can be both
`ENTRY_LEVEL` and `GEOSCIENCE_MINING`, while appearing only once in the digest.

## Publishability

V1 excludes:

- explicit `closed`, `expired`, `filled` or `inactive` opportunities;
- opportunities whose explicit application deadline has passed;
- `COMMUNITY_SIGNAL` and `DISCOVERY_INDEX` sources;
- opportunities below the configured digest freshness floor.

Freshness filtering does not mutate opportunity status. A stale freelance project may
be omitted from today's digest while remaining `open` in the source data.

## Selection

Selection is objective and deterministic:

```text
55% freshness
30% source reliability
15% actionability completeness
```

Actionability completeness currently checks only whether useful publishing facts are
present: location/work mode, publication date, URL and source category.

Diversity is enforced with caps, not quotas. By default V1 allows at most two items from
the same source host. It never promotes a weak or stale item merely to fill a bucket.

## URL policy

The digest uses `canonical_url` from enrichment when available and otherwise falls back
to the original source URL. Tracking cleanup belongs to enrichment, not to the digest
renderer.

## V1 authority boundary

V1 does not add:

- a public HTTP endpoint;
- WhatsApp or email sending;
- automated posting;
- application authority;
- follow-up authority;
- a community member profile;
- inferred group-wide candidate fit;
- courses, events or open-source contributions forced into the `Opportunity` model.

Future adapters may project other domain objects into a broader community roundup, but
their source semantics must remain explicit.
