# Opportunity OS V0.2B CV Factory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, evidence-backed CV factory that turns one selected `RadarAssessment` into a truthful ATS-first PDF and a reproducible `ApplicationPacket` without sending, submitting, or inventing candidate claims.

**Architecture:** V0.2B adds a focused `app/cv/` subsystem. Strict private snapshots hold verified facts and approved evidence modules; the radar-selected track limits the evidence pool; a deterministic selector maps posting requirements to verified support; a composer builds a provenance-backed structured document; a validator hard-gates every visible candidate claim; a deterministic ReportLab renderer creates one ATS-first PDF; and `CVPreparationService` returns either a prepared packet or a typed blocked result. Recruiter discovery, Gmail, approval, and submission remain V0.2C.

**Tech Stack:** Python >=3.12, Pydantic v2, PyYAML, existing Opportunity OS radar models and `TaxonomyResolver`, ReportLab >=4.2, pypdf >=5 as a dev-only assertion dependency, pytest/pytest-asyncio, SHA-256 canonical JSON hashing.

**Spec:** `docs/superpowers/specs/2026-08-28-opportunity-os-v0.2b-cv-factory-design.md` plus normative clarification `docs/superpowers/specs/2026-08-28-opportunity-os-v0.2b-cv-factory-self-review.md`

## Global Constraints

- Python remains `>=3.12`.
- Existing V0.1 and V0.2A1 API routes and radar scoring behavior remain unchanged.
- Real master facts, contact data, recruiter data, real generated CV files, and real application packets never enter the public repository.
- V0.2B performs no Gmail operation, recruiter discovery, Apollo enrichment, form submission, ATS submission, browser automation, approval, or send action.
- `verified=true` requires a verification method and timezone-aware `verified_at`.
- Evidence-backed verification methods require `source_ref`; `manual_confirmation` is allowed only for legitimate self-attested identity/contact/location data and explicitly reviewed wording.
- `manual_confirmation` does not establish employment, education, certifications, metrics, tools, dates, or external outcomes.
- The selected application track is a hard evidence boundary. No other track may be borrowed to fill a section.
- An unsupported posting requirement remains a gap or warning unless `CVPolicy` explicitly declares it a preparation prerequisite.
- The composer and renderer need no network and no LLM.
- The renderer may add only fixed localized section labels without provenance. Every candidate-specific visible string must come from a validated `CVClaim`.
- `ApplicationPacket` exists only for `PREPARED`. Blocked outcomes have `packet=None`.
- `packet_sha256` excludes `application_id`, `created_at`, `cv_pdf_path`, load timestamps, and filesystem-specific values.
- Identical validated `CVDocumentModel` plus identical renderer version and renderer policy must produce stable PDF bytes in fixtures.
- V0.2B ships one ATS-first, one-column PDF layout. DOCX and alternative visual layouts remain excluded.
- CI remains offline.

## File Structure

```text
app/cv/
  __init__.py
  models.py
  hashing.py
  loaders.py
  track.py
  selector.py
  composer.py
  validator.py
  renderer.py
  service.py

config/
  master_facts.example.yaml
  evidence_catalog.example.yaml

tests/
  cv_factories.py
  fixtures/cv/master_facts.yaml
  fixtures/cv/evidence_catalog.yaml
  test_cv_models.py
  test_cv_loaders.py
  test_cv_track.py
  test_cv_selector.py
  test_cv_composer.py
  test_cv_validator.py
  test_cv_renderer.py
  test_cv_service.py
  test_cv_release_contract.py
```

Existing files modified only where necessary:

```text
.gitignore
.github/workflows/tests.yml
pyproject.toml
README.md
```

---

### Task 1: CV contracts, test factories, and canonical hashing

**Files:**
- Create: `app/cv/__init__.py`
- Create: `app/cv/models.py`
- Create: `app/cv/hashing.py`
- Create: `tests/cv_factories.py`
- Create: `tests/test_cv_models.py`

**Interfaces:**
- Consumes: `SearchIntent`, `Opportunity`, `OpportunityEnrichment`, `EligibilityResult`, `ConfidenceAssessment`, `RadarAssessment`.
- Produces: all V0.2B domain contracts plus `canonical_json_bytes()` and `canonical_sha256()`.

- [ ] **Step 1: Write the contract tests first**

Create `tests/test_cv_models.py`:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.cv.hashing import canonical_sha256
from app.cv.models import MasterFact, PreparationResult, ValidationIssue

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def test_verified_fact_requires_verification_metadata() -> None:
    with pytest.raises(ValidationError):
        MasterFact(
            id="skill-postgis",
            kind="skill",
            value="PostGIS",
            track_ids=["tech"],
            verified=True,
        )


def test_manual_confirmation_allows_self_attested_contact_without_source_ref() -> None:
    fact = MasterFact(
        id="contact-email",
        kind="contact",
        value="alex@example.test",
        track_ids=["tech", "hospitality"],
        verified=True,
        verification_method="manual_confirmation",
        verified_at=NOW,
    )
    assert fact.source_ref is None


def test_evidence_backed_fact_requires_source_ref() -> None:
    with pytest.raises(ValidationError):
        MasterFact(
            id="skill-python",
            kind="skill",
            value="Python",
            track_ids=["tech"],
            verified=True,
            verification_method="repository_evidence",
            verified_at=NOW,
        )


def test_blocked_result_cannot_contain_packet() -> None:
    with pytest.raises(ValidationError):
        PreparationResult(
            status="BLOCKED_VALIDATION",
            packet={"status": "PREPARED"},
            errors=[ValidationIssue(code="claim_validation_failed", message="blocked")],
        )


