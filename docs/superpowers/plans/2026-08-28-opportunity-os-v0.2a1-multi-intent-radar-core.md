# Opportunity OS V0.2A1 Multi-Intent Radar Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn V0.1 into a deterministic multi-source daily radar that scores active opportunities for both career fit and near-term income viability, measures confidence independently, and returns at most 20 strong candidates without sending applications.

**Architecture:** Preserve the V0.1 `Opportunity` storage/API contract and its 40/20/20/10/10 career matcher. Add a separate `app/radar` boundary for requirement enrichment, candidate tracks, skill resolution, eligibility, income viability, confidence, ranking, source orchestration, and daily selection. External taxonomies are optional local snapshots; runtime scoring and CI never depend on live ESCO/O*NET.

**Tech Stack:** Python >=3.12, FastAPI, Pydantic v2, httpx, PyYAML, stdlib sqlite3, pytest + pytest-asyncio, Uvicorn. No new runtime framework is required.

**Spec:**
- `docs/superpowers/specs/2026-08-28-opportunity-os-v0.2a-intelligent-radar-design.md`
- `docs/superpowers/specs/2026-08-28-opportunity-os-v0.2a-multi-intent-amendment.md`

## Global Constraints

- Preserve all V0.1 routes and the existing `Opportunity` table behavior.
- Existing V0.1 assessment output must remain identical for the same opportunity/profile/time when no V0.2 enrichment is used.
- Career score weights remain 40% mandatory/core skills, 20% role/domain, 20% verified evidence, 10% location/remote, 10% freshness.
- Add independent `income_viability` weights: 35% verified capability, 25% logistics/location, 15% schedule/work-mode, 15% entry-friction/formal barriers, 10% freshness/deadline.
- `confidence_score` is independent from career/income fit. Missing data lowers confidence; it does not become a negative fact by default.
- `unknown != false`; hard fail requires explicit evidence of incompatibility.
- A role outside preferred career families is not a hard fail.
- Runtime scoring must work with no ESCO/O*NET snapshot; fallback is exact + approved local aliases.
- CI and unit tests perform no live job-board or taxonomy HTTP requests.
- Radar capacity defaults to 20; it never pads with weak candidates to hit 20.
- Default company cap is 2 selected active postings per company per run.
- Default candidate lookback is 30 days; do not use the legacy `list(limit=100)` as the pre-ranking universe.
- LinkedIn/Indeed scraping, browser automation, CAPTCHA bypass, CV generation, email sending, recruiter outreach, and legal/declarative inference remain outside V0.2A1.
- Personal profile/source configuration stays local and gitignored; public examples are fictional.
- Every feature follows TDD: focused failing test, verify red, minimal implementation, focused green, full-suite green, commit.

---

## File map

- `app/models/domain.py` — extend `CandidateProfile` backward-compatibly and define `CandidateTrack`/intent types; keep V0.1 domain models stable.
- `app/radar/__init__.py` — radar package marker only.
- `app/radar/models.py` — strict provenance, requirement, enrichment, eligibility, track assessment, confidence, ranking and batch contracts.
- `app/radar/profile.py` — turn a legacy root profile into an implicit track and select CAREER/INCOME_NOW tracks.
- `app/radar/extractor.py` — deterministic ES/EN requirement extraction with supporting text provenance.
- `app/radar/taxonomy.py` — approved alias registry + optional local taxonomy snapshot resolver; no live runtime HTTP.
- `app/radar/eligibility.py` — factual hard gates and unknown/soft-risk classification.
- `app/radar/scoring.py` — V0.1-compatible career assessment adapter + deterministic income viability.
- `app/radar/confidence.py` — independent deterministic confidence calculation.
- `app/radar/ranking.py` — per-intent tiers, priority and explicit source/opportunity penalties.
- `app/radar/selector.py` — deterministic max-20 selection, company caps, duplicate/history exclusions.
- `app/radar/sources.py` — strict source YAML contracts and connector factory for existing Remotive/Greenhouse/Lever/Ashby adapters.
- `app/radar/service.py` — multi-source orchestration and failure isolation.
- `app/repositories/opportunities.py` — add radar candidate lookback query only; preserve existing methods.
- `app/repositories/enrichments.py` — versioned SQLite enrichment persistence.
- `app/api/routes.py` — add manual import and radar-run endpoints without changing V0.1 responses.
- `app/main.py` — compose radar dependencies; preserve test injection style.
- `sources/example_sources.yaml` — fictional public source registry.
- `data/skill_aliases.yaml` — small public, reviewed equivalence/related registry.
- `.env.example` / `.gitignore` — local source/taxonomy paths; never secrets.
- `tests/test_radar_*.py` — focused contract/extraction/resolver/eligibility/scoring/ranking/selector/service/API tests.

