# Opportunity OS — V0.2A Intelligent Radar Design

Date: 2026-08-28
Status: review
Parent roadmap: private Opportunity OS V0.2 plan in the knowledge vault

## 1. Product goal

Turn V0.1 from a per-opportunity assessment engine into a repeatable daily radar that can discover, enrich, filter, score, rank, and return **up to 20 medium/high-confidence job opportunities** for later CV preparation.

V0.2A ends before CV generation, batch approval, or submission. Its output is the trusted ranked input for those later slices.

Operational invariant:

> 20 is a maximum capacity, never a quota. If only 7 opportunities meet the quality gates, the batch contains 7.

## 2. Starting point and compatibility

V0.1 already provides:

- `Opportunity`, `CandidateProfile`, `EvidenceItem`, and `OpportunityAssessment` strict Pydantic models;
- Remotive, Greenhouse, Lever, and Ashby connectors;
- normalized `Opportunity` objects;
- SQLite persistence and deduplication;
- deterministic scoring;
- FastAPI read/assessment routes;
- source isolation and sanitized connector errors;
- offline tests and Python 3.12 CI.

The V0.1 score is retained as the **match score**:

```text
mandatory/core skill fit   40%
role/domain fit            20%
verified evidence fit      20%
location/remote fit        10%
freshness                  10%
```

V0.2A must not silently change V0.1 results for opportunities that have no new enrichment data. Regression fixtures will lock this behavior.

## 3. Scope

V0.2A includes:

1. multi-source radar orchestration over the existing connectors;
2. structured requirement extraction with provenance;
3. approved skill aliases and taxonomy-assisted normalization;
4. eligibility gates before scoring;
5. V0.1-compatible match scoring with richer normalized inputs;
6. an independent confidence score;
7. decision tiers and priority ranking;
8. a deterministic daily selector capped at 20;
9. API/read contracts for running and inspecting the radar;
10. version metadata so historical decisions remain reproducible.

V0.2A excludes:

- CV generation/rendering;
- cover letters;
- email sending;
- application submission;
- browser/form automation;
- approval workflows;
- Gmail/Calendar integration;
- application ledger persistence beyond reading existing status/history inputs;
- LinkedIn or Indeed scraping;
- CAPTCHA handling/bypass;
- LLM-owned numeric scoring;
- embeddings/vector databases as a runtime requirement;
- LangChain/LangGraph;
- automatic score-weight learning.

## 4. Research-informed decisions

### 4.1 ESCO

ESCO is used as an external vocabulary for occupations, skills, multilingual labels, and skill↔occupation context. It is appropriate for competence-based job matching, but it is **not evidence that the candidate possesses a skill**.

Target source version for the first snapshot: ESCO v1.2.1.

References:

- https://esco.ec.europa.eu/en/about-esco/what-esco
- https://esco.ec.europa.eu/en/about-esco/escopedia/escopedia/competence-based-job-matching
- https://esco.ec.europa.eu/en/use-esco/use-esco-services-api/esco-web-service-api

### 4.2 O*NET

O*NET is used as occupational context for skills, knowledge, preparation, tasks, work activities, and related occupation metadata. It can help interpret ambiguous role titles and expected occupational preparation.

Target source version for the first snapshot: O*NET 31.0.

Reference:

- https://www.onetcenter.org/database.html

### 4.3 Runtime taxonomy rule

Scoring must not depend on live ESCO/O*NET availability.

```text
live source / downloadable dataset
        ↓ explicit refresh/build step
versioned local taxonomy snapshot/cache
        ↓
TaxonomyResolver
        ↓
radar scoring
```

A missing taxonomy cache degrades safely to exact matching + approved local aliases. It must not make the radar unavailable.

CI uses small deterministic fixtures and never calls ESCO/O*NET over the network.

### 4.4 ATS submission is not part of this slice

Greenhouse application submission requires authenticated employer/job-board access; Lever programmatic apply requires an account API key and is rate limited; Ashby candidate/application write APIs require write permissions. Therefore V0.2A only records future `application_mode` classification when it can do so confidently. It does not assume a universal applicant-side submission API.

## 5. Architecture

```text
Configured source adapters
        ↓
Radar ingestion orchestrator
        ↓
Existing normalized Opportunity
        ↓
RequirementExtractor
        ↓
OpportunityEnrichment + provenance
        ↓
SkillResolver
  exact / approved alias / taxonomy relation
        ↓
EligibilityEvaluator
        ↓
V0.1-compatible MatchScorer
        ↓
ConfidenceScorer
        ↓
TierClassifier
        ↓
PriorityRanker
        ↓
DailySelector (max 20)
        ↓
DailyRadarBatch
```