def test_canonical_hash_ignores_mapping_key_order_but_keeps_list_order() -> None:
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})
    assert canonical_sha256({"bullets": ["A", "B"]}) != canonical_sha256({"bullets": ["B", "A"]})
```

- [ ] **Step 2: Run the test and confirm RED**

```bash
python -m pytest tests/test_cv_models.py -v
```

Expected: import failure because `app.cv` does not exist.

- [ ] **Step 3: Implement strict contracts**

Create `app/cv/models.py` with `ConfigDict(extra="forbid")` and these public literals/classes:

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
SupportLevel = Literal["EXACT", "ALIAS", "RELATED", "UNSUPPORTED"]
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

class MasterFactsSnapshot(StrictCVModel):
    schema_version: str = Field(min_length=1)
    content_sha256: str = Field(min_length=64, max_length=64)
    facts: list[MasterFact]

class EvidenceCatalogSnapshot(StrictCVModel):
    schema_version: str = Field(min_length=1)
    content_sha256: str = Field(min_length=64, max_length=64)
    modules: list[EvidenceModule]

class CVPolicy(StrictCVModel):
    language: Literal["es", "en"] = "en"
    required_sections: list[CVSection] = Field(default_factory=lambda: ["experience"])
    max_summary_claims: int = Field(default=2, ge=0, le=4)
    max_experience_modules: int = Field(default=3, ge=0, le=6)
    max_project_modules: int = Field(default=3, ge=0, le=6)
    max_bullets_per_module: int = Field(default=4, ge=1, le=8)

class RequirementSupport(StrictCVModel):
    requirement_value: str
    importance: str
    exactness: str
    level: SupportLevel
    fact_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

class EvidenceSelection(StrictCVModel):
    application_track_id: str
    selected_fact_ids: list[str]
    selected_evidence_ids: list[str]
    requirement_support: list[RequirementSupport]
    unsupported_requirements: list[str]
    selection_explanations: list[str]

class CVClaim(StrictCVModel):
    claim_id: str
    kind: ClaimKind
    text: str

class ClaimProvenance(StrictCVModel):
    fact_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    approved_claim_id: str | None = None

class CVEntry(StrictCVModel):
    entry_id: str
    heading: CVClaim
    subheading: CVClaim | None = None
    date_range: CVClaim | None = None
    bullets: list[CVClaim] = Field(default_factory=list)

class CVDocumentModel(StrictCVModel):
    document_version: str
    language: Literal["es", "en"]
    header: list[CVClaim]
    headline: CVClaim | None = None
    summary: list[CVClaim] = Field(default_factory=list)
    skills: list[CVClaim] = Field(default_factory=list)
    experience: list[CVEntry] = Field(default_factory=list)
    projects: list[CVEntry] = Field(default_factory=list)
    education: list[CVEntry] = Field(default_factory=list)
    languages: list[CVClaim] = Field(default_factory=list)
    links: list[CVClaim] = Field(default_factory=list)
    provenance_map: dict[str, ClaimProvenance]

class ValidationIssue(StrictCVModel):
    code: str
    message: str
    claim_id: str | None = None

class ValidationResult(StrictCVModel):
    valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    validated_claim_ids: list[str] = Field(default_factory=list)

class RenderedCVArtifact(StrictCVModel):
    path: str
    sha256: str = Field(min_length=64, max_length=64)
    byte_size: int = Field(gt=0)
    renderer_version: str

class ApplicationPacket(StrictCVModel):
    application_id: str
    opportunity_id: str
    opportunity_snapshot_hash: str
    radar_batch_id: str | None = None
    selected_intent: SearchIntent | None = None
    application_track_id: str
    match_score: float | None = None
    income_viability: float | None = None
    confidence_score: float
    scoring_version: str
    extractor_version: str
    alias_registry_version: str
    taxonomy_versions: dict[str, str]
    master_facts_version: str
    evidence_catalog_version: str
    composer_version: str
    cv_document_version: str
    renderer_version: str
    selected_fact_ids: list[str]
    selected_evidence_ids: list[str]
    unresolved_gaps: list[str]
    cv_document: CVDocumentModel
    cv_pdf_path: str
    cv_sha256: str
    packet_sha256: str
    status: Literal["PREPARED"] = "PREPARED"
    created_at: datetime

class PreparationResult(StrictCVModel):
    status: PreparationStatus
    packet: ApplicationPacket | None = None
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
```

Add model validators enforcing aware datetimes, verification metadata, and `packet is not None` if and only if status is `PREPARED`.

Add `CVDocumentModel.iter_visible_claims()` returning header, headline, summary, skills, every entry heading/subheading/date/bullet, languages, and links in rendered order.

- [ ] **Step 4: Implement hashing helpers**

Create `app/cv/hashing.py`:

```python
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

- [ ] **Step 5: Create reusable fictional test factories**

Create `tests/cv_factories.py` with a fixed aware `NOW`, `make_fact()`, `make_master_snapshot()`, `make_evidence_catalog()`, `make_policy()`, and this radar factory:

```python
from datetime import datetime, timezone

