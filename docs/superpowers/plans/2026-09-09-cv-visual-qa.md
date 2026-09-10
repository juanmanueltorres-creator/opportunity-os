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
- Every reduction reruns structural validation, Narrative QA, rendering, RecruiterQualityQA, and VisualQualityQA with the same selected `LayoutProfile`.
- Visual hard failures produce `BLOCKED_RENDER`; blocked preparation leaves no PDF artifact.
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
- Produces: `density_thresholds_for_profile(policy: VisualPolicy, profile: LayoutProfile) -> tuple[float, float]`.
- Produces: `VisualMetrics` and `VisualQAResult` strict models.

- [ ] **Step 1: Write failing policy/model tests**

Assert the default policy loads and obeys the approved ordering:

```python
policy = load_visual_policy("config/visual_policy.yaml")
assert policy.version == "visual-policy-v1"
assert policy.underfill_error_bottom_ratio < policy.underfill_warning_bottom_ratio
assert policy.wall_text_warning_lines < policy.wall_text_error_lines
assert policy.wall_text_warning_chars < policy.wall_text_error_chars
assert policy.large_gap_warning_ratio < policy.large_gap_error_ratio
assert policy.density_warning_lines_per_page_inch < policy.density_error_lines_per_page_inch
assert set(policy.density_multipliers) == {"comfortable", "balanced", "compact"}
```

Also assert unknown fields are rejected, invalid threshold ordering fails closed, and three `LayoutProfile` fixtures produce deterministic density thresholds ordered `comfortable < balanced < compact`. Underfill thresholds must remain unchanged across profiles.

- [ ] **Step 2: Run RED**

Expected: collection/import failure because `app.cv.visual_policy` / `app.cv.visual_models` do not exist.

- [ ] **Step 3: Implement strict contracts**

`VisualPolicy` includes exactly:

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
wall_text_max_list_marker_ratio: float
large_gap_warning_ratio: float
large_gap_error_ratio: float
density_warning_lines_per_page_inch: float
density_error_lines_per_page_inch: float
density_multipliers: dict[str, float]
hierarchy_min_delta_pt: float
orphan_heading_bottom_ratio: float
orphan_heading_max_following_lines: int
```

Validate the exact three density multiplier keys and all ordering/range invariants from the spec. `density_thresholds_for_profile` multiplies only the two density thresholds by the configured multiplier for `LayoutProfile.density`.

Initial config:

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
wall_text_max_list_marker_ratio: 0.50
large_gap_warning_ratio: 0.12
large_gap_error_ratio: 0.20
density_warning_lines_per_page_inch: 5.0
density_error_lines_per_page_inch: 6.2
density_multipliers:
  comfortable: 0.92
  balanced: 1.00
  compact: 1.10
hierarchy_min_delta_pt: 1.0
orphan_heading_bottom_ratio: 0.84
orphan_heading_max_following_lines: 1
```

`VisualMetrics`:

```python
page_count: int
content_bottom_ratio: float | None
largest_internal_gap_ratio: float | None
nonempty_line_count: int
lines_per_page_inch: float
max_text_block_lines: int
max_text_block_chars: int
headline_line_count: int
body_font_size: float
observed_font_size_levels: list[float]
```

`VisualQAResult`:

```python
valid: bool
metrics: VisualMetrics
errors: list[ValidationIssue]
warnings: list[ValidationIssue]
```

- [ ] **Step 4: Run GREEN and full regression**

Run the new policy tests, then full pytest. Expected: new tests pass with no behavior change elsewhere.

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

Generate deterministic PyMuPDF fixtures for:

```text
healthy balanced page -> valid
substantive underfill -> visual_content_underfilled
few-claim sparse page -> no hard underfill
isolated bottom block -> visual_isolated_bottom_block
overcompressed page -> visual_overcompressed
moderate prose wall -> visual_wall_of_text warning
severe prose wall -> visual_wall_of_text_severe
long bullet list -> not a prose-wall hard failure
large internal gap -> visual_internal_dead_zone
flat hierarchy -> visual_hierarchy_flat warning
headline > max lines -> visual_headline_too_tall
orphan heading-like line -> visual_orphan_heading
```

Add ownership tests proving `RecruiterQualityQA` no longer emits `recruiter_content_underfilled`, `recruiter_isolated_footer_detected`, or `recruiter_headline_too_tall`, while technical page/font/extractability/overflow/raster/claim-order checks remain.

- [ ] **Step 2: Run RED**

Expected: imports/assertions fail because `VisualQualityQA` is absent and old visual ownership still exists.

- [ ] **Step 3: Implement PDF measurement helpers**

Implement deterministic helpers in `visual_qa.py`:

```python
_text_blocks(page)
_text_lines(page)
_span_font_sizes(page)
_content_bottom_ratio(page)
_largest_internal_gap_ratio(page)
_max_block_shape(page)
_is_isolated_bottom_block(page, policy)
_has_orphan_heading(page, policy, body_font_size)
_list_marker_ratio(lines)
```

Wall-of-text classification requires both line and character thresholds and `list_marker_ratio <= policy.wall_text_max_list_marker_ratio`. Common bullet glyphs and leading hyphen markers count as list structure.

