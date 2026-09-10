# CV Visual QA Design

**Status:** Proposed for implementation after user approval  
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
- profile-aware density expectations.

It receives the selected `LayoutProfile`, because `comfortable`, `balanced`, and `compact` profiles legitimately have different density expectations.

Visual QA never changes content itself. It returns typed findings only.

## 3. Non-goals

This PR does not:

- add JSON Resume export;
- add a second renderer;
- implement ATS round-trip semantic recovery;
- persist Visual QA or layout metadata in `ApplicationPacket` (that is roadmap item 4 from the remaining packet metadata work and stays a later change);
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

New visual checks are then added on top of that boundary.

The legacy `LayoutQA` class is not used by the canonical recruiter preparation path and is not removed in this PR. Removing or consolidating it would be a separate cleanup change.

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
- `CVDocumentModel` only when exact visible claim text is needed to locate semantic anchors;
- selected `LayoutProfile`;
- versioned `VisualPolicy`.

It reads the actual PDF using PyMuPDF text blocks, lines, spans, and page geometry. It does not use OCR.

## 6. New contracts

### VisualPolicy

Add `app/cv/visual_policy.py` and `config/visual_policy.yaml`.

Version: `visual-policy-v1`.

The policy is strict and forbids unknown fields. Thresholds are explicit configuration, not module constants.

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
- `large_gap_warning_ratio`;
- `large_gap_error_ratio`;
- `density_warning_lines_per_usable_inch`;
- `density_error_lines_per_usable_inch`;
- `hierarchy_min_delta_pt`;
- `orphan_heading_bottom_ratio`;
- `orphan_heading_max_following_lines`.

Profile-aware adjustment is deterministic and based only on `LayoutProfile.density`:

- `comfortable`: lower density expected;
- `balanced`: baseline;
- `compact`: higher density allowed.

The adjustment logic is public and generic. It must not contain private track names.

### VisualMetrics

Add a strict typed model containing bounded numeric measurements such as:

- `page_count`;
- `content_bottom_ratio`;
- `largest_internal_gap_ratio`;
- `nonempty_line_count`;
- `lines_per_usable_inch`;
- `max_text_block_lines`;
- `max_text_block_chars`;
- `headline_line_count`;
- `body_font_size`;
- `observed_font_size_levels`.

Metrics are diagnostic evidence only. They do not mutate the document.

### VisualQAResult

Add a strict result model:

- `valid`;
- `metrics`;
- `errors: list[ValidationIssue]`;
- `warnings: list[ValidationIssue]`.

`valid` is true only when `errors` is empty.

## 7. Detection rules

All calculations are deterministic from PDF geometry and configured thresholds.

### 7.1 Underfill / dead lower region

For one-page PDFs with at least `min_substantive_claims_for_underfill` visible recruiter claims:

- below the warning content-bottom ratio -> warning;
- below the error content-bottom ratio -> hard error `visual_content_underfilled`.

A sparse document with few evidence-backed claims must not be forced to fabricate filler. The substantive-claim minimum prevents a small legitimate CV from being rejected merely for having limited evidence.

Underfill is non-reducible because removing content cannot fix it.

### 7.2 Isolated bottom block

A text block starting in the configured lower-page region with a large vertical gap from the main body is a hard error `visual_isolated_bottom_block`.

This migrates the existing recruiter-QA behavior and keeps its intent.

It is non-reducible by content removal.

### 7.3 Overcompression

Compute non-empty rendered line density over usable vertical page area. Apply the profile-density adjustment.

- warning threshold -> `visual_density_high`;
- hard threshold -> `visual_overcompressed`.

A hard overcompression error is reducible because removing optional recruiter content may improve it.

Font-size rejection remains in `RecruiterQualityQA`; Visual QA must not duplicate `RenderPolicy.min_body_font_pt`.

### 7.4 Wall of text

Inspect text blocks reconstructed from PDF lines/spans. A block becomes wall-of-text evidence when it is both structurally long and lacks sufficient visible separation/list structure.

Use configured line and character thresholds:

- moderate -> warning `visual_wall_of_text`;
- extreme -> hard error `visual_wall_of_text_severe`.

The severe error is reducible because the existing reduction loop may remove optional bullets/claims. The warning alone never forces reduction.

### 7.5 Large internal dead zone / vertical rhythm

Measure the largest vertical gap between substantive text regions that have visible content both above and below.

- moderate -> warning `visual_vertical_rhythm_uneven`;
- extreme -> hard error `visual_internal_dead_zone`.

The hard dead-zone error is non-reducible unless the defect is caused by an isolated block already classified by the dedicated rule. V1 does not try to reposition sections automatically.

### 7.6 Hierarchy flattening

Use PDF span font sizes to compare recruiter identity/headline anchors with body text and observe the number of distinct typography levels.

If the visual hierarchy is unusually flat, emit warning `visual_hierarchy_flat`.

V1 does not hard-fail hierarchy alone because font-family weight extraction and renderer-specific typography can make a universal hard threshold brittle. It becomes a hard gate only if future fixtures establish a deterministic cross-profile contract.

### 7.7 Headline height

Move the current rendered headline line-count check into Visual QA.

If the headline exceeds `max_headline_lines`, emit hard error `visual_headline_too_tall`.

This is non-reducible because the reduction loop does not rewrite the headline.

### 7.8 Orphan heading-like block