from app.models.domain import Opportunity
from app.radar.models import (
    ConfidenceAssessment,
    EligibilityResult,
    OpportunityEnrichment,
    RadarAssessment,
    Requirement,
    DerivedValue,
)

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def make_radar_assessment(
    *,
    selected_intent: str = "CAREER",
    best_career_track: str | None = "tech",
    best_income_track: str | None = "tech",
    requirement_value: str = "PostGIS",
    requirement_exactness: str = "exact_product",
) -> RadarAssessment:
    opportunity = Opportunity(
        id="opp-1",
        source="manual",
        source_id="fixture-1",
        source_url="https://example.test/jobs/1",
        company="Example Labs",
        title="GIS Developer",
        description="Required: PostGIS.",
        discovered_at=NOW,
        published_at=NOW,
        status="found",
        location="Cordoba, Argentina",
        remote_policy="remote",
        required_skills=[requirement_value],
    )
    requirement = Requirement(
        kind="skill",
        value=requirement_value,
        importance="mandatory",
        exactness=requirement_exactness,
        provenance=DerivedValue[str](
            value=requirement_value,
            source_text=f"Required: {requirement_value}.",
            source_field="description",
            extraction_method="explicit_rule",
            confidence=0.9,
        ),
    )
    enrichment = OpportunityEnrichment(
        opportunity_id=opportunity.id,
        requirements=[requirement],
        extractor_version="rules-v1",
        created_at=NOW,
    )
    confidence = ConfidenceAssessment(
        score=80,
        requirement_extraction_quality=80,
        skill_normalization_coverage=80,
        evidence_traceability=80,
        seniority_location_legal_clarity=80,
        source_freshness_completeness=80,
    )
    return RadarAssessment(
        opportunity=opportunity,
        enrichment=enrichment,
        eligibility=EligibilityResult(eligible=True),
        best_career_track=best_career_track,
        career_match=82 if best_career_track else None,
        best_income_track=best_income_track,
        income_viability=78 if best_income_track else None,
        confidence_score=80,
        confidence_breakdown=confidence,
        intent_tiers={"CAREER": "HIGH", "INCOME_NOW": "HIGH"},
        priority_score=81,
        selected_intent=selected_intent,
        scoring_version="v0.2a.1",
        extractor_version="rules-v1",
        alias_registry_version="aliases-v1",
        taxonomy_versions={},
    )
```

All other test factories use only fictional values and `.test` domains.

- [ ] **Step 6: Run Task 1 and full regression tests**

```bash
python -m pytest tests/test_cv_models.py -v
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 1**

```bash
git add app/cv tests/cv_factories.py tests/test_cv_models.py
git commit -m "feat: add CV factory contracts and hashing"
```

---

### Task 2: Private snapshot loaders, canonical fingerprints, examples, and privacy guards

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
- Consumes: Task 1 models and hashes.
- Produces: `load_master_facts()`, `load_evidence_catalog()`, `validate_catalog_against_facts()`.

- [ ] **Step 1: Write complete RED loader tests**

Create `tests/test_cv_loaders.py`:

```python
from pathlib import Path

import pytest

from app.cv.loaders import (
    load_evidence_catalog,
    load_master_facts,
    validate_catalog_against_facts,
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_master_fingerprint_ignores_fact_order(tmp_path: Path) -> None:
    first = _write(
        tmp_path / "first.yaml",
        "schema_version: v1\nfacts:\n"
        "  - {id: a, kind: skill, value: PostGIS, track_ids: [tech], verified: false}\n"
        "  - {id: b, kind: skill, value: Python, track_ids: [tech], verified: false}\n",
    )
    second = _write(
        tmp_path / "second.yaml",
        "schema_version: v1\nfacts:\n"
        "  - {id: b, kind: skill, value: Python, track_ids: [tech], verified: false}\n"
        "  - {id: a, kind: skill, value: PostGIS, track_ids: [tech], verified: false}\n",
    )
    assert load_master_facts(first).content_sha256 == load_master_facts(second).content_sha256


def test_duplicate_fact_ids_are_rejected(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "duplicate.yaml",
        "schema_version: v1\nfacts:\n"
        "  - {id: a, kind: skill, value: PostGIS, verified: false}\n"
        "  - {id: a, kind: skill, value: Python, verified: false}\n",
    )
    with pytest.raises(ValueError, match="duplicate fact id"):
        load_master_facts(source)


def test_catalog_reference_to_missing_fact_is_rejected(tmp_path: Path) -> None:
    facts = load_master_facts(
        _write(
            tmp_path / "facts.yaml",
            "schema_version: v1\nfacts:\n"
            "  - {id: known, kind: skill, value: PostGIS, track_ids: [tech], verified: false}\n",
        )
    )
    catalog = load_evidence_catalog(
        _write(
            tmp_path / "catalog.yaml",
            "schema_version: v1\nmodules:\n"
            "  - id: module-1\n"
            "    track_ids: [tech]\n"
            "    label: Missing ref\n"
            "    fact_ids: [missing]\n"
            "    claims: []\n"
            "    verified: false\n",
        )
    )
    with pytest.raises(ValueError, match="missing fact"):
        validate_catalog_against_facts(catalog, facts)
```

Add one more test where a `verified: true` module contains an unverified fact and assert `ValueError("verified module references unverified fact")`.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_cv_loaders.py -v
```

Expected: import failure because `app.cv.loaders` does not exist.

- [ ] **Step 3: Implement deterministic YAML loaders**

Create `app/cv/loaders.py` with `yaml.safe_load()`, mapping checks, unique-ID checks, and stable-ID canonicalization:

```python
def _master_payload(schema_version: str, facts: list[MasterFact]) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "facts": [
            fact.model_dump(mode="json")
            for fact in sorted(facts, key=lambda item: item.id)
        ],
    }


def load_master_facts(path: str | Path) -> MasterFactsSnapshot:
    payload = _load_yaml_mapping(path, label="master facts")
    schema_version = str(payload.get("schema_version", "")).strip()
    if not schema_version:
        raise ValueError("master facts schema_version is required")
    raw_facts = payload.get("facts")
    if not isinstance(raw_facts, list):
        raise ValueError("master facts facts must be a list")
    facts = [MasterFact.model_validate(raw) for raw in raw_facts]
    _require_unique_ids([fact.id for fact in facts], label="fact")
    content_sha256 = canonical_sha256(_master_payload(schema_version, facts))
    return MasterFactsSnapshot(
        schema_version=schema_version,
        content_sha256=content_sha256,
        facts=sorted(facts, key=lambda item: item.id),
    )
