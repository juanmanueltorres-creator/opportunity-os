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

- strict Pydantic `Opportunity`, `CandidateProfile`, `EvidenceItem`, and `OpportunityAssessment` models;
- Remotive, Greenhouse, Lever, and Ashby connectors;
- normalized opportunities;
- SQLite persistence and deduplication;
- deterministic scoring;
- FastAPI read/assessment routes;
- source isolation and sanitized connector errors;
- offline tests and Python 3.12 CI.

The V0.1 score remains the **match score**:

```text
mandatory/core skill fit   40%
role/domain fit            20%
verified evidence fit      20%
location/remote fit        10%
freshness                  10%
```

V0.2A must not silently change V0.1 results when no new enrichment is available. Regression fixtures lock this behavior.

## 3. Scope

V0.2A includes:

1. multi-source radar orchestration over the existing connectors;
2. structured requirement extraction with provenance;
3. approved skill aliases and taxonomy-assisted normalization;
4. a minimal backward-compatible candidate eligibility-constraints contract;
5. eligibility gates before scoring;
6. V0.1-compatible match scoring with richer normalized inputs;
7. an independent confidence score;
8. decision tiers and priority ranking;
9. a deterministic daily selector capped at 20;
10. a radar API contract;
11. version metadata so decisions remain reproducible.

V0.2A excludes:

- CV generation/rendering;
- cover letters;
- email sending;
- application submission;
- browser/form automation;
- approval workflows;
- Gmail/Calendar integration;
- the full application ledger;
- LinkedIn or Indeed scraping;
- CAPTCHA handling/bypass;
- LLM-owned numeric scoring;
- embeddings/vector databases as a runtime requirement;
- LangChain/LangGraph;
- automatic score-weight learning.

## 4. Research-informed decisions

### 4.1 ESCO

ESCO is used as an external vocabulary for occupations, skills, multilingual labels, and skill↔occupation context. It is suitable for competence-based job matching, but it is **not evidence that the candidate possesses a skill**.

Target first snapshot: ESCO v1.2.1.

References:

- https://esco.ec.europa.eu/en/about-esco/what-esco
- https://esco.ec.europa.eu/en/about-esco/escopedia/escopedia/competence-based-job-matching
- https://esco.ec.europa.eu/en/use-esco/use-esco-services-api/esco-web-service-api

### 4.2 O*NET

O*NET is used as occupational context for skills, knowledge, preparation, tasks, work activities, and related occupations. It helps interpret ambiguous role titles and expected occupational preparation.

Target first snapshot: O*NET 31.0.

Reference:

- https://www.onetcenter.org/database.html

### 4.3 No live taxonomy dependency in scoring

```text
live source / downloadable dataset
        ↓ explicit refresh/build step
versioned local taxonomy snapshot/cache
        ↓
TaxonomyResolver
        ↓
radar scoring
```

A missing taxonomy snapshot degrades safely to exact matching + approved aliases. It never makes the radar unavailable.

CI uses deterministic fixtures and never calls ESCO/O*NET over the network.

### 4.4 ATS submission is outside this slice

Greenhouse application submission requires authenticated employer/job-board access; Lever programmatic apply requires an account API key and is rate limited; Ashby candidate/application writes require write permission. V0.2A therefore does not assume a universal applicant-side submission API.

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
 exact / alias / taxonomy relation
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

Scoring/ranking components are deterministic given explicit inputs. Network access is confined to source ingestion and explicit taxonomy-refresh tooling.

## 6. Preserve `Opportunity`; add companion enrichment

Do **not** overload the existing `Opportunity` storage contract with dozens of nullable V0.2 fields. V0.1 APIs and deduplication already depend on it.

Add a companion model:

```text
Opportunity
  1 ─── 0..N versioned OpportunityEnrichment
```

This separates source normalization from interpretation and allows enrichment to be recomputed when extractors, aliases, or taxonomy versions change.

### 6.1 Provenance model

Every derived field retains its origin.

```text
DerivedValue[T]
- value
- source_text optional
- source_field
- extraction_method
- confidence 0..1
```

`source_text` may be absent only when the source is already a structured field; `source_field` and `extraction_method` remain mandatory.

