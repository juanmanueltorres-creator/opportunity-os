# Opportunity OS

Open-source opportunity discovery, matching, and application-preparation infrastructure with **explainable scoring, verified evidence, and human approval**.

Opportunity OS reduces repetitive job-search work without pretending that one score or one model can decide what a person should do. The system separates strategic career fit, near-term income viability, confidence, and candidate evidence so every consequential step remains inspectable.

> **Current prerelease: V0.2C (`0.2.0c1`).** V0.2A discovers, enriches, scores, ranks, and selects opportunities. V0.2B adds a deterministic **CV Factory** that prepares evidence-backed CVs and reproducible `ApplicationPacket` records. V0.2C adds a deterministic email-outreach core with verified contact resolution, exact draft identity, explicit human approval, a separate send request, idempotent send receipts, and an auditable local ledger.

## V0.2A intelligent radar

The radar evaluates opportunities along three separate dimensions:

- **CAREER** — how strongly the opportunity matches a preferred professional direction.
- **INCOME_NOW** — how realistically the candidate can obtain and perform the work soon enough for it to be useful as income.
- **CONFIDENCE** — how trustworthy the assessment inputs are. Confidence is not job fit.

A role can therefore be a weak strategic career target and still be a strong income opportunity, or the reverse.

Example:

```text
CAREER       31 / 100
INCOME_NOW   84 / 100
CONFIDENCE   90 / 100

Interpretation:
not a strategic career target, but a strong near-term income opportunity.
```

### Candidate tracks

Candidate tracks keep unrelated evidence isolated. A technical application cannot silently borrow hospitality experience, and a hospitality application cannot claim technical experience merely because both exist in the same private profile.

A local private profile may contain separate tracks such as:

```text
tech_geospatial       -> CAREER + INCOME_NOW
gastronomy_operations -> INCOME_NOW
general_operations    -> INCOME_NOW
```

The public repository contains only fictional examples. Personal facts and evidence remain local and gitignored.

## V0.2B CV Factory

V0.2B turns a radar-selected opportunity into a truthful, inspectable application-preparation artifact.

```text
Radar-selected opportunity
-> private verified facts and evidence
-> deterministic evidence selection
-> provenance-backed CVDocumentModel
-> ClaimValidator hard gate
-> one-column ATS PDF
-> reproducible ApplicationPacket
```

### Evidence boundary

The application track selected by the radar is a hard evidence boundary. The CV Factory may select only verified facts and verified evidence modules authorized for that track.

Posting requirements are resolved as:

```text
EXACT_VERIFIED
APPROVED_ALIAS
TAXONOMY_RELATED
UNKNOWN
```

A related taxonomy skill can provide context, but it cannot silently satisfy an explicitly required product or tool. Unsupported mandatory requirements remain visible as gaps instead of being converted into invented experience.

### Provenance-backed composition

`CVDocumentModel` is deterministic and contains candidate-visible claims plus a provenance map. Candidate-specific text must originate from one of these authorities:

- a verified master fact;
- an approved evidence claim backed by verified facts.

The composer may select, omit, order, and use approved language variants. It does not invent years, employers, titles, metrics, tools, projects, credentials, or translations.

Projects remain projects. Employment remains employment. Evidence from another candidate track is not eligible filler.

### ClaimValidator hard gate

The validator runs before rendering. It checks, among other invariants:

- every visible claim has provenance;
- referenced facts and evidence exist and are verified;
- facts and evidence belong to the selected application track;
- approved evidence wording has not been altered;
- structured organization/title/date claims still match their verified source facts;
- numeric metrics are supported by referenced facts;
- unresolved posting requirements remain warnings instead of fabricated claims.

An invalid `CVDocumentModel` cannot reach the PDF renderer through `CVPreparationService`.

### ATS PDF

V0.2B ships one deliberately simple ATS-first PDF layout:

- A4;
- one column;
- built-in Helvetica / Helvetica-Bold;
- selectable text;
- no images;
- no icons;
- no tables;
- no skill bars;
- deterministic ReportLab output for identical validated documents.

The renderer hashes the final PDF with SHA-256. Re-rendering an identical validated document with the same renderer version produces identical fixture bytes.

