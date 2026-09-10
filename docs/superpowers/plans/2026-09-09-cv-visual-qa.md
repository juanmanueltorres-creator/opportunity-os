# CV Visual QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic visual-quality gate that blocks recruiter PDFs with severe visual defects even when semantic, ATS, and renderer checks pass.

**Architecture:** Introduce strict `VisualPolicy`, typed visual metrics/results, and an independent `VisualQualityQA` stage that inspects actual PDF geometry with PyMuPDF. Move visual-only checks out of `RecruiterQualityQA`; wire Visual QA into the existing render/reduction loop while preserving the selected `LayoutProfile`, evidence constraints, and Narrative QA revalidation.

**Tech Stack:** Python 3.12/3.13, Pydantic v2, PyMuPDF, pytest, RenderCV 2.8, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-09-cv-visual-qa-design.md`

## Global Constraints

- `VisualQualityQA` is deterministic and PDF-geometry based; no OCR, computer vision, or LLM aesthetic grading.
- Visual QA may inspect but never add, rewrite, remove, or reorder candidate claims.
- `LayoutProfile.density` may adjust only high-density/overcompression thresholds; it must not relax underfill checks.
- Existing visual checks move out of `RecruiterQualityQA`; they must not be duplicated.
- Only `visual_overcompressed` and `visual_wall_of_text_severe` are reducible visual hard failures in v1.
- Every reduction must rerun structural validation, Narrative QA, rendering, RecruiterQualityQA, and VisualQualityQA with the same selected `LayoutProfile`.
- Visual hard failures produce `BLOCKED_RENDER`; blocked preparation must leave no PDF artifact.
- No ApplicationPacket schema changes in this PR.
- No Gmail, outreach, approval, or send behavior changes.
- No private track identifiers may be committed.

---

### Task 1: Visual policy and typed contracts

**Files:**
- Create: `app/cv/visual_policy.py`
- Create: `app/cv/visual_models.py`
- Create: `config/visual_policy.yaml`
- Test: `tests/test_cv_visual_policy.py`

**Interfaces:**
- Produces: `VISUAL_POLICY_VERSION = "visual-policy-v1"`.
- Produces: `VisualPolicy`, `load_visual_policy(path: str | Path) -> VisualPolicy`.
- Produces: `density_thresholds_for_profile(policy: VisualPolicy, profile: LayoutProfile) -> tuple[float, float]` returning warning/error line-density thresholds.
- Produces: `VisualMetrics` and `VisualQAResult` strict models.

- [ ] **Step 1: Write failing policy/model tests**

Add tests that import the new module and assert:

```python
policy = load_visual_policy("config/visual_policy.yaml")
assert policy.version == "visual-policy-v1"
assert policy.underfill_error_bottom_ratio < policy.underfill_warning_bottom_ratio
assert policy.wall_text_warning_lines < policy.wall_text_error_lines
assert policy.wall_text_warning_chars < policy.wall_text_error_chars
assert policy.large_gap_warning_ratio < policy.large_gap_error_ratio
assert policy.density_warning_lines_per_page < policy.density_error_lines_per_page
```

Also assert unknown fields are rejected and invalid threshold ordering raises `ValueError`/Pydantic validation errors. Build three `LayoutProfile` fixtures and assert density thresholds are deterministic and ordered so `compact` allows more line density than `balanced`, which allows more than `comfortable`; underfill thresholds remain identical because they come directly from `VisualPolicy`.

- [ ] **Step 2: Run RED**

Run the new test file in CI or the repository test environment.

Expected: collection/import failure because `app.cv.visual_policy` / `app.cv.visual_models` do not exist.

- [ ] **Step 3: Implement strict contracts**

`VisualPolicy` must use the repository strict-model pattern and include exactly these fields:

```python
version: str
min_substantive_claims_for_underfill: int
underfill_warning_bottom_ratio: float
underfill_error_bottom_ratio: float
isolated_bottom_start_ratio: float
isolated_bottom_min_gap_pt: float
max_headline_lines: int
wall_text_warning_lines: int
wall_text_error_lines: int
wall_text_warning_chars: int
wall_text_error_chars: int
large_gap_warning_ratio: float
large_gap_error_ratio: float
density_warning_lines_per_page: float
density_error_lines_per_page: float
hierarchy_min_delta_pt: float
orphan_heading_bottom_ratio: float
orphan_heading_max_following_lines: int
```

Use model validation to enforce ranges and ordering. `density_thresholds_for_profile` applies fixed generic multipliers:

```python
comfortable = 0.90
balanced = 1.00
compact = 1.15
```

These multipliers apply only to the two density thresholds.

Initial config values:

```yaml
version: visual-policy-v1
min_substantive_claims_for_underfill: 8
underfill_warning_bottom_ratio: 0.45
underfill_error_bottom_ratio: 0.30
isolated_bottom_start_ratio: 0.88
isolated_bottom_min_gap_pt: 72.0
max_headline_lines: 2
wall_text_warning_lines: 6
wall_text_error_lines: 10
wall_text_warning_chars: 420
wall_text_error_chars: 700
large_gap_warning_ratio: 0.12
large_gap_error_ratio: 0.20
density_warning_lines_per_page: 58.0
density_error_lines_per_page: 72.0
hierarchy_min_delta_pt: 1.0
orphan_heading_bottom_ratio: 0.84
orphan_heading_max_following_lines: 1
```

`VisualMetrics` fields:

```python
page_count: int
content_bottom_ratio: float | None
largest_internal_gap_ratio: float | None
nonempty_line_count: int
lines_per_page: float
max_text_block_lines: int
max_text_block_chars: int
headline_line_count: int
body_font_size: float
observed_font_size_levels: list[float]
```

`VisualQAResult` fields:

```python
valid: bool
metrics: VisualMetrics
errors: list[ValidationIssue]
warnings: list[ValidationIssue]
```

- [ ] **Step 4: Run GREEN and full regression**

Run `pytest tests/test_cv_visual_policy.py -v`, then the full suite.

Expected: new tests pass; no existing behavior changes.

- [ ] **Step 5: Commit Task 1**

Commit message: `feat: add CV visual QA policy contracts`.

---

### Task 2: Visual geometry engine and QA ownership migration

**Files:**
- Create: `app/cv/visual_qa.py`
- Modify: `app/cv/recruiter_qa.py`
- Modify: `tests/test_recruiter_qa.py`
- Replace/expand: `tests/test_recruiter_visual_qa.py`
- Create: `tests/test_cv_visual_qa.py`

**Interfaces:**
- Consumes: `VisualPolicy`, `VisualMetrics`, `VisualQAResult`, `LayoutProfile`, `RecruiterRenderResult`, `RecruiterDocumentModel`, `CVDocumentModel`.
- Produces:

```python
class VisualQualityQA:
    def evaluate(
        self,
        render_result: RecruiterRenderResult,
        recruiter_document: RecruiterDocumentModel,
        source_document: CVDocumentModel,
        layout_profile: LayoutProfile,
        policy: VisualPolicy,
    ) -> VisualQAResult: ...