---

### Task 1: Backward-compatible candidate tracks and radar contracts

**Files:**
- Modify: `app/models/domain.py`
- Create: `app/radar/__init__.py`
- Create: `app/radar/models.py`
- Create: `app/radar/profile.py`
- Modify: `profiles/example_profile.yaml`
- Modify: `tests/test_domain_models.py`
- Modify: `tests/test_profiles.py`
- Create: `tests/test_radar_profile.py`

**Interfaces:**
- Produces: `SearchIntent = Literal["CAREER", "INCOME_NOW"]`
- Produces: `CandidateTrack`
- Produces: optional/defaulted profile fields `tracks`, `target_role_families`, `verified_licenses`, `work_authorizations`, `no_go_constraints`, `relocation_preferences`.
- Produces: `effective_tracks(profile: CandidateProfile) -> list[CandidateTrack]`
- Produces strict radar models: `DerivedValue`, `Requirement`, `OpportunityEnrichment`, `EligibilityResult`, `IncomeAssessment`, `ConfidenceAssessment`, `RadarAssessment`, `DailyRadarBatch`.

- [ ] **Step 1: Write failing legacy-profile compatibility tests**

```python
def test_old_v01_profile_yaml_still_loads_without_tracks(tmp_path) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text(
        """
name: Example Candidate
roles: [GIS Developer]
skills: [python, postgis]
domains: [gis]
locations: [Argentina]
remote_preferences: [remote]
evidence: []
""".strip(),
        encoding="utf-8",
    )

    profile = load_profile(path)
    assert profile.tracks == []
    assert profile.no_go_constraints == []
```

Also assert the existing V0.1 `test_profile_requires_a_name_and_skills` remains green.

- [ ] **Step 2: Run focused tests and verify red**

Run: `python -m pytest tests/test_profiles.py tests/test_domain_models.py -v`

Expected: FAIL because the new defaulted fields do not exist.

- [ ] **Step 3: Add strict candidate-track models with safe defaults**

Add to `app/models/domain.py`:

```python
SearchIntent = Literal["CAREER", "INCOME_NOW"]


class CandidateTrack(StrictModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    intents: list[SearchIntent] = Field(min_length=1)
    roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    accepted_work_modes: list[str] = Field(default_factory=list)
    no_go_constraints: list[str] = Field(default_factory=list)
```

Extend `CandidateProfile` only with defaulted fields so existing YAML stays valid:

```python
tracks: list[CandidateTrack] = Field(default_factory=list)
target_role_families: list[str] = Field(default_factory=list)
verified_licenses: list[str] = Field(default_factory=list)
work_authorizations: list[str] = Field(default_factory=list)
no_go_constraints: list[str] = Field(default_factory=list)
relocation_preferences: list[str] = Field(default_factory=list)
```

Do not add personal contact data to this public model.

- [ ] **Step 4: Write failing implicit-track tests**

```python
def test_legacy_profile_becomes_one_default_track() -> None:
    profile = CandidateProfile(name="Example", roles=["GIS Developer"], skills=["python"])
    tracks = effective_tracks(profile)

    assert len(tracks) == 1
    assert tracks[0].id == "default"
    assert tracks[0].intents == ["CAREER", "INCOME_NOW"]
    assert tracks[0].skills == ["python"]
```

Also test an explicit `gastronomy_operations` INCOME_NOW track does not inherit tech skills from the root track.

- [ ] **Step 5: Implement `effective_tracks`**