```

Implement the analogous catalog loader. `validate_catalog_against_facts()` builds fact/module indexes and enforces every module/claim reference, verified module integrity, and non-empty approved-claim language text.

- [ ] **Step 4: Add fictional public YAML examples**

`config/master_facts.example.yaml` and test fixture use only `Alex Example`, `.test` contact values, fictional employers, and two tracks named `tech` and `hospitality`. Include verified examples for identity, contact, location, PostGIS, Python, a fictional tech role, a fictional hospitality role, and one metric with evidence-backed verification.

`config/evidence_catalog.example.yaml` includes one `tech-project`, one `tech-experience`, and one `hospitality-experience` module. Each approved claim contains `es` and `en` text and references explicit fact IDs.

- [ ] **Step 5: Extend private file ignores and CI guard**

Append to `.gitignore`:

```gitignore
profile/master_facts.local.yaml
profile/evidence_catalog.local.yaml
artifacts/applications/
```

Extend the CI tracked-file guard with these exact patterns while preserving the existing PDF/DOCX ban:

```bash
'profile/master_facts.local.yaml'
'profile/evidence_catalog.local.yaml'
'artifacts/applications/**'
```

- [ ] **Step 6: Run loaders, full tests, and compile check**

```bash
python -m pytest tests/test_cv_loaders.py -v
python -m pytest -v
python -m compileall app
```

Expected: all exit 0.

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
- Consumes: `RadarAssessment`, snapshots, `CVPolicy`.
- Produces: `resolve_application_track()` and `check_minimum_evidence()`.

- [ ] **Step 1: Write RED track tests**

Create `tests/test_cv_track.py`:

```python
import pytest

from app.cv.track import TrackUnavailableError, check_minimum_evidence, resolve_application_track
from tests.cv_factories import make_evidence_catalog, make_master_snapshot, make_policy, make_radar_assessment


def test_selected_income_lane_uses_income_track() -> None:
    assessment = make_radar_assessment(
        selected_intent="INCOME_NOW",
        best_career_track="tech",
        best_income_track="hospitality",
    )
    assert resolve_application_track(assessment) == "hospitality"


def test_missing_selected_lane_falls_back_to_other_winning_track() -> None:
    assessment = make_radar_assessment(
        selected_intent="CAREER",
        best_career_track=None,
        best_income_track="tech",
    )
    assert resolve_application_track(assessment) == "tech"


def test_no_winning_track_fails_safely() -> None:
    assessment = make_radar_assessment(
        best_career_track=None,
        best_income_track=None,
    )
    with pytest.raises(TrackUnavailableError, match="No qualifying application track"):
        resolve_application_track(assessment)


def test_hospitality_evidence_does_not_satisfy_tech_minimum() -> None:
    issues = check_minimum_evidence(
        track_id="tech",
        master_facts=make_master_snapshot(include_tech_evidence=False),
        catalog=make_evidence_catalog(include_tech=False, include_hospitality=True),
        policy=make_policy(),
    )
    assert "insufficient_verified_evidence" in {issue.code for issue in issues}
```

- [ ] **Step 2: Confirm RED**

```bash
python -m pytest tests/test_cv_track.py -v
```

Expected: import failure for `app.cv.track`.

- [ ] **Step 3: Implement exact track and minimum-evidence rules**

Create `app/cv/track.py`:

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

`check_minimum_evidence()` returns issues if any of these are missing:

```text
one verified identity fact allowed for the selected track
one verified contact fact allowed for the selected track
one verified experience or project module allowed for the selected track
any section named in policy.required_sections
```

Facts explicitly shared by listing multiple `track_ids` are allowed. No other cross-track fallback is allowed.

- [ ] **Step 4: Run task and full tests**

```bash
python -m pytest tests/test_cv_track.py -v
python -m pytest -v
```

Expected: all pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add app/cv/track.py tests/test_cv_track.py
git commit -m "feat: resolve CV application tracks safely"
```

---

### Task 4: Deterministic evidence selector with exact, alias, related, and unsupported support levels

**Files:**
- Create: `app/cv/selector.py`
- Create: `tests/test_cv_selector.py`

**Interfaces:**
- Consumes: posting requirements, snapshots, `application_track_id`, `CVPolicy`, existing `TaxonomyResolver`.
- Produces: `EvidenceSelector.select() -> EvidenceSelection`.

- [ ] **Step 1: Write RED selector tests**

Create explicit fixtures using Task 1 factories and the existing `AliasRegistry`/`TaxonomyResolver`. Required assertions:

```python
def test_exact_verified_skill_is_exact_support(selector, inputs) -> None:
    selection = selector.select(**inputs)
    support = next(item for item in selection.requirement_support if item.requirement_value == "PostGIS")
    assert support.level == "EXACT"
    assert support.fact_ids == ["skill-postgis"]


def test_approved_equivalence_alias_is_full_support(selector, postgres_inputs) -> None:
    selection = selector.select(**postgres_inputs)
    support = next(item for item in selection.requirement_support if item.requirement_value == "Postgres")
    assert support.level == "ALIAS"


def test_related_skill_cannot_satisfy_exact_product(selector, related_inputs) -> None:
    selection = selector.select(**related_inputs)
    support = next(item for item in selection.requirement_support if item.requirement_value == "PostGIS")
    assert support.level == "UNSUPPORTED"
    assert "PostGIS" in selection.unsupported_requirements


def test_other_track_module_is_never_selected(selector, tech_inputs) -> None:
    selection = selector.select(**tech_inputs)
    assert "hospitality-experience" not in selection.selected_evidence_ids
```

