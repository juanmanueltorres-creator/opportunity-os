# Opportunity OS V0.2B2 One-Page Recruiter Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `PREPARED` mean a semantically valid, recruiter-quality, exactly-one-page CV that can be reproduced from a fresh operator/chat context through one canonical command.

**Architecture:** Keep the existing `EvidenceSelector -> CVComposer -> ClaimValidator` semantic pipeline intact. Add a recruiter-only document model, composer, structural validator, RenderCV/Typst renderer adapter, one-page QA, and deterministic reduction loop after semantic validation; then persist both semantic and recruiter documents in the `ApplicationPacket`. A canonical CLI and agent runbook become the only supported fresh-context preparation path.

**Tech Stack:** Python 3.12+, Pydantic v2, existing Opportunity OS CV/Radar models, RenderCV 2.8 + Typst, PyPDF, PyMuPDF for independent extraction tests, pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-opportunity-os-v0.2b2-one-page-recruiter-pipeline-design.md`

**Approval:** `docs/superpowers/specs/2026-08-30-opportunity-os-v0.2b2-one-page-recruiter-pipeline-approval-amendment.md`

## Global Constraints

- Recruiter-facing PDF output MUST contain exactly one A4 page.
- There is no automatic two-page fallback.
- `ClaimValidator` remains the semantic authority and runs before recruiter-specific grouping.
- Recruiter composition may only select, group, order or omit claim IDs already present in `ValidationResult.validated_claim_ids`.
- Candidate-specific visible text may not be invented, paraphrased or rewritten by recruiter composition or rendering.
- Skill presentation is grouped recruiter rows, never one atomic paragraph per skill.
- Default caps: headline <= 2 rendered lines; profile <= 3 rendered lines; <= 4 skill groups; <= 24 skill tokens; <= 4 projects; <= 5 experience entries; <= 1 visible bullet per experience entry; <= 4 education/training items.
- Body text MUST remain >= 9.0 pt.
- Overflow is handled by deterministic omission of lower-relevance optional validated claims; typography is not repeatedly shrunk.
- A second page, clipping, missing extractable text, unvalidated recruiter claim reference, or body font below 9.0 pt maps to `BLOCKED_RENDER` and produces no successful packet.
- Opportunity OS remains the owning repository and semantic authority; no second resume repository is created.
- Private `profile/*.local.yaml`, real generated PDFs and real ApplicationPackets remain gitignored and uncommitted.
- Render time must require no network access after dependencies are installed.
- `PREPARED != APPROVED != SENT`; this feature adds no send authority.
- Public golden fixtures MUST use fictional candidate data.

---

## File Structure

Create focused modules rather than expanding `app/cv/renderer.py` into a second semantic layer:

```text
app/cv/recruiter_models.py       # recruiter-only grouping/order models
app/cv/recruiter_policy.py       # deterministic caps, labels and grouping policy
app/cv/recruiter_composer.py     # validated CVDocumentModel -> recruiter document
app/cv/recruiter_validator.py    # prove recruiter document references validated claims only
app/cv/recruiter_qa.py           # one-page + ATS structural hard gates
app/cv/renderers/__init__.py
app/cv/renderers/base.py          # RecruiterRenderer protocol
app/cv/renderers/rendercv_typst.py# RenderCV/Typst adapter
app/application/__init__.py
app/application/prepare.py        # canonical operator CLI
config/recruiter_policy.yaml      # public deterministic recruiter profile
config/rendercv_one_page.yaml     # Opportunity OS-owned RenderCV design settings
```

Existing integration points:

```text
app/cv/models.py
app/cv/service.py
app/cv/hashing.py
pyproject.toml
README.md
ROADMAP.md
.gitignore
.github/workflows/tests.yml
docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md
```

Tests:

```text
tests/test_recruiter_models.py
tests/test_recruiter_policy.py
tests/test_recruiter_composer.py
tests/test_recruiter_validator.py
tests/test_recruiter_renderer.py
tests/test_recruiter_qa.py
tests/test_cv_service.py
tests/test_application_prepare_cli.py
tests/test_cv_release_contract.py
tests/fixtures/recruiter_software.json
tests/fixtures/recruiter_tech_operations.json
```

Keep existing `app/cv/renderer.py` and `app/cv/layout_qa.py` during V0.2B2 for backward-compatible unit coverage; `CVPreparationService` stops using them as the recruiter-facing default once the new path is green.

---

### Task 1: Recruiter policy and presentation models

**Files:**
- Create: `app/cv/recruiter_models.py`
- Create: `app/cv/recruiter_policy.py`
- Create: `config/recruiter_policy.yaml`
- Create: `tests/test_recruiter_models.py`
- Create: `tests/test_recruiter_policy.py`

**Interfaces:**
- Produces: `RecruiterPolicy`, `load_recruiter_policy(path)`, `RecruiterDocumentModel`, `TechnologyGroup`, `RecruiterExperienceEntry`.
- Consumes later: validated `CVDocumentModel` claim IDs only; no `MasterFactsSnapshot` or `EvidenceCatalogSnapshot` references are allowed in these models.

- [ ] **Step 1: Write RED model tests for caps and claim-reference-only data**

```python
from pydantic import ValidationError
import pytest

from app.cv.recruiter_models import RecruiterDocumentModel, TechnologyGroup


def test_recruiter_document_carries_claim_ids_not_free_candidate_text():
    document = RecruiterDocumentModel(
        document_version="recruiter-doc-v1",
        source_cv_document_version="cvdoc-v1",
        language="en",
        identity_claim_id="fact:name",
        headline_claim_id="fact:role",
        contact_claim_ids=["fact:email", "fact:phone"],
        profile_claim_ids=["approved:summary"],
        technology_groups=[
            TechnologyGroup(label_id="software_data", skill_claim_ids=["fact:python"])
        ],
        selected_project_claim_ids=["fact:project-1"],
        experience_entries=[],
        education_claim_ids=["fact:education"],
        language_claim_ids=["fact:language"],
        link_claim_ids=["fact:github"],
    )
    assert document.headline_claim_id == "fact:role"
    assert not hasattr(document, "headline_text")


def test_technology_group_rejects_more_than_policy_independent_safe_ceiling():
    with pytest.raises(ValidationError):
        TechnologyGroup(
            label_id="software_data",
            skill_claim_ids=[f"fact:skill-{n}" for n in range(25)],
        )
```

- [ ] **Step 2: Run RED tests**

Run:

```bash
pytest tests/test_recruiter_models.py -q
```

Expected: FAIL because `app.cv.recruiter_models` does not exist.

- [ ] **Step 3: Implement strict recruiter presentation models**

```python
# app/cv/recruiter_models.py
from typing import Literal
from pydantic import Field, model_validator
from app.cv.models import OutputLanguage, StrictCVModel

RECRUITER_DOCUMENT_VERSION = "recruiter-doc-v1"


class TechnologyGroup(StrictCVModel):
    label_id: str = Field(min_length=1)
    skill_claim_ids: list[str] = Field(min_length=1, max_length=24)


class RecruiterExperienceEntry(StrictCVModel):
    primary_claim_id: str = Field(min_length=1)
    bullet_claim_ids: list[str] = Field(default_factory=list, max_length=1)


class RecruiterDocumentModel(StrictCVModel):
    document_version: str = RECRUITER_DOCUMENT_VERSION
    source_cv_document_version: str = Field(min_length=1)
    language: OutputLanguage
    identity_claim_id: str = Field(min_length=1)
    headline_claim_id: str = Field(min_length=1)
    contact_claim_ids: list[str] = Field(default_factory=list)
    profile_claim_ids: list[str] = Field(default_factory=list)
    technology_groups: list[TechnologyGroup] = Field(default_factory=list, max_length=4)
    selected_project_claim_ids: list[str] = Field(default_factory=list, max_length=4)
    experience_entries: list[RecruiterExperienceEntry] = Field(default_factory=list, max_length=5)
    education_claim_ids: list[str] = Field(default_factory=list, max_length=4)
    language_claim_ids: list[str] = Field(default_factory=list)
    link_claim_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def claim_ids_must_not_repeat_inside_grouped_sections(self):
        # Reject duplicate recruiter references that would create repeated visible content.
        project_ids = self.selected_project_claim_ids
        if len(project_ids) != len(set(project_ids)):
            raise ValueError("recruiter project claim ids must be unique")
        return self
```

- [ ] **Step 4: Write RED policy loader test**

```python
from app.cv.recruiter_policy import load_recruiter_policy


def test_default_policy_is_exactly_one_page_and_has_fixed_caps(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text(
        """
version: recruiter-policy-v1
max_pages: 1
min_body_font_pt: 9.0
max_projects: 4
max_experience_entries: 5
max_experience_bullets: 1
max_skill_groups: 4
max_skill_tokens: 24
skill_groups:
  software_data:
    en: Software & Data
    es: Software y Datos
    members: [Python, SQL]
""".strip(),
        encoding="utf-8",
    )
    policy = load_recruiter_policy(path)
    assert policy.max_pages == 1
    assert policy.min_body_font_pt == 9.0
    assert policy.max_projects == 4
```

- [ ] **Step 5: Implement `RecruiterPolicy` and repository config**

`config/recruiter_policy.yaml` must contain only repository-owned labels/caps and generic skill grouping rules. It must not contain Juan's private employment facts or target-specific fabricated skills.

- [ ] **Step 6: Run tests and commit**

```bash
pytest tests/test_recruiter_models.py tests/test_recruiter_policy.py -q
git add app/cv/recruiter_models.py app/cv/recruiter_policy.py config/recruiter_policy.yaml tests/test_recruiter_models.py tests/test_recruiter_policy.py
git commit -m "feat: add recruiter document policy and models"
```

---

### Task 2: Compose recruiter documents only from semantically validated claims

**Files:**
- Create: `app/cv/recruiter_composer.py`
- Create: `tests/test_recruiter_composer.py`
- Read but do not weaken: `app/cv/composer.py`, `app/cv/validator.py`

**Interfaces:**
- Consumes: `CVDocumentModel`, `ValidationResult`, `EvidenceSelection`, `RecruiterPolicy`.
- Produces: `compose_recruiter_document(...) -> RecruiterDocumentModel` and deterministic `reduce_recruiter_document(...)` for overflow retries.
- Must not consume: `MasterFactsSnapshot`, `EvidenceCatalogSnapshot`.

- [ ] **Step 1: Write RED test proving unvalidated claims cannot be selected**

```python
from app.cv.recruiter_composer import compose_recruiter_document


def test_composer_ignores_claim_not_in_validated_claim_ids(validated_cv_fixture, recruiter_policy):
    document, validation, selection = validated_cv_fixture
    invalid = document.model_copy(
        update={"claims": [*document.claims, document.claims[0].model_copy(update={"claim_id": "bad", "text": "AWS Expert"})]}
    )
    recruiter = compose_recruiter_document(
        document=invalid,
        validation=validation,
        selection=selection,
        policy=recruiter_policy,
    )
    referenced = recruiter.all_claim_ids()
    assert "bad" not in referenced
```

Define `all_claim_ids()` on `RecruiterDocumentModel` in Task 1 if the test needs it; it returns recruiter references only and does not resolve text.

- [ ] **Step 2: Write RED skill-grouping test**

```python
def test_skills_are_grouped_and_never_returned_as_atomic_recruiter_rows(
    validated_cv_fixture, recruiter_policy
):
    document, validation, selection = validated_cv_fixture
    recruiter = compose_recruiter_document(
        document=document,
        validation=validation,
        selection=selection,
        policy=recruiter_policy,
    )
    assert len(recruiter.technology_groups) <= 4
    assert sum(len(group.skill_claim_ids) for group in recruiter.technology_groups) <= 24
    assert all(group.skill_claim_ids for group in recruiter.technology_groups)
```

- [ ] **Step 3: Verify RED**

```bash
pytest tests/test_recruiter_composer.py -q
```

Expected: FAIL because composer is missing.

- [ ] **Step 4: Implement deterministic claim relevance**

Use claim provenance already present on `CVDocumentModel` and support metadata in `EvidenceSelection`. Build the support set from requirement support fact/evidence IDs and score a claim without reading private facts directly:

```python
def _supported_claim_ids(document, selection) -> set[str]:
    supported_facts: set[str] = set()
    supported_evidence: set[str] = set()
    for support in selection.requirement_support.values():
        if support.support_level == "UNKNOWN":
            continue
        supported_facts.update(support.fact_ids)
        supported_evidence.update(support.evidence_ids)

    return {
        claim_id
        for claim_id, provenance in document.provenance_map.items()
        if set(provenance.fact_ids) & supported_facts
        or set(provenance.evidence_ids) & supported_evidence
    }
```

Stable ordering rule: target-supported claims first, then original `document.claims` order. Never use random order, current time or generative rewriting.

- [ ] **Step 5: Implement grouping and experience association**

Skill grouping uses exact normalized claim text against `RecruiterPolicy.skill_groups`; unmatched validated skills go to an allowlisted `additional` group only when capacity remains.

Associate a validated experience bullet with an employment/organization claim only when their semantic source provenance overlaps by at least one fact ID. Do not infer association from proximity in the PDF or natural-language similarity.

- [ ] **Step 6: Write RED deterministic reduction test**

```python
def test_reduce_drops_optional_content_in_fixed_order(recruiter_document, recruiter_policy):
    reduced = reduce_recruiter_document(recruiter_document, recruiter_policy, step=0)
    assert len(reduced.link_claim_ids) <= len(recruiter_document.link_claim_ids)

    reduced_again = reduce_recruiter_document(recruiter_document, recruiter_policy, step=0)
    assert reduced.model_dump(mode="json") == reduced_again.model_dump(mode="json")
```

Reduction priority must implement the approved order: duplicate optional links -> lower-relevance skill claims -> project #4 then #3 while keeping at least two if present -> lower-relevance optional experience -> optional training/education claim.

- [ ] **Step 7: Run tests and commit**

```bash
pytest tests/test_recruiter_composer.py -q
git add app/cv/recruiter_composer.py tests/test_recruiter_composer.py app/cv/recruiter_models.py
git commit -m "feat: compose compact recruiter documents from validated claims"
```

---

### Task 3: Add a second structural validator after recruiter composition

**Files:**
- Create: `app/cv/recruiter_validator.py`
- Create: `tests/test_recruiter_validator.py`

**Interfaces:**
- Consumes: `RecruiterDocumentModel`, source `CVDocumentModel`, source `ValidationResult`, `RecruiterPolicy`.
- Produces: existing `ValidationResult` shape with recruiter-specific bounded issue codes.

- [ ] **Step 1: Write RED unvalidated-reference test**

```python
from app.cv.recruiter_validator import validate_recruiter_document


def test_recruiter_validator_rejects_unvalidated_claim_reference(
    recruiter_document, source_document, source_validation, recruiter_policy
):
    tampered = recruiter_document.model_copy(update={"headline_claim_id": "claim:not-validated"})
    result = validate_recruiter_document(
        recruiter_document=tampered,
        source_document=source_document,
        source_validation=source_validation,
        policy=recruiter_policy,
    )
    assert not result.valid
    assert {item.code for item in result.errors} == {"recruiter_unvalidated_claim_reference"}
```

- [ ] **Step 2: Write RED policy-label test**

```python
def test_recruiter_validator_rejects_unknown_group_label(...):
    tampered = recruiter_document.model_copy(
        update={
            "technology_groups": [
                recruiter_document.technology_groups[0].model_copy(update={"label_id": "aws_expert"})
            ]
        }
    )
    result = validate_recruiter_document(...)
    assert "recruiter_group_label_not_allowed" in {e.code for e in result.errors}
```

- [ ] **Step 3: Verify RED, then implement reference validation**

The validator checks every recruiter claim ID against both:

```python
known_claim_ids = {claim.claim_id for claim in source_document.claims}
validated_claim_ids = set(source_validation.validated_claim_ids)
```

Every reference must be in their intersection. It also enforces policy caps, allowed group label IDs, one bullet per experience entry, <=4 projects, <=4 groups and <=24 skill tokens.

- [ ] **Step 4: Run tests and commit**

```bash
pytest tests/test_recruiter_validator.py -q
git add app/cv/recruiter_validator.py tests/test_recruiter_validator.py
git commit -m "feat: validate recruiter composition against semantic claims"
```

---

### Task 4: Add RenderCV/Typst behind a stable recruiter renderer protocol

**Files:**
- Create: `app/cv/renderers/__init__.py`
- Create: `app/cv/renderers/base.py`
- Create: `app/cv/renderers/rendercv_typst.py`
- Create: `config/rendercv_one_page.yaml`
- Modify: `pyproject.toml`
- Create: `tests/test_recruiter_renderer.py`

**Interfaces:**
- Produces protocol:

```python
class RecruiterRenderer(Protocol):
    renderer_version: str
    body_font_size: float
    def render(
        self,
        recruiter_document: RecruiterDocumentModel,
        source_document: CVDocumentModel,
        output_path: str | Path,
    ) -> RenderedCVArtifact: ...
```

- Default implementation: `RenderCVTypstRenderer` with `renderer_version = "rendercv-typst-v1"`.
- Resolver rule: candidate-specific text is looked up from source validated claim IDs; renderer never receives free target wording.

- [ ] **Step 1: Add dependency compatibility RED test**

```python
def test_rendercv_runtime_is_importable():
    import rendercv
    import typst
    assert rendercv is not None
    assert typst is not None
```

- [ ] **Step 2: Add pinned compatible dependencies**

Modify `pyproject.toml`:

```toml
dependencies = [
  # existing dependencies...
  "rendercv[full]>=2.8,<3",
]

[project.optional-dependencies]
dev = ["pypdf>=5", "PyMuPDF>=1.26,<2", "pytest", "pytest-asyncio"]
```

RenderCV 2.8 and Opportunity OS both require Python >=3.12. Do not add a network rendering service.

- [ ] **Step 3: Run dependency/import test**

```bash
python -m pip install -e '.[dev]'
pytest tests/test_recruiter_renderer.py::test_rendercv_runtime_is_importable -q
```

Expected after dependency install: PASS. If installation itself fails on supported Python 3.12, stop implementation and report the feasibility blocker before changing semantic code; do not silently switch architectures.

- [ ] **Step 4: Write RED one-page fixture renderer test**

```python
from pypdf import PdfReader


def test_rendercv_renderer_outputs_one_a4_page_with_extractable_text(
    tmp_path, recruiter_document, source_document
):
    artifact = RenderCVTypstRenderer().render(
        recruiter_document,
        source_document,
        tmp_path / "cv.pdf",
    )
    reader = PdfReader(artifact.path)
    assert len(reader.pages) == 1
    assert "Alex Example" in (reader.pages[0].extract_text() or "")
```

- [ ] **Step 5: Implement deterministic RenderCV payload mapping**

Use an in-process temporary directory. Map only resolved validated claims into a RenderCV-compatible structure. Use ordinary text sections with fixed section names and skill label/details rows. The Opportunity OS-owned design config must specify A4, one column, no photo, no footer, no top note, restrained typography and body >=9 pt.

Representative mapper boundary:

```python
def build_rendercv_payload(
    recruiter_document: RecruiterDocumentModel,
    source_document: CVDocumentModel,
    policy: RecruiterPolicy,
) -> dict:
    claim_by_id = {claim.claim_id: claim for claim in source_document.claims}
    return {
        "cv": {
            "name": claim_by_id[recruiter_document.identity_claim_id].text,
            "headline": claim_by_id[recruiter_document.headline_claim_id].text,
            "sections": _build_sections(recruiter_document, claim_by_id, policy),
        },
        "design": _load_owned_design(),
    }
```

Do not parse candidate text to invent company/title/date fields. Where Opportunity OS has one validated project/employment line rather than structured subfields, render it as a normal one-column text/bullet entry rather than guessing structure.

- [ ] **Step 6: Prove deterministic bytes for fixed input**

```python
def test_renderer_is_deterministic(tmp_path, recruiter_document, source_document):
    first = RenderCVTypstRenderer().render(recruiter_document, source_document, tmp_path / "a.pdf")
    second = RenderCVTypstRenderer().render(recruiter_document, source_document, tmp_path / "b.pdf")
    assert Path(first.path).read_bytes() == Path(second.path).read_bytes()
    assert first.sha256 == second.sha256
```

If upstream RenderCV/Typst inserts non-semantic volatile metadata that prevents byte-for-byte equality, normalize that metadata in the adapter before hashing; do not weaken semantic reproducibility tests.

- [ ] **Step 7: Run renderer tests and commit**

```bash
pytest tests/test_recruiter_renderer.py -q
git add app/cv/renderers config/rendercv_one_page.yaml pyproject.toml tests/test_recruiter_renderer.py
git commit -m "feat: render recruiter CVs with RenderCV and Typst"
```

---

### Task 5: RecruiterQualityQA with one page as a hard gate

**Files:**
- Create: `app/cv/recruiter_qa.py`
- Create: `tests/test_recruiter_qa.py`
- Modify only if reusable types are needed: `app/cv/models.py`

**Interfaces:**
- Consumes: `RenderedCVArtifact`, renderer-owned metrics/profile, validated recruiter document and source document.
- Produces: `RecruiterQAResult(valid, page_count, errors, warnings, extracted_text)` or an equally strict Pydantic model.

- [ ] **Step 1: Write RED two-page hard-failure test**

```python
def test_two_page_pdf_is_hard_failure(two_page_pdf_artifact, recruiter_document):
    result = RecruiterQualityQA().evaluate(
        two_page_pdf_artifact,
        recruiter_document=recruiter_document,
        body_font_size=9.4,
        headline_line_count=1,
    )
    assert not result.valid
    assert "recruiter_one_page_failed" in {e.code for e in result.errors}
```

- [ ] **Step 2: Write RED font/text tests**

```python
def test_body_font_below_nine_points_is_hard_failure(...):
    result = qa.evaluate(..., body_font_size=8.9, ...)
    assert "recruiter_body_font_too_small" in {e.code for e in result.errors}


def test_missing_extractable_text_is_hard_failure(blank_pdf_artifact, ...):
    result = qa.evaluate(blank_pdf_artifact, ...)
    assert "recruiter_text_not_extractable" in {e.code for e in result.errors}
```

- [ ] **Step 3: Implement exact one-page/A4/extractable-text gates**

Use PyPDF for runtime QA. Validate A4 dimensions within a small deterministic tolerance. `page_count != 1` is an error, never a warning.

- [ ] **Step 4: Add independent ATS extraction release test**

Use both PyPDF and PyMuPDF on the same fictional golden PDF and compare expected ground-truth fields:

```python
from pypdf import PdfReader
import fitz


def test_golden_pdf_survives_two_independent_extractors(golden_pdf):
    pypdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(golden_pdf).pages)
    pymupdf_text = "\n".join(page.get_text() for page in fitz.open(golden_pdf))
    for expected in ["Alex Example", "alex@example.test", "Python", "Example Labs"]:
        assert expected in pypdf_text
        assert expected in pymupdf_text
```

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/test_recruiter_qa.py -q
git add app/cv/recruiter_qa.py tests/test_recruiter_qa.py app/cv/models.py
git commit -m "feat: enforce recruiter one-page quality gates"
```

---

### Task 6: Integrate deterministic compose-validate-render-reduce flow into CVPreparationService

**Files:**
- Modify: `app/cv/service.py`
- Modify: `app/cv/models.py`
- Modify: `tests/test_cv_service.py`

**Interfaces:**
- Existing public input remains `CVPreparationService.prepare(RadarAssessment, MasterFactsSnapshot, EvidenceCatalogSnapshot, CVPolicy, output_root, now)`.
- New constructor collaborators: `recruiter_policy`, `recruiter_renderer`, `recruiter_qa` with deterministic defaults.
- `ApplicationPacket` persists both semantic `cv_document` and `recruiter_document` plus recruiter policy/document versions.

- [ ] **Step 1: Write RED service regression: legacy two-page success must now block**

```python
def test_prepare_never_returns_prepared_for_two_page_recruiter_output(tmp_path):
    result = _service(renderer=TwoPageRecruiterRenderer()).prepare(...)
    assert result.status == "BLOCKED_RENDER"
    assert result.packet is None
    assert list(tmp_path.rglob("*.pdf")) == []
    assert "recruiter_one_page_failed" in {e.code for e in result.errors}
```

- [ ] **Step 2: Write RED successful packet assertions**

```python
def test_prepared_packet_contains_semantic_and_recruiter_documents(tmp_path):
    result = _service().prepare(...)
    assert result.status == "PREPARED"
    assert result.packet.cv_document.document_version == "cvdoc-v1"
    assert result.packet.recruiter_document.document_version == "recruiter-doc-v1"
    assert result.packet.recruiter_policy_version == "recruiter-policy-v1"
    assert result.packet.renderer_version == "rendercv-typst-v1"
```

- [ ] **Step 3: Implement service order exactly**

```text
validate_catalog_against_facts
resolve track / selected intent
require minimum evidence
select_evidence
compose_cv
validate_cv                       # semantic hard gate
compose_recruiter_document        # validated claim IDs only
validate_recruiter_document       # structural hard gate
render recruiter document
RecruiterQualityQA
if overflow/second page caused by content density:
    deterministically reduce optional validated claims
    revalidate recruiter document
    rerender
    rerun QA
if still invalid: BLOCKED_RENDER + remove partial PDF
build ApplicationPacket
return PREPARED
```

Use a fixed maximum reduction-step count derived from policy. No open-ended render loop.

- [ ] **Step 4: Update packet hashing payload**

Include recruiter document JSON, recruiter policy version and renderer version in `_packet_content_payload()`. Packet hash must change when grouping/order changes even if the semantic `CVDocumentModel` is unchanged.

- [ ] **Step 5: Preserve existing fail-closed behavior**

Existing statuses remain:

```text
BLOCKED_TRACK_UNAVAILABLE
BLOCKED_MISSING_FACTS
BLOCKED_VALIDATION
BLOCKED_RENDER
PREPARED
```

No recruiter failure may leave a successful packet or stale PDF.

- [ ] **Step 6: Run focused + existing CV suite and commit**

```bash
pytest tests/test_cv_service.py tests/test_cv_validator.py tests/test_cv_composer.py tests/test_cv_selector.py -q
git add app/cv/service.py app/cv/models.py tests/test_cv_service.py
git commit -m "feat: make recruiter quality part of PREPARED"
```

---

### Task 7: Add fictional golden recruiter fixtures and release contracts

**Files:**
- Create: `tests/fixtures/recruiter_software.json`
- Create: `tests/fixtures/recruiter_tech_operations.json`
- Modify: `tests/test_cv_release_contract.py`
- Create or extend: `tests/test_recruiter_renderer.py`

**Interfaces:**
- Fixtures contain a complete fictional semantic CV document + recruiter composition or helper inputs; no real Juan data.
- Golden A mirrors Maptek/Esri structure: 3 skill groups, 4 projects, <=5 compact experience entries, education close.
- Golden B covers technology + operations without enterprise-tool fabrication.

- [ ] **Step 1: Write RED structural release tests**

```python
@pytest.mark.parametrize("fixture_name", ["recruiter_software", "recruiter_tech_operations"])
def test_golden_recruiter_profiles_are_exactly_one_page(fixture_name, tmp_path):
    recruiter, source = load_golden_fixture(fixture_name)
    artifact = RenderCVTypstRenderer().render(recruiter, source, tmp_path / f"{fixture_name}.pdf")
    result = RecruiterQualityQA().evaluate(...)
    assert result.valid
    assert result.page_count == 1
```

- [ ] **Step 2: Add no-private-data release guard**

The public fixture test must reject known private candidate identifiers and local snapshot filenames:

```python
def test_public_recruiter_fixtures_are_fictional():
    payload = Path("tests/fixtures/recruiter_software.json").read_text()
    for forbidden in ["juan.manuel.torres@", "+54 9 351", "master_facts.local.yaml"]:
        assert forbidden not in payload
```

- [ ] **Step 3: Add release contract for grouped skills**

Extract text and assert group label rows exist while each skill token survives ATS extraction. Do not assert pixel coordinates or private screenshot hashes.

- [ ] **Step 4: Run tests and commit**

```bash
pytest tests/test_cv_release_contract.py tests/test_recruiter_renderer.py tests/test_recruiter_qa.py -q
git add tests/fixtures/recruiter_*.json tests/test_cv_release_contract.py tests/test_recruiter_renderer.py
git commit -m "test: add one-page recruiter golden contracts"
```

---

### Task 8: Canonical application preparation CLI

**Files:**
- Create: `app/application/__init__.py`
- Create: `app/application/prepare.py`
- Create: `tests/test_application_prepare_cli.py`
- Reuse: `app/cv/loaders.py`, `app/radar/models.py`, `app/radar/taxonomy.py`

**Interfaces:**
- Deterministic canonical mode accepts a serialized `RadarAssessment`.
- CLI contract:

```bash
python -m app.application.prepare \
  --assessment artifacts/opportunities/<id>/radar_assessment.json \
  --master-facts profile/master_facts.local.yaml \
  --evidence-catalog profile/evidence_catalog.local.yaml \
  --recruiter-policy config/recruiter_policy.yaml \
  --output-root artifacts/applications
```

A fresh operator starting from a raw posting must first resolve it through the existing Radar flow; the CLI MUST NOT invent missing scores, track or selected intent from prose.

- [ ] **Step 1: Write RED CLI success test**

```python
def test_cli_prepares_from_serialized_radar_assessment(tmp_path, capsys):
    exit_code = main([
        "--assessment", str(assessment_path),
        "--master-facts", str(master_path),
        "--evidence-catalog", str(catalog_path),
        "--recruiter-policy", str(policy_path),
        "--output-root", str(tmp_path / "applications"),
    ])
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "PREPARED"
    assert output["page_count"] == 1
    assert len(output["cv_sha256"]) == 64
    assert len(output["packet_sha256"]) == 64
```

- [ ] **Step 2: Write RED no-inference test**

```python
def test_cli_rejects_plain_opportunity_as_if_it_were_assessment(...):
    exit_code = main(["--assessment", str(opportunity_only_path), ...])
    output = json.loads(capsys.readouterr().out)
    assert exit_code != 0
    assert output["error"] == "invalid_radar_assessment"
```

- [ ] **Step 3: Implement CLI with strict JSON output**

Load YAML snapshots through existing loaders. Load `RadarAssessment` with Pydantic. Load alias registry/taxonomy from repository config. Use timezone-aware current time only as the packet creation timestamp; semantic input remains serialized and auditable.

Output only a concise JSON object containing:

```text
status
application_id (when prepared)
cv_pdf_path
page_count
cv_sha256
packet_sha256
unresolved_gaps
errors
warnings
```

The CLI never sends email, mutates Gmail, submits forms or changes pipeline state to `Postulado`.

- [ ] **Step 4: Run tests and commit**

```bash
pytest tests/test_application_prepare_cli.py -q
git add app/application tests/test_application_prepare_cli.py
git commit -m "feat: add canonical one-command application preparation"
```

---

### Task 9: Agent runbook, README and CI guardrails

**Files:**
- Create: `docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md`
- Modify: `README.md`
- Modify: `ROADMAP.md`
- Modify: `.gitignore` only if current private/generated patterns are insufficient
- Modify: `.github/workflows/tests.yml`
- Add test if needed: `tests/test_cv_release_contract.py`

**Interfaces:**
- `docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md` is the authoritative fresh-context procedure.
- README links to the runbook instead of duplicating operational details.

- [ ] **Step 1: Write runbook with non-negotiable opening block**

```markdown
# Opportunity OS Agent Runbook

DO NOT reconstruct CV generation from memory.
DO NOT hand-build recruiter PDFs when the canonical command is available.
PREPARED requires exactly one recruiter-quality A4 page.
PREPARED != APPROVE != SEND.
Private candidate snapshots and generated artifacts never enter the public repo.
```

Then document prerequisites, exact canonical command, required private files, how to obtain a `RadarAssessment`, statuses, unresolved gaps, PDF inspection, active-posting vs target-account distinction, and the rule that unsupported posting requirements remain gaps.

- [ ] **Step 2: Add README/ROADMAP pointer**

README CV Factory flow must become:

```text
RadarAssessment
-> EvidenceSelector
-> CVComposer
-> ClaimValidator
-> RecruiterDocumentComposer
-> RecruiterDocumentValidator
-> RenderCV/Typst one-page renderer
-> RecruiterQualityQA
-> ApplicationPacket
```

- [ ] **Step 3: Harden CI**

CI must install the same renderer dependencies and run the complete test suite. Add a dedicated recruiter contract command before the general suite only if it makes failures easier to diagnose; do not create a second divergent test environment.

- [ ] **Step 4: Verify privacy ignore rules**

At minimum these remain ignored:

```text
profile/*.local.yaml
artifacts/applications/
*.local.yaml
```

Do not ignore public fictional fixtures.

- [ ] **Step 5: Run docs/release tests and commit**

```bash
pytest tests/test_cv_release_contract.py tests/test_application_prepare_cli.py -q
git add docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md README.md ROADMAP.md .gitignore .github/workflows/tests.yml tests/test_cv_release_contract.py
git commit -m "docs: make one-page preparation reproducible for fresh agents"
```

---

### Task 10: Full verification and private Coca-Cola smoke run

**Files:**
- No public candidate-data files created.
- Generated private output: `artifacts/applications/<application_id>/cv.pdf` and packet under the local ignored artifact root.

**Interfaces:**
- Uses the real private snapshots only from an ignored/local workspace.
- Uses a real serialized Coca-Cola Andina `RadarAssessment` with unsupported requirements preserved as gaps.

- [ ] **Step 1: Run complete automated verification**

```bash
python -m compileall app
pytest -q
```

Expected: all tests PASS, no warnings indicating a broken renderer/runtime contract.

- [ ] **Step 2: Run private canonical command**

```bash
python -m app.application.prepare \
  --assessment <private-cocacola-radar-assessment.json> \
  --master-facts profile/master_facts.local.yaml \
  --evidence-catalog profile/evidence_catalog.local.yaml \
  --recruiter-policy config/recruiter_policy.yaml \
  --output-root artifacts/applications
```

Expected: either `PREPARED` with exactly one page or an explicit fail-closed status. Do not manually bypass a failed recruiter gate.

- [ ] **Step 3: Inspect private output against the approved benchmark**

Required human/agent visual checks:

```text
one page only
name/headline hierarchy comparable to prior strong Maptek/Esri artifacts
compact contact block
profile <= 3 lines
skills grouped into recruiter rows
2-4 target-relevant projects when evidence permits
experience compact, at most one bullet per included role
education/training closes the page
no clipping
no giant blank lower region
no unsupported Power BI/SAP/B2B claims
```

The private smoke PDF is never committed.

- [ ] **Step 4: Verify git diff contains no private/generated artifacts**

```bash
git status --short
git diff --check
git ls-files | grep -E 'master_facts\.local|evidence_catalog\.local|artifacts/applications' && exit 1 || true
```

- [ ] **Step 5: Final commit only if verification is clean**

```bash
git add -u
git commit -m "feat: complete V0.2B2 one-page recruiter pipeline"
```

Do not claim V0.2B2 complete until the full suite and private recruiter-quality smoke run have both been inspected.

---

## Plan Self-Review

### Spec coverage

- Exactly one page: Tasks 4-6 and 7.
- ClaimValidator before recruiter composition: Tasks 2, 3 and 6.
- Recruiter-only claim references: Tasks 1-3.
- Grouped skills and compact content budgets: Tasks 1-2.
- Deterministic reduction before typography changes: Tasks 2 and 6.
- RenderCV/Typst adapter owned by Opportunity OS: Task 4.
- ATS extraction with two independent local extractors: Task 5/7.
- Reproducible packet: Task 6.
- Canonical fresh-context command: Task 8.
- Agent runbook/privacy/no-SEND boundary: Task 9.
- Real private smoke without committing data: Task 10.

### Placeholder scan

No `TBD`, `TODO`, "implement later", unspecified error handling, or unnamed interfaces are permitted by this plan. If execution discovers a renderer incompatibility on supported Python 3.12, stop at Task 4 and report the feasibility failure rather than silently changing architecture.

### Type consistency

The plan consistently uses:

```text
CVDocumentModel                 # semantic document
ValidationResult                # semantic/recruiter validation result shape
RecruiterDocumentModel          # grouping/order references only
RecruiterPolicy                 # deterministic public recruiter profile
RecruiterRenderer               # render protocol
RenderCVTypstRenderer           # default renderer
RecruiterQualityQA              # rendered hard gates
ApplicationPacket               # successful prepared artifact authority
```

`RecruiterDocumentComposer` never receives private MasterFacts/EvidenceCatalog directly; only the existing semantic pipeline does.