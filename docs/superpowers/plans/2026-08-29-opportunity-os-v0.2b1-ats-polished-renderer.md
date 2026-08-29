# Opportunity OS V0.2B1 — ATS Polished Renderer + Layout QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce polished, deterministic, ATS-safe CV PDFs with layout quality checks and professional recruiter-facing filenames while preserving all V0.2B truth/provenance guarantees.

**Architecture:** Keep semantics upstream: `CVComposer -> ClaimValidator -> ATSRenderer -> LayoutQA -> ApplicationPacket`. Upgrade `ATSRenderer` to `ats-pdf-v2`, add a focused `LayoutQA` that consumes bounded renderer metrics plus extracted PDF text, and add a pure deterministic filename helper. Hard layout failures map to existing `BLOCKED_RENDER`; warnings are appended to preparation warnings.

**Tech Stack:** Python 3.12+, Pydantic v2, ReportLab, pypdf, pytest.

**Spec:** `docs/superpowers/specs/2026-08-29-opportunity-os-v0.2b1-ats-polished-renderer-design.md`

## Global Constraints

- A4 only; one text column; selectable text.
- Approved fonts only: `Helvetica`, `Helvetica-Bold`; body font >= 9 pt.
- No photos, logos, sidebars, tables, charts, skill bars, semantic icons, rasterized text, external fonts or network resources.
- Renderer may not rewrite, split, invent or infer claim semantics.
- `ClaimValidator` remains mandatory before render.
- `LayoutQA` never mutates `CVDocumentModel`.
- Hard layout failure maps to `BLOCKED_RENDER`; warning thresholds are fixed at `< 0.58` and `> 0.96`; maximum page count is 2.
- Recruiter-facing filename is deterministic, path-safe and <= 120 characters.
- Fixed semantic input + fixed renderer constants must produce deterministic PDF bytes/SHA256.
- Private real-user smoke PDFs are never committed.

---

### Task 1: Renderer V2 visual contract

**Files:**
- Modify: `app/cv/renderer.py`
- Modify: `tests/test_cv_renderer.py`

**Interfaces:**
- Consumes: validated `CVDocumentModel`, `ValidationResult`, output `Path`.
- Produces: existing `RenderedCVArtifact`; `ATSRenderer.renderer_version == "ats-pdf-v2"`; bounded `layout_metrics` property on the renderer instance for Task 3 integration.

- [ ] **Step 1: Write failing renderer-contract tests**

Add assertions that V2 exposes deterministic constants and preserves the validation gate:

```python
from reportlab.lib.pagesizes import A4


def test_renderer_v2_contract() -> None:
    renderer = ATSRenderer()
    assert renderer.renderer_version == "ats-pdf-v2"
    assert renderer.page_size == A4
    assert renderer.body_font_name == "Helvetica"
    assert renderer.bold_font_name == "Helvetica-Bold"
    assert renderer.body_font_size >= 9.0
    assert renderer.name_font_size >= renderer.body_font_size + 6.0
    assert renderer.max_pages == 2
```

Update the existing artifact assertion to `ats-pdf-v2`. Keep the invalid-validation test unchanged.

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
pytest tests/test_cv_renderer.py -q
```

Expected: FAIL because current renderer reports `ats-pdf-v1` and lacks V2 constants.

- [ ] **Step 3: Implement minimal V2 constants and hierarchy**

In `ATSRenderer`, define constants/properties equivalent to:

```python
renderer_version = "ats-pdf-v2"
page_size = A4
body_font_name = "Helvetica"
bold_font_name = "Helvetica-Bold"
body_font_size = 9.8
name_font_size = 18.0
role_font_size = 11.5
section_font_size = 11.0
metadata_font_size = 9.0
max_pages = 2
accent_hex = "#173B57"
```

Build styles by `CVClaim.kind` within the existing one-column story:

```python
if section_name == "headline" and claim.kind == "identity":
    style = name_style
elif section_name == "headline" and claim.kind == "headline":
    style = role_style