```

- [ ] **Step 1: Write synthetic RED tests**

Use PyMuPDF to generate deterministic one-page PDFs covering:

```text
healthy balanced page -> valid
substantive underfill -> visual_content_underfilled
few-claim sparse page -> no hard underfill
isolated bottom block -> visual_isolated_bottom_block
overcompressed page -> visual_overcompressed
moderate wall text -> visual_wall_of_text warning
severe wall text -> visual_wall_of_text_severe
large internal gap -> visual_internal_dead_zone
flat hierarchy -> visual_hierarchy_flat warning
headline > max lines -> visual_headline_too_tall
orphan heading-like line -> visual_orphan_heading
```

For each hard failure assert `valid is False` and the exact issue code. For warnings assert `valid is True` unless another hard defect is intentionally present.

Add ownership tests proving `RecruiterQualityQA` no longer emits:

```text
recruiter_content_underfilled
recruiter_isolated_footer_detected
recruiter_headline_too_tall
```

while it still rejects page-count/page-size/font/extractability/overflow/raster/claim-order failures.

- [ ] **Step 2: Run RED**

Expected: imports or assertions fail because `VisualQualityQA` does not exist and visual checks still live in `RecruiterQualityQA`.

- [ ] **Step 3: Implement PDF measurement helpers**

In `visual_qa.py`, inspect actual PDF text blocks/lines/spans with PyMuPDF. Implement deterministic helpers for:

```python
_text_blocks(page)
_text_lines(page)
_span_font_sizes(page)
_content_bottom_ratio(page)
_largest_internal_gap_ratio(page)
_max_block_shape(page)  # line count + char count
_is_isolated_bottom_block(page, policy)
_has_orphan_heading(page, policy, body_font_size)
```

Wall-of-text classification must require both long line/character counts and a block that is not clearly a bullet/list sequence. Bullet/list lines beginning with common bullet glyphs or hyphen markers count as separated list structure rather than one prose wall.

For one-page PDFs, `lines_per_page = nonempty_line_count`. For multipage PDFs, use the maximum nonempty line count of any page as the density signal so a single overloaded page cannot be hidden by a sparse second page.

- [ ] **Step 4: Implement `VisualQualityQA.evaluate`**

Rules:

- Underfill: only when recruiter claim count >= policy minimum; `< error` hard fail, otherwise `< warning` warning.
- Isolated bottom block: hard fail.
- Density: compare `lines_per_page` to profile-adjusted warning/error thresholds.
- Wall text: warning when both warning line+char thresholds are exceeded; hard fail when both hard thresholds are exceeded.
- Internal gap: warning/error by ratio.
- Hierarchy: warning only when identity/headline/body font levels do not establish `hierarchy_min_delta_pt`.
- Headline: hard fail when `render_result.metrics.headline_line_count > policy.max_headline_lines`.
- Orphan heading: hard fail only for a short larger/stronger text line below `orphan_heading_bottom_ratio` with <= configured following body lines.

Do not repeat `RenderPolicy` checks for page size, minimum font, extractability, raster images, or overflow.

- [ ] **Step 5: Move old visual checks out of `RecruiterQualityQA`**

Delete the constants/helpers and error branches that own underfill, isolated-bottom, and headline-height visual judgments from `recruiter_qa.py`. Keep technical/ATS contracts unchanged.

- [ ] **Step 6: Run GREEN and regression**

Run the new visual QA tests, recruiter QA tests, then full pytest.

Expected: ownership tests prove no duplicate visual codes remain.

- [ ] **Step 7: Commit Task 2**

Commit message: `feat: add deterministic recruiter visual quality gate`.

---

### Task 3: Wire Visual QA into canonical preparation and reduction

**Files:**
- Modify: `app/cv/service.py`
- Test: `tests/test_cv_service_visual_qa.py`
- Modify as needed: `tests/test_cv_service.py`
- Modify as needed: `tests/test_cv_service_layout_profile.py`

**Interfaces:**
- `CVPreparationService.__init__` gains:

```python
visual_policy: VisualPolicy | None = None
visual_qa: VisualQualityQA | None = None
```

- Default policy path: `config/visual_policy.yaml`.
- Same previously selected `LayoutProfile` is passed to every visual-QA evaluation.

- [ ] **Step 1: Write service RED tests**

Create spies/stubs and assert:

```text
technical QA pass + visual pass -> PREPARED
technical QA pass + non-reducible visual fail -> BLOCKED_RENDER and PDF removed
visual warning -> PREPARED with warning propagated
visual QA exception -> BLOCKED_RENDER / visual_qa_failed and PDF removed
visual_overcompressed -> reduction occurs
visual_wall_of_text_severe -> reduction occurs
reduced render uses same LayoutProfile object/id
reduced document reruns Narrative QA before acceptance
reduced Narrative QA failure -> BLOCKED_VALIDATION
reduced Visual QA pass -> PREPARED
```

- [ ] **Step 2: Run RED**

Expected: constructor/signature/integration assertions fail because service does not know `visual_policy` or `visual_qa`.

- [ ] **Step 3: Implement service wiring**

Add `_DEFAULT_VISUAL_POLICY_PATH`, dependency injection, and defaults. Per render attempt:

```python
qa_result = recruiter_qa.evaluate(...)
if recruiter QA is valid:
    visual_result = visual_qa.evaluate(
        render_result,
        final_recruiter_document,
        document,
        selected_layout_profile,
        visual_policy,
    )