All scoring/ranking components are pure or deterministic given their explicit inputs. Network access is confined to source ingestion and optional offline taxonomy refresh operations.

## 6. Preserve `Opportunity`; add companion enrichment

Do **not** overload the existing `Opportunity` storage model with dozens of nullable V0.2 fields. V0.1 APIs and deduplication depend on that contract.

Instead add a companion model:

```text
Opportunity
  1 ─── 0..1 OpportunityEnrichment
```

This keeps source normalization separate from interpretation and lets enrichment be recomputed when extractors/taxonomies evolve.

### 6.1 Provenance model

Every derived field must retain its origin.

```python
DerivedValue[T]
- value: T
- source_text: str | None
- source_field: str
- extraction_method: str
- confidence: float  # 0..1
```

`source_field` examples:

```text
title
description
required_skills
preferred_skills
location
remote_policy
source_metadata
```

`extraction_method` examples:

```text
source_structured
explicit_rule
approved_alias
taxonomy_snapshot
manual_override
```

Derived facts without provenance are invalid.

## 7. Enrichment contract

`OpportunityEnrichment` contains only interpreted/derived information:

```text
opportunity_id
normalized_title
role_family
seniority
employment_type
language
country
region
work_authorization_requirement
visa_sponsorship
salary_min
salary_max
salary_currency
requirements[]
application_mode
source_reliability
source_freshness_quality
extractor_version
taxonomy_versions
created_at
```

Unknown values remain `None`/`unknown`; they are not converted into negative facts.

### 7.1 Requirement model

```text
Requirement
- kind
- value
- importance
- exactness
- provenance
```

`kind`:

```text
skill
experience
education
license
work_authorization
location
schedule
language
other
```

`importance`:

```text
mandatory
preferred
unknown
```

`exactness`:

```text
conceptual       # a related competency may partially satisfy it
exact_product    # named tool/product must not be silently substituted
declarative      # legal/credential statement; never inferred from similarity
```

## 8. Requirement extraction

Public interface:

```python
class RequirementExtractor(Protocol):
    def extract(self, opportunity: Opportunity) -> OpportunityEnrichment: ...
```

First implementation is deterministic and rule-based.

Inputs:

- structured source fields already present on `Opportunity`;
- title;
- description;
- location/remote metadata.

V0.2A recognizes explicit English/Spanish cues such as:

```text
required / must / mandatory / minimum
preferred / nice to have / bonus
requerido / obligatorio / excluyente / mínimo
preferido / deseable / será un plus
```

The extractor may segment text into sentences/bullets, but each extracted requirement must keep its exact supporting span in `source_text`.

An optional future LLM extractor may implement the same interface, but V0.2A correctness cannot depend on it.

## 9. Skill normalization and taxonomy

### 9.1 Match levels

```text
EXACT_VERIFIED       1.00
APPROVED_ALIAS       1.00
TAXONOMY_RELATED     0.70
SEMANTIC_CANDIDATE   0.40   # reserved; does not assert possession
UNKNOWN              0.00
```

V0.2A implements exact, approved alias, taxonomy-related, and unknown. `SEMANTIC_CANDIDATE` is reserved for later experimentation and is not required for V0.2A done.

### 9.2 Alias registry

A small versioned registry is the authority for equivalence aliases.

```text
canonical_skill
aliases[]
relationship
confidence
approved_by
approved_at
```

Only relationships explicitly classified as equivalence can produce `APPROVED_ALIAS = 1.00`.

Examples:

```text
postgres -> PostgreSQL        equivalence
js -> JavaScript              equivalence
spatial database -> PostGIS   related, not equivalence
```

No automatically suggested alias becomes authoritative without being added to the registry.

### 9.3 Taxonomy resolver

Public interface:

```python
class TaxonomyResolver(Protocol):
    def resolve_skill(self, term: str) -> ResolvedSkill: ...
    def resolve_role(self, title: str) -> ResolvedRole: ...
```

Runtime implementations read local snapshots/cache. Live network clients, if added for refresh tooling, stay outside scoring services.

### 9.4 Exact-product rule

A taxonomy relation does not silently satisfy an explicitly named mandatory product/tool.

Example:

```text
Requirement: "PostGIS required"
Candidate evidence: generic spatial databases
Taxonomy: related

Result:
- relation may be displayed as nearby evidence;
- mandatory PostGIS gap remains;
- it cannot receive full mandatory credit.
```

## 10. Eligibility gates

Eligibility runs before match scoring.

Output:

```text
EligibilityResult
- eligible: bool
- hard_fail_reasons[]
- soft_risks[]
- unknowns[]
```

