# Opportunity OS V0.2B CV Factory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, evidence-backed CV factory that turns one selected `RadarAssessment` into a truthful ATS-first PDF and a reproducible `ApplicationPacket` without sending, submitting, or inventing candidate claims.

**Architecture:** V0.2B adds a focused `app/cv/` subsystem. Private master facts and evidence catalogs are loaded into strict snapshots, a winning radar track limits the candidate evidence pool, a deterministic selector chooses relevant verified evidence, a composer builds a provenance-backed `CVDocumentModel`, a hard `ClaimValidator` gates rendering, and a deterministic ReportLab renderer produces a private PDF. `CVPreparationService` orchestrates those units and returns either a prepared packet or a typed blocked result; Gmail/recruiter/submission work remains V0.2C.

**Tech Stack:** Python >=3.12, Pydantic v2, PyYAML, existing Opportunity OS radar models/taxonomy resolver, ReportLab >=4.2 for PDF generation, pypdf >=5 as a dev-only PDF text/structure assertion dependency, pytest/pytest-asyncio, SHA-256 canonical JSON hashing.

**Spec:** `docs/superpowers/specs/2026-08-28-opportunity-os-v0.2b-cv-factory-design.md` plus normative clarification `docs/superpowers/specs/2026-08-28-opportunity-os-v0.2b-cv-factory-self-review.md`

## Global Constraints

- Python remains `>=3.12`.
- V0.1 and V0.2A1 public API contracts and radar scoring behavior remain unchanged.
- Real master facts, contact data, recruiter data, generated CV PDF/DOCX files, and real application packets must never be committed to the public repository.
- V0.2B performs no Gmail operations, recruiter discovery, Apollo enrichment, form submission, ATS submission, browser automation, or approval/send action.
- Only verified facts may support candidate claims; `verified=true` requires a verification method and timezone-aware `verified_at`.
- Evidence-backed verification methods require a non-empty source reference; `manual_confirmation` is limited to legitimate self-attested facts/approved wording and cannot establish employment, education, certifications, metrics, tools, dates, or external outcomes.
- The selected application track is a hard evidence boundary. No silent cross-track borrowing is allowed.
- Unsupported job requirements are gaps/warnings by default, not invented CV claims and not automatic preparation hard-fails.
- The composer and renderer require no LLM or network access.
- The renderer may add only fixed localized section labels without provenance; all candidate/application content must come from validated structured claims.
- `ApplicationPacket` exists only for `PREPARED`; blocked outcomes return `PreparationResult(packet=None, ...)`.
- `packet_sha256` excludes `application_id`, `created_at`, `cv_pdf_path`, load timestamps, and filesystem-specific values.
- Identical validated `CVDocumentModel` + renderer version + renderer policy must produce stable PDF bytes and therefore stable `cv_sha256` in test fixtures.
- One ATS-first, one-column PDF layout only; DOCX and alternative visual designs remain out of scope.
- CI remains offline.

## File Structure

New subsystem:

```text
app/cv/
  __init__.py          package exports/version constants
  models.py            strict facts/evidence/CV/packet/result contracts
  hashing.py           canonical content normalization and SHA-256 helpers
  loaders.py           private YAML snapshot loading and verification validation
  track.py             selected application-track resolution and minimum-evidence gate
  selector.py          deterministic requirement-to-evidence selection
  composer.py          provenance-backed CVDocumentModel construction
  validator.py         hard claim/provenance validation
  renderer.py          deterministic one-column ATS PDF rendering
  service.py           end-to-end CV preparation orchestration

config/
  master_facts.example.yaml
  evidence_catalog.example.yaml

tests/
  fixtures/cv/
    master_facts.yaml
    evidence_catalog.yaml
  test_cv_models.py
  test_cv_loaders.py
  test_cv_track.py
  test_cv_selector.py
  test_cv_composer.py
  test_cv_validator.py
  test_cv_renderer.py
  test_cv_service.py
```

Existing files changed only where necessary:

```text
.gitignore
.github/workflows/tests.yml
pyproject.toml
README.md
```

---

### Task 1: CV contracts and canonical hashing

**Files:**
- Create: `app/cv/__init__.py`
- Create: `app/cv/models.py`
- Create: `app/cv/hashing.py`
- Test: `tests/test_cv_models.py`

**Interfaces:**
- Consumes: `SearchIntent` from `app.models.domain`; no filesystem or network.
- Produces: `MasterFact`, `ApprovedClaim`, `EvidenceModule`, `MasterFactsSnapshot`, `EvidenceCatalogSnapshot`, `CVPolicy`, `RequirementSupport`, `EvidenceSelection`, `CVClaim`, `CVEntry`, `ClaimProvenance`, `CVDocumentModel`, `ValidationIssue`, `ValidationResult`, `RenderedCVArtifact`, `ApplicationPacket`, `PreparationResult`, `canonical_sha256()`.

- [ ] **Step 1: Write failing strict-contract tests**

Create `tests/test_cv_models.py` with at least these cases:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.cv.models import MasterFact