```python
def effective_tracks(profile: CandidateProfile) -> list[CandidateTrack]:
    if profile.tracks:
        return profile.tracks
    return [
        CandidateTrack(
            id="default",
            label="Default",
            intents=["CAREER", "INCOME_NOW"],
            roles=profile.roles,
            skills=profile.skills,
            domains=profile.domains,
            evidence=profile.evidence,
            accepted_work_modes=profile.remote_preferences,
            no_go_constraints=profile.no_go_constraints,
        )
    ]
```

- [ ] **Step 6: Add strict radar value/provenance contracts**

In `app/radar/models.py`, use `ConfigDict(extra="forbid")` for every model. A derived free-text value requires `source_field`, `extraction_method`, `confidence` and either a supporting `source_text` or an explicitly structured source field. All datetimes must be timezone-aware.

Core enums/literals:

```text
RequirementKind: skill | experience | education | license | work_authorization | location | schedule | language | other
Importance: mandatory | preferred | unknown
Exactness: conceptual | exact_product | declarative
Tier: HIGH | MEDIUM | STRETCH | DISCARD
```

- [ ] **Step 7: Update the fictional example profile and run full suite**

Keep existing root fields. Add only fictional optional examples such as an empty `tracks: []`; do not encode the real candidate profile.

Run: `python -m pytest -v`

Expected: all existing 36 tests plus new tests PASS.

Commit: `feat: add multi-intent candidate tracks and radar contracts`

---

### Task 2: Deterministic ES/EN requirement extraction with provenance

**Files:**
- Create: `app/radar/extractor.py`
- Create: `tests/test_radar_extractor.py`
- Create: `tests/fixtures/radar_requirement_cases.yaml`

**Interfaces:**
- Consumes: `Opportunity`
- Produces protocol: `RequirementExtractor.extract(opportunity: Opportunity) -> OpportunityEnrichment`
- Produces: `RuleBasedRequirementExtractor`

- [ ] **Step 1: Commit bilingual fixture cases and failing tests**

Fixture cases must include at least:

```yaml
- title: Python Developer
  description: "Required: Python and SQL. Nice to have: Docker."
  expected:
    - {kind: skill, value: Python, importance: mandatory}
    - {kind: skill, value: SQL, importance: mandatory}
    - {kind: skill, value: Docker, importance: preferred}

- title: Analista GIS
  description: "Python excluyente. PostGIS deseable. Inglés será un plus."
  expected:
    - {kind: skill, value: Python, importance: mandatory}
    - {kind: skill, value: PostGIS, importance: preferred}
```

Tests must assert each free-text requirement preserves the exact supporting sentence/span in `provenance.source_text`.

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_radar_extractor.py -v`

Expected: FAIL because the extractor does not exist.

- [ ] **Step 3: Implement structured-source extraction first**

Convert existing `Opportunity.required_skills` into mandatory skill requirements with:

```text
source_field=required_skills
extraction_method=source_structured
confidence=1.0
```

Convert `preferred_skills` similarly with `importance=preferred`.

- [ ] **Step 4: Implement conservative cue-based sentence extraction**

Recognize only explicit cues:

```python
MANDATORY_CUES = ("required", "must", "mandatory", "minimum", "requerido", "obligatorio", "excluyente", "mínimo")
PREFERRED_CUES = ("preferred", "nice to have", "bonus", "preferido", "deseable", "será un plus", "sera un plus")
```

Use deterministic sentence/bullet splitting. Do not promote ambiguous statements to mandatory. If parsing cannot isolate a requirement safely, leave it as `unknown` or omit it and let confidence reflect missing structure.

- [ ] **Step 5: Add basic enrichment facts with provenance**

Populate only facts that can be derived safely in this task: normalized title string, explicit remote/location hints, language cues, explicit salary text when parseable, and explicit application deadline when parseable. Do not infer work authorization or legal status from geography.

- [ ] **Step 6: Run focused/full tests and commit**

Run: `python -m pytest tests/test_radar_extractor.py -v` then `python -m pytest -v`.

Commit: `feat: extract structured job requirements with provenance`

---

### Task 3: Approved aliases and optional local taxonomy snapshots

**Files:**
- Create: `app/radar/taxonomy.py`
- Create: `data/skill_aliases.yaml`
- Create: `tests/fixtures/taxonomy_snapshot.json`
- Create: `tests/test_radar_taxonomy.py`
- Modify: `.gitignore`
- Modify: `.env.example`

**Interfaces:**
- Produces: `SkillMatchLevel = EXACT_VERIFIED | APPROVED_ALIAS | TAXONOMY_RELATED | UNKNOWN`
- Produces: `ResolvedSkill`
- Produces: `AliasRegistry.load(path) -> AliasRegistry`
- Produces: `TaxonomyResolver.resolve_skill(term: str, candidate_skills: list[str]) -> ResolvedSkill`
- Produces optional `LocalTaxonomySnapshot` loaded from a file path; no runtime network client.

- [ ] **Step 1: Write failing resolution tests**

```python
def test_approved_equivalence_scores_as_exact(alias_registry) -> None:
    result = resolver(alias_registry).resolve_skill("postgres", ["PostgreSQL"])
    assert result.level == "APPROVED_ALIAS"
    assert result.multiplier == 1.0


