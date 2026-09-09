# CV Narrative QA Design

**Date:** 2026-09-09
**Status:** Approved for PR3 implementation
**Parent architecture:** CV Strategy, Narrative Composition, Layout, and Quality Architecture

## Goal

Add a deterministic, pre-render narrative quality gate for the strategy-aware CV path. The gate must determine whether a `RecruiterDocumentModel` actually communicates its `CVStrategy`, without inventing recruiter-facing text and without depending on the PDF renderer.

## Inputs and authority boundaries

Narrative QA consumes:

- `CVDocumentModel` as the canonical visible-claim/provenance source;
- `RecruiterDocumentModel` as the proposed recruiter-visible selection/order;
- `CVStrategy` as the editorial intent;
- versioned `NarrativePolicy` as the threshold/configuration authority.

Narrative QA does not receive permission to rewrite claims. It only evaluates existing claim IDs and provenance.

## Result model

```python
class NarrativeQAResult(StrictCVModel):
    valid: bool
    core_message_coverage: dict[str, float]
    off_strategy_claim_ratio: float
    competing_identity_count: int
    scanability_score: float
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]
```

All metrics are deterministic for identical inputs.

## Policy additions

Extend `NarrativePolicy` with backward-compatible defaults and explicit values in `config/narrative_policy.yaml`:

```yaml
max_off_strategy_claim_ratio: 0.35
max_competing_identity_signals: 1
min_scanability_score: 0.67
generic_language_phrases:
  en:
    - results-driven
    - passionate
    - hard-working
    - team player
    - fast learner
    - proactive
    - detail-oriented
  es:
    - orientado a resultados
    - apasionado
    - trabajador
    - trabajo en equipo
    - aprendizaje rápido
    - proactivo
    - detallista
```

The public phrases are generic recruiting filler only; user-specific career identities remain private runtime configuration and are not committed.

## Visible support model

A visible claim supports strategy when its provenance overlaps any of:

- `strategy.must_show_fact_ids`;
- `strategy.supporting_fact_ids`;
- `strategy.optional_fact_ids`;
- a `CoreMessage.fact_ids` reference;
- a `CoreMessage.evidence_ids` reference.

### Core-message coverage

For each core message, coverage is the fraction of that message's referenced facts that are represented by at least one visible claim provenance. `CoreMessage.fact_ids` is non-empty, so the denominator is stable.

A core message with `coverage == 0.0` is a hard narrative error:

`narrative_core_message_uncovered`.

## Editorial vs structural context

Off-strategy ratio is calculated only across editorial claims, not structural chronology/context.

Editorial claims are:

- profile/summary claims;
- visible skill claims;
- project primary claims and project bullets;
- experience bullets.

Structural/context claims excluded from this denominator include:

- identity;
- contact/location;
- the selected headline;
- experience primary/title chronology;
- education;
- languages;
- links.

This prevents legitimate history from being treated as narrative noise.

`off_strategy_claim_ratio = off_strategy_editorial_claims / all_editorial_claims`, or `0.0` when no editorial claims are visible.

If the ratio exceeds `policy.max_off_strategy_claim_ratio`, emit hard error:

`narrative_off_strategy_ratio_exceeded`.

## Identity coherence V1

V1 does not guess professions from free text and does not use user-private identity vocabularies.

A competing identity signal is a top-of-document profile/summary claim that does not support any strategy/core-message provenance. Historical experience titles are not counted because they are legitimate chronology.

If `competing_identity_count > policy.max_competing_identity_signals`, emit hard error:

`narrative_competing_identity_limit_exceeded`.

The headline must normalize exactly to `strategy.positioning` and its provenance must overlap the positioning core message. Otherwise emit:

- `narrative_positioning_mismatch`, or
- `narrative_positioning_unsupported`.

This is the V1 seniority/identity safety re-check. Since recruiter-visible text is inherited from an already validated semantic document, Narrative QA must not add separate speculative seniority inference.

## Generic-language detection

For editorial claims, case-insensitive phrase matching uses the language-specific phrase list from `NarrativePolicy`.

Each match produces warning:

`narrative_generic_claim_detected`.

Generic-language warnings do not independently invalidate V1; they remain visible QA evidence and can become a stricter policy later without changing the result contract.

## Ten-second scan proxy

Build a deterministic reduced scan set from:

- headline;
- all profile claims;
- visible skill claims;
- each project primary and its first bullet;
- each experience primary and its first bullet.

For every core message, mark it scan-covered when at least one reduced-scan claim provenance overlaps that message's fact/evidence references.

`scanability_score = scan-covered core messages / total core messages`.

If score is below `policy.min_scanability_score`, emit hard error:

`narrative_scanability_failed`.

This is explicitly a deterministic recruiter-scan proxy, not a claim about human eye-tracking or recruiter behavior.

## Fail-closed input validation

Narrative QA must fail closed with bounded `ValueError` codes when:

- recruiter document references a claim absent from the semantic document;
- strategy/recruiter source-document versions do not align with the semantic document where applicable;
- the headline claim is absent.

It must never echo private claim text in error messages.

## Public API

```python
from app.cv.narrative import NarrativeQualityQA

result = NarrativeQualityQA().evaluate(
    recruiter_document=recruiter_document,
    source_document=document,
    strategy=strategy,
    policy=narrative_policy,
)
```

## Non-goals for PR3

PR3 does not:

- wire Narrative QA into `CVPreparationService`;
- change `ApplicationPacket`;
- change renderer or PDF QA;
- change legacy recruiter composer behavior;
- rewrite or mint claims;
- add layout profiles or visual QA;
- add user-private identity terms;
- call an LLM.

A later integration PR will make `NarrativeQAResult.valid == False` block `PREPARED` on the strategy-aware production path.