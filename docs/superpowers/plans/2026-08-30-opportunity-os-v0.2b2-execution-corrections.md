# Opportunity OS V0.2B2 — Execution Corrections

Date: 2026-08-30
Status: normative execution clarification
Applies to: `2026-08-30-opportunity-os-v0.2b2-one-page-recruiter-pipeline.md`

## Renderer metric validation boundary

`RecruiterRenderMetrics` records what the renderer actually produced. It therefore MUST be able to represent a positive body font size below the recruiter-quality threshold.

The model-level constraint is:

```text
body_font_size > 0
```

The recruiter-quality constraint remains unchanged:

```text
body_font_size >= 9.0 pt
```

`RecruiterQualityQA` owns that hard gate and maps a lower measured value to:

```text
BLOCKED_RENDER
recruiter_body_font_too_small
```

This clarification prevents Pydantic model construction from hiding a renderer-quality defect before QA can inspect and classify it. It does not weaken the approved one-page recruiter contract.