elif section_name == "headline" and claim.kind in {"contact", "location", "link"}:
    style = metadata_style
```

Use only ReportLab built-in fonts. Add deterministic spacing and a non-semantic thin divider after the header using a small custom `Flowable` or `HRFlowable`; do not introduce tables or frames.

- [ ] **Step 4: Run focused tests and confirm GREEN**

```bash
pytest tests/test_cv_renderer.py -q
```

Expected: PASS, including selectable text and deterministic bytes.

- [ ] **Step 5: Commit**

```bash
git add app/cv/renderer.py tests/test_cv_renderer.py
git commit -m "feat: add ATS renderer v2 hierarchy"
```

---

### Task 2: Professional recruiter-facing filename

**Files:**
- Create: `app/cv/filename.py`
- Create: `tests/test_cv_filename.py`

**Interfaces:**
- Produces: `build_cv_filename(candidate_name: str, role: str, company: str, *, max_length: int = 120) -> str`.

- [ ] **Step 1: Write failing filename tests**

```python
from app.cv.filename import build_cv_filename


def test_filename_is_professional_and_deterministic() -> None:
    filename = build_cv_filename(
        "Juan Manuel Torres",
        "Backend Engineer – Python, AWS & GenAI",
        "Scale Up Recruiting Partners",
    )
    assert filename.endswith(".pdf")
    assert "UPDATED" not in filename.upper()
    assert "FINAL" not in filename.upper()
    assert "/" not in filename and "\\" not in filename
    assert len(filename) <= 120
    assert filename == build_cv_filename(
        "Juan Manuel Torres",
        "Backend Engineer – Python, AWS & GenAI",
        "Scale Up Recruiting Partners",
    )


def test_filename_normalizes_path_unsafe_characters() -> None:
    filename = build_cv_filename("A/B", "Dev: API", "ACME (LATAM)")
    assert filename == "A_B_Dev_API_ACME_LATAM.pdf"
```

- [ ] **Step 2: Confirm RED**

```bash
pytest tests/test_cv_filename.py -q
```

Expected: import failure because helper does not exist.

- [ ] **Step 3: Implement pure deterministic sanitizer**

Use Unicode normalization and a strict token policy without timestamps/UUIDs:

```python
def build_cv_filename(candidate_name: str, role: str, company: str, *, max_length: int = 120) -> str:
    stem = "_".join(_sanitize(part) for part in (candidate_name, role, company) if part.strip())
    stem = re.sub(r"_+", "_", stem).strip("_") or "CV"
    return _truncate_stem(stem, max_length - 4) + ".pdf"
```

Strip operational suffix tokens `updated`, `final`, `latest`, and copy-number-only suffixes when they appear as standalone generated filename noise; never remove meaningful words from candidate/role/company inputs.

- [ ] **Step 4: Confirm GREEN**

```bash
pytest tests/test_cv_filename.py -q
```

- [ ] **Step 5: Commit**

```bash
git add app/cv/filename.py tests/test_cv_filename.py
git commit -m "feat: add professional CV filename builder"
```

---

### Task 3: Deterministic Layout QA

**Files:**
- Create: `app/cv/layout_qa.py`
- Modify: `app/cv/models.py`
- Create: `tests/test_cv_layout_qa.py`
- Modify: `app/cv/renderer.py`

**Interfaces:**
- Produces models:

```python
class RenderLayoutMetrics(StrictCVModel):
    page_count: int
    usable_height: float
    rendered_content_height: float
    headline_line_count: int
    body_font_size: float

class LayoutQAResult(StrictCVModel):
    valid: bool
    page_count: int
    warnings: list[ValidationIssue] = []
    errors: list[ValidationIssue] = []
    used_height_ratio: float
```

- Produces service:

```python
class LayoutQA:
    def evaluate(self, artifact: RenderedCVArtifact, metrics: RenderLayoutMetrics, *, expected_nonempty: bool = True) -> LayoutQAResult: ...