def test_verified_fact_requires_method_and_aware_timestamp() -> None:
    with pytest.raises(ValidationError):
        MasterFact(
            id="skill-postgis",
            kind="skill",
            value="PostGIS",
            track_ids=["tech"],
            verified=True,
        )


def test_manual_confirmation_may_verify_self_attested_contact() -> None:
    fact = MasterFact(
        id="contact-email",
        kind="contact",
        value="alex@example.test",
        track_ids=["tech", "ops"],
        verified=True,
        verification_method="manual_confirmation",
        verified_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )
    assert fact.source_ref is None


def test_repository_evidence_requires_source_ref() -> None:
    with pytest.raises(ValidationError):
        MasterFact(
            id="skill-python",
            kind="skill",
            value="Python",
            track_ids=["tech"],
            verified=True,
            verification_method="repository_evidence",
            verified_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
        )
```

Also test `extra="forbid"`, non-empty stable IDs, and timezone-aware verification dates.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
python -m pytest tests/test_cv_models.py -v
```

Expected: collection/import failure because `app.cv.models` does not exist.

- [ ] **Step 3: Implement the strict model surface**

Create `app/cv/models.py` with these public contracts and exact initial literals:

```python
FactKind = Literal[
    "identity", "contact", "summary_claim", "skill", "role", "employment",
    "education", "project", "language", "location", "link", "achievement",
    "metric", "other",
]
VerificationMethod = Literal[
    "manual_confirmation", "repository_evidence", "document_evidence",
    "employment_record", "education_record", "public_profile",
    "other_reviewed_source",
]
CVSection = Literal[
    "headline", "summary", "experience", "projects", "education",
    "skills", "languages", "links",
]
ClaimKind = Literal[
    "identity", "contact", "location", "headline", "summary", "organization",
    "title", "date", "bullet", "project", "education", "skill", "language", "link",
]
PreparationStatus = Literal[
    "PREPARED", "BLOCKED_VALIDATION", "BLOCKED_MISSING_FACTS",
    "BLOCKED_TRACK_UNAVAILABLE", "BLOCKED_RENDER",
]

class MasterFact(StrictCVModel):
    id: str = Field(min_length=1)
    kind: FactKind
    value: str = Field(min_length=1)
    display_values: dict[str, str] = Field(default_factory=dict)
    track_ids: list[str] = Field(default_factory=list)
    verified: bool = False
    verification_method: VerificationMethod | None = None
    verified_at: datetime | None = None
    source_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class ApprovedClaim(StrictCVModel):
    id: str = Field(min_length=1)
    section: CVSection
    kind: ClaimKind
    text_by_language: dict[str, str]
    fact_ids: list[str] = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)

class EvidenceModule(StrictCVModel):
    id: str = Field(min_length=1)
    track_ids: list[str] = Field(min_length=1)
    label: str = Field(min_length=1)
    fact_ids: list[str] = Field(min_length=1)
    claims: list[ApprovedClaim] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    verified: bool
```

Add snapshot wrappers with `schema_version`, `content_sha256`, and lists of facts/modules. Add document/validation/packet/result models named in **Interfaces**. `ApplicationPacket.status` is fixed to `Literal["PREPARED"]`; blocked statuses belong only to `PreparationResult`.

Add validators so:

```python
if self.verified:
    assert self.verification_method is not None
    assert self.verified_at is not None and self.verified_at.tzinfo is not None
    if self.verification_method != "manual_confirmation":
        assert self.source_ref and self.source_ref.strip()
```

Do not attempt to infer whether a user-confirmed claim is legitimate inside the Pydantic model; loader/policy tests will restrict example usage.

- [ ] **Step 4: Add canonical SHA-256 helpers and tests**

Create `app/cv/hashing.py`:

```python
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
```

Add tests showing dictionary key order does not change a hash and semantically ordered CV bullet lists do change a hash.

- [ ] **Step 5: Run Task 1 tests and full regression suite**

Run:

```bash
python -m pytest tests/test_cv_models.py -v
python -m pytest -v
```

Expected: all tests pass, including the existing V0.1/V0.2A1 suite.

- [ ] **Step 6: Commit Task 1**

```bash
git add app/cv/__init__.py app/cv/models.py app/cv/hashing.py tests/test_cv_models.py
git commit -m "feat: add CV factory contracts and hashing"
```

---

### Task 2: Private snapshot loaders, canonical fingerprints, and public fictional examples

**Files:**
- Create: `app/cv/loaders.py`
- Create: `config/master_facts.example.yaml`
- Create: `config/evidence_catalog.example.yaml`
- Create: `tests/fixtures/cv/master_facts.yaml`
- Create: `tests/fixtures/cv/evidence_catalog.yaml`
- Create: `tests/test_cv_loaders.py`
- Modify: `.gitignore`
- Modify: `.github/workflows/tests.yml`

