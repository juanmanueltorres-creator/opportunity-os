# Opportunity OS V0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public-safe FastAPI application that ingests authorized job postings, normalizes and deduplicates them, stores them in SQLite, and returns deterministic explainable opportunity assessments against a local candidate profile.

**Architecture:** Keep four boundaries explicit: source connectors, normalized domain models, SQLite repository, and deterministic matching. FastAPI composes those boundaries but does not own business logic. External HTTP is isolated behind connectors and all tests use fixtures/mocks, so the suite never requires network access.

**Tech Stack:** Python >=3.12, FastAPI, Pydantic v2, httpx, PyYAML, stdlib sqlite3, pytest, Uvicorn.

**Spec:** `docs/superpowers/specs/2026-08-28-opportunity-os-v0.1-design.md`

## Global Constraints

- Employment opportunities only in V0.1.
- No auto-apply, message sending, CAPTCHA bypass, browser automation, LinkedIn/Indeed scraping, portal password storage, or legal/declarative automation.
- No LLM score, LangChain/LangGraph, vector DB, React, Supabase/Postgres, MCP, or client/prospecting engine in V0.1.
- API prefix is `/api/v1`; `/health` stays unversioned.
- Scoring weights: core/mandatory skill fit 40%, domain fit 20%, evidence fit 20%, location/remote fit 10%, freshness 10%.
- Personal profiles use `profile.local.yaml` and must remain gitignored.
- `.env` remains ignored and `.env.example` contains variable names/default examples only, never secrets.
- Every outbound HTTP request uses an explicit timeout.
- Every connector failure is isolated and must not corrupt already stored opportunities.
- Every slice is TDD: failing test, minimal implementation, green tests, commit.

---

## File map

- `app/main.py` — app factory and FastAPI composition only.
- `app/models/domain.py` — Opportunity, CandidateProfile, EvidenceItem, OpportunityAssessment and enums.
- `app/profiles.py` — YAML profile loading/validation.
- `app/matching/scorer.py` — deterministic matching and recommendation logic only.
- `app/repositories/opportunities.py` — SQLite schema and opportunity persistence/deduplication.
- `app/connectors/base.py` — connector protocol + typed connector errors.
- `app/connectors/remotive.py` — Remotive fetch/normalize.
- `app/connectors/greenhouse.py` — Greenhouse fetch/normalize.
- `app/connectors/lever.py` — Lever fetch/normalize.
- `app/connectors/ashby.py` — Ashby fetch/normalize.
- `app/services/ingestion.py` — connector → repository orchestration.
- `app/api/routes.py` — explicit HTTP endpoints and response models.
- `profiles/example_profile.yaml` — public safe sample profile only.
- `tests/` — isolated unit/contract tests and connector fixtures.
- `pyproject.toml` — runtime/dev dependencies and pytest config.
- `.env.example` — local configuration names.
- `README.md` — install/run/API/safety documentation.

---

### Task 1: Runnable skeleton and stable health contract

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `tests/test_health.py`
- Create: `.env.example`
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- Produces: `create_app() -> FastAPI`
- Produces: module-level `app = create_app()` for `uvicorn app.main:app`
- Produces: `GET /health -> {"status": "ok", "service": "opportunity-os"}`

- [ ] **Step 1: Write the failing health test**

```python
from fastapi.testclient import TestClient
from app.main import create_app


def test_health_contract() -> None:
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "opportunity-os"}
```

- [ ] **Step 2: Add package metadata and dependencies**

`pyproject.toml` must define Python `>=3.12`, runtime dependencies `fastapi`, `httpx`, `pydantic`, `PyYAML`, `uvicorn`, and dev dependency `pytest`. Configure pytest with `testpaths = ["tests"]`.

- [ ] **Step 3: Run the focused test and verify red**

Run: `python -m pytest tests/test_health.py -v`

Expected: FAIL because `app.main` / `create_app` does not exist yet.

- [ ] **Step 4: Implement only the app factory and health route**

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    api = FastAPI(title="Opportunity OS", version="0.1.0")

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "opportunity-os"}

    return api