### Reproducible ApplicationPacket

A successful preparation returns `PREPARED` with an `ApplicationPacket` containing the selected track, radar metadata, source snapshot hashes, selected evidence IDs, unresolved gaps, validated `CVDocumentModel`, renderer version, CV SHA-256, and semantic packet SHA-256.

The semantic packet hash intentionally excludes volatile values such as:

- `application_id`;
- `created_at`;
- local output path.

That means changing a UUID, execution time, or machine path does not change the semantic application identity. Changing the verified facts, selected evidence, CV content, source opportunity snapshot, or relevant version metadata does.

Blocked outcomes never contain a packet:

```text
BLOCKED_TRACK_UNAVAILABLE
BLOCKED_MISSING_FACTS
BLOCKED_VALIDATION
BLOCKED_RENDER
```

A render failure also removes partial PDF output.

### Private/local CV data

Real candidate facts, evidence, and generated application documents are local-only:

```text
profile/master_facts.local.yaml
profile/evidence_catalog.local.yaml
artifacts/applications/<application_id>/cv.pdf
```

These paths are gitignored and CI also fails if forbidden private/generated files become tracked.

Public examples under `profile/` are fictional fixtures only.

### Scope boundary

**V0.2B does not send email and does not submit applications.** It does not log into recruiting portals, accept terms, answer sensitive legal declarations, bypass CAPTCHAs, or contact recruiters.

Email-first outreach, recruiter/contact resolution, Gmail draft/send operations, form-assist flows, and explicit external-action approval belong to V0.2C.

## V0.2C email outreach core

V0.2C consumes an existing validated `ApplicationPacket`; it does not rewrite CV evidence or create new factual authority.

```text
ApplicationPacket
-> verified contact
-> OutreachBrief
-> user-requested Gmail draft
-> exact draft hash
-> explicit approval
-> separate explicit SendRequest
-> idempotent SendReceipt
```

The deterministic core resolves only permitted contacts, prepares evidence-bounded outreach metadata, records exact semantic draft snapshots, binds approval to one exact draft hash, and requires a second explicit send instruction before authorization.

### Operator boundary

Opportunity OS does not create Gmail drafts automatically. ChatGPT may create a Gmail draft only when the user asks and must use the exact recipient, canonical subject/body, and validated CV attachment represented by the outreach state.

**Approval is not a send command.** A valid `ApprovalRecord` cannot send anything by itself. Sending additionally requires a fresh explicit `SendRequest`, a successful `SendGate` validation, a recorded `SEND_ATTEMPTED` event, and provider success evidence before `SENT` may be recorded.

The core does not instantiate Gmail or Apollo clients. Gmail and Apollo remain connected operator capabilities outside deterministic project code.

### Contact priority and anti-spam

Default resolution order:

```text
published vacancy email
-> verified official Careers / HR email
-> verified recruiter / Talent Acquisition contact
-> manual/form route
```

Opportunity OS never guesses conventional addresses such as `jobs@company.com`. One successful initial contact blocks another initial send to the same requisition even when the later message body has a different hash. Recruiter contacts remain capped by policy.

### Exact draft identity

`DraftSnapshot` hashes semantic content rather than Gmail resource IDs. Recipient, subject, body, reply target, attachment filename, attachment SHA-256, selected CV hash, and content type are material. Provider draft ID and timestamps are not.

Therefore an exact semantic replica can retain the same draft hash when Gmail returns a different draft ID. Any material mutation changes the hash and invalidates the previous approval.

### Private/local outreach data

Real outreach state remains local-only:

```text
state/outreach.local.sqlite3
artifacts/applications/<application_id>/outreach/
```

No Gmail/Apollo credentials, mailbox exports, real recruiter data, approval records, send requests, or receipts belong in the public repository. Apollo enrichment remains optional and requires the connected tool's explicit credit confirmation before any credit-consuming action.

## Scoring

### CAREER match

The original V0.1 career score remains authoritative for strategic matching:

| Component | Weight |
| --- | ---: |
| Core / mandatory skill fit | 40% |
| Role / domain fit | 20% |
| Verified evidence fit | 20% |
| Location / remote fit | 10% |
| Freshness | 10% |