Add an equal-score test asserting stable ID tiebreak order `module-a` before `module-b`.

- [ ] **Step 2: Confirm RED**

```bash
python -m pytest tests/test_cv_selector.py -v
```

Expected: import failure for `app.cv.selector`.

- [ ] **Step 3: Implement requirement support using the existing resolver**

Create `EvidenceSelector` with:

```python
resolved = self.taxonomy_resolver.resolve_skill(requirement.value, candidate_skill_values)
if resolved.level == SkillMatchLevel.EXACT_VERIFIED:
    level = "EXACT"
elif resolved.level == SkillMatchLevel.APPROVED_ALIAS:
    level = "ALIAS"
elif resolved.level == SkillMatchLevel.TAXONOMY_RELATED and requirement.exactness != "exact_product":
    level = "RELATED"
else:
    level = "UNSUPPORTED"
```

Map supporting skill facts to evidence modules through module `fact_ids`.

Initial deterministic module relevance:

```text
mandatory EXACT or ALIAS support       +100
mandatory RELATED conceptual support    +70
preferred EXACT or ALIAS support         +50
preferred RELATED conceptual support     +35
normalized title/requirement keyword hit +10 each unique hit
radar evidence overlap                    +5
```

Sort modules by `(-relevance, module.id)`. Apply `max_experience_modules` and `max_project_modules` by section. `selected_fact_ids` is the sorted union of selected module facts plus direct supported skill facts. The selector writes explanations, never CV prose.

- [ ] **Step 4: Run selector and regression tests**

```bash
python -m pytest tests/test_cv_selector.py -v
python -m pytest -v
```

Expected: all pass and existing taxonomy tests remain unchanged.

- [ ] **Step 5: Commit Task 4**

```bash
git add app/cv/selector.py tests/test_cv_selector.py
git commit -m "feat: select CV evidence deterministically"
```

---

### Task 5: Deterministic provenance-backed `CVDocumentModel` composer

**Files:**
- Create: `app/cv/composer.py`
- Create: `tests/test_cv_composer.py`

**Interfaces:**
- Consumes: `EvidenceSelection`, snapshots, `CVPolicy`.
- Produces: `CVComposer.compose() -> CVDocumentModel`.

- [ ] **Step 1: Write RED composer tests**

```python
def test_same_inputs_produce_identical_document_model(composer_inputs) -> None:
    first = CVComposer().compose(**composer_inputs)
    second = CVComposer().compose(**composer_inputs)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_every_visible_claim_has_provenance(composer_inputs) -> None:
    document = CVComposer().compose(**composer_inputs)
    for claim in document.iter_visible_claims():
        assert claim.claim_id in document.provenance_map


def test_requested_language_uses_only_approved_text(composer_inputs) -> None:
    composer_inputs["policy"] = composer_inputs["policy"].model_copy(update={"language": "es"})
    document = CVComposer().compose(**composer_inputs)
    assert any("Desarroll" in claim.text for claim in document.summary + ([document.headline] if document.headline else []))
    assert all("Generated translation" not in claim.text for claim in document.iter_visible_claims())


def test_unselected_hospitality_claim_never_enters_tech_document(composer_inputs) -> None:
    document = CVComposer().compose(**composer_inputs)
    assert all("Restaurant" not in claim.text for claim in document.iter_visible_claims())
```

- [ ] **Step 2: Confirm RED**

```bash
python -m pytest tests/test_cv_composer.py -v
```

Expected: import failure for `app.cv.composer`.

- [ ] **Step 3: Implement stable claim creation**

Use these exact conventions:

```python
def fact_claim(fact: MasterFact, kind: ClaimKind, language: str) -> tuple[CVClaim, ClaimProvenance]:
    text = fact.display_values.get(language, fact.value)
    claim = CVClaim(claim_id=f"fact:{fact.id}:{language}", kind=kind, text=text)
    provenance = ClaimProvenance(fact_ids=[fact.id])
    return claim, provenance


def evidence_claim(module: EvidenceModule, approved: ApprovedClaim, language: str) -> tuple[CVClaim, ClaimProvenance] | None:
    text = approved.text_by_language.get(language)
    if text is None:
        return None
    claim = CVClaim(
        claim_id=f"evidence:{module.id}:{approved.id}:{language}",
        kind=approved.kind,
        text=text,
    )
    provenance = ClaimProvenance(
        fact_ids=sorted(approved.fact_ids),
        evidence_ids=[module.id],
        approved_claim_id=approved.id,
    )
    return claim, provenance
```

Composition order:

```text
header      verified identity, contact, optional location facts
headline    highest-ranked selected approved headline; fallback to verified role fact
summary     first policy.max_summary_claims selected approved summary claims
skills      relevant verified skill facts from selection, sorted by selector relevance then fact ID
experience  selected experience modules in selector order
projects    selected project modules in selector order
education   verified education modules/facts allowed for selected track
languages   verified language facts allowed for selected track
links       verified link facts allowed for selected track
```

For an experience entry, approved `title`, `organization`, and `date` claims populate heading/subheading/date and approved `bullet` claims populate bullets up to `max_bullets_per_module`. A project entry uses `project` as heading, optional date, and bullets. Missing requested-language text is omitted; no translation is generated.

- [ ] **Step 4: Run composer and full tests**

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

### Task 6: `ClaimValidator` hard gate

**Files:**
- Create: `app/cv/validator.py`
- Create: `tests/test_cv_validator.py`

**Interfaces:**
- Consumes: `CVDocumentModel`, snapshots, selected track, unresolved requirements.
- Produces: `ClaimValidator.validate() -> ValidationResult`.