app = create_app()
```

- [ ] **Step 5: Harden local-public defaults**

Append to `.gitignore`:

```text
profile.local.yaml
*.db
*.sqlite
*.sqlite3
```

Create `.env.example` with:

```text
OPPORTUNITY_DB_PATH=opportunities.db
OPPORTUNITY_PROFILE_PATH=profile.local.yaml
HTTP_TIMEOUT_SECONDS=10
```

No credentials.

- [ ] **Step 6: Run tests and commit**

Run: `python -m pytest -v`

Expected: PASS.

Commit: `feat: bootstrap FastAPI service`

---

### Task 2: Domain models and safe profile loading

**Files:**
- Create: `app/models/__init__.py`
- Create: `app/models/domain.py`
- Create: `app/profiles.py`
- Create: `profiles/example_profile.yaml`
- Create: `tests/test_profiles.py`
- Create: `tests/test_domain_models.py`

**Interfaces:**
- Produces: `Opportunity`, `EvidenceItem`, `CandidateProfile`, `OpportunityAssessment`
- Produces: `Recommendation = Literal["apply", "stretch", "nurture", "discard"]`
- Produces: `load_profile(path: str | Path) -> CandidateProfile`

- [ ] **Step 1: Write failing validation tests**

```python
import pytest
from pydantic import ValidationError
from app.models.domain import CandidateProfile, EvidenceItem


def test_profile_requires_a_name_and_skills() -> None:
    with pytest.raises(ValidationError):
        CandidateProfile(name="", roles=[], skills=[], domains=[], locations=[], remote_preferences=[], evidence=[])


def test_evidence_is_explicitly_verified_or_not() -> None:
    item = EvidenceItem(label="Example", type="project", skills=["python"], domains=["gis"], verified=True)
    assert item.verified is True
```

- [ ] **Step 2: Implement strict Pydantic domain models**

Use UTC-aware `datetime`; lists default to empty factories; normalize no data silently. `Opportunity.status` defaults to `"found"`. Evidence types are `project | skill | experience | education | document`.

- [ ] **Step 3: Write failing YAML loader tests**

Test a valid temporary YAML and an invalid YAML missing `skills`; invalid profiles must surface a `ValueError` whose message does not include arbitrary raw file contents.

- [ ] **Step 4: Implement `load_profile`**

```python
def load_profile(path: str | Path) -> CandidateProfile:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    try:
        return CandidateProfile.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid candidate profile: {path}") from exc
```

- [ ] **Step 5: Add public example profile**

Use fictional/generic values, for example `Example Candidate`; do not copy personal phone/email/address/CV content into the public repo.

- [ ] **Step 6: Run focused/full tests and commit**

Run: `python -m pytest tests/test_profiles.py tests/test_domain_models.py -v` then `python -m pytest -v`.

Commit: `feat: add domain models and profile loading`

---

### Task 3: Deterministic explainable matcher

**Files:**
- Create: `app/matching/__init__.py`
- Create: `app/matching/scorer.py`
- Create: `tests/test_matching.py`

**Interfaces:**
- Consumes: `Opportunity`, `CandidateProfile`
- Produces: `assess_opportunity(opportunity: Opportunity, profile: CandidateProfile, now: datetime | None = None) -> OpportunityAssessment`

- [ ] **Step 1: Write failing score tests**

Cover exact deterministic behavior:

```python
def test_missing_required_skill_is_a_gap() -> None:
    assessment = assess_opportunity(opportunity_with_required(["python", "kubernetes"]), profile_with_skills(["python"]))
    assert "kubernetes" in assessment.gaps
    assert assessment.mandatory_fit == 50.0


def test_evidence_is_selected_only_when_verified_and_relevant() -> None:
    assessment = assess_opportunity(opportunity_requiring("postgis"), profile_with_verified_postgis_evidence())
    assert [item.label for item in assessment.evidence] == ["GIS project"]
```

Also test same input + same `now` gives identical output.

- [ ] **Step 2: Implement normalization helpers**

Use casefolded exact-token/phrase matching only. Do not infer `postgresql == postgis`, `javascript == typescript`, or any other semantic equivalence unless a future explicit alias table is introduced and tested.

- [ ] **Step 3: Implement component scores**

```text
mandatory_fit = matched required skills / required skills
if required skills empty: evaluate explicit preferred/core mentions, else neutral 50

domain_fit = overlap of opportunity text/declared skills with profile domains