**Interfaces:**
- Consumes: Task 1 models/hashing.
- Produces: `load_master_facts(path: str | Path) -> MasterFactsSnapshot`, `load_evidence_catalog(path: str | Path) -> EvidenceCatalogSnapshot`.

- [ ] **Step 1: Write RED loader/fingerprint tests**

Create `tests/test_cv_loaders.py` with:

```python
from pathlib import Path

from app.cv.loaders import load_evidence_catalog, load_master_facts

FIXTURES = Path(__file__).parent / "fixtures" / "cv"


def test_master_facts_fingerprint_is_independent_of_yaml_item_order(tmp_path: Path) -> None:
    original = load_master_facts(FIXTURES / "master_facts.yaml")
    reordered = tmp_path / "reordered.yaml"
    reordered.write_text(
        "schema_version: v1\nfacts:\n"
        "  - {id: b, kind: skill, value: Python, track_ids: [tech], verified: false}\n"
        "  - {id: a, kind: skill, value: PostGIS, track_ids: [tech], verified: false}\n",
        encoding="utf-8",
    )
    # A companion source with a/b reversed must hash the same once canonicalized by stable ID.
    # The fixture created in this task will use matching semantic records for this assertion.
    assert len(original.content_sha256) == 64


def test_loader_rejects_duplicate_fact_ids() -> None:
    ...
```

Replace the illustrative first test body with two complete semantically identical temp YAML files whose facts differ only in order; assert identical `content_sha256`. Add tests for duplicate IDs, module references to missing fact IDs, and evidence modules marked verified while containing unverified facts.

- [ ] **Step 2: Verify RED**

Run:

```bash
python -m pytest tests/test_cv_loaders.py -v
```

Expected: import failure because `app.cv.loaders` does not exist.

- [ ] **Step 3: Implement deterministic YAML loading**

Create `app/cv/loaders.py` with strict `yaml.safe_load()` parsing. Canonicalize snapshot identity using stable ID ordering:

```python
def _master_payload(schema_version: str, facts: list[MasterFact]) -> dict[str, object]:
    ordered = sorted(facts, key=lambda fact: fact.id)
    return {
        "schema_version": schema_version,
        "facts": [fact.model_dump(mode="json") for fact in ordered],
    }


def load_master_facts(path: str | Path) -> MasterFactsSnapshot:
    payload = _load_yaml_mapping(path, "master facts")
    schema_version = str(payload.get("schema_version", "")).strip()
    facts = [MasterFact.model_validate(item) for item in payload.get("facts", [])]
    _require_unique_ids(facts, label="fact")
    content_sha256 = canonical_sha256(_master_payload(schema_version, facts))
    return MasterFactsSnapshot(
        schema_version=schema_version,
        content_sha256=content_sha256,
        facts=sorted(facts, key=lambda fact: fact.id),
    )
```

Implement the evidence-catalog analogue. Validate every module `fact_id` and every approved claim `fact_id` against the master-facts-independent catalog syntax where possible; cross-snapshot consistency is exposed as `validate_catalog_against_facts(catalog, master_facts)` and called by the service later.

- [ ] **Step 4: Add fictional examples only**

`config/master_facts.example.yaml` uses a fictional candidate such as `Alex Example` and `.test` email domains. Include two tracks (`tech`, `hospitality`) so isolation is testable. No real names, phones, emails, employers, schools, or repository URLs.

`config/evidence_catalog.example.yaml` includes one tech module and one hospitality module with approved ES/EN claims.

- [ ] **Step 5: Strengthen private-file guards**

Append to `.gitignore`:

```gitignore
profile/master_facts.local.yaml
profile/evidence_catalog.local.yaml
artifacts/applications/
```

Extend the workflow guard command to include:

```bash
'profile/master_facts.local.yaml' \
'profile/evidence_catalog.local.yaml' \
'artifacts/applications/**'
```

Keep the existing global `*.pdf` and `*.docx` tracked-file checks.

- [ ] **Step 6: Run loader tests and privacy regression**

Run:

```bash
python -m pytest tests/test_cv_loaders.py -v
python -m pytest -v
python -m compileall app
```

Expected: all pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add app/cv/loaders.py config/master_facts.example.yaml config/evidence_catalog.example.yaml tests/fixtures/cv tests/test_cv_loaders.py .gitignore .github/workflows/tests.yml
git commit -m "feat: load private CV evidence snapshots safely"
```

---

### Task 3: Application-track resolution and minimum truthful-evidence gate

**Files:**
- Create: `app/cv/track.py`
- Create: `tests/test_cv_track.py`

**Interfaces:**
- Consumes: `RadarAssessment`, `MasterFactsSnapshot`, `EvidenceCatalogSnapshot`, `CVPolicy`.
- Produces: `resolve_application_track(assessment: RadarAssessment) -> str`, `check_minimum_evidence(track_id: str, master_facts: MasterFactsSnapshot, catalog: EvidenceCatalogSnapshot, policy: CVPolicy) -> list[ValidationIssue]`.

- [ ] **Step 1: Write RED tests for lane-aware track choice**

```python
def test_income_selected_intent_uses_best_income_track() -> None:
    assessment = make_radar_assessment(
        selected_intent="INCOME_NOW",
        best_income_track="hospitality",
        best_career_track="tech",
    )
    assert resolve_application_track(assessment) == "hospitality"