Hard fail requires explicit evidence of incompatibility. Unknown data is never a hard fail.

Initial hard-fail policies:

- closed/unlisted/non-public posting when known;
- explicit on-site/location requirement incompatible with configured candidate constraints;
- explicit work-authorization condition contradicted by verified profile data;
- mandatory license/certification explicitly absent;
- explicit schedule/work pattern matching a configured `no_go` constraint;
- role family explicitly outside configured target families;
- another mandatory condition explicitly contradicted by verified profile facts.

Unknown legal/work-authorization data goes to `unknowns` and lowers confidence; the radar must not infer a legal answer.

## 11. Match score V0.2A

Keep the public 100-point structure:

| Component | Weight |
| --- | ---: |
| Mandatory/core skill fit | 40 |
| Role/domain fit | 20 |
| Verified evidence fit | 20 |
| Location/remote fit | 10 |
| Freshness | 10 |

### 11.1 Compatibility rule

When V0.2A has no enrichment beyond the original V0.1 fields and no alias/taxonomy resolution is used, the result must equal the current V0.1 assessment for the same profile/opportunity/time.

### 11.2 Mandatory skill fit

Mandatory requirements dominate preferred requirements.

Priority of evidence:

```text
exact verified candidate skill
approved equivalent alias
taxonomy-related competency
unknown / absent
```

Preferred requirements can improve context but cannot erase a serious mandatory gap.

### 11.3 Role/domain fit

Role-family normalization may use:

- local role aliases;
- ESCO occupation relationships;
- O*NET occupation context;
- configured internal role families.

Taxonomy context refines interpretation; it does not replace the actual job description.

### 11.4 Evidence fit

Only `verified=True` candidate evidence can award verified-evidence credit.

Every evidence-based strength must point back to an existing evidence item. No new claim is generated by the matcher.

### 11.5 Location

Explicit incompatible location may already have failed eligibility. Otherwise location remains a scored factor for remote/LATAM/relocation preferences.

### 11.6 Freshness

Retain the current age curve for backward compatibility:

```text
<= 7 days    100
<= 30 days    75
unknown       50
<= 90 days    25
> 90 days      0
```

Add `source_freshness_quality` to the explanation so an aggregator-delayed timestamp is not presented as equal provenance to a direct ATS timestamp.

## 12. Confidence score

`confidence_score` answers:

> How much do we trust this assessment given the quality/completeness of its inputs?

It does **not** answer whether the job is a good fit.

Initial deterministic weights:

| Signal | Weight |
| --- | ---: |
| Requirement extraction quality | 25 |
| Skill normalization coverage | 20 |
| Evidence traceability | 20 |
| Seniority/location/legal clarity | 20 |
| Source/freshness completeness | 15 |
| **Total** | **100** |

Rules:

- missing information lowers confidence, not match by default;
- source incompleteness must not fabricate a negative fit;
- verified provenance improves confidence;
- taxonomy availability may improve normalization coverage but cannot prove candidate experience;
- the full component breakdown is returned with the total.

## 13. Decision tiers

Thresholds are configuration, with these defaults:

```text
HIGH
  eligible = true
  match >= 78
  confidence >= 75

MEDIUM
  eligible = true
  match >= 65
  confidence >= 65

STRETCH
  eligible = true
  match >= 55
  but does not meet MEDIUM

DISCARD
  hard fail OR match < 55
```

Only HIGH and MEDIUM are candidates for the automatic daily radar batch.

Threshold configuration must be explicit and serializable in output metadata.

## 14. Priority score

Match and priority remain separate concepts.

Default formula:

```text
priority_score =
    0.80 * match_score
  + 0.20 * confidence_score
  - policy_penalties
```

Allowed initial penalties are observable process rules only, for example:

- probable duplicate of a stronger/original posting;
- already applied requisition;
- same-company daily cap interaction;
- configured recent-company/role cooldown supplied by history;
- stale/indirect source when a direct ATS copy exists.

No sensitive personal attribute can be used as a ranking penalty.

The output must list every applied penalty and its numeric value.

## 15. Daily selector

Public pure interface:

```python
select_daily_batch(
    ranked_items,
    policy,
    history,
    *,
    now,
) -> DailyRadarBatch
```

Default policy:

```text
max_items = 20
max_per_company = 2
allowed_tiers = [HIGH, MEDIUM]
```

Selection order:

1. remove ineligible/STRETCH/DISCARD;
2. remove known already-applied requisitions;
3. apply duplicate and company/cooldown policies;
4. HIGH before MEDIUM;
5. within tier sort by:
   - priority desc,
   - match desc,
   - confidence desc,
   - published_at desc with unknown last,
   - opportunity id asc for deterministic ties;
