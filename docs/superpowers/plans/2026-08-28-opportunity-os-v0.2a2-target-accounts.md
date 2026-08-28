# Opportunity OS V0.2A2 Target Accounts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic target-company radar that can recommend high-affinity organizations for spontaneous candidature even when no active vacancy exists, while preserving provenance, proximity, cooldown and anti-spam rules.

**Architecture:** Build on V0.2A1 candidate tracks and confidence conventions but keep target companies separate from `Opportunity` because an organization without a requisition is not a job posting. Load target-account facts from local/public-safe structured registries, score affinity from explicit signals, rank candidates, and expose a read-only target radar. CV creation, recruiter enrichment, Gmail drafts and sending remain later slices.

**Tech Stack:** Python >=3.12, FastAPI, Pydantic v2, PyYAML, stdlib sqlite3 only if needed for existing repository boundaries, pytest. No new runtime dependency is required.

**Spec:**
- `docs/superpowers/specs/2026-08-28-opportunity-os-v0.2-target-accounts-speculative-outreach-amendment.md`
- `docs/superpowers/specs/2026-08-28-opportunity-os-v0.2a-multi-intent-amendment.md`

**Dependency:** Complete V0.2A1 Task 1 candidate-track contracts before implementing this plan. V0.2A2 consumes `CandidateProfile`, `CandidateTrack`, `SearchIntent`, radar provenance conventions and profile fingerprinting from A1.

## Global Constraints

- An organization without an active vacancy is a `TARGET_ACCOUNT`, not a fake `Opportunity`.
- Never imply a vacancy exists when it does not.
- Target-account score is separate from `career_match`, `income_viability`, and `confidence`.
- Account-affinity weights: capability/sector 30%, proximity/logistics 20%, scale/stability 15%, innovation/AI/digital 15%, contactability/CV channel 10%, current hiring signal 10%.
- Proximity is a coarse private bucket, not a public exact address.
- No automatic geocoding of a personal address in the public core.
- No guessed recruiter email addresses.
- No Apollo credit consumption in V0.2A2 core.
- No email sending, CV generation, form filling or outreach side effect.
- Default spontaneous-outreach cooldown is 30 days per organization; known recent contact suppresses action recommendation.
- Recommend one relevant contact path per organization event; do not design multi-recipient blasting.
- Public example target data is fictional. Real Córdoba targets belong in the private vault/local registry, not hardcoded in the public repository.
- Every fact used for affinity scoring keeps provenance/source reference and observation date.
- Every task is TDD and ends with full-suite green + commit.

---

## File map

- `app/targets/__init__.py` — package marker.
- `app/targets/models.py` — strict target account, signal, assessment, policy and batch contracts.
- `app/targets/registry.py` — load/validate target registries from YAML.
- `app/targets/scoring.py` — deterministic account affinity and best candidate-track association.
- `app/targets/selector.py` — cooldown, target priority and deterministic target batch.
- `app/targets/service.py` — registry → assessments → target batch orchestration.
- `app/api/routes.py` — add read-only target radar endpoint.
- `app/main.py` — compose optional target service/config path.
- `targets/example_targets.yaml` — fictional public examples only.
- `.env.example` / `.gitignore` — `OPPORTUNITY_TARGETS_PATH=targets.local.yaml`; ignore local target registry.
- `tests/test_target_*.py` — contracts, registry, scoring, selector, service and API.

---

### Task 1: Strict target-account and provenance contracts

**Files:**
- Create: `app/targets/__init__.py`
- Create: `app/targets/models.py`
- Create: `tests/test_target_models.py`

**Interfaces:**
- Produces: `TargetMode = Literal["TARGET_ACCOUNT", "SPECULATIVE_OUTREACH"]`
- Produces: `ProximityBucket = Literal["VERY_CLOSE", "CLOSE", "CITY_WIDE", "LONG_COMMUTE", "REMOTE", "UNKNOWN"]`
- Produces: `Contactability = Literal["APPLICATION_EMAIL", "VERIFIED_RECRUITER", "GENERAL_CV", "CAREERS_FORM", "NONE", "UNKNOWN"]`
- Produces: `TargetSignal`, `TargetAccount`, `TargetAccountAssessment`, `TargetAccountPolicy`, `TargetAccountBatch`.