def test_missing_selected_lane_falls_back_to_other_qualifying_track() -> None:
    assessment = make_radar_assessment(
        selected_intent="CAREER",
        best_career_track=None,
        best_income_track="tech",
    )
    assert resolve_application_track(assessment) == "tech"


def test_no_winning_track_raises_typed_track_unavailable() -> None:
    ...
```

Also test that a tech application cannot satisfy minimum evidence using hospitality-only modules.

- [ ] **Step 2: Verify RED**

Run:

```bash
python -m pytest tests/test_cv_track.py -v
```

Expected: import failure because `app.cv.track` does not exist.

- [ ] **Step 3: Implement exact track rules**

```python
class TrackUnavailableError(ValueError):
    pass


def resolve_application_track(assessment: RadarAssessment) -> str:
    if assessment.selected_intent == "CAREER" and assessment.best_career_track:
        return assessment.best_career_track
    if assessment.selected_intent == "INCOME_NOW" and assessment.best_income_track:
        return assessment.best_income_track
    if assessment.best_career_track:
        return assessment.best_career_track
    if assessment.best_income_track:
        return assessment.best_income_track
    raise TrackUnavailableError("No qualifying application track is available")
```

`check_minimum_evidence()` must require only policy-defined CV structure, not all job requirements. Initial default policy requirements:

```text
identity fact present and verified
at least one verified contact fact
at least one verified experience or project evidence module for application_track_id
all policy.required_sections have truthful content when declared required
```

Return typed issues; do not mutate facts or borrow another track.

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_cv_track.py -v
python -m pytest -v
```

Expected: all pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add app/cv/track.py tests/test_cv_track.py
git commit -m "feat: resolve CV application track safely"
```

---

### Task 4: Deterministic evidence selector with exact/alias/related distinctions

**Files:**
- Create: `app/cv/selector.py`
- Create: `tests/test_cv_selector.py`

**Interfaces:**
- Consumes: `RadarAssessment.enrichment.requirements`, `MasterFactsSnapshot`, `EvidenceCatalogSnapshot`, `CVPolicy`, existing `TaxonomyResolver` from `app.radar.taxonomy`.
- Produces: `EvidenceSelector.select(...) -> EvidenceSelection`.

- [ ] **Step 1: Write RED selection tests**

Cover these exact invariants:

```python
def test_exact_verified_skill_support_outranks_related_skill() -> None:
    selection = selector.select(...)
    support = selection.requirement_support[0]
    assert support.level == "EXACT"
    assert support.fact_ids == ["skill-postgresql"]


def test_approved_alias_counts_as_full_support() -> None:
    # requirement "Postgres", verified fact "PostgreSQL", approved equivalence alias
    assert support.level == "ALIAS"


def test_taxonomy_related_does_not_support_exact_product_requirement() -> None:
    # requirement exact_product "PostGIS", candidate fact only "spatial databases"
    assert support.level == "UNSUPPORTED"
    assert "PostGIS" in selection.unsupported_requirements


def test_hospitality_module_cannot_enter_tech_selection() -> None:
    assert "hospitality-role" not in selection.selected_evidence_ids
```

Add deterministic-order test: equal relevance sorts by stable evidence-module ID.

- [ ] **Step 2: Verify RED**

```bash
python -m pytest tests/test_cv_selector.py -v
```

Expected: import failure for `app.cv.selector`.

- [ ] **Step 3: Implement selector scoring without prose generation**

Use only verified facts/modules in `application_track_id`. For skill requirements, pass verified skill fact values to the existing resolver:

```python
resolved = taxonomy_resolver.resolve_skill(requirement.value, candidate_skill_values)

if resolved.level == SkillMatchLevel.EXACT_VERIFIED:
    level, credit = "EXACT", 1.0
elif resolved.level == SkillMatchLevel.APPROVED_ALIAS:
    level, credit = "ALIAS", 1.0
elif resolved.level == SkillMatchLevel.TAXONOMY_RELATED and requirement.exactness != "exact_product":
    level, credit = "RELATED", 0.70
else:
    level, credit = "UNSUPPORTED", 0.0
```

Initial deterministic module relevance:

```text
+100 each mandatory EXACT/ALIAS requirement supported by module facts
 +70 each mandatory RELATED conceptual requirement
 +50 each preferred EXACT/ALIAS requirement
 +35 each preferred RELATED conceptual requirement
 +10 each normalized requirement/title keyword overlap with module keywords
  +5 if module contains evidence ID already cited by the radar match assessment