Default CAREER tiers:

```text
HIGH    match >= 78 and confidence >= 75
MEDIUM  match >= 65 and confidence >= 65
STRETCH match >= 55 but below MEDIUM
DISCARD match < 55 or factual hard fail
```

### INCOME_NOW viability

INCOME_NOW answers a different question:

| Component | Weight |
| --- | ---: |
| Verified capability / requirement fit | 35% |
| Logistics / location feasibility | 25% |
| Schedule / work-mode compatibility | 15% |
| Entry friction / formal barrier fit | 15% |
| Freshness / deadline | 10% |

Default INCOME_NOW tiers:

```text
HIGH    viability >= 75 and confidence >= 75
MEDIUM  viability >= 62 and confidence >= 65
LOW     otherwise
```

Weights and thresholds are versioned product configuration, not scientific facts.

### Confidence

Confidence is independent from fit:

| Signal | Weight |
| --- | ---: |
| Requirement extraction quality | 25% |
| Skill normalization coverage | 20% |
| Evidence traceability | 20% |
| Seniority / location / legal clarity | 20% |
| Source / freshness completeness | 15% |

Missing or ambiguous information lowers confidence instead of silently becoming a negative candidate fact.

## Daily selector

The default selector mode is `income_first`.

The daily batch has strict anti-spam constraints:

- maximum **20 opportunities total**;
- 20 is a ceiling, never a quota;
- only HIGH or MEDIUM opportunities can enter;
- STRETCH opportunities never fill unused capacity;
- maximum 2 opportunities from the same company by default;
- known already-applied requisitions are excluded;
- duplicate requisitions appear once;
- optional company/role cooldown is explicit;
- HIGH precedes MEDIUM;
- ties are deterministic;
- strong CAREER opportunities remain visible under `income_first`.

If only 7 opportunities meet the configured quality thresholds, the batch contains 7.

## Architecture

```text
Authorized public sources / manual import
                ↓
Source adapters + isolated failures
                ↓
Normalized Opportunity
                ↓
SQLite persistence + deduplication
                ↓
Versioned enrichment + provenance
                ↓
Candidate tracks
                ↓
Factual eligibility gates
                ↓
CAREER + INCOME_NOW scoring
                ↓
Independent confidence
                ↓
Tier + priority ranking
                ↓
Deterministic daily selector (max 20)
                ↓
DailyRadarBatch
                ↓
Verified private facts + evidence
                ↓
CV Factory
                ↓
Validated ATS PDF + ApplicationPacket
                ↓
Verified contact + OutreachBrief
                ↓
Exact DraftSnapshot + ApprovalRecord
                ↓
Explicit SendRequest + SendGate
                ↓
Provider receipt + append-only outreach ledger
```

Source-specific payloads stay inside connectors. Scoring, CV preparation, and outreach policy do not depend on raw ATS JSON, a live taxonomy service, Gmail/Apollo SDKs, or an LLM correctness dependency.

## Sources

V0.2A can build a local source registry from supported public adapters:

- **Remotive** — public remote-job feed.
- **Greenhouse Job Board API** — public GET job-board data.
- **Lever Postings API** — public published postings.
- **Ashby Public Job Posting API** — public job-board postings; unlisted postings are excluded.

One source failing does not invalidate successful sources or stored candidates. Failures are returned as sanitized diagnostics rather than raw upstream errors.

Source identifiers such as Greenhouse board tokens, Lever site names, and Ashby board names are public routing identifiers, not credentials.

### Source registry

Start from the fictional example:

```bash
cp sources/example_sources.yaml sources.local.yaml
```

`sources.local.yaml` is gitignored. Unknown fields and unsupported source types are rejected.

### Manual opportunity import

Public APIs do not cover every local board, public-sector notice, freelance listing, or directly shared opportunity. The source-neutral manual import path accepts supplied opportunity facts and sends them through the same persistence, enrichment, scoring, confidence, ranking, and selection pipeline.

Opportunity OS does not scrape the destination page as part of manual import.

## Skill normalization and taxonomy

Approved aliases live in `data/skill_aliases.yaml`.