- [ ] **Step 1: Write RED hard-gate tests**

```python
def test_unverified_fact_is_hard_error(validation_inputs) -> None:
    result = ClaimValidator().validate(**validation_inputs_with_unverified_fact(validation_inputs))
    assert result.valid is False
    assert "unverified_fact" in {item.code for item in result.errors}


def test_cross_track_fact_is_hard_error(validation_inputs) -> None:
    result = ClaimValidator().validate(**validation_inputs_with_cross_track_fact(validation_inputs))
    assert "incompatible_track" in {item.code for item in result.errors}


def test_missing_claim_provenance_is_hard_error(validation_inputs) -> None:
    result = ClaimValidator().validate(**validation_inputs_without_one_provenance_entry(validation_inputs))
    assert "missing_provenance" in {item.code for item in result.errors}


def test_modified_direct_fact_text_is_hard_error(validation_inputs) -> None:
    result = ClaimValidator().validate(**validation_inputs_with_modified_title(validation_inputs))
    assert "claim_text_mismatch" in {item.code for item in result.errors}


def test_numeric_bullet_requires_metric_fact(validation_inputs) -> None:
    result = ClaimValidator().validate(**validation_inputs_with_unbacked_numeric_bullet(validation_inputs))
    assert "unsupported_metric" in {item.code for item in result.errors}


def test_unsupported_requirement_is_warning_only(validation_inputs) -> None:
    payload = dict(validation_inputs)
    payload["unresolved_requirements"] = ["Kubernetes"]
    result = ClaimValidator().validate(**payload)
    assert result.valid is True
    assert "unsupported_requirement" in {item.code for item in result.warnings}
```

The helper transforms named above are local pure test helpers in `tests/test_cv_validator.py`; each copies the base Pydantic model with `model_copy(deep=True)` and changes exactly one fact/claim/provenance field.

- [ ] **Step 2: Confirm RED**

```bash
python -m pytest tests/test_cv_validator.py -v
```

Expected: import failure for `app.cv.validator`.

- [ ] **Step 3: Implement validation authority rules**

`ClaimValidator.validate()` must perform these checks in deterministic claim order:

```text
1. every visible claim has provenance
2. every referenced fact exists and is verified
3. every referenced evidence module exists and is verified
4. every referenced fact/module permits application_track_id
5. direct fact claim text exactly equals the fact's requested display value
6. evidence claim text exactly equals the approved claim text for document.language
7. summary/headline/bullet text containing digits requires a referenced metric fact
8. unresolved posting requirements create warnings only
```

For direct facts, identify authority from `ClaimProvenance.approved_claim_id is None` and require one primary fact whose display text matches. For evidence claims, locate `approved_claim_id` inside the referenced module and require exact text equality.

Return `validated_claim_ids` only for claims with no hard error. `valid` is `not errors`.

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

### Task 7: Deterministic one-column ATS PDF renderer

**Files:**
- Create: `app/cv/renderer.py`
- Create: `tests/test_cv_renderer.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: validated `CVDocumentModel` and output path.
- Produces: `ATSRenderer.render() -> RenderedCVArtifact`.

- [ ] **Step 1: Add dependencies and RED renderer tests**

Modify dependencies to include:

```toml
"reportlab>=4.2"
```

Modify dev dependencies to include:

```toml
"pypdf>=5"
```

Create tests:

```python
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.cv.renderer import ATSRenderer


def test_renderer_rejects_invalid_validation(valid_document, invalid_validation, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="validated"):
        ATSRenderer().render(valid_document, invalid_validation, tmp_path / "cv.pdf")


def test_pdf_contains_selectable_candidate_text(valid_document, valid_validation, tmp_path: Path) -> None:
    artifact = ATSRenderer().render(valid_document, valid_validation, tmp_path / "cv.pdf")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(artifact.path).pages)
    assert "Alex Example" in text
    assert "PostGIS" in text


def test_identical_document_produces_identical_pdf_bytes(valid_document, valid_validation, tmp_path: Path) -> None:
    first = ATSRenderer().render(valid_document, valid_validation, tmp_path / "a.pdf")
    second = ATSRenderer().render(valid_document, valid_validation, tmp_path / "b.pdf")
    assert Path(first.path).read_bytes() == Path(second.path).read_bytes()
    assert first.sha256 == second.sha256
```

- [ ] **Step 2: Confirm RED**

```bash
python -m pytest tests/test_cv_renderer.py -v
```

Expected: import failure for `app.cv.renderer`.

- [ ] **Step 3: Implement deterministic ReportLab rendering**

Use Platypus plus invariant canvas:

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
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_suffix(".tmp.pdf")
        story = self._build_story(document)
        doc = SimpleDocTemplate(
            str(temp),
            pagesize=A4,
            leftMargin=42,
            rightMargin=42,
            topMargin=36,
            bottomMargin=36,
            title="CV",
            author="",
        )
        doc.build(story, canvasmaker=DeterministicCanvas)
        payload = temp.read_bytes()
        sha256 = hashlib.sha256(payload).hexdigest()
        temp.replace(output)
        return RenderedCVArtifact(
            path=str(output),
            sha256=sha256,
            byte_size=len(payload),
            renderer_version=self.renderer_version,
        )
```

`_build_story()` uses only built-in Helvetica/Helvetica-Bold fonts, 9.5-11 pt body text, one column, no images, no icons, no tables, no skill bars. Escape claim text before `Paragraph`. Fixed section labels are selected only from:

```python
LABELS = {
    "en": {"experience": "Experience", "projects": "Projects", "education": "Education", "skills": "Skills", "languages": "Languages"},
    "es": {"experience": "Experiencia", "projects": "Proyectos", "education": "Educacion", "skills": "Habilidades", "languages": "Idiomas"},
}
```