```

Sort by `(-score, module.id)` and cap by policy section limits. Store human-readable `selection_explanations`; selector does not write CV prose.

- [ ] **Step 4: Run selector and full regression tests**

```bash
python -m pytest tests/test_cv_selector.py -v
python -m pytest -v
```

Expected: all pass and V0.2A taxonomy tests remain unchanged.

- [ ] **Step 5: Commit Task 4**

```bash
git add app/cv/selector.py tests/test_cv_selector.py
git commit -m "feat: select CV evidence deterministically"
```

---

### Task 5: Provenance-backed deterministic CV composer

**Files:**
- Create: `app/cv/composer.py`
- Create: `tests/test_cv_composer.py`

**Interfaces:**
- Consumes: `EvidenceSelection`, snapshots, `CVPolicy`.
- Produces: `CVComposer.compose(...) -> CVDocumentModel`.

- [ ] **Step 1: Write RED composer tests**

Required cases:

```python
def test_same_inputs_produce_identical_document_model() -> None:
    first = composer.compose(...)
    second = composer.compose(...)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_every_visible_claim_has_provenance() -> None:
    document = composer.compose(...)
    for claim in document.iter_visible_claims():
        assert claim.claim_id in document.provenance_map


def test_role_specific_order_can_change_without_changing_fact_values() -> None:
    tech_document = composer.compose(...tech selection...)
    hospitality_document = composer.compose(...hospitality selection...)
    assert tech_document.experience != hospitality_document.experience
    assert master_facts.content_sha256 == original_hash
```

Also test ES/EN claim selection: if an approved claim has no requested-language text, it is omitted or blocked according to policy; it is never machine-translated silently.

- [ ] **Step 2: Verify RED**

```bash
python -m pytest tests/test_cv_composer.py -v
```

Expected: import failure for `app.cv.composer`.

- [ ] **Step 3: Implement claim construction with stable IDs**

Use fact IDs or approved-claim IDs as stable claim IDs rather than UUIDs:

```python
def _fact_claim(fact: MasterFact, *, kind: ClaimKind, language: str) -> CVClaim:
    text = fact.display_values.get(language, fact.value)
    return CVClaim(claim_id=f"fact:{fact.id}:{language}", kind=kind, text=text)


def _approved_claim(module: EvidenceModule, claim: ApprovedClaim, language: str) -> CVClaim | None:
    text = claim.text_by_language.get(language)
    if text is None:
        return None
    return CVClaim(
        claim_id=f"evidence:{module.id}:{claim.id}:{language}",
        kind=claim.kind,
        text=text,
    )
```

For every created claim, populate `provenance_map[claim_id] = ClaimProvenance(fact_ids=[...], evidence_ids=[...])`.

Initial composition policy:

```text
header: verified identity + contact + optional location
headline: highest-ranked approved headline claim for selected modules
summary: up to 2 approved summary claims
skills: supported/relevant verified skill facts, deterministic relevance then ID
experience: selected experience modules
projects: selected project modules
education: verified education facts/modules allowed for track
languages: verified language facts
links: verified link facts
```

The composer may reorder or omit; it may not alter an approved claim text.

- [ ] **Step 4: Run tests and regression suite**

```bash
python -m pytest tests/test_cv_composer.py -v
python -m pytest -v
```

Expected: all pass.

- [ ] **Step 5: Commit Task 5**

```bash
git add app/cv/composer.py tests/test_cv_composer.py
git commit -m "feat: compose provenance-backed CV models"
```

---

### Task 6: ClaimValidator hard gate

**Files:**
- Create: `app/cv/validator.py`
- Create: `tests/test_cv_validator.py`

**Interfaces:**
- Consumes: `CVDocumentModel`, snapshots, `application_track_id`.
- Produces: `ClaimValidator.validate(...) -> ValidationResult`.

- [ ] **Step 1: Write RED validation tests for every hard-error category**

Add focused tests:

```python
def test_unverified_fact_hard_fails() -> None:
    result = validator.validate(...)
    assert result.valid is False
    assert "unverified_fact" in {issue.code for issue in result.errors}


def test_cross_track_provenance_hard_fails() -> None:
    assert "incompatible_track" in error_codes


def test_missing_provenance_hard_fails() -> None:
    assert "missing_provenance" in error_codes


def test_modified_title_hard_fails() -> None:
    # visible title differs from direct fact/approved claim it cites
    assert "claim_text_mismatch" in error_codes


def test_numeric_bullet_requires_metric_fact() -> None:
    # approved bullet contains "30%" but provenance contains no metric fact
    assert "unsupported_metric" in error_codes


def test_unsupported_job_requirement_is_warning_not_invention() -> None:
    assert result.valid is True
    assert "unsupported_requirement" in warning_codes
```

- [ ] **Step 2: Verify RED**

```bash
python -m pytest tests/test_cv_validator.py -v
```

Expected: import failure for `app.cv.validator`.

- [ ] **Step 3: Implement validation indexes and exact-text authority rules**

Implement:

```python
class ClaimValidator:
    def validate(
        self,
        document: CVDocumentModel,
        master_facts: MasterFactsSnapshot,
        evidence_catalog: EvidenceCatalogSnapshot,
        application_track_id: str,
        unresolved_requirements: list[str],
    ) -> ValidationResult:
        ...
