# Opportunity OS — Search Health Metrics + Historical Backfill Design

## Status

Design approved in conversation for a dogfooding-first release.

This slice is for the operator's own real job-search workflow first. It is not a multi-user analytics product, SaaS dashboard, productivity score, or generalized job-seeker UI.

## Problem

Opportunity OS already records much of the job-search funnel, but the useful evidence is distributed across several bounded contexts:

- `Opportunity` persistence records discovery;
- `DailyRadarBatch` and `RadarAssessment` model qualification and confidence;
- `ApplicationPacket` records successful recruiter-package preparation;
- the Outreach Core records draft, approval, send and response events;
- Relationship Memory records contacted/replied/process state;
- Gmail can provide provider evidence for historical events that happened before the native ledgers were consistently populated.

The system can therefore answer many product questions, but it does not yet expose a single defensible report. A naive dashboard would create false precision by treating missing history as zero, double-counting provider evidence already represented by native events, or recomputing old decisions under today's scoring policy.

The goal is to add a read-only metrics projection plus a separate historical reconstruction store so Opportunity OS can report what is known, how it is known, and where coverage is incomplete.

## Product goal

The first release should let the operator run a command such as:

```bash
python -m app.metrics.report --from 2026-08-01
```

and receive:

1. a concise human-readable Search Health summary on stdout; and
2. an aggregate, machine-readable JSON artifact at `artifacts/metrics/search-health.json`.

The report is evidence about the search process. It is not an instruction to apply more, contact more people, or send anything automatically.

## Success criteria

The V1 succeeds when it can, without mutating native operational state:

- count observed opportunities in a time window;
- count recruiter `ApplicationPacket` artifacts that are actually `PREPARED`;
- count verified drafts and confirmed sends from native outreach state when available;
- count observed replies and process transitions from native relationship/outreach evidence when available;
- incorporate explicitly imported historical Gmail evidence without pretending it was recorded natively at the time;
- reconcile duplicate native/imported evidence conservatively;
- compute only defensible conversion ratios;
- expose coverage, basis and warnings with every ratio;
- represent unavailable or insufficiently observed values as unknown rather than zero;
- emit no contact PII, email bodies, provider message IDs or private notes in the aggregate report.

## Non-goals

V1 will not add:

- a web dashboard;
- FastAPI metrics endpoints;
- multi-user accounts or shared analytics;
- leaderboards, streaks or a productivity score;
- recommendations to increase application volume;
- causal claims such as "source X improves reply probability";
- automatic strategy optimization;
- automatic Gmail mailbox sync;
- automatic sends or follow-ups;
- retrospective fabrication of `OutreachEvent`, `SendReceipt` or `RelationshipEvent` rows;
- rewriting old Radar decisions with the current scoring version;
- public persistence of candidate history or recruiter data.

Comparative slices such as best source, best language, best CV version or strategy winner are deliberately deferred until sample size and coverage justify them.

## Core invariants

### 1. Native history and reconstructed history are different things

```text
native ledger != historical reconstruction
```

Historical reconstruction never inserts fake past `SENT`, `REPLIED`, `PROCESS_OPENED` or other events into the existing native ledgers.

### 2. Native evidence has precedence

For the same real-world fact:

```text
native confirmed fact
    > imported provider evidence
    > manual historical assertion
    > unknown
```

A stronger source replaces a weaker duplicate for projection purposes. It does not delete the weaker private evidence.

### 3. Unknown is not zero

If the system cannot establish that it observed the relevant outcome space, a rate is `null`/unknown or explicitly partial. Silence is not automatically interpreted as a rejection or no-reply outcome.

### 4. Metrics are read-only

Metrics code can read operational repositories and private historical reconstruction. It cannot call send paths, approve outreach, mutate relationship state, change opportunity status, import a Gmail observation into Relationship Memory, or alter an `ApplicationPacket`.

### 5. Historical scoring is not recomputed silently

A current scoring policy must not be applied to an old opportunity and presented as the score/tier that existed in the past. Historical HIGH/MEDIUM qualification counts are included only when a versioned historical `RadarAssessment`/batch or another canonical persisted artifact supports them. Otherwise their coverage is partial/unknown.

## Architecture

```text
              existing local/private state
                         |
       +-----------------+------------------+
       |                 |                  |
 Opportunity DB     Outreach state     Relationship Memory
       |                 |                  |
       |          ApplicationPacket files  |
       |                 |                  |
       +-----------------+------------------+
                         |
                   native readers
                         |
                         v
                 Metrics Projection <----------------+
                         ^                            |
                         |                            |
             Historical Observation Store            |
                         ^                            |
                         |                            |
           explicit historical import                |
                         ^                            |
                         |                            |
           selected/authorized Gmail evidence -------+

                         |
                         v
                 SearchHealthReport
                   /             \
                stdout          JSON
```