evidence_fit = verified relevant evidence coverage
location_fit = 100 for compatible remote/location, 50 unknown, 0 explicit conflict
freshness_fit = 100 <=7 days, 75 <=30, 50 unknown, 25 <=90, 0 older
```

Compute `overall_score = 0.40*mandatory + 0.20*domain + 0.20*evidence + 0.10*location + 0.10*freshness`, rounded to one decimal.

- [ ] **Step 4: Implement recommendation thresholds**

```text
apply   >= 75 and no hard incompatibility
stretch >= 55
nurture >= 35
discard < 35
```

An explicit location conflict or explicit missing mandatory credential adds a risk and caps recommendation at `stretch` or `discard` according to the tested rule; do not hide the incompatibility behind the numeric score.

- [ ] **Step 5: Ensure explanation is structured from facts**

Explanation names score components, matched skills, gaps and risks. It must never invent an experience claim.

- [ ] **Step 6: Run focused/full tests and commit**

Commit: `feat: add deterministic opportunity scoring`

---

### Task 4: SQLite repository and reversible deduplication boundary

**Files:**
- Create: `app/repositories/__init__.py`
- Create: `app/repositories/opportunities.py`
- Create: `tests/test_repository.py`

**Interfaces:**
- Produces: `SQLiteOpportunityRepository(path: str | Path)`
- Produces: `initialize() -> None`
- Produces: `upsert(opportunity: Opportunity) -> tuple[Opportunity, bool]` where bool is `created`
- Produces: `get(opportunity_id: str) -> Opportunity | None`
- Produces: `list(limit: int = 100) -> list[Opportunity]`

- [ ] **Step 1: Write failing persistence/dedupe tests**

Use pytest `tmp_path`; never write the project root DB in tests. Test persistence across repository instances and duplicate insertion.

- [ ] **Step 2: Implement schema with stdlib `sqlite3`**

Store normalized scalar fields plus JSON strings for arrays. Add unique index on `(source, source_id)`. Add `dedupe_key` computed from normalized `company|title|location`; keep the original source/source_id/source_url so dedupe remains inspectable.

- [ ] **Step 3: Implement transactions**

One `with sqlite3.connect(...) as conn:` transaction per write. Parse the row back through `Opportunity.model_validate` before returning it.

- [ ] **Step 4: Test failure safety**

Force a malformed write and assert previously committed rows remain readable.

- [ ] **Step 5: Run full tests and commit**

Commit: `feat: add SQLite opportunity repository`

---

### Task 5: Connector contract, Remotive normalization and ingestion service

**Files:**
- Create: `app/connectors/__init__.py`
- Create: `app/connectors/base.py`
- Create: `app/connectors/remotive.py`
- Create: `app/services/__init__.py`
- Create: `app/services/ingestion.py`
- Create: `tests/fixtures/remotive_jobs.json`
- Create: `tests/test_remotive.py`
- Create: `tests/test_ingestion.py`

**Interfaces:**
- Produces: `ConnectorError`, `ConnectorTimeoutError`, `ConnectorPayloadError`
- Produces protocol: `async fetch() -> list[Opportunity]`
- Produces: `RemotiveConnector(client: httpx.AsyncClient, timeout_seconds: float = 10.0)`
- Produces: `async ingest(connector, repository) -> IngestionResult(created: int, existing: int)`

- [ ] **Step 1: Write normalization test from committed fixture**

Assert exact mapping of id, URL, company, title, location, description, publication timestamp and source=`remotive`.

- [ ] **Step 2: Write malformed payload and timeout tests**

Mock `httpx` transport/client; no live HTTP. A timeout becomes `ConnectorTimeoutError`; a malformed `jobs` payload becomes `ConnectorPayloadError`.

- [ ] **Step 3: Implement Remotive adapter**

Use explicit timeout. Keep raw payload local to connector; only normalized `Opportunity` crosses the boundary.

- [ ] **Step 4: Write ingestion failure-safety test**

Seed repository with one opportunity, make connector raise, call ingestion, then assert seeded opportunity still exists.

- [ ] **Step 5: Implement ingestion orchestration**

Loop normalized jobs through `repository.upsert`; return counts. Do not delete or truncate existing data at ingestion start.

- [ ] **Step 6: Run full tests and commit**

Commit: `feat: ingest Remotive opportunities safely`

---

### Task 6: Versioned opportunity, ingestion and assessment API

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/api/routes.py`
- Modify: `app/main.py`
- Create: `tests/test_api_opportunities.py`
- Create: `tests/test_api_ingestion.py`
- Create: `tests/test_api_assessments.py`

**Interfaces:**
- `GET /api/v1/opportunities`
- `GET /api/v1/opportunities/{id}`
- `POST /api/v1/ingest/remotive`
- `POST /api/v1/assessments/{opportunity_id}`

- [ ] **Step 1: Refactor app creation through explicit dependencies**

`create_app(repository: SQLiteOpportunityRepository | None = None, profile: CandidateProfile | None = None, remotive_connector: JobConnector | None = None) -> FastAPI` so tests inject temp repository and fake connector without monkeypatching global state.