```

A visual exception returns bounded code `visual_qa_failed` without raw PDF/candidate text.

Add visual warnings to accumulated warnings.

Define exactly:

```python
_REDUCIBLE_VISUAL_QA_CODES = {
    "visual_overcompressed",
    "visual_wall_of_text_severe",
}
```

The reduction decision considers technical reducible errors and visual reducible errors separately; any non-reducible visual hard error blocks immediately.

After reduction, keep the existing structural validation + Narrative QA sequence before the next render attempt. Never reselect the layout profile.

- [ ] **Step 4: Run GREEN and full regression**

Run service visual tests, narrative-gate tests, layout-profile tests, then full suite.

- [ ] **Step 5: Commit Task 3**

Commit message: `feat: gate CV preparation on visual quality`.

---

### Task 4: Preview calibration, offline contract, and final verification

**Files:**
- Modify: `scripts/render_recruiter_previews.py`
- Modify as required: `scripts/verify_offline_runtime.py`
- Modify as required: `tests/test_offline_runtime_prepare_contract.py`
- Create: `tests/test_cv_visual_qa_previews.py`
- Modify docs only if implementation names differ from the approved spec; do not broaden scope.

**Interfaces:**
- CI preview script loads `VisualPolicy` and runs `VisualQualityQA` for each of the three layout previews before printing/uploading the PDF path.

- [ ] **Step 1: Write preview acceptance RED**

Assert the script contains/uses `VisualQualityQA` and `load_visual_policy`, and that all three profile previews remain required:

```text
recruiter_software__technical_clean.pdf
recruiter_tech_operations__operations_clean.pdf
recruiter_software__compact_ats.pdf
```

Add a direct test that renders each profile and asserts Visual QA has no hard errors under the calibrated v1 policy.

- [ ] **Step 2: Run RED**

Expected: preview contract fails because the current script runs only recruiter technical QA.

- [ ] **Step 3: Wire preview Visual QA and calibrate thresholds only through fixtures**

Update preview script to run technical QA first and visual QA second. If any of the three intended-valid previews hard-fail, inspect the actual measured metrics and adjust `config/visual_policy.yaml` only when the synthetic severe-defect tests still fail correctly. Do not add runtime exceptions or profile-specific allowlists.

- [ ] **Step 4: Verify no private identifiers or unrelated subsystems changed**

Search the PR diff for private track IDs and inspect changed filenames. Scope must remain CV visual QA, service, tests, scripts, spec, and plan only.

- [ ] **Step 5: Run final full CI**

Required final head evidence:

```text
pytest full suite: 0 failures
python -m compileall app: success
git diff --check base...HEAD: success
private/generated files guard: success
3 recruiter visual previews: success
build offline runtime Python 3.12: success
build offline runtime Python 3.13: success
verify offline runtime Python 3.12 without package indexes: success
verify offline runtime Python 3.13 without package indexes: success
```

- [ ] **Step 6: Final spec/plan acceptance review**

Check each acceptance criterion in `docs/superpowers/specs/2026-09-09-cv-visual-qa-design.md` against code/tests. Do not claim completion from pytest alone.

- [ ] **Step 7: Commit final calibration/CI work**

Commit message: `test: enforce CV visual QA in recruiter previews`.