The projection is derived state. V1 does not add another persistent aggregate database.

## Proposed package boundary

```text
app/metrics/
    __init__.py
    models.py          # report, metric and coverage contracts
    history.py         # historical observation models/repository/import validation
    projection.py      # native + historical reconciliation and metric computation
    sources.py         # read-only adapters over existing local state/artifacts
    report.py          # CLI + human/JSON serialization
```

Implementation may split files further if a responsibility becomes large, but the public boundary remains: source readers -> reconciled facts -> metrics projection -> report.

## Historical reconstruction model

Historical evidence is stored separately, by default at:

```text
state/history.local.sqlite3
```

The path is private/gitignored and may be overridden explicitly by CLI/environment configuration.

### `HistoricalObservation`

Minimum contract:

```text
observation_id
kind
opportunity_id?        # nullable when the match is not defensible
account_id?            # nullable
company?               # private matching aid, never emitted in aggregate output
role?                  # private matching aid, never emitted in aggregate output
occurred_at
observed_at
provenance
source_ref?
provider_message_id?
provider_thread_id?
confidence
reconstruction_notes?
```

Supported V1 kinds:

```text
DRAFT_OBSERVED
SEND_OBSERVED
REPLY_OBSERVED
PROCESS_OPENED_OBSERVED
PROCESS_CLOSED_OBSERVED
```

Historical provenance is limited to explicit sources such as:

```text
IMPORTED_GMAIL
MANUAL_ASSERTION
```

`NATIVE` is not a historical-observation provenance. Native events remain in their native repositories.

`confidence` is bounded to `[0, 1]`. It describes confidence in the reconstruction/match, not probability that the event happened if provider evidence directly confirms it.

### Privacy boundary

Historical storage may retain provider identifiers needed for exact reconciliation because the database is private/local. It must reject or discard:

- email bodies;
- raw MIME;
- attachments;
- unrestricted provider payloads;
- OAuth/access tokens;
- credentials.

The aggregate Search Health JSON never contains provider identifiers, contact names, addresses, subjects, company-specific private notes or message content.

## Historical import contract

V1 does not introduce mailbox-wide synchronization.

Gmail backfill uses an explicitly authorized selection of messages/threads for the requested historical window. The selection can be supplied as a private manifest produced by an operator/provider adapter. The importer receives normalized, allowlisted evidence; it does not persist raw Gmail payloads.

For the initial dogfooding run, the target window is:

```text
2026-08-01 -> report as-of time
```

The import must be idempotent. Re-importing the same provider evidence yields the same `HistoricalObservation` identity and does not create a duplicate.

A historical observation that cannot be defensibly linked to an `opportunity_id` may still be retained as unmatched evidence, but it cannot silently enter a conversion numerator that requires an opportunity/send linkage.

## Import batch / coverage record

A one-time backfill needs to distinguish "no reply observed" from "we did not inspect all relevant threads". Each import therefore records a private batch manifest containing at least:

```text
batch_id
provider
window_start
window_end
selection_scope
selected_message_count
selected_thread_count
completed_at
complete_for_declared_scope
```

`selection_scope` is explicit, for example `SELECTED_THREADS` or `ALL_DECLARED_OUTREACH_THREADS`. The system never upgrades `SELECTED_THREADS` to complete mailbox coverage on its own.

This batch information feeds metric coverage; it is not included as PII in the aggregate report.

## Reconciliation

The projection converts native and historical sources into internal normalized facts, then reconciles them before counting.

### Exact reconciliation anchors

Prefer exact anchors in this order when available:

1. native provider message/thread identifier;
2. exact native entity hash/ID tied to the same opportunity;
3. exact opportunity + event kind + canonical timestamp identity when the source contract guarantees uniqueness.

V1 does not use fuzzy company-name, subject similarity or "nearest timestamp" matching to suppress a possible duplicate.

If imported evidence appears likely to duplicate a native fact but exact reconciliation is unavailable, the projection preserves the ambiguity, excludes the ambiguous item from ratios that would be distorted, and emits a coverage warning.

### Send precedence

A native `SendReceipt` is the strongest send evidence. If a Gmail historical `SEND_OBSERVED` record references the same provider message, the report counts one send with native basis.

### Reply/process precedence

Native relationship/outreach evidence outranks a historical observation only when the two facts can be reconciled to the same event. Unmatched historical replies/process transitions remain visible as unmatched counts/coverage warnings rather than being forced onto an opportunity.

## Native metric sources

### Discovery

`SQLiteOpportunityRepository` is authoritative for opportunities that Opportunity OS persisted. `Opportunity.discovered_at` defines when the system first observed the canonical stored opportunity.

V1 definitions:

- `opportunities_observed`: distinct stored opportunities whose `discovered_at` falls inside the report window;
- `opportunities_new`: same as observed in V1 because the repository preserves the first inserted canonical opportunity and deduplicates subsequent source duplicates.

Source ingestion's transient `created/existing` diagnostics may be reported separately later, but V1 does not reconstruct historical duplicate volume from logs that were never persisted.

### Qualification

`qualified_high` and `qualified_medium` require canonical, versioned historical Radar evidence. Do not recompute old tier counts from current enrichment/scoring code and label them historical.

If suitable Radar batch/assessment artifacts are available to the reader, count them. If they are absent for part/all of the report window, return partial/unknown coverage.

### Prepared application packets

Read `artifacts/applications/*/application_packet.json` (or an explicitly configured applications root), validate each file as the current typed `ApplicationPacket`, require `status=PREPARED`, and use `created_at` for the report window.

Invalid, unreadable or incompatible files do not become prepared packets. They produce bounded warnings.

### Drafts and sends

Use native Outreach Core evidence when a configured outreach repository exists.

- verified draft count is based on canonical `DraftSnapshot` / corresponding native draft evidence, not Gmail's Drafts folder alone;
- confirmed sends are based on `SendReceipt` when native receipts exist;
- historical Gmail send evidence may fill historical gaps but is marked imported and reconciled against native receipts.

### Replies and process state

Prefer canonical native Relationship Memory/outreach evidence for `REPLIED`, `PROCESS_OPENED` and `PROCESS_CLOSED` facts. Historical Gmail/provider observations may supplement gaps without writing relationship events retrospectively.

## Metrics contract

### Coverage

```text
COMPLETE
PARTIAL
UNKNOWN
```

`COMPLETE` means the configured evidence sources are known to cover the metric's declared scope for the entire report window.

`PARTIAL` means useful evidence exists but the system knows the window/entity set is incompletely observed or contains unresolved matches.

`UNKNOWN` means the system cannot defend a numeric interpretation for that metric.

A numeric count may coexist with `PARTIAL` coverage: it means "at least this many observed", not "this is the complete population".

### Count metrics

Each count records:

```text
name
value?              # nullable when not defensible
coverage
basis[]
warnings[]
```

### Ratio metrics

Every ratio records:

```text
name
value?              # null when denominator/coverage makes a ratio indefensible
numerator
 denominator
coverage
basis[]
warnings[]
```

Ratios are calculated from reconciled facts, never by dividing independently displayed counts that use incompatible coverage scopes.

## V1 Search Health report

### DISCOVERY

- `opportunities_observed`
- `opportunities_new`
- `qualified_high`
- `qualified_medium`

### EXECUTION

- `packets_prepared`
- `drafts_verified`
- `confirmed_sends`

### OUTCOMES

- `replies_observed`
- `processes_opened`
- `processes_closed`

### CONVERSION

- `qualification_rate`
- `draft_to_send_rate`
- `send_to_reply_rate`
- `reply_to_process_rate`

### COVERAGE

The JSON also exposes summary coverage for:

- radar;
- outreach;
- reply observation;
- process observation.

## Ratio semantics

### `qualification_rate`

```text
(qualified HIGH + qualified MEDIUM) / opportunities observed
```

Only emitted when historical qualification evidence covers the relevant observed opportunities sufficiently to make the denominator compatible. Otherwise `value=null` with partial/unknown coverage.

### `draft_to_send_rate`

```text
confirmed sends linked to verified drafts / verified drafts eligible for send observation
```

An imported Gmail send without a defensible matching draft does not inflate this ratio.

### `send_to_reply_rate`

```text
reconciled replies linked to confirmed sends / confirmed sends with adequate reply-observation coverage
```

The denominator is not automatically every send ever observed. If reply coverage is partial, the report either uses only the explicitly covered send cohort and marks the basis, or returns `null` when the covered cohort cannot be established.

### `reply_to_process_rate`

```text
processes opened linked to observed replies / replies with adequate process-observation coverage
```

An unmatched process/reply can contribute to an observed count but not to a linkage-dependent ratio.

## CLI

Initial command:

```bash
python -m app.metrics.report \
  --from 2026-08-01 \
  --output artifacts/metrics/search-health.json
```

V1 supports an explicit `--to`/`--as-of` boundary for reproducible reports.

Read-only source paths can be supplied explicitly. Defaults may follow existing local conventions, for example:

```text
--opportunity-db opportunities.db
--relationships-db state/relationships.local.sqlite3
--outreach-db state/outreach.local.sqlite3
--history-db state/history.local.sqlite3
--applications-root artifacts/applications
```

A missing optional source does not create the database as a side effect. It degrades the affected metric coverage to `PARTIAL` or `UNKNOWN` and emits a warning.

## Human-readable output