- [ ] **Step 2: Write list/detail contract tests first**

404 body must be stable (`{"detail": "Opportunity not found"}`); list and detail use Pydantic response models, not raw SQLite rows.

- [ ] **Step 3: Write ingestion endpoint tests**

Success returns counts; typed connector error maps to `502` with a public-safe detail such as `"Upstream job source unavailable"`. Do not expose raw exception strings.

- [ ] **Step 4: Write assessment tests**

Load seeded opportunity and injected profile; response includes all five component scores, strengths, gaps, risks, evidence and recommendation.

- [ ] **Step 5: Implement routes minimally and run full suite**

Commit: `feat: expose opportunity and assessment API`

---

### Task 7: Greenhouse, Lever and Ashby public-source adapters

**Files:**
- Create: `app/connectors/greenhouse.py`
- Create: `app/connectors/lever.py`
- Create: `app/connectors/ashby.py`
- Create: `tests/fixtures/greenhouse_jobs.json`
- Create: `tests/fixtures/lever_jobs.json`
- Create: `tests/fixtures/ashby_jobs.json`
- Create: `tests/test_greenhouse.py`
- Create: `tests/test_lever.py`
- Create: `tests/test_ashby.py`

**Interfaces:**
- Each adapter exposes `async fetch() -> list[Opportunity]` and a pure payload normalizer testable without HTTP.
- Company/board identifiers are constructor arguments, never secrets.

- [ ] **Step 1: Greenhouse TDD slice**

Fixture → failing normalization test → implementation → timeout/malformed test → green suite → commit `feat: add Greenhouse connector`.

- [ ] **Step 2: Lever TDD slice**

Same contract, independent module and error mapping → commit `feat: add Lever connector`.

- [ ] **Step 3: Ashby TDD slice**

Same contract, independent module and error mapping → commit `feat: add Ashby connector`.

- [ ] **Step 4: Verify connector isolation**

A test with one failing fake connector and one successful connector must demonstrate that orchestration can process sources independently; failure of one source cannot wipe or invalidate rows from another.

---

### Task 8: Public documentation, CI and V0.1 completion gate

**Files:**
- Modify: `README.md`
- Create: `.github/workflows/tests.yml`
- Modify: `.env.example` only if final config names changed
- Modify: `docs/superpowers/specs/2026-08-28-opportunity-os-v0.1-design.md` status from `proposed` to `implemented` only after verification

**Interfaces:**
- Public contributor path: clone → venv → install → copy example profile → run API → test.

- [ ] **Step 1: Expand README with exact commands**

```bash
python -m venv .venv
# activate environment for the local shell
python -m pip install -e ".[dev]"
cp profiles/example_profile.yaml profile.local.yaml
uvicorn app.main:app --reload
python -m pytest -v
```

Document that the system prepares/evaluates opportunities and deliberately does not submit applications.

- [ ] **Step 2: Add CI**

GitHub Actions uses Python 3.12, installs `.[dev]`, and runs `python -m pytest -v`. Tests must succeed with outbound network unavailable because connector HTTP is mocked.

- [ ] **Step 3: Run security/public-safety inspection**

Search tracked files for `.env`, `profile.local.yaml`, CV files, tokens, passwords, API keys and personal contact data. Verify no endpoint/function named apply/send/submit performs external side effects.

- [ ] **Step 4: Run final verification**

Run full test suite; launch app locally; manually call `/health`; ingest through mocked/controlled tests; verify list/detail/assessment contracts. Confirm Remotive plus at least Greenhouse satisfy the V0.1 done definition.

- [ ] **Step 5: Update spec status and commit**

Only with all checks green, change `Status: proposed` to `Status: implemented`.

Commit: `docs: complete Opportunity OS v0.1`

---

## Self-review against spec

- Spec scope: covered by Tasks 1–8.
- Public authorized ingestion: Tasks 5 and 7.
- Normalization/deduplication: Tasks 4, 5, 7.
- YAML candidate profile: Task 2.
- Deterministic explainable scoring: Task 3.
- SQLite boundary: Task 4.
- Versioned API and explicit contracts: Task 6.
- Connector isolation/failure safety: Tasks 5 and 7.
- Security/privacy defaults: Tasks 1 and 8.
- Offline tests: Tasks 5, 7, 8.
- Remotive + company ATS done gate: Tasks 5, 7, 8.
- Forbidden auto-apply/browser/LLM scope: explicitly excluded globally; no task introduces it.

No placeholder implementation steps remain. Type names used by later tasks are defined in earlier tasks.