- [ ] **Step 1: Write failing strict-model tests**

```python
def test_target_account_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TargetAccount(
            id="example",
            name="Example Corp",
            sectors=["technology"],
            unknown_private_field="nope",
        )


def test_scoring_signal_requires_provenance() -> None:
    with pytest.raises(ValidationError):
        TargetSignal(label="ai adoption", value=90)
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_target_models.py -v`.

- [ ] **Step 3: Implement contracts**

Use strict Pydantic models. `TargetSignal` minimum contract:

```python
class TargetSignal(StrictTargetModel):
    label: str
    value: float = Field(ge=0, le=100)
    source_url: str | None = None
    source_note: str | None = None
    observed_at: datetime
```

`TargetAccount` contains only organization facts and coarse signals:

```text
id
name
website optional
sectors[]
role_families[]
capability_tags[]
proximity_bucket
scale_stability_signal
innovation_signal
contactability
hiring_signal
application_channel optional
notes optional
```

Every numeric signal is represented by `TargetSignal`, not a bare unexplained number.

- [ ] **Step 4: Implement assessment/batch contracts**

`TargetAccountAssessment` must expose each component score, total affinity, best track id, reasons, risks, cooldown state and recommended action. `TargetAccountBatch` records policy, profile fingerprint, generated_at and ordered items.

- [ ] **Step 5: Run focused/full tests and commit**

Commit: `feat: add target account domain contracts`

---

### Task 2: Public-safe target registry and local configuration

**Files:**
- Create: `app/targets/registry.py`
- Create: `targets/example_targets.yaml`
- Create: `tests/test_target_registry.py`
- Modify: `.env.example`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `load_target_registry(path: str | Path) -> list[TargetAccount]`

- [ ] **Step 1: Write failing registry tests**

Test valid fictional YAML, malformed YAML, unknown fields and a local file containing a private note whose raw contents must not leak in the public-safe `ValueError` message.

- [ ] **Step 2: Add fictional example registry**

Example shape:

```yaml
targets:
  - id: example-industrial
    name: Example Industrial Co
    website: https://example.com
    sectors: [manufacturing]
    role_families: [operations, data]
    capability_tags: [operations, analytics]
    proximity_bucket: CITY_WIDE
    scale_stability_signal:
      label: large established organization
      value: 90
      source_url: https://example.com/about
      observed_at: 2026-08-28T15:00:00Z
    innovation_signal:
      label: public digital transformation program
      value: 80
      source_url: https://example.com/innovation
      observed_at: 2026-08-28T15:00:00Z
    contactability: GENERAL_CV
    hiring_signal:
      label: careers portal available
      value: 50
      source_url: https://example.com/careers
      observed_at: 2026-08-28T15:00:00Z
```

Do not place Coca-Cola, Naranja X, Arcor or any real private research list in this public sample; the real target list stays in the private vault/local file.

- [ ] **Step 3: Implement safe loader**

Mirror `load_profile`: YAML parse → Pydantic validation → safe `ValueError("Invalid target registry: <path>")` without raw YAML contents.

- [ ] **Step 4: Configure local path**

`.env.example`:

```text
OPPORTUNITY_TARGETS_PATH=targets.local.yaml
```

`.gitignore`:

```text
targets.local.yaml
```

- [ ] **Step 5: Run focused/full tests and commit**

Commit: `feat: load public-safe target account registries`

---

### Task 3: Deterministic company affinity scoring

**Files:**
- Create: `app/targets/scoring.py`
- Create: `tests/test_target_scoring.py`

**Interfaces:**
- Consumes: `TargetAccount`, `CandidateProfile`, A1 `effective_tracks(profile)`.
- Produces: `assess_target_account(account, profile, *, now) -> TargetAccountAssessment`.

- [ ] **Step 1: Write failing component-score tests**