The renderer must never rewrite a claim string.

- [ ] **Step 4: Run tests and render-first visual verification**

```bash
python -m pytest tests/test_cv_renderer.py -v
python -m pytest -v
```

Generate one fictional PDF under `/tmp/opportunity-os-v02b-render/cv.pdf`. If the PDF skill exists in the execution environment, render it:

```bash
python /home/oai/skills/pdfs/scripts/render_pdf.py /tmp/opportunity-os-v02b-render/cv.pdf --out_dir /tmp/opportunity-os-v02b-render/png --dpi 200
```

Inspect every PNG. Acceptance: no clipped text, no overlap, no broken glyphs, single-column reading order, standard headings, and all candidate text visibly matches the structured model. Do not commit generated PDF/PNG files.

- [ ] **Step 5: Commit Task 7**

```bash
git add app/cv/renderer.py tests/test_cv_renderer.py pyproject.toml
git commit -m "feat: render deterministic ATS CV PDFs"
```

---

### Task 8: `ApplicationPacket` semantic hashing and `CVPreparationService`

**Files:**
- Create: `app/cv/service.py`
- Create: `tests/test_cv_service.py`

**Interfaces:**
- Consumes: Tasks 1-7 plus one `RadarAssessment`.
- Produces: `CVPreparationService.prepare() -> PreparationResult`.

- [ ] **Step 1: Write RED service tests**

```python
from datetime import timedelta
from pathlib import Path


def test_prepare_returns_packet_only_after_validation_and_render(service_inputs, tmp_path: Path) -> None:
    result = service_inputs.service.prepare(output_root=tmp_path, **service_inputs.kwargs)
    assert result.status == "PREPARED"
    assert result.packet is not None
    assert Path(result.packet.cv_pdf_path).exists()
    assert len(result.packet.cv_sha256) == 64
    assert len(result.packet.packet_sha256) == 64


def test_missing_minimum_evidence_writes_no_pdf(blocked_service_inputs, tmp_path: Path) -> None:
    result = blocked_service_inputs.service.prepare(output_root=tmp_path, **blocked_service_inputs.kwargs)
    assert result.status == "BLOCKED_MISSING_FACTS"
    assert result.packet is None
    assert list(tmp_path.rglob("*.pdf")) == []


def test_packet_hash_excludes_id_time_and_path(service_inputs, tmp_path: Path) -> None:
    first_service = service_inputs.with_id("app-a")
    second_service = service_inputs.with_id("app-b")
    first = first_service.service.prepare(output_root=tmp_path / "a", now=service_inputs.now, **first_service.kwargs_without_now)
    second = second_service.service.prepare(output_root=tmp_path / "b", now=service_inputs.now + timedelta(hours=1), **second_service.kwargs_without_now)
    assert first.packet is not None
    assert second.packet is not None
    assert first.packet.packet_sha256 == second.packet.packet_sha256


def test_semantic_fact_change_changes_packet_hash(service_inputs, changed_fact_service_inputs, tmp_path: Path) -> None:
    first = service_inputs.service.prepare(output_root=tmp_path / "a", **service_inputs.kwargs)
    second = changed_fact_service_inputs.service.prepare(output_root=tmp_path / "b", **changed_fact_service_inputs.kwargs)
    assert first.packet is not None
    assert second.packet is not None
    assert first.packet.packet_sha256 != second.packet.packet_sha256
```

Implement `service_inputs` as a local pytest fixture dataclass containing `service`, `kwargs`, `kwargs_without_now`, `now`, and `with_id()`; all values are fictional and use factories from Task 1.

Add tests for `BLOCKED_TRACK_UNAVAILABLE`, `BLOCKED_VALIDATION`, and `BLOCKED_RENDER`, each asserting `packet is None` and no final CV is left on disk.

- [ ] **Step 2: Confirm RED**

```bash
python -m pytest tests/test_cv_service.py -v
```

Expected: import failure for `app.cv.service`.

- [ ] **Step 3: Implement semantic packet-hash payload**

Create:

```python
def _opportunity_snapshot_hash(assessment: RadarAssessment) -> str:
    return canonical_sha256(assessment.opportunity.model_dump(mode="json"))


def _packet_content_payload(packet: ApplicationPacket) -> dict[str, object]:
    return {
        "opportunity_snapshot_hash": packet.opportunity_snapshot_hash,
        "selected_intent": packet.selected_intent,
        "application_track_id": packet.application_track_id,
        "match_score": packet.match_score,
        "income_viability": packet.income_viability,
        "confidence_score": packet.confidence_score,
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

Do not include `application_id`, `created_at`, or `cv_pdf_path`.

- [ ] **Step 4: Implement orchestration**

Public signature:

```python
class CVPreparationService:
    def __init__(
        self,
        taxonomy_resolver: TaxonomyResolver,
        id_factory: Callable[[], str] | None = None,
        renderer: ATSRenderer | None = None,
    ) -> None:
        self.taxonomy_resolver = taxonomy_resolver
        self.id_factory = id_factory or (lambda: str(uuid4()))
        self.renderer = renderer or ATSRenderer()

    def prepare(
        self,
        assessment: RadarAssessment,
        master_facts: MasterFactsSnapshot,
        evidence_catalog: EvidenceCatalogSnapshot,
        policy: CVPolicy,
        output_root: str | Path,
        now: datetime,
    ) -> PreparationResult:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
