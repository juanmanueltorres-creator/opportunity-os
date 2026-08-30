# Opportunity OS V0.2B2 One-Page Recruiter Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `PREPARED` mean a semantically valid, recruiter-quality, exactly-one-page CV that can be reproduced from a fresh operator/chat context through one canonical command.

**Architecture:** Keep the existing `EvidenceSelector -> CVComposer -> ClaimValidator` semantic pipeline intact. Add a recruiter-only document model, composer, structural validator, RenderCV/Typst renderer adapter, one-page QA, and deterministic reduction loop after semantic validation; then persist both semantic and recruiter documents in the `ApplicationPacket`. A canonical CLI and agent runbook become the only supported fresh-context preparation path.

**Tech Stack:** Python 3.12+, Pydantic v2, existing Opportunity OS CV/Radar models, RenderCV 2.8 + Typst, PyPDF, PyMuPDF, pytest.

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

Create focused modules rather than expanding the legacy ReportLab renderer into a second semantic layer:

```text
app/cv/recruiter_models.py
app/cv/recruiter_policy.py
app/cv/recruiter_composer.py
app/cv/recruiter_validator.py
app/cv/recruiter_qa.py
app/cv/renderers/__init__.py
app/cv/renderers/base.py
app/cv/renderers/rendercv_typst.py
app/application/__init__.py
app/application/prepare.py
config/recruiter_policy.yaml
config/rendercv_one_page.yaml
docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md
```

Existing integration points:

```text
app/cv/models.py
app/cv/service.py
pyproject.toml
README.md
ROADMAP.md
.gitignore
.github/workflows/tests.yml
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

Keep `app/cv/renderer.py` and `app/cv/layout_qa.py` during V0.2B2 for backward-compatible tests. `CVPreparationService` stops using them as the recruiter-facing default once the new path is green.

---

### Task 1: Recruiter policy, render metrics, and presentation models

**Files:**
- Create: `app/cv/recruiter_models.py`
- Create: `app/cv/recruiter_policy.py`
- Create: `config/recruiter_policy.yaml`
- Create: `tests/test_recruiter_models.py`
- Create: `tests/test_recruiter_policy.py`

**Interfaces:**
- Produces: `RecruiterPolicy`, `load_recruiter_policy(path)`, `RecruiterDocumentModel`, `TechnologyGroup`, `RecruiterExperienceEntry`, `RecruiterRenderMetrics`, `RecruiterRenderResult`, `RecruiterQAResult`.
- Recruiter models carry claim IDs and renderer measurements only. They never carry an independent candidate fact store.

- [ ] **Step 1: Write RED model tests**

```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.cv.models import RenderedCVArtifact
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterExperienceEntry,
    RecruiterRenderMetrics,
    RecruiterRenderResult,
    TechnologyGroup,
)


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
        experience_entries=[
            RecruiterExperienceEntry(
                primary_claim_id="fact:employment-1",
                bullet_claim_ids=["approved:employment-1-bullet"],
            )
        ],
        education_claim_ids=["fact:education"],
        language_claim_ids=["fact:language"],
        link_claim_ids=["fact:github"],
    )
    assert document.headline_claim_id == "fact:role"
    assert "fact:python" in document.all_claim_ids()
    assert not hasattr(document, "headline_text")


def test_technology_group_rejects_more_than_twenty_four_skill_claims():
    with pytest.raises(ValidationError):
        TechnologyGroup(
            label_id="software_data",
            skill_claim_ids=[f"fact:skill-{index}" for index in range(25)],
        )


def test_render_result_carries_artifact_and_metrics(tmp_path: Path):
    artifact = RenderedCVArtifact(
        path=str(tmp_path / "cv.pdf"),
        sha256="a" * 64,
        renderer_version="rendercv-typst-v1",
    )
    result = RecruiterRenderResult(
        artifact=artifact,
        metrics=RecruiterRenderMetrics(
            body_font_size=9.4,
            headline_line_count=1,
            overflow_detected=False,
        ),
    )
    assert result.metrics.body_font_size == 9.4
```

- [ ] **Step 2: Run RED**

```bash
pytest tests/test_recruiter_models.py -q
```

Expected: FAIL because `app.cv.recruiter_models` does not exist.

- [ ] **Step 3: Implement strict recruiter models**

```python
# app/cv/recruiter_models.py
from pydantic import Field, model_validator