Examples of `source_field`:

```text
title
description
required_skills
preferred_skills
location
remote_policy
source_metadata
```

Examples of `extraction_method`:

```text
source_structured
explicit_rule
approved_alias
taxonomy_snapshot
manual_override
```

A derived fact without provenance is invalid.

### 6.2 Minimal candidate eligibility constraints

V0.2A needs explicit candidate facts for hard gates, but the full V0.2 profile redesign belongs to V0.2B. Therefore extend `CandidateProfile` only with optional/defaulted fields required by radar eligibility:

```text
target_role_families[]
verified_licenses[]
work_authorizations[]
no_go_constraints[]
relocation_preferences[]
```

Rules:

- all fields default to empty lists so existing V0.1 YAML remains valid;
- empty means unknown/not configured, never incompatible;
- personal values remain in `profile.local.yaml`, which stays gitignored;
- the public example uses fictional/empty values;
- no protected/sensitive self-identification fields are added;
- a legal/work-authorization gate can only use an explicitly stored verified value.

The full master-facts/evidence-module profile remains V0.2B scope.

## 7. Enrichment contract

`OpportunityEnrichment` contains interpreted/derived information:

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
conceptual       # related competency may partially support it
exact_product    # named tool/product cannot be silently substituted
declarative      # legal/credential statement; never inferred by similarity
```

## 8. Requirement extraction

Public interface:

```python
class RequirementExtractor(Protocol):
    def extract(self, opportunity: Opportunity) -> OpportunityEnrichment: ...
```

First implementation is deterministic/rule-based and consumes:

- existing structured `Opportunity` fields;
- title;
- description;
- location/remote metadata.

Initial explicit cues include English and Spanish forms such as:

```text
required / must / mandatory / minimum
preferred / nice to have / bonus
requerido / obligatorio / excluyente / mínimo
preferido / deseable / será un plus
```

The extractor may segment text into sentences/bullets, but each derived requirement retains its supporting span when it comes from free text.

Ambiguous wording remains `unknown`; the extractor must not promote it to mandatory merely to increase structure.

An optional future LLM extractor may implement the same interface, but V0.2A correctness cannot depend on it.

## 9. Skill normalization and taxonomy

### 9.1 Match levels

```text
EXACT_VERIFIED       1.00
APPROVED_ALIAS       1.00
TAXONOMY_RELATED     0.70
SEMANTIC_CANDIDATE   0.40   # reserved for later suggestions
UNKNOWN              0.00
```

V0.2A implements exact, approved alias, taxonomy-related, and unknown. `SEMANTIC_CANDIDATE` is reserved and not required for done.

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

Only `relationship=equivalence` can produce `APPROVED_ALIAS = 1.00`.

Examples:

```text
postgres -> PostgreSQL        equivalence
js -> JavaScript              equivalence
spatial database -> PostGIS   related, not equivalence
```

No automatically suggested alias becomes authoritative without being added to the registry.

### 9.3 Taxonomy resolver

```python
class TaxonomyResolver(Protocol):
    def resolve_skill(self, term: str) -> ResolvedSkill: ...
    def resolve_role(self, title: str) -> ResolvedRole: ...
```

Runtime resolution reads local snapshots/cache. Live network clients, if added for refresh tooling, stay outside scoring services.

### 9.4 Exact-product rule

A taxonomy relation never silently satisfies an explicitly named mandatory product/tool.

Example:

```text
Requirement: "PostGIS required"
Candidate evidence: generic spatial databases
Taxonomy relation: related

