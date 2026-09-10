# CV Visual QA Design

**Status:** Approved for implementation
**Roadmap:** CV architecture item 6 of 9
**Base:** `feat/cv-layout-profiles` / PR #47
**Feature branch:** `feat/cv-visual-qa`

## 1. Purpose

Opportunity-OS already validates semantic evidence, narrative strategy, recruiter scanability, renderer constraints, ATS-oriented extractability, and layout selection. PR #47 adds explicit layout profiles, but a PDF can still satisfy those contracts and look visibly poor.

This change introduces an independent visual-quality gate so that:

> ATS-safe + visually poor is not considered PREPARED.

The gate must detect severe visual defects without giving the renderer or QA any authority to invent candidate claims, add filler, change provenance, or silently rewrite narrative order.

## 2. Scope

Visual QA v1 evaluates the geometry and typography of the rendered recruiter PDF. It owns:

- underfill and large unused lower-page regions;
- isolated bottom blocks / dead zones;
- excessive page density / overcompression;
- wall-of-text conditions;
- hierarchy flattening signals;
- orphan heading-like blocks;
- extreme vertical-rhythm imbalance;
- profile-aware overcompression expectations.

It receives the selected `LayoutProfile`, because `comfortable`, `balanced`, and `compact` profiles legitimately tolerate different maximum densities.

Visual QA never changes content itself. It returns typed findings only.

## 3. Non-goals

This PR does not:

- add JSON Resume export;
- add a second renderer;
- implement ATS round-trip semantic recovery;
- persist Visual QA or layout metadata in `ApplicationPacket`;
- alter Gmail, outreach, approval, or send behavior;
- introduce private track identifiers into the public repository;
- use computer vision, OCR, screenshots, LLM aesthetic grading, or non-deterministic scoring;
- invent content to fill empty space;
- allow layout selection to change narrative order.

## 4. Existing QA responsibilities and migration

`RecruiterQualityQA` currently mixes technical/recoverability checks with a few visual checks. PR #48 separates these responsibilities.

### RecruiterQualityQA remains responsible for

- configured page count;
- configured page size;
- extractable/selectable text;
- minimum body font from `RenderPolicy`;
- renderer overflow;
- raster-image rejection;
- canonical claim text presence and order.

These are renderer/ATS/recoverability contracts, not aesthetic judgments.

### VisualQualityQA becomes responsible for

The existing visual checks move here rather than being duplicated:

- `recruiter_content_underfilled` -> `visual_content_underfilled`;
- `recruiter_isolated_footer_detected` -> `visual_isolated_bottom_block`;
- rendered headline height/wrapping -> `visual_headline_too_tall`.

New visual checks are added on top of that boundary.

The legacy `LayoutQA` class is not used by the canonical recruiter preparation path and is not removed in this PR. Removing or consolidating it is separate cleanup.

## 5. Architecture

```text
CVStrategy
  -> RecruiterDocument
  -> LayoutSelector
  -> LayoutProfile
  -> Renderer
  -> RecruiterQualityQA       # technical / ATS / recoverability
  -> VisualQualityQA          # visual composition / geometry
  -> PREPARED or reduction/block
```

The canonical service resolves one `LayoutProfile` before rendering. The same profile is reused for every render attempt in the reduction loop.

`VisualQualityQA` consumes:

- `RecruiterRenderResult`;
- `RecruiterDocumentModel`;
- `CVDocumentModel` only to locate exact identity/headline claim anchors when needed;
- selected `LayoutProfile`;
- versioned `VisualPolicy`.

It reads the actual PDF using PyMuPDF text blocks, lines, spans, font sizes, flags, and page geometry. It does not use OCR.

## 6. New contracts

### VisualPolicy

Add `app/cv/visual_policy.py` and `config/visual_policy.yaml`.

Version: `visual-policy-v1`.

The model is strict and forbids unknown fields. Thresholds are explicit configuration, not module constants.

V1 fields:

- `version`;
- `min_substantive_claims_for_underfill`;
- `underfill_warning_bottom_ratio`;
- `underfill_error_bottom_ratio`;
- `isolated_bottom_start_ratio`;
- `isolated_bottom_min_gap_pt`;
- `max_headline_lines`;
- `wall_text_warning_lines`;
- `wall_text_error_lines`;
- `wall_text_warning_chars`;
- `wall_text_error_chars`;
- `wall_text_max_list_marker_ratio`;
- `large_gap_warning_ratio`;
- `large_gap_error_ratio`;
- `density_warning_lines_per_page_inch`;
- `density_error_lines_per_page_inch`;
- `density_multipliers` with exactly `comfortable`, `balanced`, and `compact` keys;
- `hierarchy_min_delta_pt`;
- `orphan_heading_bottom_ratio`;
- `orphan_heading_max_following_lines`.

Ordering invariants are explicit:

- `0 < underfill_error_bottom_ratio < underfill_warning_bottom_ratio < 1`;
- `0 < large_gap_warning_ratio < large_gap_error_ratio < 1`;
- warning line/character wall thresholds are lower than their error equivalents;
- warning density is lower than error density;
- all three density multipliers are positive.

V1 density multipliers are fixed in config at:

- `comfortable: 0.92`;
- `balanced: 1.00`;
- `compact: 1.10`.

These multipliers apply **only** to the high-density/overcompression thresholds. Underfill and dead-zone thresholds are identical across profiles, so a `comfortable` profile cannot excuse a half-empty page.

The adjustment logic is public and generic. It contains no private track names.

### VisualMetrics

Add a strict typed model with bounded measurements:

- `page_count`;
- `content_bottom_ratio`;
- `largest_internal_gap_ratio`;
- `nonempty_line_count`;
- `lines_per_page_inch`;
- `max_text_block_lines`;
- `max_text_block_chars`;
- `headline_line_count`;
- `body_font_size`;
- `observed_font_size_levels`.

`lines_per_page_inch` uses the actual PDF page height in inches (`points / 72`) rather than a guessed usable-height value. The selected profile multiplier supplies the intentional density tolerance.

Metrics are diagnostic evidence only. They do not mutate the document.

### VisualQAResult

Add a strict result model:

- `valid`;
- `metrics`;
- `errors: list[ValidationIssue]`;
- `warnings: list[ValidationIssue]`.

`valid` is true if and only if `errors` is empty.

## 7. Detection rules

All calculations are deterministic from PDF geometry, document anchors, selected layout profile, and configured thresholds.

### 7.1 Underfill / dead lower region

For one-page PDFs with at least `min_substantive_claims_for_underfill` visible recruiter claims:

- `content_bottom_ratio < underfill_error_bottom_ratio` -> hard error `visual_content_underfilled`;
- otherwise, if below `underfill_warning_bottom_ratio` -> warning `visual_content_underfilled_warning`.

A sparse document with fewer substantive evidence-backed claims is not forced to fabricate filler. Underfill is non-reducible because removing content cannot fix it.

### 7.2 Isolated bottom block

A text block beginning at or below `isolated_bottom_start_ratio * page_height`, with substantive content above it and a vertical gap of at least `isolated_bottom_min_gap_pt`, is hard error `visual_isolated_bottom_block`.

This migrates the existing recruiter-QA behavior and keeps its intent. It is non-reducible by content removal.

### 7.3 Overcompression

Count non-empty rendered text lines and divide by actual page height in inches. For multi-page PDFs, evaluate each page independently and keep the worst page density in the result.

Compute effective thresholds as:

```text
effective_warning = policy.density_warning_lines_per_page_inch * density_multiplier
effective_error   = policy.density_error_lines_per_page_inch   * density_multiplier
```

Then:

- above effective error -> hard error `visual_overcompressed`;
- otherwise above effective warning -> warning `visual_density_high`.

`visual_overcompressed` is reducible because removing optional recruiter content may improve it.

Minimum font-size rejection remains exclusively in `RecruiterQualityQA`; Visual QA does not duplicate `RenderPolicy.min_body_font_pt`.

### 7.4 Wall of text

Reconstruct each PDF text block as non-empty lines. For each line, count whether trimmed text begins with a list marker (`-`, `•`, `▪`, `*`, or a numeric marker such as `1.`). Define:

```text
list_marker_ratio = list_marker_lines / block_line_count
```

A block is paragraph-like for this rule only when `list_marker_ratio <= wall_text_max_list_marker_ratio`.

For paragraph-like blocks:

- if both `block_lines >= wall_text_error_lines` and `block_chars >= wall_text_error_chars`, hard error `visual_wall_of_text_severe`;
- otherwise if both warning thresholds are met, warning `visual_wall_of_text`.

Requiring both line and character thresholds prevents a stack of short labels from being mistaken for prose. Ignoring list-heavy blocks prevents ordinary bullet sections from being penalized as walls of text.

`visual_wall_of_text_severe` is reducible; the warning is not.

### 7.5 Large internal dead zone / vertical rhythm

Sort substantive text blocks by vertical position. Consider only gaps that have non-empty substantive text both above and below. Divide each gap by page height and keep the largest ratio.

- ratio >= `large_gap_error_ratio` -> hard error `visual_internal_dead_zone`;
- otherwise ratio >= `large_gap_warning_ratio` -> warning `visual_vertical_rhythm_uneven`.

This hard error is non-reducible in v1. The system does not reposition sections automatically.

### 7.6 Hierarchy flattening

Locate the exact identity/headline claim text in PDF line/span output using `RecruiterDocumentModel` + `CVDocumentModel`. Compare the largest font size used by those anchors with `render_result.metrics.body_font_size`.

If the delta is below `hierarchy_min_delta_pt`, emit warning `visual_hierarchy_flat`.

`observed_font_size_levels` is recorded as a diagnostic metric but is not independently hard-gated in v1. Hierarchy alone remains warning-only because weight/font extraction can vary by renderer.

### 7.7 Headline height

Move the existing rendered headline line-count check into Visual QA.

If `render_result.metrics.headline_line_count > max_headline_lines`, emit hard error `visual_headline_too_tall`.

This is non-reducible because the reduction loop does not rewrite the headline.

### 7.8 Orphan heading-like block

A line is heading-like only when all are true:

- it is short relative to ordinary body lines;
- its span is bold **or** at least `hierarchy_min_delta_pt` larger than body font;
- it begins at or below `orphan_heading_bottom_ratio * page_height`.

If no non-empty body line follows it on that page, emit hard error `visual_orphan_heading`.

If one through `orphan_heading_max_following_lines` body lines follow it, emit warning `visual_orphan_heading_warning`.

This rule uses typography/geometry, not a language-specific heading dictionary. The hard error is non-reducible in v1.

## 8. Reduction-loop behavior

The service sequence per render attempt is:

1. render with the already-selected `LayoutProfile`;
2. run `RecruiterQualityQA`;
3. if recruiter QA has a non-reducible hard error, block;
4. if recruiter QA has only its existing reducible render errors, use the existing reduction loop;
5. when recruiter QA is valid, run `VisualQualityQA`;
6. if Visual QA has no errors, accept the attempt and propagate its warnings;
7. if all Visual QA hard errors are in the visual reducible allowlist, reduce recruiter content once through the existing reducer;
8. re-run recruiter structural validation and Narrative QA on the reduced document;
9. re-render using the **same** selected `LayoutProfile`;
10. re-run RecruiterQualityQA and VisualQualityQA.

Use a separate `_REDUCIBLE_VISUAL_QA_CODES` allowlist instead of mixing visual semantics into `_REDUCIBLE_QA_CODES`.

Visual reducible hard codes in v1:

- `visual_overcompressed`;
- `visual_wall_of_text_severe`.

All other visual hard failures are non-reducible.

Warnings from all successful validation stages accumulate. Reduction never bypasses Narrative QA, structural validation, or evidence provenance.

## 9. Failure semantics

Visual hard errors return existing preparation state `BLOCKED_RENDER`: the evidence/narrative document may be valid while the artifact is unacceptable.

No PDF survives blocked preparation. Partial/generated PDFs are removed using the existing cleanup path.

Visual QA exceptions map to bounded public code `visual_qa_failed`. Raw PDF content, extracted candidate text, file internals, and private data are never copied into public error messages.