Detect a short heading-like line near the bottom of a page when there are no more than the configured number of body lines following it on that page.

Use typography evidence (short line, stronger/larger span than body) rather than a language-specific list of section labels.

Emit hard error `visual_orphan_heading` only when the signal is unambiguous. Borderline cases remain warnings.

It is non-reducible in v1; the system must not delete or reorder a section to hide the problem.

## 8. Reduction-loop behavior

The service sequence per attempt is:

1. render using the already-selected `LayoutProfile`;
2. run `RecruiterQualityQA`;
3. if recruiter QA has a non-reducible error, block;
4. if recruiter QA has only existing reducible render errors, use the existing reduction loop;
5. when recruiter QA is valid, run `VisualQualityQA`;
6. if Visual QA is valid, accept this render attempt;
7. if Visual QA contains only reducible hard errors, run the existing content reduction step;
8. re-run structural validation and Narrative QA for the reduced recruiter document;
9. re-render with the same LayoutProfile;
10. re-run RecruiterQualityQA and VisualQualityQA.

Visual reducible codes in v1:

- `visual_overcompressed`;
- `visual_wall_of_text_severe`.

All other visual hard failures are non-reducible.

Warnings from every successful validation stage are accumulated. A reduction may never bypass Narrative QA or evidence validation.

## 9. Failure semantics

Visual hard errors return the existing public preparation state `BLOCKED_RENDER` because the evidence/narrative document can be valid while the rendered artifact is unacceptable.

No PDF survives a blocked preparation. Partial/generated PDFs are removed using the existing cleanup path.

Visual QA exceptions are bounded to a safe public error code such as `visual_qa_failed`; raw PDF content or private candidate text must not be echoed into exceptions/logs.

## 10. Threshold calibration

V1 thresholds are configuration-owned and must be calibrated against two classes of fixtures before merge:

1. the three real layout-profile preview outputs introduced by PR #47 (`technical_clean`, `operations_clean`, `compact_ats`), which should not hard-fail when their geometry is intentionally valid;
2. synthetic PDFs that deliberately produce each severe defect and must hard-fail.

Existing visual constants being migrated keep equivalent behavior initially. New thresholds may be tuned only through tests/fixtures, not by ad-hoc runtime fallback.

The three profile previews must continue to render and be uploaded in CI.

## 11. Test strategy

TDD is mandatory.

### VisualPolicy tests

- default policy loads and is versioned;
- unknown fields rejected;
- invalid threshold ordering rejected (warning threshold cannot be stricter than its hard threshold in the wrong direction);
- profile-density adjustments are deterministic;
- no private track IDs exist in visual policy/config.

### Geometry unit tests

Generate small synthetic PDFs with PyMuPDF for:

- healthy balanced page;
- underfilled substantive page;
- legitimate sparse page below substantive-claim minimum;
- isolated bottom block;
- overcompressed page;
- moderate and severe wall of text;
- large internal dead zone;
- flat hierarchy warning;
- headline over max lines;
- orphan heading-like block.

Each hard failure asserts exact issue code and `valid=False`.

### Ownership regression tests

Verify migrated visual issue codes no longer originate in `RecruiterQualityQA`, while technical page/font/extractability/overflow checks remain there.

### Service integration tests

- technical-pass + visual-pass -> PREPARED;
- technical-pass + non-reducible visual fail -> BLOCKED_RENDER and PDF removed;
- reducible visual overcompression -> reducer invoked, Narrative QA rechecked, same LayoutProfile reused;
- reduced visual pass -> PREPARED;
- reduced narrative fail -> BLOCKED_VALIDATION;
- Visual QA exception -> bounded `visual_qa_failed`, no output artifact;
- visual warnings propagate into `PreparationResult.warnings`.

### CI/runtime tests

Full existing suite, compile, whitespace, privacy guard, all three recruiter previews, offline-runtime build/verify on Python 3.12 and 3.13.

## 12. Acceptance criteria

PR #48 is complete only when all are true:

1. `VisualQualityQA` is an independent canonical pipeline stage.
2. Visual thresholds live in strict `visual-policy-v1` configuration.
3. Existing visual checks are migrated out of `RecruiterQualityQA` rather than duplicated.
4. Severe underfill/dead-zone, overcompression, wall-of-text, headline, and orphan-heading fixtures fail deterministically.
5. Hierarchy and moderate density/rhythm defects generate deterministic warnings.
6. Only explicitly reducible visual failures can enter the reduction loop.
7. Every reduction revalidates narrative and reuses the same selected LayoutProfile.
8. Visual QA never adds, rewrites, or reorders candidate claims.
9. No private track identifiers are committed.
10. The three PR #47 layout previews remain technically and visually acceptable under the calibrated v1 policy.
11. No Gmail/outreach/send behavior changes.
12. Full CI and offline 3.12/3.13 verification are green on the final head before merge approval is requested.

## 13. Follow-on roadmap

After PR #47 and PR #48 are integrated, regenerate representative real application CVs (including the previously poor-looking AMMAZY/YEL cases) and compare them against the old artifacts. That comparison is validation of the system, not an excuse to add private CV data to the public repository.

Remaining original roadmap after Visual QA:

- JSON Resume export;
- optional second visual renderer;
- ATS recoverability round-trip.

ApplicationPacket reproducibility metadata (`CVStrategy`, narrative policy version, layout profile id, QA results) remains a separate explicitly-scoped follow-up before or alongside those interoperability steps.
