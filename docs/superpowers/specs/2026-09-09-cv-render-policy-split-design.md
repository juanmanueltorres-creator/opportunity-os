# CV Render Policy Split Design

**Date:** 2026-09-09
**Status:** Approved direction, narrowed from the CV Strategy/Narrative architecture
**Scope:** PR4 — separate physical PDF constraints from recruiter composition policy

## Problem

`RecruiterPolicy` currently mixes two responsibilities:

1. recruiter-document composition limits (`max_projects`, `max_experience_entries`, skill groups, profile caps, etc.); and
2. physical PDF constraints (`max_pages`, `min_body_font_pt`, `preferred_body_font_pt`).

It also enforces `max_pages == 1`, which makes one-page output a domain invariant instead of a render preference.

## Target boundary

- `NarrativePolicy` remains the authority for CV strategy and narrative-quality thresholds.
- `RecruiterPolicy` becomes composition-only: section/entry/token caps and skill-group taxonomy.
- New `RenderPolicy` becomes the sole authority for physical PDF constraints.
- `RecruiterQualityQA` consumes `RenderPolicy` for page-count, page-size, and font-size rules.
- `CVPreparationService` loads both composition and render policy independently.
- RenderCV/Typst remains the renderer and continues consuming `RecruiterPolicy` only for recruiter-document labels/group mappings.

## RenderPolicy V1

```python
class RenderPolicy(StrictCVModel):
    version: str
    page_size: Literal["A4", "LETTER"]
    preferred_pages: int
    max_pages: int
    min_body_font_pt: float
    preferred_body_font_pt: float
```

Invariants:

- `version == "render-policy-v1"`;
- `1 <= preferred_pages <= max_pages <= 2`;
- `min_body_font_pt >= 9.0`;
- `preferred_body_font_pt >= min_body_font_pt`.

## Backward-compatible default

`config/render_policy.yaml` initially preserves current runtime behavior:

```yaml
version: render-policy-v1
page_size: A4
preferred_pages: 1
max_pages: 1
min_body_font_pt: 9.0
preferred_body_font_pt: 9.4
```

The model allows `max_pages: 2`, but the default remains one page until a later rollout explicitly changes it.

## QA behavior

For the default one-page policy, existing hard-failure behavior and issue codes remain stable.

For a future `preferred_pages: 1, max_pages: 2` policy:

- one page passes;
- two pages may pass physical page-count validation and should produce a bounded warning that the preferred page count was exceeded;
- more than two pages fails;
- narrative QA still runs after every reduction and remains authoritative for narrative quality.

Page-size validation must derive from `RenderPolicy.page_size`, not a hard-coded semantic assumption.

## Non-goals

This PR does not:

- add LayoutProfile;
- alter RenderCV styling;
- enable two pages in the default CLI config;
- add Visual QA;
- add JSON Resume export;
- add ATS round-trip QA;
- change Gmail/outreach/send behavior;
- add ApplicationPacket QA metadata yet.

## Exit criteria

- `RecruiterPolicy` contains no physical page/font fields.
- `RenderPolicy` is versioned, strict, and supports max two pages.
- default CLI/service behavior remains one-page.
- `RecruiterQualityQA` uses `RenderPolicy` for physical constraints.
- existing semantic/narrative models no longer require exactly one page.
- all tests, compile, privacy/diff guards, previews, and offline runtime checks pass.