The CLI should favor a compact report rather than a dashboard dump, for example:

```text
OPPORTUNITY OS — SEARCH HEALTH
2026-08-01 -> 2026-08-31

DISCOVERY
Observed opportunities        86
Qualified HIGH/MEDIUM         unknown (radar history partial)

EXECUTION
Prepared packets              21
Verified drafts               18
Confirmed sends               15

OUTCOMES
Replies observed               5  [partial coverage]
Processes opened               2  [partial coverage]

CONVERSION
Send -> reply                 33.3%  [covered cohort: 15]

COVERAGE
Radar                         PARTIAL
Outreach                      COMPLETE
Replies                       PARTIAL
Processes                     PARTIAL
```

Exact values are illustrative only. Tests and docs must use fictional data.

## JSON output

The JSON is aggregate-only and schema-versioned. Minimum top-level fields:

```text
report_version
generated_at
window
counts
ratios
coverage
warnings
source_summary
```

`source_summary` describes source classes and coverage only; it does not contain private provider IDs or contact/company PII.

The same canonical inputs plus fixed `--as-of` produce deterministic metric values and stable ordering. `generated_at` may vary unless explicitly fixed for a reproducible snapshot.

## Error handling

The report should fail hard only when:

- the requested time window is invalid;
- a required configured source exists but is structurally corrupt in a way that makes safe reading impossible;
- historical import violates the strict private schema or attempts to include forbidden payload/body/credential fields.

Normal incompleteness is not an exception. Missing databases, absent historical Radar artifacts, unmatched observations and partial provider coverage are represented as coverage/warnings.

## Testing strategy

Implementation follows TDD. At minimum, tests cover:

1. opportunities are counted once using persisted canonical discovery time;
2. current scoring is never used to fabricate historical HIGH/MEDIUM counts when historical Radar evidence is absent;
3. only typed `PREPARED` `ApplicationPacket` files count as prepared packets;
4. a native `SendReceipt` plus imported Gmail evidence for the same provider message counts as one send;
5. native evidence wins over imported provider evidence; imported provider evidence wins over a manual assertion for the same exact fact;
6. ambiguous possible duplicates are not fuzzily collapsed;
7. an unmatched historical reply can be retained but cannot inflate `send_to_reply_rate`;
8. missing reply/process coverage produces `PARTIAL`/`UNKNOWN`, not a fabricated zero outcome;
9. a zero denominator yields `value=null`, not division errors or a misleading 0%;
10. historical import is idempotent;
11. historical import cannot write to the native outreach or relationship repositories;
12. raw body/MIME/credential-like fields are rejected or discarded according to the strict importer contract;
13. aggregate JSON contains no provider message/thread IDs, contact names, addresses, subjects or message bodies;
14. missing optional databases are not created by report reads;
15. fixed inputs + fixed `--as-of` yield deterministic metric values and stable JSON ordering.

Public fixtures contain fictional identities only.

## Documentation / operator boundary

README/ROADMAP updates should describe Search Health as local reporting over observed evidence, not as a success predictor.

The operator contract should state:

> Metrics describe the evidence Opportunity OS has observed. Missing evidence remains visible as missing coverage. A metric never grants permission to contact, follow up, apply or send.

## Research-informed product constraints

The design intentionally incorporates recurring patterns observed in existing job-search trackers and user discussions:

- job trackers become burdensome when every event requires duplicate manual entry;
- users want to know which CV/application state was actually used, not just the company name;
- follow-up timing and lost relationship context are common tracking failures;
- aggregate funnel statistics are useful, but misleading when the system does not distinguish missing data from negative outcomes;
- broad auto-apply behavior creates volume without preserving operator intent;
- full mailbox access creates legitimate privacy concerns.

Opportunity OS should therefore automate observation/projection where evidence exists, preserve exact artifact identity, remain conservative about incomplete history and keep external authority human-gated.

## Delivery sequence

One implementation plan may stage the work internally, but the capability remains one coherent slice:

1. strict metrics/report contracts and RED tests;
2. read-only native source adapters;
3. historical observation repository + idempotent private import;
4. reconciliation;
5. Search Health projection;
6. CLI + aggregate JSON;
7. private August backfill run;
8. evidence review against the actual Gmail/native state;
9. README/ROADMAP update only after the real dogfood report demonstrates the behavior.

The private August data and generated personal Search Health report are not committed to the public repository.

## Future work deliberately deferred

After V1 is dogfooded, separate designs may evaluate:

- source/language/track/application-mode slices;
- median send-to-reply timing;
- follow-up/actionable-next-state summaries;
- longitudinal strategy/version comparisons;
- local UI/dashboard;
- redacted portfolio snapshots;
- additional provider adapters.

These features must inherit the same coverage/provenance semantics rather than bypassing them.