6. stop at `max_items`.

If only 7 items survive, return 7.

History is passed through a small read interface. V0.2A tests the policy with fixtures; the full auditable application ledger is a later slice.

## 16. Radar orchestration

V0.2A adds a service that composes existing source connectors without changing their source-specific boundaries.

```python
RadarService.run(config, profile, now) -> RadarRunResult
```

Responsibilities:

1. run enabled connectors independently;
2. persist/dedupe normalized opportunities through the existing repository;
3. continue when one connector fails;
4. collect source-level ingestion diagnostics;
5. enrich and assess candidate opportunities;
6. build the daily batch.

A source failure must not invalidate successful source results.

### 16.1 Source configuration

Use a local config file such as `sources.local.yaml` plus a fictional public example.

Supported V0.2A source entries map only to existing connectors:

```text
remotive
greenhouse
lever
ashby
```

Greenhouse board tokens, Lever site names, and Ashby board names are public routing identifiers. Secrets, if a future connector needs them, belong in environment variables and never in source YAML.

V0.2A does not require Adzuna or another new feed connector to be complete. New feeds can be added independently after the radar core is stable.

## 17. Persistence

### 17.1 Existing opportunities

Keep the current `opportunities` table and repository behavior stable.

### 17.2 Enrichment

Persist enrichment separately so it can be invalidated/recomputed by version.

Conceptual table:

```text
opportunity_enrichments
- opportunity_id
- payload_json
- extractor_version
- alias_registry_version
- taxonomy_versions_json
- created_at
```

One current enrichment per `(opportunity_id, version tuple)` is sufficient for V0.2A. The repository boundary should hide SQLite details.

### 17.3 Batch persistence

V0.2A may return a computed `DailyRadarBatch` without making it an approval artifact. Immutable/persisted `ApplicationPacket` and approval hashes belong to V0.2B/V0.2C.

## 18. Output models

### 18.1 RadarAssessment

```text
opportunity
enrichment
eligibility
match_assessment
confidence_score
confidence_breakdown
tier
priority_score
priority_penalties
scoring_version
alias_registry_version
taxonomy_versions
```

### 18.2 DailyRadarBatch

```text
batch_id
generated_at
policy
profile_fingerprint
scoring_version
alias_registry_version
taxonomy_versions
items[]
count
high_count
medium_count
source_diagnostics
```

`profile_fingerprint` is a non-secret hash/version identifier, not the personal profile contents.

`batch_id` must be reproducible from the run snapshot or generated once and returned with complete version metadata. No downstream code may treat it as application approval.

## 19. API surface

Keep V0.1 routes compatible.

Add V0.2A endpoints under the existing `/api/v1` prefix:

```text
POST /api/v1/radar/run
GET  /api/v1/radar/opportunities/{opportunity_id}
```

`POST /radar/run` performs the configured radar run and returns `DailyRadarBatch` plus source diagnostics.

It has no submission side effects.

If no profile is configured: `503 Candidate profile unavailable`.

If one source fails but others succeed: return a successful radar result with a sanitized source diagnostic for the failed connector.

If all enabled sources fail and there are no stored candidates to assess: return a sanitized upstream failure response rather than an empty-success ambiguity.

## 20. Error handling and degradation

Typed failure categories:

```text
source_unavailable
invalid_source_config
extraction_failed
taxonomy_unavailable_or_missing
invalid_enrichment
profile_unavailable
```

Rules:

- raw upstream bodies/secrets never reach API responses;
- one source failure is isolated;
- missing taxonomy snapshot is a warning and deterministic fallback, not fatal;
- one malformed opportunity enrichment does not delete the original opportunity;
- unknown requirement data lowers confidence;
- no exception converts unknown into a hard incompatibility.

## 21. Versioning and reproducibility

Every radar assessment/batch records:

```text
scoring_version
enrichment/extractor_version
alias_registry_version
taxonomy source versions
threshold/policy configuration
profile fingerprint
```

Initial scoring version: `v0.2a.1`.

Changing weights, tier thresholds, match-level multipliers, or gate semantics requires a scoring-version change.

Alias changes require an alias-registry version/hash change.

## 22. Security and privacy

- personal profile remains local and gitignored;
- public repo ships fictional profile/source examples only;
- no CV is introduced in V0.2A;
- no job portal credentials are stored;
- no LinkedIn/Indeed scraping;
- no submission endpoint;
- no legal/declarative fact is inferred from taxonomy/semantic similarity;
- taxonomy refresh uses explicit timeouts and pinned source versions;
- offline CI never requires personal data or external network access.

