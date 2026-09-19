# Discovery Patterns — 2026-09-18

This note captures patterns observed while dogfooding Opportunity OS against a real,
mixed geospatial / geoscience / software audience.

It records discovery policy, not claims about any individual opportunity.

## Evidence boundary

```text
search result != active opportunity
community mention != verified opening
platform listing != official employer confirmation
proximity != relevance
discovery != qualification
qualification != application authority
```

A source can help discover an opportunity without being authoritative enough to prove
that the opportunity is still active. When a stronger source exists, verification should
prefer the official employer, official ATS, or the platform that owns the project.

## Observed opportunity families

The useful search space is broader than roles containing the literal term `GIS`.

### Freelance / project work

High-signal terms include:

- GIS freelance
- QGIS freelance
- remote sensing freelance
- geospatial Python contract
- PostGIS contract
- cartography contract
- photogrammetry freelance
- Civil 3D GIS
- spatial data contract
- Earth observation consulting

These opportunities often decay faster than standard job postings because proposals
accumulate quickly or the client can close the project at any time.

### Geospatial-adjacent roles

Useful lateral titles and concepts include:

- spatial data
- Earth observation
- environmental data
- land data
- geomatics
- surveying
- cadastre
- hydrogeology
- mining data
- infrastructure GIS
- asset management
- environmental analyst

The absence of `GIS` from the title is not evidence that geospatial capability is
irrelevant.

### Early-career entry points

Searches should include:

- junior
- trainee
- internship
- graduate
- early career
- assistant
- analyst I

Entry routes should not be limited to traditional full-time jobs. Internships, paid
projects, apprenticeships and short-term contracts can all be valid doors into the
market when represented truthfully.

### Contractor networks and direct project channels

A separate discovery lane should track organizations that maintain freelancer,
contractor or specialist networks. This is not the same as a public job opening.

```text
CONTRACTOR_NETWORK != ACTIVE_POSTING
DIRECT_OUTREACH != APPLICATION
```

The value of this lane is reduced marketplace competition and access to project-based
work, but the system must not manufacture an opening where none is published.

## Source roles

Different sources have different jobs in the pipeline.

- Official employer / ATS: strongest evidence for availability and application details.
- Freelance marketplace: primary evidence for the project while the listing is active.
- Regional or niche job board: useful discovery surface; verify against the employer
  when possible.
- Discovery index: useful for finding opportunities, not sufficient on its own to prove
  that a posting remains active.
- Community / Reddit / forums: useful for discovering platforms, search strategies,
  market language and user experience; not authoritative evidence of an opening.

## Diversity pattern

A daily digest should avoid becoming a mirror of one marketplace.

Observed useful diversity includes:

- freelance / project work;
- junior / trainee / first experience;
- GIS / remote sensing;
- geology / mining / environment;
- geospatial software / data / GeoAI;
- experienced / senior roles;
- programs, research or public contribution opportunities when clearly separated from
  job openings.

Diversity is a selection concern. It must not inflate weak opportunities merely to fill
a quota.

## Freshness pattern

One freshness curve is not sufficient for every opportunity type.

A seven-day-old traditional job can still be actionable. A seven-day-old freelance
project with many proposals may already be low value.

Future policy should therefore distinguish at least:

```text
standard_job
fast_market_project
deadline_sensitive_program
```

Until source-aware freshness is implemented, freshness must remain explicit and
conservative.

## URL hygiene

Public digests should prefer canonical URLs and remove known tracking parameters where
this can be done without changing the resource identity.

Examples of removable tracking parameters include `utm_*`, `gclid` and `fbclid`.

Arbitrary query parameters must not be stripped because they may be required to identify
the opportunity.

## Operational consequence

The next discovery increment should focus on:

1. a versioned source catalog;
2. versioned discovery query packs;
3. source-aware enrichment;
4. canonical public URLs;
5. source-diverse selection;
6. source-aware freshness and availability evidence.

This does not grant SEND, APPLY, FOLLOW_UP or external mutation authority.