## 10. Threshold calibration

V1 thresholds are configuration-owned and calibrated before merge against two classes of fixtures:

1. the three layout-profile preview outputs from PR #47 (`technical_clean`, `operations_clean`, `compact_ats`); they may produce warnings but must not hard-fail when their geometry is intentionally valid;
2. synthetic PDFs deliberately producing each severe defect; each must hard-fail with its exact issue code.

Existing visual constants being migrated retain equivalent behavior initially. New thresholds are tuned only through explicit fixtures/tests, never through runtime fallback or profile-specific exceptions.

The three profile previews continue to render and upload in CI.

## 11. Test strategy

TDD is mandatory.

### VisualPolicy tests

- default policy loads and reports exact `visual-policy-v1`;
- unknown fields rejected;
- all ordering invariants enforced;
- density multiplier key set must be exactly `comfortable`, `balanced`, `compact`;
- profile density adjustment produces exact deterministic effective thresholds;
- no private track IDs exist in visual policy/config.

### Geometry unit tests

Generate synthetic PDFs with PyMuPDF for:

- healthy balanced page;
- underfilled substantive page;
- legitimate sparse page below substantive-claim minimum;
- isolated bottom block;
- overcompressed page;
- moderate and severe wall of text;
- bullet-heavy block that must not trigger wall-of-text;
- large internal dead zone;
- flat hierarchy warning;
- headline over max lines;
- orphan heading with zero following lines;
- near-orphan heading with a small following body block.

Every hard failure asserts exact issue code and `valid=False`.

### Ownership regression tests

Verify migrated visual issue codes no longer originate in `RecruiterQualityQA`, while technical page/font/extractability/overflow/raster/claim-order checks remain there.

### Service integration tests

- technical-pass + visual-pass -> PREPARED;
- technical-pass + visual warning -> PREPARED with warning propagated;
- technical-pass + non-reducible visual fail -> BLOCKED_RENDER and PDF removed;
- reducible visual overcompression -> reducer invoked, Narrative QA rechecked, same LayoutProfile reused;
- reduced visual pass -> PREPARED;
- reduced narrative fail -> BLOCKED_VALIDATION;
- Visual QA exception -> bounded `visual_qa_failed`, no output artifact;
- mixed reducible + non-reducible visual hard errors -> block without reduction.

### CI/runtime tests

Run the full existing suite, compile, whitespace check, privacy guard, all three recruiter previews, and offline-runtime build/verify on Python 3.12 and 3.13.

## 12. Acceptance criteria

PR #48 is complete only when all are true:

1. `VisualQualityQA` is an independent canonical pipeline stage.
2. Visual thresholds live in strict `visual-policy-v1` configuration.
3. Existing visual checks are migrated out of `RecruiterQualityQA` rather than duplicated.
4. Severe underfill/dead-zone, overcompression, wall-of-text, headline, and orphan-heading fixtures fail deterministically.
5. Hierarchy and moderate density/rhythm defects produce deterministic warnings.
6. Bullet-heavy sections are not falsely classified as walls of text.
7. Only explicitly allowlisted visual hard failures can enter the reduction loop.
8. Every reduction revalidates narrative and reuses the same selected LayoutProfile.
9. Visual QA never adds, rewrites, or reorders candidate claims.
10. No private track identifiers are committed.
11. The three PR #47 layout previews remain technically acceptable and have no Visual QA hard errors under calibrated v1 policy.
12. No Gmail/outreach/send behavior changes.
13. Full CI and offline 3.12/3.13 verification are green on the final head before merge approval is requested.

## 13. Follow-on roadmap

After PR #47 and PR #48 are integrated, regenerate representative real application CVs (including the previously poor-looking AMMAZY/YEL cases) and compare them with the old artifacts. That comparison validates the system without putting private CV data in the public repository.

Remaining original roadmap after Visual QA:

- JSON Resume export;
- optional second visual renderer;
- ATS recoverability round-trip.

ApplicationPacket reproducibility metadata (`CVStrategy`, narrative policy version, layout profile id, QA results) remains a separate explicitly-scoped follow-up before or alongside those interoperability steps.