Result:
- nearby evidence may be shown;
- mandatory PostGIS gap remains;
- no full mandatory credit.
```

## 10. Eligibility gates

Eligibility runs before match scoring.

```text
EligibilityResult
- eligible
- hard_fail_reasons[]
- soft_risks[]
- unknowns[]
```

Hard fail requires explicit evidence of incompatibility. Unknown is never a hard fail.

Initial hard-fail policies:

- posting known to be closed/unlisted/non-public;
- explicit on-site/location requirement incompatible with configured candidate constraints;
- explicit work-authorization condition contradicted by verified local profile data;
- mandatory license/certification explicitly required and verified absent;
- explicit schedule/work pattern matching a configured `no_go` constraint;
- role family explicitly outside non-empty configured target families;
- another mandatory condition explicitly contradicted by a verified candidate fact.

Unknown legal/work-authorization/location data goes to `unknowns`, lowers confidence when relevant, and never creates an inferred legal answer.

## 11. Match score V0.2A

Keep the public 100-point structure:

| Component | Weight |
| --- | ---: |
| Mandatory/core skill fit | 40 |
| Role/domain fit | 20 |
| Verified evidence fit | 20 |
| Location/remote fit | 10 |
| Freshness | 10 |

### 11.1 Regression rule

With no new enrichment/alias/taxonomy information, the same opportunity/profile/time must produce the current V0.1 assessment.

### 11.2 Mandatory skill fit

Mandatory requirements dominate preferred requirements.

Evidence priority:

```text
exact verified candidate skill
approved equivalent alias
taxonomy-related competency
unknown / absent
```

Preferred requirements may improve context but cannot erase a serious mandatory gap.

### 11.3 Role/domain fit

Role-family normalization may use:

- local role aliases;
- ESCO occupations;
- O*NET occupation context;
- configured internal role families.

Taxonomy context refines interpretation; the actual posting remains authoritative.

### 11.4 Evidence fit

Only `verified=True` evidence can award verified-evidence credit. Every evidence-backed strength points to a real evidence item; the matcher never manufactures a claim.

### 11.5 Location

Explicit incompatibility may already fail eligibility. Otherwise location remains a scored factor for remote/location/relocation preferences.

### 11.6 Freshness

Retain the V0.1 age curve:

```text
<= 7 days    100
<= 30 days    75
unknown       50
<= 90 days    25
> 90 days      0
```

Also expose `source_freshness_quality` so direct ATS timestamps and delayed/indirect sources are distinguishable in explanations.

## 12. Confidence score

`confidence_score` measures trust in the assessment inputs, not job fit.

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
- source incompleteness cannot fabricate negative fit;
- verified provenance improves confidence;
- taxonomy coverage may improve normalization confidence but cannot prove candidate experience;
- API/model returns the full component breakdown.

## 13. Decision tiers

Defaults are configuration:

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

Only HIGH and MEDIUM can enter the daily batch.

Threshold configuration is serialized in batch metadata.

## 14. Priority score

Match and priority remain separate.

Default formula:

```text
priority_score =
    0.80 * match_score
  + 0.20 * confidence_score
  - ranking_penalties
```

Ranking penalties are limited to properties of the opportunity/source itself, for example:

- indirect/stale copy when a stronger direct ATS source exists;
- unresolved probable duplicate where deduplication cannot prove identity.

Every penalty is numeric and explained.

**Do not** encode already-applied status, company caps, or cooldown as ranking penalties. Those are selector constraints and exclusions.

No sensitive personal attribute is used as a ranking penalty.

## 15. Candidate universe and daily selector

The radar does not use the existing generic `list(limit=100)` as its universe.

Add a repository read query for radar candidates with an explicit configurable lookback:

```text
candidate_lookback_days = 30  # default
```

Eligibility for the candidate universe:

- use `published_at` when known;
- otherwise use `discovered_at`;
- exclude known terminal/applied statuses supplied by the history/status policy;
- no arbitrary 100-row truncation before ranking.

Pure selection interface:

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
candidate_lookback_days = 30
allowed_tiers = [HIGH, MEDIUM]
```

Selection order:

1. remove ineligible/STRETCH/DISCARD;
2. remove known already-applied requisitions;
3. apply duplicate/company/cooldown constraints from explicit history/policy;
4. HIGH before MEDIUM;
5. within tier sort by:
   - priority desc,
   - match desc,
   - confidence desc,
   - published_at desc with unknown last,
   - opportunity id asc for deterministic ties;
6. stop at `max_items`.

If only 7 survive, return 7.

History is consumed through a small read interface. V0.2A tests selection with history fixtures; the durable auditable application ledger remains V0.2D scope.

If history has no timestamp information, cooldown is not guessed; only known requisition/status exclusions are applied.

## 16. Radar orchestration

```python
RadarService.run(config, profile, now) -> RadarRunResult
```