from app.cv.models import OutputLanguage, RenderedCVArtifact, StrictCVModel, ValidationIssue

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
    profile_claim_ids: list[str] = Field(default_factory=list, max_length=3)
    technology_groups: list[TechnologyGroup] = Field(default_factory=list, max_length=4)
    selected_project_claim_ids: list[str] = Field(default_factory=list, max_length=4)
    experience_entries: list[RecruiterExperienceEntry] = Field(default_factory=list, max_length=5)
    education_claim_ids: list[str] = Field(default_factory=list, max_length=4)
    language_claim_ids: list[str] = Field(default_factory=list)
    link_claim_ids: list[str] = Field(default_factory=list)

    def all_claim_ids(self) -> list[str]:
        ordered = [self.identity_claim_id, self.headline_claim_id]
        ordered.extend(self.contact_claim_ids)
        ordered.extend(self.profile_claim_ids)
        for group in self.technology_groups:
            ordered.extend(group.skill_claim_ids)
        ordered.extend(self.selected_project_claim_ids)
        for entry in self.experience_entries:
            ordered.append(entry.primary_claim_id)
            ordered.extend(entry.bullet_claim_ids)
        ordered.extend(self.education_claim_ids)
        ordered.extend(self.language_claim_ids)
        ordered.extend(self.link_claim_ids)
        return ordered

    @model_validator(mode="after")
    def project_claim_ids_must_be_unique(self):
        if len(self.selected_project_claim_ids) != len(set(self.selected_project_claim_ids)):
            raise ValueError("recruiter project claim ids must be unique")
        return self


class RecruiterRenderMetrics(StrictCVModel):
    body_font_size: float = Field(ge=9.0)
    headline_line_count: int = Field(ge=0)
    overflow_detected: bool = False


class RecruiterRenderResult(StrictCVModel):
    artifact: RenderedCVArtifact
    metrics: RecruiterRenderMetrics


class RecruiterQAResult(StrictCVModel):
    valid: bool
    page_count: int = Field(ge=0)
    extracted_text: str = ""
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
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
preferred_body_font_pt: 9.4
max_projects: 4
max_experience_entries: 5
max_experience_bullets: 1
max_skill_groups: 4
max_skill_tokens: 24
max_profile_claims: 3
max_education_items: 4
skill_groups:
  software_data:
    en: Software & Data
    es: Software y Datos
    members: [Python, SQL]
  additional:
    en: Additional
    es: Adicional
    members: []