```

Rules:

1. Every `document.iter_visible_claims()` claim ID exists in `provenance_map`.
2. Every referenced fact/module exists and is verified.
3. Referenced fact/module contains `application_track_id` unless the fact is explicitly shared via multiple track IDs.
4. Direct fact claims (`fact:*`) must equal that fact's requested display value exactly.
5. Evidence claims (`evidence:*`) must equal one approved claim text in that module exactly.
6. Any visible numeric claim containing `\d` in a `summary`, `headline`, or `bullet` requires at least one referenced `metric` fact, except a `date` claim whose exact text is backed by a date/source fact.
7. Unknown posting requirements become warnings from `unresolved_requirements`; validator never writes replacement content.

- [ ] **Step 4: Run validator and full tests**

```bash
python -m pytest tests/test_cv_validator.py -v
python -m pytest -v
```

Expected: all pass.

- [ ] **Step 5: Commit Task 6**

```bash
git add app/cv/validator.py tests/test_cv_validator.py
git commit -m "feat: validate CV claims against verified evidence"
```

---

### Task 7: Deterministic ATS-first PDF renderer

**Files:**
- Create: `app/cv/renderer.py`
- Create: `tests/test_cv_renderer.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: validated `CVDocumentModel`, `ValidationResult`, output path.
- Produces: `ATSRenderer.render(...) -> RenderedCVArtifact` with path, SHA-256, byte size, renderer version.

- [ ] **Step 1: Add PDF dependencies and RED tests**

Modify `pyproject.toml`:

```toml
# runtime
dependencies = [
  "fastapi",
  "httpx",
  "pydantic>=2",
  "PyYAML",
  "reportlab>=4.2",
  "uvicorn",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "pypdf>=5"]
```

Create `tests/test_cv_renderer.py`:

```python
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


def test_renderer_refuses_invalid_document(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="validated"):
        renderer.render(document, invalid_validation, tmp_path / "cv.pdf")


def test_pdf_contains_selectable_candidate_text(tmp_path: Path) -> None:
    artifact = renderer.render(document, valid_validation, tmp_path / "cv.pdf")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(artifact.path).pages)
    assert "Alex Example" in text
    assert "PostGIS" in text


def test_identical_document_produces_identical_pdf_bytes(tmp_path: Path) -> None:
    first = renderer.render(document, valid_validation, tmp_path / "a.pdf")
    second = renderer.render(document, valid_validation, tmp_path / "b.pdf")
    assert Path(first.path).read_bytes() == Path(second.path).read_bytes()
    assert first.sha256 == second.sha256
```

- [ ] **Step 2: Verify RED**

```bash
python -m pytest tests/test_cv_renderer.py -v
```

Expected: import failure for `app.cv.renderer`.

- [ ] **Step 3: Implement one-column deterministic ReportLab renderer**

Use Platypus for text flow and a deterministic canvas:

```python
class DeterministicCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)


class ATSRenderer:
    renderer_version = "ats-pdf-v1"

    def render(
        self,
        document: CVDocumentModel,
        validation: ValidationResult,
        output_path: str | Path,
    ) -> RenderedCVArtifact:
        if not validation.valid:
            raise ValueError("CVDocumentModel must be validated before rendering")
        ...
        doc.build(story, canvasmaker=DeterministicCanvas)
        pdf_bytes = temp_path.read_bytes()
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        temp_path.replace(output_path)
        return RenderedCVArtifact(...)
```

Renderer rules:

```text
A4
single column
Helvetica / Helvetica-Bold built-in fonts only
9.5-11 pt body text
standard margins
no images
no icons
no skill bars
no tables/multi-column layout
fixed labels only from an es/en label dictionary
candidate text copied verbatim from CVDocumentModel
atomic temp-file -> final-file rename
```

Do not embed current timestamps or paths in metadata.

- [ ] **Step 4: Run renderer tests and verify PDF visually**

Run unit tests:

```bash
python -m pytest tests/test_cv_renderer.py -v
python -m pytest -v
```

Then generate a fictional fixture PDF in a temporary directory and, when the execution environment has the PDF skill installed, render it to PNG:

```bash
python /home/oai/skills/pdfs/scripts/render_pdf.py /tmp/opportunity-os-cv-fixture.pdf --out_dir /tmp/opportunity-os-cv-render --dpi 200
```

Inspect the rendered page(s) and reject the task if there is clipping, overlap, broken glyphs, unexpected columns, or invisible/selectability issues. Do not commit the PDF or render images.

- [ ] **Step 5: Commit Task 7**

```bash
git add app/cv/renderer.py tests/test_cv_renderer.py pyproject.toml
git commit -m "feat: render deterministic ATS CV PDFs"
```

---

### Task 8: ApplicationPacket and end-to-end CVPreparationService

**Files:**
- Create: `app/cv/service.py`
- Create: `tests/test_cv_service.py`