Responsibilities:

1. run enabled connectors independently;
2. persist/dedupe through the existing opportunity repository;
3. continue when one source fails;
4. collect sanitized source diagnostics;
5. query the full configured radar candidate universe;
6. enrich/assess candidates;
7. build the daily batch.

A source failure never invalidates successful source results.

### 16.1 Source configuration

Use `sources.local.yaml` plus a fictional public example.

Supported V0.2A source types map to existing connectors:

```text
remotive
greenhouse
lever
ashby
```

Greenhouse board tokens, Lever site names, and Ashby board names are public routing identifiers. Any future secret belongs in environment variables, not YAML.

V0.2A does not require Adzuna or another new connector to be done. Additional feeds can be added independently after the radar core is stable.

## 17. Persistence

### 17.1 Existing opportunities

Keep the current `opportunities` table/API behavior stable. Add radar-specific read methods instead of changing `list()` semantics.

### 17.2 Enrichment

Persist enrichment separately and version it.

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

A version tuple identifies reusable enrichment. Changing extractor/alias/taxonomy versions permits recomputation without mutating the source opportunity.

### 17.3 Batch/history persistence

V0.2A may return a computed `DailyRadarBatch`; it is **not** an approval artifact. Immutable Application Packets, approval hashes, and a durable submission ledger belong to later slices.

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
ranking_penalties
scoring_version
extractor_version
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
extractor_version
alias_registry_version
taxonomy_versions
items[]
count
high_count
medium_count
source_diagnostics
```

`profile_fingerprint` is a local non-secret version/hash identifier, not profile contents.

`batch_id` identifies a radar result only; downstream code must not treat it as application approval.

## 19. API surface

Keep all V0.1 routes compatible.

Add one V0.2A endpoint:

```text
POST /api/v1/radar/run
```

It returns the computed `DailyRadarBatch` with each selected item's full `RadarAssessment` and sanitized source diagnostics.

It has no CV/submission side effects.

Failure behavior:

- no candidate profile: `503 Candidate profile unavailable`;
- one/more sources fail but stored/successful candidates exist: successful batch + source diagnostics;
- all enabled sources fail but stored candidates remain inside the lookback: score stored candidates + diagnostics;
- all enabled sources fail and no stored candidates are available: sanitized upstream failure, not ambiguous empty success.

No extra per-opportunity radar endpoint is required in V0.2A; the existing opportunity and assessment routes remain available, and the batch already contains its full assessment snapshot.

## 20. Error handling and degradation

Typed failure categories:

```text
source_unavailable
invalid_source_config
extraction_failed
taxonomy_missing
invalid_enrichment
profile_unavailable
```

Rules:

- raw upstream bodies/secrets never reach API responses;
- source failures are isolated;
- missing taxonomy snapshot is a warning + exact/alias fallback, not fatal;
- malformed enrichment never deletes the source opportunity;
- unknown requirement data lowers confidence;
- no exception converts unknown into incompatibility.

## 21. Versioning and reproducibility

Every radar result records:

```text
scoring_version
extractor_version
alias_registry_version
taxonomy source versions
threshold/policy configuration
profile fingerprint
```

Initial scoring version: `v0.2a.1`.

Changing weights, thresholds, match multipliers, or gate semantics requires a scoring-version change. Alias changes require an alias-registry version/hash change.

## 22. Security and privacy

- personal profile remains local and gitignored;
- public repo ships fictional profile/source examples only;
- no CV exists in V0.2A;
- no portal credentials are stored;
- no LinkedIn/Indeed scraping;
- no submission endpoint;
- no legal/declarative fact is inferred from taxonomy similarity;
- taxonomy refresh uses explicit timeouts and pinned versions;
- offline CI requires no personal data or external network.

## 23. Testing strategy

Tests remain offline and fixture-driven.

### Contract

- strict enrichment/provenance models reject unknown fields;
- derived values without provenance fail;
- timestamps are timezone-aware;
- unknown remains unknown;
- old V0.1 profile YAML still loads with default eligibility fields.

### Extraction

- English mandatory/preferred cues;
- Spanish mandatory/preferred cues;
- structured source skills outrank weaker text inference;
- exact source span is retained;
- ambiguous wording remains `unknown`.

### Resolver

- exact = 1.00;
- approved equivalence alias = 1.00;
- taxonomy relation = 0.70;
- taxonomy relation cannot satisfy exact-product silently;
- missing taxonomy cache falls back safely;
- case/whitespace normalization is stable.

### Eligibility

- explicit hard fail never enters batch;
- empty/unconfigured candidate constraints do not hard fail;
- unknown legal/location information is not a hard fail;
- explicit location conflict blocks;
- verified missing mandatory license blocks;
- configured no-go constraint blocks.

### Match regression

- V0.1 fixtures preserve scores without enrichment;
- unverified evidence never receives verified credit;
- approved alias can satisfy equivalent skill;
- related skill remains partial/nearby evidence;
- freshness curve remains unchanged.

### Confidence

- missing/ambiguous extraction lowers confidence;
- source incompleteness lowers confidence without lowering match automatically;
- better provenance raises confidence;
- component total is deterministic.

### Candidate query/ranking/selector

- radar query is not capped by the legacy 100-row `list()` default;
- items outside lookback are excluded by policy;
- never returns more than 20;
- never fills with STRETCH;
- 7 valid items returns 7;
- HIGH precedes MEDIUM;
- max two per company by default;
- same requisition never appears twice;
- known applied history is excluded;
- cooldown is only applied from explicit timestamped history;
- ordering is deterministic under ties.

### Orchestration/API

- one connector failure does not suppress successful sources;
- all connector HTTP is mocked;
- source diagnostics are sanitized;
- missing taxonomy does not cause live network fallback;
- all-sources-failed behavior distinguishes stored-candidate fallback from true no-data failure;
- `POST /api/v1/radar/run` has no write side effects outside opportunity/enrichment persistence.

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
│   ├── opportunities.py    # existing contract stable
│   └── enrichments.py
└── api/
    └── routes.py

sources/
└── example_sources.yaml

profiles/
└── example_profile.yaml    # backward-compatible defaulted fields

local/ignored taxonomy cache or generated snapshots
+ small deterministic test fixtures
```