""".strip(),
        encoding="utf-8",
    )
    policy = load_recruiter_policy(path)
    assert policy.max_pages == 1
    assert policy.min_body_font_pt == 9.0
    assert policy.max_projects == 4
```

- [ ] **Step 5: Implement `RecruiterPolicy` and public config**

`config/recruiter_policy.yaml` contains only repository-owned caps, labels and generic skill grouping rules. It must not contain real employment facts or fabricated target skills.

- [ ] **Step 6: Run tests and commit**

```bash
pytest tests/test_recruiter_models.py tests/test_recruiter_policy.py -q
git add app/cv/recruiter_models.py app/cv/recruiter_policy.py config/recruiter_policy.yaml tests/test_recruiter_models.py tests/test_recruiter_policy.py
git commit -m "feat: add recruiter policy and presentation models"
```

---

### Task 2: Compose recruiter documents only from semantically validated claims

**Files:**
- Create: `app/cv/recruiter_composer.py`
- Create: `tests/test_recruiter_composer.py`
- Read without weakening: `app/cv/composer.py`, `app/cv/validator.py`

**Interfaces:**
- Consumes: `CVDocumentModel`, `ValidationResult`, `EvidenceSelection`, `RecruiterPolicy`.
- Produces: `compose_recruiter_document(...) -> RecruiterDocumentModel` and `reduce_recruiter_document(...) -> RecruiterDocumentModel`.
- Must not consume: `MasterFactsSnapshot`, `EvidenceCatalogSnapshot`.

- [ ] **Step 1: Write RED unvalidated-claim test**

```python
from app.cv.models import CVClaim
from app.cv.recruiter_composer import compose_recruiter_document


def test_composer_never_selects_claim_outside_validated_claim_ids(
    validated_cv_fixture,
    recruiter_policy,
):
    document, validation, selection = validated_cv_fixture
    tampered = document.model_copy(
        update={
            "claims": [
                *document.claims,
                CVClaim(
                    claim_id="bad",
                    section="skills",
                    kind="skill",
                    text="AWS Expert",
                ),
            ]
        }
    )
    recruiter = compose_recruiter_document(
        document=tampered,
        validation=validation,
        selection=selection,
        policy=recruiter_policy,
    )
    assert "bad" not in recruiter.all_claim_ids()
```

- [ ] **Step 2: Write RED grouped-skill and cap tests**

```python
def test_skills_are_grouped_under_policy_caps(validated_cv_fixture, recruiter_policy):
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
    assert len(recruiter.selected_project_claim_ids) <= 4
    assert all(len(entry.bullet_claim_ids) <= 1 for entry in recruiter.experience_entries)
```

- [ ] **Step 3: Verify RED**

```bash
pytest tests/test_recruiter_composer.py -q
```

Expected: FAIL because composer is missing.

- [ ] **Step 4: Implement deterministic claim relevance**

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

Stable ordering: requirement-supported claims first, then original `document.claims` order. No randomness, current-time ordering or generative rewriting.

- [ ] **Step 5: Implement grouping and experience association**

Skill grouping uses exact normalized validated skill text against `RecruiterPolicy.skill_groups`. Unmatched validated skills may enter only the allowlisted `additional` group while capacity remains.

Associate an experience bullet with an employment/organization claim only when their source provenance shares at least one fact ID. Never infer association from natural-language similarity or PDF proximity.

- [ ] **Step 6: Write RED deterministic reduction test**

```python
def test_reduction_is_deterministic(recruiter_document, recruiter_policy):
    first = reduce_recruiter_document(
        document=recruiter_document,
        policy=recruiter_policy,
        reduction_index=0,
    )
    second = reduce_recruiter_document(
        document=recruiter_document,
        policy=recruiter_policy,
        reduction_index=0,
    )
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert len(first.link_claim_ids) <= len(recruiter_document.link_claim_ids)
```

Reduction sequence is fixed: duplicated optional links -> lower-relevance skill claims -> project #4 then #3 while keeping two projects when two are available -> lower-relevance optional experience -> optional education/training claims.

- [ ] **Step 7: Run tests and commit**

```bash
pytest tests/test_recruiter_composer.py -q
git add app/cv/recruiter_composer.py app/cv/recruiter_models.py tests/test_recruiter_composer.py
git commit -m "feat: compose compact recruiter documents from validated claims"
```

---

### Task 3: Validate recruiter composition against the semantic document

**Files:**
- Create: `app/cv/recruiter_validator.py`
- Create: `tests/test_recruiter_validator.py`

**Interfaces:**
- Consumes: `RecruiterDocumentModel`, `CVDocumentModel`, `ValidationResult`, `RecruiterPolicy`.
- Produces: `ValidationResult` with recruiter-specific bounded issue codes.

- [ ] **Step 1: Write RED unvalidated-reference test**

```python
from app.cv.recruiter_validator import validate_recruiter_document


def test_recruiter_validator_rejects_unvalidated_claim_reference(
    recruiter_document,
    source_document,
    source_validation,
    recruiter_policy,
):
    tampered = recruiter_document.model_copy(
        update={"headline_claim_id": "claim:not-validated"}
    )
    result = validate_recruiter_document(
        recruiter_document=tampered,
        source_document=source_document,
        source_validation=source_validation,
        policy=recruiter_policy,
    )
    assert not result.valid
    assert "recruiter_unvalidated_claim_reference" in {item.code for item in result.errors}
```

- [ ] **Step 2: Write RED group-label test**

```python
def test_recruiter_validator_rejects_unknown_group_label(
    recruiter_document,
    source_document,
    source_validation,
    recruiter_policy,
):
    first_group = recruiter_document.technology_groups[0]
    tampered = recruiter_document.model_copy(
        update={
            "technology_groups": [
                first_group.model_copy(update={"label_id": "aws_expert"})
            ]
        }
    )
    result = validate_recruiter_document(
        recruiter_document=tampered,
        source_document=source_document,
        source_validation=source_validation,
        policy=recruiter_policy,
    )
    assert "recruiter_group_label_not_allowed" in {item.code for item in result.errors}
```

- [ ] **Step 3: Verify RED and implement**

The validator computes:

```python
known_claim_ids = {claim.claim_id for claim in source_document.claims}
validated_claim_ids = set(source_validation.validated_claim_ids)
allowed_claim_ids = known_claim_ids & validated_claim_ids
```

Every ID returned by `recruiter_document.all_claim_ids()` must be in `allowed_claim_ids`. Also enforce allowed group label IDs and policy caps.

- [ ] **Step 4: Run and commit**

```bash
pytest tests/test_recruiter_validator.py -q
git add app/cv/recruiter_validator.py tests/test_recruiter_validator.py
git commit -m "feat: validate recruiter composition against semantic claims"
```

---

### Task 4: Add RenderCV/Typst behind `RecruiterRenderer`

**Files:**
- Create: `app/cv/renderers/__init__.py`
- Create: `app/cv/renderers/base.py`
- Create: `app/cv/renderers/rendercv_typst.py`
- Create: `config/rendercv_one_page.yaml`
- Modify: `pyproject.toml`
- Create: `tests/test_recruiter_renderer.py`

**Interfaces:**

```python
class RecruiterRenderer(Protocol):
    renderer_version: str

    def render(
        self,
        recruiter_document: RecruiterDocumentModel,
        source_document: CVDocumentModel,
        output_path: str | Path,
        policy: RecruiterPolicy,
    ) -> RecruiterRenderResult:
        raise NotImplementedError
```

Default implementation: `RenderCVTypstRenderer`, version `rendercv-typst-v1`.

- [ ] **Step 1: Write dependency compatibility RED test**

```python
def test_rendercv_runtime_is_importable():
    import rendercv
    import typst

    assert rendercv is not None
    assert typst is not None
```

- [ ] **Step 2: Add exact compatible dependencies**

Replace the project dependency arrays with the existing dependencies plus RenderCV and PyMuPDF:

```toml
dependencies = [
  "fastapi",
  "httpx",
  "pydantic>=2",
  "PyYAML",
  "reportlab>=4.2",
  "rendercv[full]>=2.8,<3",
  "uvicorn",
]

[project.optional-dependencies]
dev = ["pypdf>=5", "PyMuPDF>=1.26,<2", "pytest", "pytest-asyncio"]
```

- [ ] **Step 3: Install and verify runtime feasibility**

```bash
python -m pip install -e '.[dev]'
pytest tests/test_recruiter_renderer.py::test_rendercv_runtime_is_importable -q
```

Expected: PASS on Python 3.12+. If supported installation fails, stop Task 4 and report the dependency/runtime blocker. Do not silently change renderer architecture.

- [ ] **Step 4: Write RED one-page renderer test**

```python
from pathlib import Path
from pypdf import PdfReader

from app.cv.renderers.rendercv_typst import RenderCVTypstRenderer


def test_rendercv_renderer_outputs_one_a4_page_with_extractable_text(
    tmp_path,
    recruiter_document,
    source_document,
    recruiter_policy,
):
    result = RenderCVTypstRenderer().render(
        recruiter_document=recruiter_document,
        source_document=source_document,
        output_path=tmp_path / "cv.pdf",
        policy=recruiter_policy,
    )
    reader = PdfReader(result.artifact.path)
    assert len(reader.pages) == 1
    assert "Alex Example" in (reader.pages[0].extract_text() or "")
    assert Path(result.artifact.path).exists()
    assert result.metrics.body_font_size >= 9.0
```

- [ ] **Step 5: Implement exact RenderCV CLI adapter**

Create a private temporary YAML and invoke the installed local CLI with `shell=False`:

```python
command = [
    "rendercv",
    "render",
    str(input_yaml),
    "--design",
    str(design_yaml),
    "--pdf-path",
    str(output_path),
    "--dont-generate-markdown",
    "--dont-generate-html",
    "--dont-generate-png",
    "--quiet",
]
completed = subprocess.run(
    command,
    cwd=temp_dir,
    capture_output=True,
    text=True,
    check=False,
)
if completed.returncode != 0:
    raise ValueError("RenderCV/Typst render failed")
```

`config/rendercv_one_page.yaml` uses built-in `sb2nov` as the base theme with A4 page size, no photo, no footer, no top note, one-column flow, body font 9.4 pt, and compact spacing. The config is owned by Opportunity OS and contains no candidate content.

- [ ] **Step 6: Implement payload mapping without semantic parsing**

Resolve text only through source claim IDs:

```python
def _claim_text(source_document: CVDocumentModel, claim_id: str) -> str:
    claim_by_id = {claim.claim_id: claim for claim in source_document.claims}
    return claim_by_id[claim_id].text
```

Build sections as RenderCV text entries and label/detail skill entries. Do not split an employment string into guessed company/title/date fields. Markdown emphasis may wrap a validated claim for presentation, but the visible candidate text must remain byte-for-byte the validated claim text after Markdown syntax is removed by rendering.

- [ ] **Step 7: Measure renderer-owned metrics from the generated PDF**

Use PyMuPDF to count the rendered headline lines and detect any text block outside page bounds. Set `body_font_size` from the fixed design config. Set `overflow_detected=True` if any text block exceeds page bounds.

- [ ] **Step 8: Prove deterministic bytes**

```python
def test_renderer_is_deterministic(
    tmp_path,
    recruiter_document,
    source_document,
    recruiter_policy,
):
    renderer = RenderCVTypstRenderer()
    first = renderer.render(
        recruiter_document,
        source_document,
        tmp_path / "a.pdf",
        recruiter_policy,
    )
    second = renderer.render(
        recruiter_document,
        source_document,
        tmp_path / "b.pdf",
        recruiter_policy,
    )
    assert Path(first.artifact.path).read_bytes() == Path(second.artifact.path).read_bytes()
    assert first.artifact.sha256 == second.artifact.sha256
```

- [ ] **Step 9: Run and commit**

```bash
pytest tests/test_recruiter_renderer.py -q
git add app/cv/renderers config/rendercv_one_page.yaml pyproject.toml tests/test_recruiter_renderer.py
git commit -m "feat: render recruiter CVs with RenderCV and Typst"
```

---

### Task 5: RecruiterQualityQA with exact one-page hard gates

**Files:**
- Create: `app/cv/recruiter_qa.py`
- Create: `tests/test_recruiter_qa.py`

**Interfaces:**

```python
class RecruiterQualityQA:
    def evaluate(
        self,
        render_result: RecruiterRenderResult,
        recruiter_document: RecruiterDocumentModel,
        source_document: CVDocumentModel,
        policy: RecruiterPolicy,
    ) -> RecruiterQAResult:
        raise NotImplementedError
```

- [ ] **Step 1: Write RED two-page hard-failure test**

```python
def test_two_page_pdf_is_hard_failure(
    two_page_render_result,
    recruiter_document,
    source_document,
    recruiter_policy,
):
    result = RecruiterQualityQA().evaluate(
        render_result=two_page_render_result,
        recruiter_document=recruiter_document,
        source_document=source_document,
        policy=recruiter_policy,
    )
    assert not result.valid
    assert "recruiter_one_page_failed" in {item.code for item in result.errors}
```

- [ ] **Step 2: Write RED font and extractable-text tests**

```python
def test_body_font_below_nine_points_is_hard_failure(
    one_page_render_result,
    recruiter_document,
    source_document,
    recruiter_policy,
):
    render_result = one_page_render_result.model_copy(
        update={
            "metrics": one_page_render_result.metrics.model_copy(
                update={"body_font_size": 8.9}
            )
        }
    )
    result = RecruiterQualityQA().evaluate(
        render_result,
        recruiter_document,
        source_document,
        recruiter_policy,
    )
    assert "recruiter_body_font_too_small" in {item.code for item in result.errors}


def test_missing_extractable_text_is_hard_failure(
    blank_render_result,
    recruiter_document,
    source_document,
    recruiter_policy,
):
    result = RecruiterQualityQA().evaluate(
        blank_render_result,
        recruiter_document,
        source_document,
        recruiter_policy,
    )
    assert "recruiter_text_not_extractable" in {item.code for item in result.errors}
```

- [ ] **Step 3: Implement hard gates**

Runtime QA checks:

```text
page_count == 1
A4 dimensions within deterministic tolerance
metrics.body_font_size >= 9.0
metrics.headline_line_count <= 2
metrics.overflow_detected == false
extractable text is non-empty
page contains no embedded raster images
candidate claim texts appear in canonical section order
```

Any failure produces a recruiter-specific `ValidationIssue`; `page_count != 1` always uses `recruiter_one_page_failed`.

- [ ] **Step 4: Add two-extractor ATS test**

```python
from pypdf import PdfReader
import fitz


def test_golden_pdf_survives_two_independent_extractors(golden_pdf):
    pypdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(golden_pdf).pages
    )
    pymupdf_text = "\n".join(page.get_text() for page in fitz.open(golden_pdf))
    expected_fields = [
        "Alex Example",
        "alex@example.test",
        "Python",
        "Example Labs",
    ]
    for expected in expected_fields:
        assert expected in pypdf_text
        assert expected in pymupdf_text
```

- [ ] **Step 5: Run and commit**

```bash
pytest tests/test_recruiter_qa.py -q
git add app/cv/recruiter_qa.py tests/test_recruiter_qa.py
git commit -m "feat: enforce recruiter one-page quality gates"
```

---

### Task 6: Integrate recruiter composition, render, reduction, and packet hashing

**Files:**
- Modify: `app/cv/service.py`
- Modify: `app/cv/models.py`
- Modify: `tests/test_cv_service.py`

**Interfaces:**
- Existing `CVPreparationService.prepare(...)` inputs remain unchanged.
- Add constructor collaborators: `recruiter_policy`, `recruiter_renderer`, `recruiter_qa`.
- Add packet fields: `recruiter_document`, `recruiter_policy_version`.
- Existing `renderer_version` records `rendercv-typst-v1` for the recruiter artifact.

- [ ] **Step 1: Write RED two-page service regression**

Use existing helpers in `tests/test_cv_service.py`:

```python
def test_prepare_blocks_when_recruiter_output_is_two_pages(tmp_path):
    master, catalog, policy = _inputs()
    result = _service(renderer=TwoPageRecruiterRenderer()).prepare(
        assessment=_assessment(),
        master_facts=master,
        evidence_catalog=catalog,
        policy=policy,
        output_root=tmp_path,
        now=NOW,
    )
    assert result.status == "BLOCKED_RENDER"
    assert result.packet is None
    assert list(tmp_path.rglob("*.pdf")) == []
    assert "recruiter_one_page_failed" in {item.code for item in result.errors}
```

- [ ] **Step 2: Write RED packet-content test**

```python
def test_prepared_packet_contains_semantic_and_recruiter_documents(tmp_path):
    master, catalog, policy = _inputs()
    result = _service().prepare(
        assessment=_assessment(),
        master_facts=master,
        evidence_catalog=catalog,
        policy=policy,
        output_root=tmp_path,
        now=NOW,
    )
    assert result.status == "PREPARED"
    assert result.packet is not None
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
validate_cv
compose_recruiter_document
validate_recruiter_document
render
RecruiterQualityQA
if QA fails only for density/one-page overflow:
    reduce optional validated claims using next deterministic reduction index
    validate recruiter document again
    render again
    run QA again
if no reduction remains or a non-density hard gate fails:
    remove partial PDF
    return BLOCKED_RENDER
build ApplicationPacket
return PREPARED
```

The loop iterates over a finite reduction sequence returned by recruiter policy/composer. No open-ended retries.

- [ ] **Step 4: Update packet hash payload**

Include:

```python
"recruiter_document": packet.recruiter_document.model_dump(mode="json"),
"recruiter_policy_version": packet.recruiter_policy_version,
"renderer_version": packet.renderer_version,
```

Grouping/order changes must change `packet_sha256` even when semantic `cv_document` is unchanged.

- [ ] **Step 5: Run focused CV suite and commit**

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
- Modify: `tests/test_recruiter_renderer.py`

**Interfaces:**
- Golden A: fictional software/geospatial structure with three skill groups, four projects, compact experience, education close.
- Golden B: fictional technology + operations structure with software/data + operations/process groups and unsupported enterprise tools absent.

- [ ] **Step 1: Write RED one-page golden test**

```python
import pytest


@pytest.mark.parametrize(
    "fixture_name",
    ["recruiter_software", "recruiter_tech_operations"],
)
def test_golden_recruiter_profiles_are_exactly_one_page(
    fixture_name,
    tmp_path,
    recruiter_policy,
):
    recruiter_document, source_document = load_golden_fixture(fixture_name)
    render_result = RenderCVTypstRenderer().render(
        recruiter_document,
        source_document,
        tmp_path / f"{fixture_name}.pdf",
        recruiter_policy,
    )
    qa_result = RecruiterQualityQA().evaluate(
        render_result,
        recruiter_document,
        source_document,
        recruiter_policy,
    )
    assert qa_result.valid
    assert qa_result.page_count == 1
```

- [ ] **Step 2: Add no-private-data fixture guard**

```python
from pathlib import Path


def test_public_recruiter_fixtures_are_fictional():
    paths = [
        Path("tests/fixtures/recruiter_software.json"),
        Path("tests/fixtures/recruiter_tech_operations.json"),
    ]
    forbidden = [
        "juan.manuel.torres@",
        "+54 9 351",
        "master_facts.local.yaml",
        "evidence_catalog.local.yaml",
    ]
    payload = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for token in forbidden:
        assert token not in payload
```

- [ ] **Step 3: Add grouped-skill extraction assertions**

Assert that each fictional skill-group label and every selected skill token survives both PyPDF and PyMuPDF extraction. Do not use private screenshot hashes or pixel-perfect assertions.

- [ ] **Step 4: Run and commit**

```bash
pytest tests/test_cv_release_contract.py tests/test_recruiter_renderer.py tests/test_recruiter_qa.py -q
git add tests/fixtures/recruiter_software.json tests/fixtures/recruiter_tech_operations.json tests/test_cv_release_contract.py tests/test_recruiter_renderer.py
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
- Canonical input file passed through `--opportunity` MUST validate as a serialized `RadarAssessment`; a raw `Opportunity` alone is rejected rather than assigned invented track/score/intent values.
- Exact command:

```bash
python -m app.application.prepare \
  --opportunity artifacts/opportunities/<id>/radar_assessment.json \
  --master-facts profile/master_facts.local.yaml \
  --evidence-catalog profile/evidence_catalog.local.yaml \
  --recruiter-policy config/recruiter_policy.yaml \
  --output-root artifacts/applications
```

- [ ] **Step 1: Write RED CLI success test**

```python
import json

from app.application.prepare import main


def test_cli_prepares_from_serialized_radar_assessment(
    assessment_path,
    master_path,
    catalog_path,
    policy_path,
    tmp_path,
    capsys,
):
    exit_code = main(
        [
            "--opportunity",
            str(assessment_path),
            "--master-facts",
            str(master_path),
            "--evidence-catalog",
            str(catalog_path),
            "--recruiter-policy",
            str(policy_path),
            "--output-root",
            str(tmp_path / "applications"),
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "PREPARED"
    assert output["page_count"] == 1
    assert len(output["cv_sha256"]) == 64
    assert len(output["packet_sha256"]) == 64
```

- [ ] **Step 2: Write RED no-inference test**

```python
def test_cli_rejects_plain_opportunity_without_radar_assessment(
    opportunity_only_path,
    master_path,
    catalog_path,
    policy_path,
    tmp_path,
    capsys,
):
    exit_code = main(
        [
            "--opportunity",
            str(opportunity_only_path),
            "--master-facts",
            str(master_path),
            "--evidence-catalog",
            str(catalog_path),
            "--recruiter-policy",
            str(policy_path),
            "--output-root",
            str(tmp_path / "applications"),
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert exit_code != 0
    assert output["error"] == "invalid_radar_assessment"
```

- [ ] **Step 3: Implement strict CLI**

Load private YAML snapshots through existing CV loaders. Parse `--opportunity` as `RadarAssessment.model_validate_json(...)`. Load taxonomy/alias registry from repository config. Use timezone-aware current time only as packet creation time.

Print one JSON object containing:

```text
status
application_id
cv_pdf_path
page_count
cv_sha256
packet_sha256
unresolved_gaps
errors
warnings
```

The CLI never sends email, mutates Gmail, submits forms, or marks an opportunity `Postulado`.

- [ ] **Step 4: Run and commit**

```bash
pytest tests/test_application_prepare_cli.py -q
git add app/application tests/test_application_prepare_cli.py
git commit -m "feat: add canonical one-command application preparation"
```

---

### Task 9: Agent runbook, README, privacy and CI guardrails

**Files:**
- Create: `docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md`
- Modify: `README.md`
- Modify: `ROADMAP.md`
- Modify: `.gitignore` only if current patterns are insufficient
- Modify: `.github/workflows/tests.yml`
- Modify: `tests/test_cv_release_contract.py`

- [ ] **Step 1: Create authoritative fresh-context runbook**

Opening block must be exactly:

```markdown
# Opportunity OS Agent Runbook

DO NOT reconstruct CV generation from memory.
DO NOT hand-build recruiter PDFs when the canonical command is available.
PREPARED requires exactly one recruiter-quality A4 page.
PREPARED != APPROVE != SEND.
Private candidate snapshots and generated artifacts never enter the public repo.
```

Document prerequisites, canonical command, private file locations, how to obtain a `RadarAssessment`, blocked statuses, unresolved gaps, post-render inspection, active-posting versus target-account distinction, and unsupported-requirement behavior.

- [ ] **Step 2: Update README/ROADMAP flow**

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

CI installs `.[dev]` so the same RenderCV/Typst and extraction dependencies used locally exist in CI, then runs the complete test suite. Do not create a divergent second environment.

- [ ] **Step 4: Verify privacy ignores**

At minimum, ensure these patterns are ignored:

```text
profile/*.local.yaml
artifacts/applications/
*.local.yaml
```

Public fictional fixtures stay tracked.

- [ ] **Step 5: Run and commit**

```bash
pytest tests/test_cv_release_contract.py tests/test_application_prepare_cli.py -q
git add docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md README.md ROADMAP.md .gitignore .github/workflows/tests.yml tests/test_cv_release_contract.py
git commit -m "docs: make one-page preparation reproducible for fresh agents"
```

---

### Task 10: Full verification and private Coca-Cola smoke run

**Files:**
- No real candidate data is committed.
- Local ignored output: `artifacts/applications/<application_id>/cv.pdf` and `ApplicationPacket` JSON.

- [ ] **Step 1: Run complete automated verification**

```bash
python -m compileall app
pytest -q
```

Expected: all tests PASS.

- [ ] **Step 2: Run the canonical command against the private Coca-Cola assessment**

```bash
python -m app.application.prepare \
  --opportunity <private-cocacola-radar-assessment.json> \
  --master-facts profile/master_facts.local.yaml \
  --evidence-catalog profile/evidence_catalog.local.yaml \
  --recruiter-policy config/recruiter_policy.yaml \
  --output-root artifacts/applications
```

Expected: `PREPARED` with exactly one page, or an explicit fail-closed status. Never bypass a failed gate manually.

- [ ] **Step 3: Inspect private output against the approved benchmark**

```text
one page only
name/headline hierarchy comparable to strong Maptek/Esri artifacts
compact contact block
profile <= 3 lines
skills grouped into recruiter rows
2-4 target-relevant projects when evidence permits
experience compact, <= 1 bullet per included role
education/training closes the page
no clipping
no giant blank lower region
no unsupported Power BI/SAP/B2B claims
```

The smoke PDF is never committed.

- [ ] **Step 4: Verify git diff and privacy**

```bash
git status --short
git diff --check
git ls-files | grep -E 'master_facts\.local|evidence_catalog\.local|artifacts/applications' && exit 1 || true
```

- [ ] **Step 5: Final implementation commit only after clean verification**

```bash
git add -u
git commit -m "feat: complete V0.2B2 one-page recruiter pipeline"
```

Do not claim V0.2B2 complete until the full suite and private recruiter-quality smoke have both passed inspection.

---

## Plan Self-Review

### Spec coverage

- Exactly one page: Tasks 4-7.
- ClaimValidator before recruiter composition: Tasks 2, 3 and 6.
- Recruiter claim-reference isolation: Tasks 1-3.
- Grouped skills/content budgets: Tasks 1-2.
- Deterministic fit reduction: Tasks 2 and 6.
- RenderCV/Typst inside Opportunity OS: Task 4.
- ATS verification with two independent extractors: Tasks 5 and 7.
- Reproducible packet: Task 6.
- Canonical fresh-context command: Task 8.
- Agent runbook/privacy/no-SEND contract: Task 9.
- Real private smoke without committing candidate data: Task 10.

### Placeholder scan

Every code step names concrete functions, arguments and assertions. No implementation step relies on `TBD`, `TODO`, unnamed error handling, omitted test arguments, or an unspecified renderer interface.

### Type consistency

```text
CVDocumentModel
ValidationResult
RecruiterDocumentModel
RecruiterPolicy
RecruiterRenderMetrics
RecruiterRenderResult
RecruiterQAResult
RecruiterRenderer
RenderCVTypstRenderer
RecruiterQualityQA
ApplicationPacket
```

`RecruiterDocumentComposer` never receives private `MasterFactsSnapshot` or `EvidenceCatalogSnapshot` directly. The existing semantic pipeline remains the sole path from private facts/evidence to validated `CVDocumentModel` claims.