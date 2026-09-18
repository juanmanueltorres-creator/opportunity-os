# Community Digest Renderer V1

The Community Digest renderer turns an already-selected `CommunityDigest` into
human-readable text without adding new opportunity facts.

## Boundary

```text
RENDER != DISCOVER
RENDER != VERIFY
RENDER != RANK
RENDER != SEND
```

The renderer does not infer skills, salary, seniority, fit, urgency or recommendation.
It only formats fields already present in `CommunityDigestItem`.

## V1 formats

- `whatsapp`: compact formatting with bold headings and numbered emoji markers.
- `markdown`: heading-based output suitable for notes, docs or later adapters.

Both formats use the same underlying facts.

## Public fields

V1 may display:

- digest title and generated date;
- primary bucket label;
- opportunity title;
- company;
- location and/or work mode;
- source label derived from the URL host;
- explicit application deadline;
- canonical public URL.

V1 intentionally does not display internal scoring fields such as:

- `selection_score`;
- `freshness_score`;
- career match;
- income viability;
- confidence score;
- ranking penalties.

## URL behavior

The renderer uses `CommunityDigestItem.source_url` verbatim.

URL canonicalization and tracking removal belong upstream in enrichment. The renderer
must not append tracking parameters or mutate functional query parameters.

## Timezone behavior

Formatting timezone is explicit through `CommunityDigestRenderOptions.timezone_name`.
The default is UTC so repository behavior is not tied to one operator location.

## Authority

V1 returns a string only. It does not send to WhatsApp, Telegram, email or any other
external channel.