## 23. Testing strategy

Tests remain offline and fixture-driven.

### Contract tests

- strict enrichment/provenance models reject unknown fields;
- derived values without provenance fail;
- timestamps are timezone-aware;
- unknown values remain unknown.

### Extraction tests

- English mandatory/preferred cues;
- Spanish mandatory/preferred cues;
- source-structured skills outrank weaker text inference;
- exact supporting source span is retained;
- ambiguous wording remains `unknown` rather than mandatory.

### Resolver tests

- exact match = 1.00;
- approved equivalence alias = 1.00;
- taxonomy relation = 0.70;
- taxonomy relation does not become exact-product satisfaction;
- missing taxonomy cache falls back safely;
- alias resolution is case/whitespace stable.

### Eligibility tests

- explicit hard fail never enters batch;
- unknown legal/location information is not a hard fail;
- explicit location conflict blocks;
- missing mandatory license blocks when absence is verified;
- configured no-go constraint blocks.

### Match regression tests

- existing V0.1 fixtures preserve scores without new enrichment;
- unverified evidence never receives verified-evidence credit;
- approved alias can satisfy equivalent skill;
- related skill remains partial/nearby evidence;
- freshness curve remains unchanged.

### Confidence tests

- missing/ambiguous extraction lowers confidence;
- source incompleteness lowers confidence without lowering match automatically;
- better provenance raises confidence;
- confidence components sum deterministically.

### Rank/selector tests

- never returns more than 20;
- never fills with STRETCH;
- 7 valid items returns exactly 7;
- HIGH precedes MEDIUM;
- max two per company by default;
- same requisition never appears twice;
- history exclusion works;
- ordering is deterministic under ties.

### Orchestration tests

- one connector failure does not suppress successful sources;
- all connectors are mocked;
- source diagnostics are sanitized;
- no taxonomy network call occurs during scoring.

## 24. Proposed module boundaries

```text
app/
├── radar/
│   ├── models.py
│   ├── extractor.py
│   ├── taxonomy.py
│   ├── eligibility.py
│   ├── confidence.py
│   ├── ranking.py
│   ├── selector.py
│   └── service.py
├── matching/
│   └── scorer.py           # preserve/refactor carefully
├── repositories/
│   ├── opportunities.py    # existing contract remains stable
│   └── enrichments.py
└── api/
    └── routes.py

profiles/
├── example_profile.yaml
└── ...

sources/
└── example_sources.yaml

data or cache boundary/
└── taxonomy metadata/fixtures as needed
```

Exact filenames may change during planning if a smaller boundary is clearer; responsibilities must remain separated.

## 25. Definition of V0.2A done

V0.2A is complete when a developer can:

1. configure one or more supported public sources;
2. run one radar operation;
3. ingest/dedupe available opportunities with connector isolation;
4. extract structured requirements in English/Spanish with provenance;
5. normalize skills through exact matches, approved aliases, and optional local taxonomy snapshots;
6. evaluate explicit hard eligibility constraints;
7. retain the V0.1 100-point match contract;
8. receive an independent confidence score and component breakdown;
9. classify opportunities into HIGH/MEDIUM/STRETCH/DISCARD;
10. rank eligible candidates with explicit priority penalties;
11. receive no more than 20 HIGH/MEDIUM opportunities and never pad the batch with lower-quality items;
12. see selected evidence, mandatory matches/gaps, risks, unknowns, source diagnostics, and version metadata;
13. run the complete suite without network access;
14. pass CI from a clean Python 3.12 installation;
15. perform all of the above without generating or sending a CV/application.

## 26. Design constraints

- evidence before inference;
- unknown is not false;
- hard constraints cannot be averaged away by a high score;
- match and confidence are separate;
- match and priority are separate;
- taxonomies interpret vocabulary; they do not invent candidate experience;
- deterministic core before optional AI enrichment;
- no live taxonomy dependency in scoring;
- no hidden side effects;
- explicit schemas and provenance;
- keep V0.1 API/storage compatibility where practical;
- simplest correct implementation first.

## 27. Follow-on slices

After V0.2A is stable:

- **V0.2B — CV Factory:** master facts, evidence modules, structured CV model, rendering, immutable application packet.
- **V0.2C — Approval + Submission:** batch approval, direct email/authorized channels, form assist/manual fallback, idempotent submission.
- **V0.2D — Learning Loop:** application ledger, follow-up, response/interview metrics, explicit score calibration reports.

None of those capabilities should leak into V0.2A merely to make the demo look more complete.