**Interfaces:**
- Consumes: all Task 1-7 units plus one `RadarAssessment`.
- Produces: `CVPreparationService.prepare(...) -> PreparationResult`.

- [ ] **Step 1: Write RED end-to-end preparation tests**

Required tests:

```python
def test_prepare_returns_packet_only_after_validation_and_render(tmp_path: Path) -> None:
    result = service.prepare(
        assessment=assessment,
        master_facts=master_facts,
        evidence_catalog=evidence_catalog,
        policy=policy,
        output_root=tmp_path,
        now=NOW,
    )
    assert result.status == "PREPARED"
    assert result.packet is not None
    assert Path(result.packet.cv_pdf_path).exists()
    assert len(result.packet.cv_sha256) == 64
    assert len(result.packet.packet_sha256) == 64


def test_blocked_missing_facts_creates_no_packet_or_pdf(tmp_path: Path) -> None:
    result = service.prepare(...insufficient facts...)
    assert result.status == "BLOCKED_MISSING_FACTS"
    assert result.packet is None
    assert list(tmp_path.rglob("*.pdf")) == []


def test_packet_hash_ignores_application_id_time_and_path(tmp_path: Path) -> None:
    first = service.prepare(...id_factory=lambda: "app-a", now=TIME_A, output_root=tmp_path / "a")
    second = service.prepare(...id_factory=lambda: "app-b", now=TIME_B, output_root=tmp_path / "b")
    assert first.packet.packet_sha256 == second.packet.packet_sha256


def test_packet_hash_changes_when_cv_semantics_change(tmp_path: Path) -> None:
    changed = master_facts_with_changed_verified_claim()
    assert prepare(changed).packet.packet_sha256 != prepare(original).packet.packet_sha256
```

Also test track unavailable, validator hard fail, renderer failure, and that renderer failure leaves no `PREPARED` packet.

- [ ] **Step 2: Verify RED**

```bash
python -m pytest tests/test_cv_service.py -v
```

Expected: import failure for `app.cv.service`.

- [ ] **Step 3: Implement semantic snapshot and packet hashing**

Add private helpers in `service.py`:

```python
def _opportunity_snapshot_hash(assessment: RadarAssessment) -> str:
    return canonical_sha256(assessment.opportunity.model_dump(mode="json"))


def _packet_content_payload(packet: ApplicationPacket) -> dict[str, object]:
    return {
        "opportunity_snapshot_hash": packet.opportunity_snapshot_hash,
        "selected_intent": packet.selected_intent,
        "application_track_id": packet.application_track_id,
        "scoring_version": packet.scoring_version,
        "extractor_version": packet.extractor_version,
        "alias_registry_version": packet.alias_registry_version,
        "taxonomy_versions": dict(sorted(packet.taxonomy_versions.items())),
        "master_facts_version": packet.master_facts_version,
        "evidence_catalog_version": packet.evidence_catalog_version,
        "composer_version": packet.composer_version,
        "cv_document_version": packet.cv_document_version,
        "renderer_version": packet.renderer_version,
        "selected_fact_ids": sorted(packet.selected_fact_ids),
        "selected_evidence_ids": sorted(packet.selected_evidence_ids),
        "unresolved_gaps": sorted(packet.unresolved_gaps),
        "cv_document": packet.cv_document.model_dump(mode="json"),
        "cv_sha256": packet.cv_sha256,
    }
```

Explicitly exclude `application_id`, `created_at`, `cv_pdf_path`.

- [ ] **Step 4: Implement orchestration and typed failure mapping**

Public signature:

```python
class CVPreparationService:
    def __init__(
        self,
        *,
        taxonomy_resolver: TaxonomyResolver,
        id_factory: Callable[[], str] | None = None,
        renderer: ATSRenderer | None = None,
    ) -> None: ...

    def prepare(
        self,
        assessment: RadarAssessment,
        master_facts: MasterFactsSnapshot,
        evidence_catalog: EvidenceCatalogSnapshot,
        policy: CVPolicy,
        output_root: str | Path,
        now: datetime,
    ) -> PreparationResult:
        ...
```

Exact orchestration order:

```text
validate catalog↔facts consistency
resolve application track
minimum evidence gate
EvidenceSelector.select
CVComposer.compose
ClaimValidator.validate
if invalid -> BLOCKED_VALIDATION, no renderer
render to artifacts/applications-like output root/application_id/cv.pdf
compute cv_sha256
construct PREPARED ApplicationPacket
compute semantic packet_sha256
return PreparationResult(status=PREPARED, packet=packet)
```

Catch only known typed preparation/render exceptions and return sanitized `ValidationIssue` codes. Unexpected programming errors should still fail tests rather than be swallowed.

- [ ] **Step 5: Run end-to-end and full regression tests**

```bash
python -m pytest tests/test_cv_service.py -v
python -m pytest -v
python -m compileall app
```

Expected: all pass.

- [ ] **Step 6: Commit Task 8**

```bash
git add app/cv/service.py tests/test_cv_service.py
git commit -m "feat: prepare reproducible CV application packets"
```