```

Then perform this exact order:

```text
validate catalog against master facts
resolve application track
run minimum evidence gate
run EvidenceSelector
run CVComposer
run ClaimValidator
if validation invalid: return BLOCKED_VALIDATION without renderer call
create application_id
render to output_root/application_id/cv.pdf
construct PREPARED ApplicationPacket with empty packet_sha256 initially
compute semantic packet_sha256 from _packet_content_payload
return PreparationResult(status=PREPARED, packet=final packet, warnings=validation warnings)
```

Map only known failures:

```text
TrackUnavailableError -> BLOCKED_TRACK_UNAVAILABLE
minimum evidence issues -> BLOCKED_MISSING_FACTS
invalid ValidationResult -> BLOCKED_VALIDATION
OSError/renderer ValueError during rendering -> BLOCKED_RENDER
```

Unexpected exceptions are not swallowed.

- [ ] **Step 5: Run service and full tests**

```bash
python -m pytest tests/test_cv_service.py -v
python -m pytest -v
python -m compileall app
```

Expected: all exit 0.

- [ ] **Step 6: Commit Task 8**

```bash
git add app/cv/service.py tests/test_cv_service.py
git commit -m "feat: prepare reproducible CV application packets"
```

---

### Task 9: V0.2B release contract, documentation, privacy CI, and Draft PR

**Files:**
- Create: `tests/test_cv_release_contract.py`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `.github/workflows/tests.yml` only if Task 2 guard needs a correction

**Interfaces:**
- Consumes: completed CV subsystem.
- Produces: documented prerelease `0.2.0b1`; no new HTTP endpoint.

- [ ] **Step 1: Write RED release-contract tests**

Create:

```python
from pathlib import Path
import tomllib


def test_package_version_is_v02b_prerelease() -> None:
    payload = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert payload["project"]["version"] == "0.2.0b1"


def test_readme_documents_cv_factory_without_auto_send_claim() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    assert "CV Factory" in text
    assert "ApplicationPacket" in text
    assert "does not send" in text
    assert "does not submit" in text
```

Run:

```bash
python -m pytest tests/test_cv_release_contract.py -v
```

Expected: fail because version is still `0.2.0a1` and README has no complete V0.2B contract.

- [ ] **Step 2: Update version and README**

Set:

```toml
version = "0.2.0b1"
```

README must document this flow verbatim in meaning:

```text
Radar-selected opportunity
-> private verified facts and evidence
-> deterministic evidence selection
-> provenance-backed CVDocumentModel
-> ClaimValidator hard gate
-> one-column ATS PDF
-> reproducible ApplicationPacket
```

Also document local-only paths:

```text
profile/master_facts.local.yaml
profile/evidence_catalog.local.yaml
artifacts/applications/<application_id>/cv.pdf
```

State explicitly: "V0.2B does not send email and does not submit applications."

- [ ] **Step 3: Run complete release verification**

```bash
python -m pytest -v
python -m compileall app
git diff --check origin/main...HEAD
```

Run the tracked-private-file check:

```bash
forbidden="$(git ls-files -- '.env' 'profile.local.yaml' 'sources.local.yaml' 'profile/master_facts.local.yaml' 'profile/evidence_catalog.local.yaml' 'artifacts/applications/**' '*.pdf' '*.docx')"
test -z "$forbidden"
```

Expected: every command exits 0.

- [ ] **Step 4: Run final fictional end-to-end PDF verification**

Use `CVPreparationService` with fictional fixtures to produce `/tmp/opportunity-os-v02b-final/cv.pdf`. Assert with pypdf that candidate name, headline, one skill, and one experience bullet are extractable. Then render the PDF if the PDF skill exists:

```bash
python /home/oai/skills/pdfs/scripts/render_pdf.py /tmp/opportunity-os-v02b-final/cv.pdf --out_dir /tmp/opportunity-os-v02b-final/rendered --dpi 200
```

Inspect all rendered pages. Reject completion if there is clipping, overlap, broken glyphs, hidden content, multi-column ambiguity, or text not present in the validated model. Delete `/tmp/opportunity-os-v02b-final` after verification.

- [ ] **Step 5: Review the complete branch against `main`**

Review these exact risks:

```text
private data leakage
track isolation
verification-method semantics
exact-product versus related skill support
provenance completeness
unsupported metric/title/date claims
renderer byte determinism
packet hash volatile-field exclusions
V0.2C email/submission scope creep
V0.1/V0.2A API and scoring regressions
```

For every real defect discovered, first add a regression test that fails for that defect, confirm RED, then implement the minimal fix and rerun the full suite.

- [ ] **Step 6: Commit Task 9**

```bash
git add README.md pyproject.toml tests/test_cv_release_contract.py .github/workflows/tests.yml
git commit -m "docs: finalize Opportunity OS V0.2B CV Factory"
```

- [ ] **Step 7: Open a Draft PR after fresh verification**

Open a Draft PR from `feat/v0.2b-cv-factory` to `main`. The PR body must include exact pytest count, compile result, `git diff --check` result, private-file-guard result, deterministic PDF hash test result, and visual PDF verification result. Keep the PR Draft until code review is complete. Merge only after explicit user approval.

---

## Execution Order and Checkpoints

```text
Task 1 contracts + hashing
Task 2 loaders + examples + privacy
Task 3 track + minimum evidence
Task 4 evidence selector
Task 5 composer
Task 6 validator
Task 7 deterministic ATS PDF
Task 8 packet + preparation service
Task 9 release verification + Draft PR
```

After every task:

```text
confirm RED failed for the intended new behavior
implement minimal GREEN
run task-specific tests
run full pytest regression
inspect the task diff for scope creep/private data
commit
update the private handoff only when the checkpoint materially changes restart context
```

Do not create or commit a real personal master-facts file during this public-engine implementation. Real candidate facts are assembled only in a private/local operation after the engine is green and reviewed.