def test_related_term_is_not_silent_equivalence(alias_registry) -> None:
    result = resolver(alias_registry).resolve_skill("spatial database", ["PostGIS"])
    assert result.level == "TAXONOMY_RELATED"
    assert result.multiplier == 0.70
```

Also test missing taxonomy snapshot still resolves exact/alias cases and never makes construction fail.

- [ ] **Step 2: Add reviewed public alias registry**

`data/skill_aliases.yaml` starts small:

```yaml
version: "1"
entries:
  - canonical_skill: PostgreSQL
    aliases: [postgres]
    relationship: equivalence
    confidence: 1.0
    approved_by: maintainers
  - canonical_skill: JavaScript
    aliases: [js]
    relationship: equivalence
    confidence: 1.0
    approved_by: maintainers
  - canonical_skill: PostGIS
    aliases: [spatial database]
    relationship: related
    confidence: 0.7
    approved_by: maintainers
```

Do not add questionable equivalences simply to improve scores.

- [ ] **Step 3: Implement resolver precedence**

Exact normalized candidate skill → approved equivalence → local taxonomy/related registry → UNKNOWN. `exact_product` mandatory requirements only accept exact/equivalence for full satisfaction; related competency remains partial evidence.

- [ ] **Step 4: Add optional local taxonomy path**

`.env.example`:

```text
OPPORTUNITY_TAXONOMY_PATH=
OPPORTUNITY_ALIAS_REGISTRY_PATH=data/skill_aliases.yaml
```

`.gitignore`:

```text
taxonomy.local.json
data/taxonomy/*.local.json
```

Do not add ESCO/O*NET as new live runtime dependencies.

- [ ] **Step 5: Run focused/full tests and commit**

Commit: `feat: add approved skill aliases and offline taxonomy resolution`

---

### Task 4: Factual eligibility gates

**Files:**
- Create: `app/radar/eligibility.py`
- Create: `tests/test_radar_eligibility.py`

**Interfaces:**
- Consumes: `Opportunity`, `OpportunityEnrichment`, `CandidateProfile`, `CandidateTrack`
- Produces: `evaluate_eligibility(...) -> EligibilityResult`

- [ ] **Step 1: Write failing gate tests**

Cover these exact behaviors:

```python
def test_role_outside_target_family_is_not_a_hard_fail(): ...
def test_unknown_work_authorization_is_not_a_hard_fail(): ...
def test_explicit_incompatible_location_is_a_hard_fail(): ...
def test_verified_missing_mandatory_license_is_a_hard_fail(): ...
def test_configured_no_go_schedule_is_a_hard_fail(): ...
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_radar_eligibility.py -v`.

- [ ] **Step 3: Implement gates from explicit facts only**

Hard-fail reasons are stable machine-readable codes plus human explanation, e.g.:

```text
posting_closed
location_incompatible
work_authorization_incompatible
mandatory_license_missing
schedule_no_go
verified_mandatory_condition_conflict
```

If candidate data is absent/unconfigured, append to `unknowns`; never fabricate incompatibility.

- [ ] **Step 4: Run focused/full tests and commit**

Commit: `feat: add explicit opportunity eligibility gates`

---

### Task 5: Career assessment adapter and independent income-now viability

**Files:**
- Create: `app/radar/scoring.py`
- Modify carefully: `app/matching/scorer.py` only if a small reusable helper is necessary; do not change V0.1 public behavior.
- Create: `tests/test_radar_scoring.py`
- Modify: `tests/test_matching.py` only to add regression fixtures if needed.

**Interfaces:**
- Produces: `assess_career(opportunity, enrichment, profile, track, resolver, *, now) -> OpportunityAssessment`
- Produces: `assess_income(opportunity, enrichment, profile, track, resolver, *, now) -> IncomeAssessment`
- Produces: `best_track_assessments(...) -> tuple[TrackCareerAssessment | None, TrackIncomeAssessment | None]`

- [ ] **Step 1: Lock V0.1 regression before touching scorer code**

Add a test that calls current `assess_opportunity` with a fixed opportunity/profile/NOW and asserts the complete `OpportunityAssessment.model_dump()` equals a committed expected dict. Run it and commit the fixture in the same task before refactoring.

- [ ] **Step 2: Write failing track-isolation tests**

A profile with `tech_geospatial` and `gastronomy_operations` tracks must not receive Python/PostGIS career credit from the gastronomy track, and a kitchen/operations opportunity must be able to score high on INCOME_NOW without receiving a high tech career score.

- [ ] **Step 3: Implement enriched career adapter without changing weights**

Create a copy of the source opportunity for scoring only:

```python
def _opportunity_for_career_score(opportunity, enrichment, resolver, track):
    return opportunity.model_copy(
        update={
            "required_skills": resolved_mandatory_skill_terms(enrichment, resolver, track),
            "preferred_skills": resolved_preferred_skill_terms(enrichment, resolver, track),
        }
    )
```

Create a track-scoped `CandidateProfile` copy using only that track's roles/skills/domains/evidence while preserving root location/remote constraints. Then call the existing V0.1 scorer. If enrichment provides no usable new requirements, pass the original opportunity unchanged so regression stays exact.

- [ ] **Step 4: Write failing income-score component tests**

Use the exact formula:

```text
income_viability =
  0.35 * capability_fit
+ 0.25 * logistics_fit
+ 0.15 * schedule_fit
+ 0.15 * entry_friction_fit
+ 0.10 * freshness_fit
```

Component rules:

- `capability_fit`: mandatory skill/experience requirement satisfaction ratio; if no mandatory capability requirements, preferred ratio; if no capability requirements at all, neutral 50.
- `logistics_fit`: 100 explicit compatible remote/location, 50 unknown, 0 explicit incompatibility (normally already gated).
- `schedule_fit`: 100 explicit compatible, 50 unknown, 0 explicit configured no-go (normally gated).
- `entry_friction_fit`: mean of observable barrier statuses for mandatory license/education/experience/declarative requirements: satisfied=100, unknown=50, contradicted=0. If no barrier requirements, 100.
- `freshness_fit`: reuse the current V0.1 freshness curve; if an explicit future application deadline exists, do not lower freshness below the publication-based result solely because the deadline is unknown.

- [ ] **Step 5: Implement income assessment with full breakdown**

Return matched capability, gaps, unknown barriers and selected track id. Never award capability from unverified evidence or another track.

- [ ] **Step 6: Select best track per intent deterministically**

For CAREER, choose the eligible CAREER track with highest career `overall_score`, tie-break by track id. For INCOME_NOW, choose highest `income_viability`, tie-break by track id. If no track supports an intent, return `None` for that lane rather than synthesizing one.

- [ ] **Step 7: Run V0.1 regression + radar tests + full suite**

Run:

```bash
python -m pytest tests/test_matching.py tests/test_radar_scoring.py -v
python -m pytest -v
```

Commit: `feat: add multi-intent career and income scoring`

---

### Task 6: Independent confidence, tiers and priority ranking

**Files:**
- Create: `app/radar/confidence.py`
- Create: `app/radar/ranking.py`
- Create: `tests/test_radar_confidence.py`
- Create: `tests/test_radar_ranking.py`

**Interfaces:**
- Produces: `score_confidence(enrichment, career, income) -> ConfidenceAssessment`
- Produces: `classify_fit(score: float | None, confidence: float, policy: RadarPolicy) -> Tier | None`
- Produces: `rank_assessment(...) -> RadarAssessment`

- [ ] **Step 1: Write failing confidence tests**

Assert:

- missing/ambiguous extraction lowers confidence but leaves the underlying fit score unchanged;
- stronger provenance raises extraction confidence;
- missing taxonomy snapshot does not cause a fatal error;
- the component weighted sum is deterministic.

- [ ] **Step 2: Implement exact confidence weights**

```text
requirement extraction quality   25
skill normalization coverage     20
evidence traceability            20
seniority/location/legal clarity 20
source/freshness completeness    15
```

Each component is 0..100 and returned in the model. Use neutral 50 for genuinely non-applicable/unknown categories rather than pretending full certainty.

- [ ] **Step 3: Write failing tier tests for both intents**

Use the same configurable default fit/confidence thresholds per lane:

```text
HIGH:   fit >= 78 and confidence >= 75
MEDIUM: fit >= 65 and confidence >= 65
STRETCH: fit >= 55 but does not meet MEDIUM
DISCARD: fit < 55 or hard fail
```

Career and income lane tiers are stored separately. This keeps the rule simple and makes later calibration explicit/versioned.

- [ ] **Step 4: Implement per-lane priority and winning intent**

```python
lane_priority = 0.80 * fit_score + 0.20 * confidence_score
```

After opportunity/source penalties, choose the higher qualifying lane as `selected_intent`. A low career score must not suppress a high income lane. Return both lane scores and both tiers in `RadarAssessment`.

Allowed ranking penalties in A1: direct-source preference over stale/indirect duplicate and unresolved probable duplicate. Already-applied/company-cap/cooldown are selector rules, not penalties.

- [ ] **Step 5: Run focused/full tests and commit**

Commit: `feat: add confidence tiers and multi-intent priority ranking`

---

### Task 7: Versioned enrichment storage and full radar candidate query

**Files:**
- Create: `app/repositories/enrichments.py`
- Modify: `app/repositories/opportunities.py`
- Create: `tests/test_enrichment_repository.py`
- Modify: `tests/test_repository.py`

**Interfaces:**
- Produces: `SQLiteEnrichmentRepository`
- Produces: `save(enrichment, *, extractor_version, alias_registry_version, taxonomy_versions) -> None`
- Produces: `get_current(opportunity_id, version_tuple) -> OpportunityEnrichment | None`
- Produces: `SQLiteOpportunityRepository.list_radar_candidates(*, now: datetime, lookback_days: int) -> list[Opportunity]`

- [ ] **Step 1: Write failing versioned-enrichment tests**

Persist enrichment v1, then enrichment v2 for the same opportunity with a different extractor/alias version. Assert both rows are independently retrievable and the original `opportunities` row is unchanged.

- [ ] **Step 2: Implement enrichment table**

Use a separate table with JSON payload and explicit version columns. Unique identity is `(opportunity_id, extractor_version, alias_registry_version, taxonomy_versions_json)`.

- [ ] **Step 3: Write failing lookback-query tests**

Seed >100 opportunities to prove the radar query is not truncated by `list(limit=100)`. Known `published_at` controls age; otherwise use `discovered_at`. Default lookback test is 30 days.

- [ ] **Step 4: Implement `list_radar_candidates`**

Query SQLite directly by date fields and return all rows inside lookback in stable order. Do not alter existing `list()` semantics.

- [ ] **Step 5: Run focused/full tests and commit**

Commit: `feat: persist radar enrichment and query full candidate window`

---

### Task 8: Deterministic selector and history exclusions

**Files:**
- Create: `app/radar/selector.py`
- Create: `tests/test_radar_selector.py`

**Interfaces:**
- Produces: `RadarPolicy`
- Produces protocol: `ApplicationHistory.was_applied(opportunity: Opportunity) -> bool`
- Produces protocol: `ApplicationHistory.last_company_role_contact_at(company: str, title: str) -> datetime | None`
- Produces: `select_daily_batch(ranked_items, policy, history, *, now) -> DailyRadarBatch`

- [ ] **Step 1: Write failing selection invariants**

Tests must prove:

```text
21 qualified -> exactly 20
7 qualified -> exactly 7
STRETCH never pads the batch
known applied requisition is excluded
same requisition never appears twice
max 2/company by default
HIGH precedes MEDIUM within the winning lane
ordering is deterministic under ties
```

Use an in-memory fake history; durable ledger belongs to V0.2D.

- [ ] **Step 2: Implement stable selection key**

For qualifying candidates use:

```text
best tier rank (HIGH before MEDIUM)
priority desc
winning fit desc
confidence desc
published_at desc, unknown last
opportunity id asc
```

Apply company/history/cooldown exclusions before appending each item. If history lacks timestamps, do not invent cooldown information.

- [ ] **Step 3: Add batch metadata**

`DailyRadarBatch` records generated_at, policy, profile fingerprint, scoring/extractor/alias/taxonomy versions, selected counts by intent/tier and item list. `batch_id` identifies radar output only; it is not an approval token.

- [ ] **Step 4: Run focused/full tests and commit**

Commit: `feat: select deterministic daily opportunity batches`

---

### Task 9: Source registry, multi-source orchestration and generic manual import

**Files:**
- Create: `app/radar/sources.py`
- Create: `app/radar/service.py`
- Create: `sources/example_sources.yaml`
- Create: `tests/test_radar_sources.py`
- Create: `tests/test_radar_service.py`
- Modify: `.gitignore`
- Modify: `.env.example`

**Interfaces:**
- Produces strict source config union for `remotive`, `greenhouse`, `lever`, `ashby`.
- Produces: `load_source_config(path) -> SourceRegistry`
- Produces: `build_connectors(registry, client, timeout_seconds) -> list[ConfiguredConnector]`
- Produces: `RadarService.run(profile, *, now) -> DailyRadarBatch`
- Produces: `ManualOpportunityInput.to_opportunity(now) -> Opportunity` for authorized/manual discoveries.

- [ ] **Step 1: Write failing source-config tests**

Fictional YAML:

```yaml
sources:
  - type: remotive
    enabled: true
  - type: greenhouse
    enabled: true
    company_name: Example GIS Co
    board_token: example-gis
  - type: lever
    enabled: false
    company_name: Example Data Co
    site: example-data
  - type: ashby
    enabled: false
    company_name: Example AI Co
    board_name: example-ai
```

Unknown fields/types must fail strict validation. Public board routing identifiers are allowed; secrets are not part of the schema.

- [ ] **Step 2: Implement connector factory against existing constructors**

Map exactly:

```text
remotive -> RemotiveConnector(client, timeout_seconds=...)
greenhouse -> GreenhouseConnector(client, board_token=..., company_name=..., timeout_seconds=...)
lever -> LeverConnector(client, site=..., company_name=..., timeout_seconds=...)
ashby -> AshbyConnector(client, board_name=..., company_name=..., timeout_seconds=...)
```

- [ ] **Step 3: Write failing orchestration-isolation test**

Configure one successful fake connector and one failing fake connector. Assert successful opportunities are persisted/assessed and the failing source produces only sanitized diagnostics.

- [ ] **Step 4: Implement `RadarService.run`**

Sequence:

```text
run enabled connectors independently
→ persist/dedupe successful opportunities
→ query full lookback candidate universe
→ load/recompute versioned enrichment
→ evaluate best CAREER/INCOME_NOW tracks
→ eligibility + career/income + confidence + rank
→ select max-20 batch
→ attach sanitized source diagnostics
```

If all enabled sources fail but stored candidates exist inside lookback, score stored candidates and return diagnostics. If all fail and there are no candidates, raise a typed public-safe radar source error.

- [ ] **Step 5: Add generic manual opportunity conversion tests**

Required manual fields:

```text
source
source_url
title
company or organization
raw description
optional location
optional published/deadline
```

Manual import is not scraping: the caller supplies data/URL. It must enter the same normalized repository/radar pipeline.

- [ ] **Step 6: Add local config paths**

`.env.example`:

```text
OPPORTUNITY_SOURCES_PATH=sources.local.yaml
```

`.gitignore`:

```text
sources.local.yaml
```

- [ ] **Step 7: Run focused/full tests and commit**

Commit: `feat: orchestrate multi-source radar runs`

---

### Task 10: Radar API, manual-import API, docs and release verification

**Files:**
- Modify: `app/api/routes.py`
- Modify: `app/main.py`
- Create: `tests/test_api_radar.py`
- Create: `tests/test_api_manual_opportunity.py`
- Modify: `README.md`
- Modify: `pyproject.toml` version only when the feature is ready for the V0.2A release decision.

**Interfaces:**
- `POST /api/v1/radar/run -> DailyRadarBatch`
- `POST /api/v1/opportunities/manual -> Opportunity`
- Preserve all V0.1 routes unchanged.

- [ ] **Step 1: Write failing API contract tests**

Test:

```text
no profile -> 503 Candidate profile unavailable
one source fails -> 200 batch + sanitized diagnostic if other/stored candidates exist
all sources fail and no candidates -> 502 public-safe detail
manual import valid -> persisted normalized opportunity
manual import duplicate -> returns existing identity without duplicate row
radar endpoint has no CV/email/submission side effect
```

- [ ] **Step 2: Extend dependency injection cleanly**

Do not make tests depend on environment globals. Extend `create_app(...)` with injectable `radar_service` or `source_registry` dependencies while preserving existing `repository`, `profile`, and `remotive_connector` arguments used by V0.1 tests.

- [ ] **Step 3: Implement routes with explicit Pydantic response models**

Map typed radar/source/config errors to stable sanitized status/details. Never serialize raw upstream bodies or local profile contents.

- [ ] **Step 4: Update README with V0.2A behavior**

Document:

- CAREER vs INCOME_NOW vs CONFIDENCE;
- max 20 is a ceiling, not quota;
- source registry setup;
- manual URL/import fallback;
- no live taxonomy dependency;
- no CV generation or sending yet;
- public/private configuration boundary.

- [ ] **Step 5: Run complete verification**

Run from clean environment:

```bash
python -m pip install -e ".[dev]"
python -m pytest -v
python -m compileall app
```

Expected: all tests PASS, no live network required by tests.

Also run repository hygiene checks appropriate to the environment:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intentional files changed.

- [ ] **Step 6: Security/privacy scan**

Search tracked diff for personal profile/CV filenames, email addresses, tokens/password-like strings, and local source/taxonomy files. The public examples must remain fictional.

- [ ] **Step 7: Commit**

Commit: `feat: expose multi-intent daily radar`

---

## Plan self-review

### Spec coverage

- Enriched opportunity + provenance: Tasks 1–2.
- ES/EN extraction: Task 2.
- Alias/taxonomy fallback: Task 3.
- Factual eligibility: Task 4.
- V0.1 career compatibility: Task 5.
- INCOME_NOW score + track isolation: Task 5.
- Independent confidence: Task 6.
- Tiers/priority: Task 6.
- Full lookback universe/versioned enrichment: Task 7.
- Max-20/history/company-cap selection: Task 8.
- Multi-source isolation: Task 9.
- Manual/import fallback for random sources: Task 9–10.
- API + public-safe degradation: Task 10.
- CV/email/submission explicitly excluded: Global Constraints + Task 10 docs.

### Placeholder scan

The plan contains no `TBD`, `TODO`, “implement later”, or unbounded “add tests” steps. Later slices are named only as scope boundaries.

### Type consistency

`CandidateTrack` and intent types originate in `app/models/domain.py`; radar value/assessment contracts originate in `app/radar/models.py`; subsequent tasks consume those exact types. V0.1 `OpportunityAssessment` remains the career-assessment contract rather than introducing a second incompatible career-score type.

## Handoff to V0.2A2

V0.2A1 deliberately handles **active/manual opportunities** only. Target-company affinity and speculative outreach are implemented by the separate V0.2A2 plan and must consume the same candidate tracks, confidence conventions, version metadata, and selection principles rather than duplicating them.
