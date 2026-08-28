# Opportunity OS

Open-source opportunity discovery, normalization, matching, and application-preparation infrastructure with **explainable scoring and human approval**.

Opportunity OS automates repetitive opportunity research and prioritization without pretending that a single score can answer every work decision. V0.2A introduces a multi-intent radar that can distinguish between work that advances a preferred career and work that is realistically useful for income now.

> **Current scope:** V0.2A discovers, enriches, scores, ranks, and selects opportunities. It does **not** generate CVs, send applications, submit forms, bypass CAPTCHAs, or answer legal/declarative questions.

## V0.2A intelligent radar

The radar evaluates opportunities along three separate dimensions:

- **CAREER** — how strongly the opportunity matches a preferred professional direction.
- **INCOME_NOW** — how realistically the candidate can obtain and perform the work soon enough for it to be useful as income.
- **CONFIDENCE** — how trustworthy the assessment inputs are. Confidence is not job fit.

This separation matters. A role can be a weak career target and still be a strong income opportunity, or the reverse.

Example:

```text
CAREER       31 / 100
INCOME_NOW   84 / 100
CONFIDENCE   90 / 100

Interpretation:
not a strategic career target, but a strong near-term income opportunity.
```

### Candidate tracks

V0.2A can keep different verified experience groups isolated through candidate tracks. Unrelated experience is not allowed to contaminate another role family.

For example, a local private profile may contain separate tracks for:

```text
tech_geospatial       -> CAREER + INCOME_NOW
gastronomy_operations -> INCOME_NOW
general_operations    -> INCOME_NOW
```

The public repository contains only fictional examples. Personal profiles remain local and gitignored.

## Scoring

### CAREER match

The original V0.1 score remains authoritative for career-oriented matching:

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

INCOME_NOW answers a different question and therefore has a different deterministic score:

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

Thresholds and weights are product configuration, not scientific facts. They are versioned so they can later be calibrated against actual outcomes.

### Confidence

Confidence is independent from both fit scores:

| Signal | Weight |
| --- | ---: |
| Requirement extraction quality | 25% |
| Skill normalization coverage | 20% |
| Evidence traceability | 20% |
| Seniority / location / legal clarity | 20% |
| Source / freshness completeness | 15% |

Missing or ambiguous information lowers confidence rather than silently becoming a negative candidate fact.

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
```

Source-specific payloads stay inside connectors. Scoring does not depend on raw ATS JSON or live taxonomy calls.

## Sources

V0.2A can build a local source registry from these supported public adapters:

- **Remotive** — public remote-job feed.
- **Greenhouse Job Board API** — public GET job-board data.
- **Lever Postings API** — public published postings.
- **Ashby Public Job Posting API** — public job-board postings; unlisted postings are excluded.

One source failing does not invalidate successful sources or stored candidates. Source failures are returned as sanitized diagnostics rather than raw upstream errors.

Source identifiers such as Greenhouse board tokens, Lever site names, and Ashby board names are public routing identifiers, not credentials.

### Source registry

Start from the fictional example:

```bash
cp sources/example_sources.yaml sources.local.yaml
```

`sources.local.yaml` is gitignored. A source entry is strict: unknown fields and unsupported source types are rejected instead of being silently accepted.

### Manual opportunity import

Public APIs do not cover every local board, public-sector notice, freelance listing, or opportunity someone sends directly. V0.2A therefore includes a source-neutral manual import path.

The caller supplies the URL and opportunity facts. Opportunity OS does not scrape the destination page as part of manual import. Imported opportunities enter the same persistence, enrichment, scoring, confidence, ranking, and selection pipeline as connector-sourced opportunities.

## Skill normalization and taxonomy

V0.2A supports deterministic skill normalization with:

```text
EXACT_VERIFIED      1.00
APPROVED_ALIAS      1.00
TAXONOMY_RELATED    0.70 maximum partial support
UNKNOWN             0.00
```

Approved aliases live in the versioned local registry under `data/skill_aliases.yaml`.

An optional local taxonomy snapshot may add reviewed related-skill relations. Runtime scoring does **not** require a live ESCO/O*NET/network request. A related taxonomy term never silently proves experience with an explicitly required product or tool.

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

Run the test suite:

```bash
python -m pytest -v
```

Compile-check the application:

```bash
python -m compileall app
```

Tests do not require live job-board access.

## Local configuration

`.env.example` documents the supported paths and timeouts:

```text
OPPORTUNITY_DB_PATH=opportunities.db
OPPORTUNITY_PROFILE_PATH=profile.local.yaml
HTTP_TIMEOUT_SECONDS=10
OPPORTUNITY_TAXONOMY_PATH=
OPPORTUNITY_ALIAS_REGISTRY_PATH=data/skill_aliases.yaml
OPPORTUNITY_SOURCES_PATH=sources.local.yaml
```

Private/local files such as `profile.local.yaml`, `sources.local.yaml`, `.env`, SQLite databases, CVs, and generated application documents must not be committed to the public repository.

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

`POST /api/v1/radar/run` returns a typed `DailyRadarBatch` containing selected assessments, version metadata, policy metadata, tier/intent counts, profile fingerprint, and sanitized source diagnostics.

A missing candidate profile returns `503 Candidate profile unavailable`. If all configured sources fail and there are no stored candidates inside the lookback window, the radar returns a public-safe 502 rather than leaking upstream details.

## Backward compatibility

V0.2A extends Opportunity OS rather than replacing V0.1:

- the original `Opportunity` storage contract remains intact;
- V0.1 API routes remain available;
- the original 40/20/20/10/10 career score remains intact;
- existing single-profile YAML works as an implicit default track;
- enrichment is stored separately and versioned by extractor, alias registry, and taxonomy versions.

## What V0.2A does not do

Opportunity OS V0.2A does **not**:

- generate tailored CVs;
- send applications or recruiter messages;
- submit job forms;
- log into LinkedIn, Indeed, government portals, or marketplaces;
- scrape restricted platforms;
- bypass CAPTCHAs or anti-bot controls;
- store job-portal passwords;
- infer citizenship, work authorization, health, criminal background, or other sensitive/legal declarations;
- accept terms on the user's behalf;
- use an LLM as the final authority for fit, truth, eligibility, or submission.

CV composition and application packets belong to the later V0.2B slice. Approval and permitted submission adapters belong to V0.2C.

## Safety and privacy defaults

- no committed credentials;
- no public personal candidate profile;
- no public CV by default;
- local source configuration is gitignored;
- explicit HTTP timeouts;
- one connector failure does not erase successful or stored opportunities;
- external source errors are sanitized before reaching API clients;
- unknown candidate facts remain unknown rather than becoming fabricated incompatibilities;
- scoring is deterministic from explicit inputs;
- consequential external actions remain outside V0.2A.

## Development

The implementation remains intentionally incremental. Domain models, source adapters, persistence, enrichment, scoring, ranking, selection, orchestration, and HTTP composition are separate boundaries.

V0.1 design and plan:

```text
docs/superpowers/specs/2026-08-28-opportunity-os-v0.1-design.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.1.md
```

V0.2A design and implementation plan:

```text
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2a-intelligent-radar-design.md
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2a-multi-intent-amendment.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.2a1-multi-intent-radar-core.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.2a1-self-review-corrections.md
```

## License

MIT