```

- [ ] **Step 1: Write failing QA tests**

Cover exact fixed policy:

```python
def test_low_utilization_is_warning_not_error(...):
    result = qa.evaluate(artifact, metrics(rendered=0.50 * usable))
    assert result.valid is True
    assert [w.code for w in result.warnings] == ["layout_low_utilization"]


def test_high_utilization_is_warning_not_error(...):
    result = qa.evaluate(artifact, metrics(rendered=0.97 * usable))
    assert result.valid is True
    assert "layout_high_utilization" in {w.code for w in result.warnings}


def test_more_than_two_pages_is_hard_error(...):
    result = qa.evaluate(artifact, metrics(page_count=3))
    assert result.valid is False
    assert "layout_page_count_exceeded" in {e.code for e in result.errors}


def test_missing_extractable_text_is_hard_error(...):
    result = qa.evaluate(empty_text_artifact, metrics(...), expected_nonempty=True)
    assert result.valid is False
    assert "layout_missing_extractable_text" in {e.code for e in result.errors}
```

Also test `headline_line_count > 2` gives `layout_headline_wrap` warning and body font below 9 gives hard `layout_body_font_too_small`.

- [ ] **Step 2: Confirm RED**

```bash
pytest tests/test_cv_layout_qa.py -q
```

Expected: import/model failures.

- [ ] **Step 3: Add bounded models and renderer instrumentation**

Add strict models to `app/cv/models.py`. Instrument only renderer-owned geometry; do not inspect claims semantically. The renderer records `RenderLayoutMetrics` after document build. Derive used height from deterministic flowable wrap heights accumulated while building the story or a dedicated renderer-owned measurement pass; do not use computer vision.

- [ ] **Step 4: Implement `LayoutQA`**

Use pypdf to verify page count and selectable extraction:

```python
reader = PdfReader(artifact.path)
text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
ratio = metrics.rendered_content_height / metrics.usable_height if metrics.usable_height else 0.0
```

Fixed constants:

```python
LOW_UTILIZATION = 0.58
HIGH_UTILIZATION = 0.96
MAX_PAGES = 2
MIN_BODY_FONT = 9.0
MAX_HEADLINE_LINES = 2
```

Warnings never flip `valid`; hard errors do.

- [ ] **Step 5: Confirm GREEN**

```bash
pytest tests/test_cv_layout_qa.py tests/test_cv_renderer.py -q
```

- [ ] **Step 6: Commit**

```bash
git add app/cv/layout_qa.py app/cv/models.py app/cv/renderer.py tests/test_cv_layout_qa.py tests/test_cv_renderer.py
git commit -m "feat: add deterministic CV layout QA"
```

---

### Task 4: CVPreparationService integration

**Files:**
- Modify: `app/cv/service.py`
- Modify existing CV service/factory tests containing `CVPreparationService`; if no focused integration test exists, create `tests/test_cv_factory_integration.py`.

**Interfaces:**
- `CVPreparationService(..., renderer: ATSRenderer | None = None, layout_qa: LayoutQA | None = None)`.
- Hard QA failure returns existing `PreparationStatus == "BLOCKED_RENDER"` with `ValidationIssue(code="layout_qa_failed", ...)` or the first bounded layout error code.
- QA warnings append to existing validation warnings.

- [ ] **Step 1: Write failing integration tests**

Use fake renderer/QA boundaries to prove service behavior rather than testing ReportLab again:

```python
def test_hard_layout_failure_blocks_packet_and_removes_pdf(...):
    service = CVPreparationService(..., renderer=fake_renderer, layout_qa=failing_qa)
    result = service.prepare(...)
    assert result.status == "BLOCKED_RENDER"
    assert result.packet is None
    assert not expected_pdf.exists()


def test_layout_warnings_are_returned_without_blocking_packet(...):
    service = CVPreparationService(..., renderer=fake_renderer, layout_qa=warning_qa)
    result = service.prepare(...)
    assert result.status == "PREPARED"
    assert "layout_low_utilization" in {w.code for w in result.warnings}
