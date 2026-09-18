# Community Digest Preview API V1

The Community Digest Preview API exposes the community roundup as a read-only product
surface.

## Endpoint

`POST /api/v1/community/digest/preview`

The endpoint returns:

- the number of repository candidates inspected;
- the structured `CommunityDigest`;
- rendered text;
- the selected render format.

## Profile independence

The endpoint does not require a `CandidateProfile`.

It reads opportunities from the repository, enriches them in memory and projects them
through the Community Digest rules. It does not invoke personal CAREER/INCOME_NOW
scoring or the personal daily selector.

```text
repository opportunities
-> in-memory enrichment
-> CommunityDigestCandidate
-> CommunityDigest
-> renderer
-> preview response
```

## Read-only boundary

Preview does not:

- fetch or refresh external sources;
- apply to opportunities;
- send WhatsApp, email or Telegram messages;
- mutate opportunity status;
- write enrichment cache rows;
- create relationship events;
- update application history.

Source refresh/import remains a separate explicit operation.

## Request options

V1 exposes:

- `format`: `whatsapp` or `markdown`;
- `timezone_name`;
- `title`;
- `include_intro`;
- `include_footer`;
- `max_items`;
- `max_per_source`;
- `max_per_bucket`;
- `min_freshness_score`.

Invalid rendering configuration fails with a public-safe 422 response.

## Candidate window

The default preview service reads up to 90 days of stored opportunity candidates.
Community Digest freshness policy still determines whether an item is publishable in
the current roundup.

This wider read window allows ordinary job postings to retain the existing
`standard_job` freshness semantics while fast-market projects continue to decay much
faster.

## Authority

Preview returns data only.

```text
PREVIEW != SEND
PREVIEW != APPLY
PREVIEW != REFRESH SOURCES
PREVIEW != EXTERNAL MUTATION
```