Exact filenames may change in the implementation plan if a smaller boundary is clearer; responsibilities may not be collapsed into one large service.

## 25. Definition of V0.2A done

V0.2A is complete when a developer can:

1. configure one or more existing supported public sources;
2. run one radar operation;
3. ingest/dedupe with connector isolation;
4. extract structured requirements in English/Spanish with provenance;
5. normalize skills through exact, approved aliases, and optional local taxonomy snapshots;
6. evaluate explicit hard eligibility constraints using only configured/verified candidate facts;
7. retain the V0.1 100-point match contract;
8. receive independent confidence + component breakdown;
9. classify HIGH/MEDIUM/STRETCH/DISCARD;
10. rank with explicit opportunity/source penalties;
11. query a configured lookback without arbitrary pre-ranking truncation;
12. receive no more than 20 HIGH/MEDIUM opportunities and never pad with lower-quality items;
13. see evidence, mandatory matches/gaps, risks, unknowns, source diagnostics, and version metadata;
14. run the complete suite offline;
15. pass CI from a clean Python 3.12 install;
16. do all of the above without generating or sending a CV/application.

## 26. Design constraints

- evidence before inference;
- unknown is not false;
- hard constraints cannot be averaged away;
- match and confidence are separate;
- match and priority are separate;
- selection constraints are not ranking penalties;
- taxonomies interpret vocabulary, not candidate truth;
- deterministic core before optional AI enrichment;
- no live taxonomy dependency during scoring;
- no hidden side effects;
- explicit schemas + provenance;
- preserve V0.1 API/storage behavior where practical;
- simplest correct implementation first.

## 27. Follow-on slices

After V0.2A is stable:

- **V0.2B — CV Factory:** master facts, evidence modules, structured CV model, rendering, immutable application packet.
- **V0.2C — Approval + Submission:** batch approval, direct email/authorized channels, form assist/manual fallback, idempotent submission.
- **V0.2D — Learning Loop:** durable application ledger, follow-up, response/interview metrics, explicit score calibration reports.

None of those capabilities should leak into V0.2A merely to make the demo look more complete.