Proximity mapping is explicit:

```text
VERY_CLOSE   100
CLOSE         85
CITY_WIDE     65
LONG_COMMUTE  30
REMOTE       100
UNKNOWN       50
```

Contactability mapping is explicit:

```text
APPLICATION_EMAIL   100
VERIFIED_RECRUITER   90
GENERAL_CV           85
CAREERS_FORM         60
UNKNOWN              50
NONE                  20
```

Tests assert these mappings exactly.

- [ ] **Step 2: Write failing candidate-track affinity tests**

Capability/sector component must choose the best compatible track, not merge unrelated track skills. Use:

```text
role-family overlap contribution: 50%
sector/domain/capability-tag overlap contribution: 50%
```

Each subcomponent is an overlap ratio 0..100; if the account provides no usable data for one half, that half is neutral 50 rather than fabricated 0/100.

- [ ] **Step 3: Implement component normalization**

Use account `TargetSignal.value` directly for scale/stability, innovation and hiring components because those values already require provenance. Clamp only through model validation; do not silently rewrite scores.

- [ ] **Step 4: Implement total affinity**

```python
affinity = round(
    0.30 * capability_sector_fit
    + 0.20 * proximity_fit
    + 0.15 * scale_stability
    + 0.15 * innovation
    + 0.10 * contactability_fit
    + 0.10 * hiring_signal,
    1,
)
```

Return all six components and the selected candidate track id. No active vacancy is required for a high target score.

- [ ] **Step 5: Add confidence/risk explanation**

A target account with stale/weak provenance gets an explanation/risk; do not hide missing contact path or outdated evidence behind the total score. Use a simple target-confidence value based on number/freshness of sourced signals; do not reuse job-requirement extraction confidence mechanically.

- [ ] **Step 6: Run focused/full tests and commit**

Commit: `feat: score target account affinity`

---

### Task 4: Cooldown and speculative-action selector

**Files:**
- Create: `app/targets/selector.py`
- Create: `tests/test_target_selector.py`

**Interfaces:**
- Produces protocol: `OutreachHistory.last_contacted_at(account_id: str) -> datetime | None`
- Produces: `select_target_batch(assessments, policy, history, *, now) -> TargetAccountBatch`

- [ ] **Step 1: Write failing cooldown tests**

```python
def test_recent_spontaneous_contact_suppresses_action() -> None:
    # contacted 10 days ago, default cooldown 30
    ...
    assert item.cooldown_active is True
    assert item.recommended_action == "WATCH"


def test_no_contact_history_can_recommend_prepare_outreach() -> None:
    ...
    assert item.recommended_action == "PREPARE_SPECULATIVE"
```

- [ ] **Step 2: Define policy explicitly**

```text
cooldown_days = 30
max_items = 20
minimum_affinity = 65
minimum_confidence = 60
```

These are configuration defaults for **recommendations**, not outbound-send quotas. A later approval/email slice may choose fewer.

- [ ] **Step 3: Implement deterministic action rules**

```text
cooldown active -> WATCH
no usable contactability -> RESEARCH_CONTACT
affinity/confidence below threshold -> WATCH
otherwise -> PREPARE_SPECULATIVE
```

Never return `SEND`. V0.2A2 cannot send or draft email.

- [ ] **Step 4: Implement ordering**

Sort by actionability (`PREPARE_SPECULATIVE`, `RESEARCH_CONTACT`, `WATCH`), affinity desc, confidence desc, proximity value desc, account id asc. Stop at `max_items`; never duplicate account ids.

- [ ] **Step 5: Run focused/full tests and commit**

Commit: `feat: select spontaneous target account candidates`

---

### Task 5: Target radar service and API

**Files:**
- Create: `app/targets/service.py`
- Modify: `app/api/routes.py`
- Modify: `app/main.py`
- Create: `tests/test_target_service.py`
- Create: `tests/test_api_target_radar.py`

**Interfaces:**
- Produces: `TargetRadarService.run(profile, *, now) -> TargetAccountBatch`
- Adds: `POST /api/v1/targets/radar/run -> TargetAccountBatch`

