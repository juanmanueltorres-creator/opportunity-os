# Opportunity OS — V0.1 Design

Date: 2026-08-28
Status: proposed

## 1. Product goal

Build a small, public, open-source system that discovers job opportunities from authorized public sources, normalizes them, deduplicates them, scores them against a candidate profile, explains the match, and prepares the next action for human review.

The system is **not** an auto-apply bot and must not send CVs, messages, legal declarations, or platform interactions without explicit human approval.

## 2. V0.1 scope

V0.1 contains one engine only: **employment opportunities**.

Included:

- ingest public job postings from supported sources;
- normalize different source payloads into one internal schema;
- deduplicate repeated postings;
- load a candidate profile from a local YAML file;
- compute a deterministic, explainable score;
- expose strengths, gaps, risks, and recommendation;
- expose results through a small FastAPI API;
- persist local development data in SQLite;
- provide tests for normalization, scoring, deduplication, and API contracts.

Excluded from V0.1:

- automatic CV submission;
- browser automation;
- LinkedIn scraping or messaging;
- Indeed scraping;
- CAPTCHA bypass;
- automated legal/declarative answers;
- credential storage for job portals;
- LLM-generated scores;
- LangChain/LangGraph;
- vector databases;
- Supabase/Postgres;
- React dashboard;
- client/prospecting pipeline;
- MCP/ChatGPT App integration.

## 3. Initial sources

V0.1 will support adapters for public/authorized sources, starting incrementally.

Priority order:

1. Remotive public API — first end-to-end connector because it exposes a broad public feed and is useful for validating the pipeline.
2. Greenhouse public job boards.
3. Lever public postings.
4. Ashby public job postings.

Each connector must fail independently. One unavailable source must not break the whole ingestion pipeline.

## 4. Architecture

```text
Public source adapter
        ↓
Raw source payload
        ↓
Normalizer
        ↓
Opportunity
        ↓
Deduplicator
        ↓
Candidate profile
        ↓
Deterministic matcher
        ↓
OpportunityAssessment
        ↓
FastAPI read API
```

The architecture is intentionally modular so connectors, matching logic, and storage can evolve independently.

## 5. Core domain models

### Opportunity

Required fields:

```text
id
source
source_id
source_url
company
title
description
discovered_at
status
```

Optional fields:

```text
location
remote_policy
published_at
required_skills
preferred_skills
compensation
```

### CandidateProfile

```text
name
roles
skills
domains
locations
remote_preferences
evidence
```

Public repository rule: the repository ships only an example profile. Personal profiles use `profile.local.yaml` and are gitignored.

### OpportunityAssessment

```text
opportunity_id
overall_score
mandatory_fit
domain_fit
evidence_fit
location_fit
freshness_fit
strengths
gaps
risks
recommendation
explanation
```

Recommendation enum:

```text
apply
stretch
nurture
discard
```

## 6. Deterministic scoring

Initial weights:

```text
mandatory skills / core skill fit  40%
domain fit                         20%
evidence fit                       20%
location / remote fit              10%
freshness                          10%
```

The score must remain explainable. The API cannot return only a percentage.

Hard incompatibilities may cap or override the final recommendation. Examples include an explicit required location that conflicts with the candidate profile or a mandatory credential that is absent.

The matcher must not claim equivalence between unrelated skills.

## 7. Evidence model

Each evidence item represents something the candidate can actually demonstrate.

```text
label
type
skills
domains
url (optional)
verified
```

The matcher may select evidence that supports a requirement but must not invent experience.

## 8. Persistence

V0.1 uses SQLite through a small repository/storage boundary.

Reason:

- zero external infrastructure;
- easy local execution;
- suitable for a public demo;
- trivial to replace later with PostgreSQL behind the same boundary.

No migration to Supabase/Postgres is planned until the domain model stabilizes.

## 9. API surface

Initial API prefix: `/api/v1`.

Planned endpoints:

```text
GET  /health
GET  /api/v1/opportunities
GET  /api/v1/opportunities/{id}
POST /api/v1/ingest/remotive
POST /api/v1/assessments/{opportunity_id}
```

The API will use explicit Pydantic response models. Internal exceptions and raw upstream payloads must not leak through responses.

V0.1 contains no endpoint that sends an application or message.

## 10. Error handling

Connector errors are isolated and converted into typed application errors.

Expected cases:

- upstream timeout;
- non-200 response;
- malformed upstream payload;
- duplicate posting;
- invalid profile;
- opportunity not found.

A failed source ingestion must return a clear error without corrupting existing stored opportunities.

## 11. Security and privacy

Rules from day one:

- no credentials committed to Git;
- `.env` is ignored;
- `.env.example` contains names only, never secrets;
- personal candidate profile is ignored;
- no CV file is public by default;
- no passwords for employment portals are stored;
- no automated submission endpoints;
- no scraping of restricted platforms;
- outbound HTTP calls use explicit timeouts;
- dependencies remain minimal.

## 12. Proposed repository structure

```text
opportunity-os/
├── app/
│   ├── main.py
│   ├── api/
│   ├── connectors/
│   ├── matching/
│   ├── models/
│   ├── repositories/
│   └── services/
├── profiles/
│   └── example_profile.yaml
├── tests/
├── docs/
├── .env.example
├── .gitignore
├── LICENSE
├── README.md
└── pyproject.toml
```

## 13. Testing strategy

Every feature is introduced through small tests.

Minimum V0.1 coverage by behavior:

- normalizer maps a known source payload correctly;
- malformed source payload fails safely;
- duplicate opportunities do not create duplicate records;
- matching weights produce deterministic results;
- missing mandatory skills are exposed as gaps;
- evidence is never fabricated;
- invalid profile is rejected;
- API health endpoint contract is stable;
- opportunity list/detail response models are stable;
- connector failure does not destroy previously stored data.

External HTTP tests use fixtures/mocks; CI must not depend on a live job board.

## 14. Implementation order

Incremental slices:

1. project skeleton + health endpoint;
2. domain models + example profile;
3. deterministic matcher;
4. SQLite repository;
5. Remotive adapter + normalization;
6. ingestion service + deduplication;
7. opportunity/assessment API endpoints;
8. Greenhouse adapter;
9. Lever adapter;
10. Ashby adapter.

Each slice must leave the repository runnable and tests passing.

## 15. Definition of V0.1 done

V0.1 is complete when a developer can:

1. clone the public repository;
2. install dependencies;
3. copy the example profile to a local ignored profile;
4. start FastAPI;
5. ingest public opportunities from at least Remotive plus one company-oriented ATS connector;
6. list normalized opportunities;
7. request an assessment;
8. see a deterministic score, strengths, gaps, evidence, risks, and recommendation;
9. run the full test suite locally without network access.

## 16. Design constraints

- simplest correct solution first;
- no unnecessary abstractions;
- no premature agent framework;
- no hidden side effects;
- no destructive or irreversible external actions;
- explicit schemas and versioned API;
- public-safe defaults;
- incremental development with tests.

## 17. Future directions, not commitments

Possible later phases:

- modular CV generation;
- cover-letter/message drafts;
- Gmail response tracking;
- scheduled discovery;
- PostgreSQL/PostGIS/Supabase if justified;
- React review dashboard;
- MCP / ChatGPT App;
- separate client/prospecting engine;
- optional LLM assistance for extraction/explanation with structured outputs and human review.

None of these belong to V0.1 unless the scope is explicitly revised.