---

### Task 9: Release documentation, versioning, privacy CI, and final verification

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `.github/workflows/tests.yml` only if final privacy assertions need adjustment after Task 2
- Test: full existing suite + all V0.2B tests

**Interfaces:**
- Consumes: completed V0.2B subsystem.
- Produces: documented prerelease surface `0.2.0b1`, no new HTTP endpoints.

- [ ] **Step 1: Write documentation assertions before changing README/version**

Add a small regression in an existing README/version test file or create `tests/test_cv_release_contract.py`:

```python
from pathlib import Path
import tomllib


def test_package_is_v02b_prerelease() -> None:
    payload = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert payload["project"]["version"] == "0.2.0b1"


def test_readme_documents_cv_factory_without_claiming_auto_send() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    assert "CV Factory" in text
    assert "ApplicationPacket" in text
    assert "does not send" in text or "does not submit" in text
```

Run and confirm RED because version/README still describe `0.2.0a1`.

- [ ] **Step 2: Update prerelease version and README**

Set:

```toml
version = "0.2.0b1"
```

README V0.2B section must document:

```text
Radar selects opportunity
→ private verified facts/evidence
→ deterministic evidence selection
→ provenance-backed CVDocumentModel
→ hard ClaimValidator
→ one-column ATS PDF
→ reproducible ApplicationPacket
```

State explicitly that V0.2B does **not** discover recruiters, draft/send Gmail, submit forms, or auto-apply.

Document local private paths:

```text
profile/master_facts.local.yaml
profile/evidence_catalog.local.yaml
artifacts/applications/<application_id>/cv.pdf
```

- [ ] **Step 3: Strengthen final CI privacy guard if necessary**

The final workflow tracked-file guard must include at least:

```bash
'.env'
'profile.local.yaml'
'sources.local.yaml'
'profile/master_facts.local.yaml'
'profile/evidence_catalog.local.yaml'
'artifacts/applications/**'
'*.pdf'
'*.docx'
```

Public fictional YAML examples remain allowed.

- [ ] **Step 4: Run full release verification**

Run:

```bash
python -m pytest -v
python -m compileall app
git diff --check origin/main...HEAD
```

Then verify no forbidden tracked files:

```bash
forbidden="$(git ls-files -- '.env' 'profile.local.yaml' 'sources.local.yaml' 'profile/master_facts.local.yaml' 'profile/evidence_catalog.local.yaml' 'artifacts/applications/**' '*.pdf' '*.docx')"
test -z "$forbidden"
```

Expected: all commands exit 0.

- [ ] **Step 5: Verify final fictional PDF artifact without committing it**

Generate one end-to-end fictional CV using `CVPreparationService`, confirm `PreparationResult.status == PREPARED`, and inspect the PDF with pypdf plus render-first visual verification:

```bash
python /home/oai/skills/pdfs/scripts/render_pdf.py /tmp/opportunity-os-v02b-final/cv.pdf --out_dir /tmp/opportunity-os-v02b-final/rendered --dpi 200
```

Acceptance criteria: no clipping/overlap, one-column reading order, selectable text, standard headings, no images/bars/icons, and visible text matches the validated `CVDocumentModel`.

- [ ] **Step 6: Review the full branch against `main`**

Review specifically:

```text
privacy boundary
track isolation
fact verification semantics
exact-product/related distinction
provenance completeness
metric/title/date validation
PDF deterministic bytes
packet semantic hash exclusions
no V0.2C email/submission scope creep
V0.1/V0.2A API/scoring regression
```

Any discovered defect receives a new failing regression test before its fix.

- [ ] **Step 7: Commit Task 9**

```bash
git add README.md pyproject.toml .github/workflows/tests.yml tests/test_cv_release_contract.py
git commit -m "docs: finalize Opportunity OS V0.2B CV Factory"
```

- [ ] **Step 8: Open a Draft PR only after fresh verification**

Target `main`, summarize exact scope and include test/compile/privacy/PDF-verification evidence. Keep it Draft during code review. Do not merge until the user explicitly chooses merge after the PR checks and review are green.

---

## Implementation Order and Checkpoints

Execute strictly in this order:

```text
Task 1  contracts + hashing
  ↓
Task 2  private loaders + privacy guards
  ↓
Task 3  application track + minimum evidence
  ↓
Task 4  evidence selector
  ↓
Task 5  composer
  ↓
Task 6  validator hard gate
  ↓
Task 7  deterministic ATS PDF
  ↓
Task 8  ApplicationPacket + service
  ↓
Task 9  release verification + Draft PR
```

Checkpoint after every task:

```text
1. confirm the intended RED reason
2. minimal GREEN implementation
3. run task-specific tests
4. run full pytest regression
5. inspect task diff for scope creep/private data
6. commit
7. update private Opportunity OS handoff with task status/SHA only when useful
```

Do not create a real personal master-facts file in GitHub. When the public engine is green, real candidate facts may be assembled privately from user-reviewed CV/context in a later local/private operation.