- [ ] **Step 1: Write failing service test**

Inject a registry with three fictional accounts and fake outreach history. Assert the service scores all, applies cooldown, and produces deterministic order without network access.

- [ ] **Step 2: Implement pure service composition**

```text
load/injected target registry
→ assess each account against candidate tracks
→ apply target selector/history
→ return TargetAccountBatch
```

No public-web fetch occurs inside this service. ChatGPT/manual research can update the local/private registry separately.

- [ ] **Step 3: Write failing API tests**

Cases:

```text
profile unavailable -> 503
registry unavailable -> 503 Target account registry unavailable
valid registry -> 200 strict TargetAccountBatch
endpoint creates no CV/draft/email/contact side effect
```

- [ ] **Step 4: Compose optional target service in `create_app`**

Preserve existing V0.1/A1 injection arguments. Add an optional injected `target_service` or registry path without making target configuration mandatory for health/V0.1 routes.

- [ ] **Step 5: Implement API route with public-safe errors**

Do not expose local registry filesystem details beyond the safe configured path label; never serialize private free-form notes unless explicitly part of the safe response model.

- [ ] **Step 6: Run focused/full tests and commit**

Commit: `feat: expose target account radar`

---

### Task 6: Documentation, private/public boundary and release verification

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Verify: `.gitignore`
- Test: entire `tests/` suite

**Interfaces:**
- No new runtime interface; documents how later V0.2B/C consume `PREPARE_SPECULATIVE` recommendations.

- [ ] **Step 1: Document the semantic distinction**

README must state:

```text
ACTIVE_POSTING = real published requisition
TARGET_ACCOUNT = organization worth watching/approaching
SPECULATIVE_OUTREACH = recommendation to prepare a truthful spontaneous candidature
```

Never represent a target account as an active opening.

- [ ] **Step 2: Document research/update workflow**

Explain that public-web/ChatGPT research may populate a private `targets.local.yaml`, but the core scorer only consumes structured sourced facts. Include example commands/config, not real personal target data.

- [ ] **Step 3: Verify no outreach implementation leaked into A2**

Search source/diff for new functions named `send`, `submit`, `email_recruiter`, `apply`, or similar outbound mutation. Existing V0.1/non-target meanings are fine; A2 must add none.

- [ ] **Step 4: Run full verification**

```bash
python -m pytest -v
python -m compileall app
git diff --check
git status --short
```

Expected: all tests PASS and only intentional files changed.

- [ ] **Step 5: Privacy scan**

Ensure tracked files contain no personal exact address, personal CV, local recruiter emails, Apollo-enriched data, tokens, passwords or `targets.local.yaml`.

- [ ] **Step 6: Commit**

Commit: `docs: document target account radar workflow`

---

## Plan self-review

### Spec coverage

- Target account distinct from vacancy: Tasks 1 and 6.
- Account-affinity score and component weights: Task 3.
- Coarse proximity: Tasks 1 and 3.
- Provenance: Tasks 1–3.
- Spontaneous-candidacy recommendation: Task 4.
- 30-day anti-spam cooldown: Task 4.
- One contact path / no guessed emails: Global Constraints and Task 4 action model.
- Private real target list/public fictional example: Task 2 + Task 6.
- No CV/email/send yet: Global Constraints + Tasks 5–6.

### Placeholder scan

No `TBD`, `TODO`, “implement later”, or unspecific test instructions are present. Later CV/email features are only named as explicit scope boundaries.

### Type consistency

`TargetAccount`, `TargetAccountAssessment`, `TargetAccountPolicy` and `TargetAccountBatch` originate in `app/targets/models.py`; scoring, selector, service and API consume those exact types. Candidate tracks come from V0.2A1 rather than being redefined.

## Handoff to V0.2B/V0.2C

A target item whose `recommended_action == PREPARE_SPECULATIVE` becomes eligible for the later CV Factory. Only after a versioned CV/application packet exists may V0.2C identify a legitimate contact, create a Gmail draft and ask for explicit approval before sending.