```

- [ ] **Step 2: Confirm RED**

Run the focused service test file and expect missing `layout_qa` injection/invocation.

- [ ] **Step 3: Implement integration**

After successful render:

```python
layout_result = self.layout_qa.evaluate(
    artifact,
    self.renderer.layout_metrics,
    expected_nonempty=bool(document.claims),
)
if not layout_result.valid:
    _remove_partial_pdf(output_path)
    return PreparationResult(status="BLOCKED_RENDER", errors=layout_result.errors, warnings=layout_result.warnings)
```

For success:

```python
warnings=[*validation.warnings, *layout_result.warnings]
```

Do not include layout metrics in semantic `packet_sha256`; presentation bytes remain represented by `cv_sha256` and renderer version.

- [ ] **Step 4: Confirm GREEN**

Run focused CV service + renderer + QA tests.

- [ ] **Step 5: Commit**

```bash
git add app/cv/service.py tests/test_cv_factory_integration.py
git commit -m "feat: gate CV packets with layout QA"
```

---

### Task 5: Release contracts and documentation

**Files:**
- Modify: `tests/test_cv_release_contract.py`
- Modify: `README.md`
- Modify: `ROADMAP.md`

**Interfaces:** No new runtime API.

- [ ] **Step 1: Write failing release-contract assertions**

Assert repository source contains the V2 guarantees and excludes unsafe renderer patterns:

```python
assert "ats-pdf-v2" in renderer_source
for forbidden in ("Image(", "Table(", "ImageReader", "registerFont", "TTFont"):
    assert forbidden not in renderer_source
assert "LOW_UTILIZATION = 0.58" in layout_source
assert "HIGH_UTILIZATION = 0.96" in layout_source
assert "MAX_PAGES = 2" in layout_source
```

Keep existing provenance/track/private-file guards unchanged.

- [ ] **Step 2: Confirm RED**

Run release-contract tests before doc/source update.

- [ ] **Step 3: Update README/ROADMAP**

Document V0.2B1 as polished ATS-safe rendering + deterministic layout QA. State explicitly that visual polish does not authorize unsupported claims and that target skills such as AWS remain gaps unless evidence supports them.

- [ ] **Step 4: Run full verification**

```bash
pytest -q
python -m compileall app

git diff --check main...HEAD
```

Also run the repository's private/generated-file guard command exactly as CI defines it.

- [ ] **Step 5: Commit**

```bash
git add tests/test_cv_release_contract.py README.md ROADMAP.md
git commit -m "docs: document ATS polished CV rendering"
```

---

### Task 6: Real private Scale Up smoke render

**Files:**
- No private output committed.
- Optional test-only/public synthetic fixture additions only if a regression is discovered.

**Interfaces:** Real smoke uses the same `CVPreparationService`/renderer path; no special production bypass.

- [ ] **Step 1: Build a verified backend-oriented document from existing user evidence**

Use only evidence already supported by the user's verified CV/evidence catalog: Python, FastAPI, REST APIs, PostgreSQL/PostGIS, React/TypeScript, Docker, GitHub Actions/CI/CD, testing, integrations, AI-assisted workflows. Do not claim AWS production experience.

Target headline if supported by existing facts/evidence:

```text
PYTHON BACKEND & GEOSPATIAL SOFTWARE DEVELOPER
```

- [ ] **Step 2: Render through V2 and run Layout QA**

Expected:

```text
renderer_version = ats-pdf-v2
layout.valid = true
page_count <= 2
selectable text present
no AWS experience claim
```

- [ ] **Step 3: Inspect visually**

Render page image locally for inspection. Check name/role hierarchy, contact readability, section rhythm, lower-page balance, projects, no clipping/overlap, and professional filename.

- [ ] **Step 4: If a defect is found, add RED regression test before fixing it**

No ad-hoc visual patch without a testable deterministic rule.

- [ ] **Step 5: Final branch verification**

Run full CI on the final branch HEAD and inspect its logs/status before claiming completion.