An optional local taxonomy snapshot may add reviewed related-skill relations. Runtime scoring does **not** require a live ESCO/O*NET/network request. A related term never silently proves direct experience with an explicitly required product or tool.

## Quick start

Requires **Python 3.12+**.

```bash
python -m venv .venv
# Activate .venv for your shell/operating system.
python -m pip install -e ".[dev]"
cp profiles/example_profile.yaml profile.local.yaml
cp sources/example_sources.yaml sources.local.yaml
uvicorn app.main:app --reload
```

Run the suite:

```bash
python -m pytest -v
python -m compileall app
```

Tests, CV preparation fixtures, and outreach integration fixtures do not require live job-board, taxonomy, Gmail, or Apollo access.

## Local configuration

`.env.example` documents supported runtime paths and timeouts:

```text
OPPORTUNITY_DB_PATH=opportunities.db
OPPORTUNITY_PROFILE_PATH=profile.local.yaml
HTTP_TIMEOUT_SECONDS=10
OPPORTUNITY_TAXONOMY_PATH=
OPPORTUNITY_ALIAS_REGISTRY_PATH=data/skill_aliases.yaml
OPPORTUNITY_SOURCES_PATH=sources.local.yaml
```

Private/local files such as `.env`, `profile.local.yaml`, `sources.local.yaml`, SQLite databases, master facts, evidence catalogs, CVs, generated application documents, and outreach state must not be committed to the public repository.

## HTTP API

Health:

```text
GET /health
```

Opportunities:

```text
GET  /api/v1/opportunities
GET  /api/v1/opportunities/{id}
POST /api/v1/opportunities/manual
```

Existing Remotive ingestion:

```text
POST /api/v1/ingest/remotive
```

Existing V0.1 assessment:

```text
POST /api/v1/assessments/{opportunity_id}
```

V0.2A radar:

```text
POST /api/v1/radar/run
```

V0.2B and V0.2C intentionally add **no public HTTP endpoint**. CV preparation and outreach orchestration remain internal/local boundaries; connected Gmail/Apollo operations are performed externally by the ChatGPT operator only after the relevant user instruction.

## Backward compatibility

V0.2C extends Opportunity OS rather than replacing earlier slices:

- the original `Opportunity` storage contract remains intact;
- V0.1 API routes remain available;
- the original 40/20/20/10/10 career score remains intact;
- existing single-profile YAML still works as an implicit default radar track;
- V0.2A enrichment remains separately versioned;
- V0.2B does not change radar scoring or selection thresholds;
- CV preparation is downstream from a typed `RadarAssessment`;
- V0.2C consumes the validated `ApplicationPacket` without weakening V0.2B evidence rules;
- Gmail/Apollo are not deterministic-core dependencies.

## Safety and privacy defaults

- no committed credentials;
- no public personal candidate profile;
- no public real CV by default;
- private master facts and evidence catalogs are gitignored;
- generated PDFs/DOCX files are forbidden from tracked public source by CI;
- real outreach SQLite state and generated outreach artifacts are gitignored and CI-guarded;
- external source errors are sanitized;
- unknown candidate facts remain unknown;
- application tracks are hard evidence boundaries;
- numeric/title/date claims require verified support;
- scoring, evidence selection, composition, validation, PDF rendering, packet hashing, outreach hashing, approval checks, and send authorization are deterministic from explicit inputs;
- Approval is not a send command;
- provider success evidence is required before `SENT` is recorded.

## Development

The implementation is intentionally incremental. Domain models, connectors, persistence, radar enrichment/scoring, evidence selection, composition, validation, rendering, packet orchestration, contact resolution, approval, and send authorization remain separate boundaries.

V0.1 design and plan:

```text
docs/superpowers/specs/2026-08-28-opportunity-os-v0.1-design.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.1.md
```

V0.2A design and plans:

```text
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2a-intelligent-radar-design.md
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2a-multi-intent-amendment.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.2a1-multi-intent-radar-core.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.2a1-self-review-corrections.md
```

V0.2B design and implementation plan:

```text
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2b-cv-factory-design.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.2b-cv-factory.md
```

V0.2C design and implementation plans:

```text
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2c-email-outreach-design.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.2c-email-outreach.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.2c-email-outreach-self-review.md
```

## License

MIT