Density is renderer-independent: for every page compute `nonempty_lines / (page_height_points / 72.0)`. `lines_per_page_inch` is the maximum page value so a dense page cannot be hidden by a sparse second page.

- [ ] **Step 4: Implement `VisualQualityQA.evaluate`**

Rules:

- Underfill: one page + substantive claim minimum; `< error` hard fail, else `< warning` warning.
- Isolated bottom block: hard fail.
- Density: profile-adjusted warning/error thresholds.
- Wall text: warning/error only when both respective line+char thresholds are exceeded and list-marker ratio stays below/equal policy limit.
- Internal gap: warning/error by configured ratio.
- Hierarchy: warning only if identity/headline anchors do not exceed body typography by `hierarchy_min_delta_pt`.
- Headline: hard fail when renderer metric exceeds `max_headline_lines`.
- Orphan heading: hard fail only for unambiguous short larger/stronger line near page bottom with <= configured following body lines.

Do not duplicate RenderPolicy technical checks.

- [ ] **Step 5: Move old visual checks out of `RecruiterQualityQA`**

Delete visual-only constants/helpers/branches for underfill, isolated-bottom, and headline-height. Leave technical/ATS contracts intact.

- [ ] **Step 6: Run GREEN and regression**

Run visual tests + recruiter QA tests + full pytest. Ownership tests must prove no duplicate visual codes remain.

- [ ] **Step 7: Commit Task 2**

Commit message: `feat: add deterministic recruiter visual quality gate`.

---

### Task 3: Wire Visual QA into canonical preparation and reduction

**Files:**
- Modify: `app/cv/service.py`
- Create: `tests/test_cv_service_visual_qa.py`
- Modify as needed: `tests/test_cv_service.py`
- Modify as needed: `tests/test_cv_service_layout_profile.py`

**Interfaces:**

`CVPreparationService.__init__` gains:

```python
visual_policy: VisualPolicy | None = None
visual_qa: VisualQualityQA | None = None
```

Default policy path is `config/visual_policy.yaml`.

- [ ] **Step 1: Write service RED tests**

Assert:

```text
technical pass + visual pass -> PREPARED
technical pass + non-reducible visual fail -> BLOCKED_RENDER and PDF removed
visual warning -> PREPARED with warning propagated
visual QA exception -> BLOCKED_RENDER / visual_qa_failed and PDF removed
visual_overcompressed -> reduction occurs
visual_wall_of_text_severe -> reduction occurs
reduced render/visual QA reuse the same LayoutProfile id
reduced document reruns Narrative QA before acceptance
reduced Narrative QA failure -> BLOCKED_VALIDATION
reduced Visual QA pass -> PREPARED
```

- [ ] **Step 2: Run RED**

Expected: constructor/integration tests fail because service does not know the visual dependencies.

- [ ] **Step 3: Implement service wiring**

Add `_DEFAULT_VISUAL_POLICY_PATH` and injected defaults. Per attempt run RecruiterQualityQA first; only if technical QA is valid run VisualQualityQA with the already-selected profile.

Define exactly:

```python
_REDUCIBLE_VISUAL_QA_CODES = {
    "visual_overcompressed",
    "visual_wall_of_text_severe",
}
```

Visual exceptions map to bounded `visual_qa_failed`. Accumulate visual warnings. Any non-reducible visual hard error blocks immediately. Reducible visual failures enter the existing reduction path, which must preserve structural validation + Narrative QA before rerendering. Never reselect layout.

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

**Interfaces:**
- CI preview script loads `VisualPolicy` and runs `VisualQualityQA` for each profile after technical QA.

- [ ] **Step 1: Write preview acceptance RED**

Require the script to use `VisualQualityQA` + `load_visual_policy` and preserve the exact three preview artifacts:

```text
recruiter_software__technical_clean.pdf
recruiter_tech_operations__operations_clean.pdf
recruiter_software__compact_ats.pdf
```

Directly render each profile and assert no visual hard errors under the v1 policy.

- [ ] **Step 2: Run RED**

Expected: preview contract fails because current preview validation is technical-only.

- [ ] **Step 3: Wire preview QA and calibrate only through fixtures**

Run technical QA then visual QA. If an intended-valid preview hard-fails, inspect its `VisualMetrics` and adjust config only if every synthetic severe-defect regression still fails correctly. No profile-specific allowlists or runtime exceptions.

- [ ] **Step 4: Verify privacy and scope**

Inspect changed filenames and search diff for private track IDs. Scope stays CV visual QA/service/tests/scripts/spec/plan only; no ApplicationPacket/Gmail/outreach changes.

- [ ] **Step 5: Run final full CI**

Required final-head evidence:

```text
pytest full suite: 0 failures
python -m compileall app: success
git diff --check stacked-base...HEAD: success
private/generated files guard: success
3 recruiter visual previews: success
build offline runtime Python 3.12: success
build offline runtime Python 3.13: success
verify offline runtime Python 3.12 without package indexes: success
verify offline runtime Python 3.13 without package indexes: success
```

- [ ] **Step 6: Final acceptance review**

Check every acceptance criterion in the spec against code/tests. Do not claim completion from pytest alone.

- [ ] **Step 7: Commit final calibration/CI work**

Commit message: `test: enforce CV visual QA in recruiter previews`.
