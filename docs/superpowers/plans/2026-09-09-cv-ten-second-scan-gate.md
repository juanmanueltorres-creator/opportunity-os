# CV Ten-Second Scan Gate — Implementation Plan

## Goal

Turn the currently neutral `scanability_score=1.0` in narrative QA into a deterministic, provenance-backed fast-scan proxy, then wire narrative QA into `CVPreparationService` so a recruiter document cannot reach `PREPARED` when narrative hard gates fail.

## Scope

This change must remain renderer-independent and must not modify Gmail, outreach, CLI semantics, RenderCV templates, or the legacy recruiter composer beyond choosing the already-merged strategy-aware path in the service integration task.

## Task 1 — Deterministic ten-second scan proxy

Files:
- modify `app/cv/narrative/qa.py`
- modify `app/cv/strategy/policy.py`
- modify `config/narrative_policy.yaml`
- add `tests/test_cv_narrative_scan.py`

TDD cycle:
1. RED: tests define a bounded scan view and require scanability to fall when one or more core messages are only visible late in the document.
2. GREEN: add a policy-controlled `max_scan_claims` and deterministic scan claim ordering.
3. Score = fraction of core messages with at least one provenance-backed supporting fact/evidence in the bounded scan view.
4. If score `< min_scanability_score`, emit hard error `narrative_scanability_below_threshold`.
5. Preserve existing core-message coverage and other narrative QA behavior.

Scan order for V1:
- headline
- profile claims
- technology skills
- experience primary claim + first bullet, in order
- project primary claim + first bullet, in order

Identity/contact claims and lower-document education/language/link claims do not consume the scan budget.

## Task 2 — Service integration gate

Files:
- modify `app/cv/service.py`
- add/modify service tests

TDD cycle:
1. RED: service test demonstrates a semantically valid CV/recruiter document is blocked before rendering when narrative QA fails.
2. GREEN: inject/load `NarrativePolicy`, build `CVStrategy`, compose with `compose_strategy_recruiter_document`, run `NarrativeQualityQA` after recruiter validation and again after any reduction.
3. Narrative failures return `BLOCKED_VALIDATION`; no PDF artifact may remain.
4. Narrative warnings are preserved in the returned warning list.
5. Reduction may not silently destroy narrative validity; every reduced recruiter document must re-pass narrative QA before re-rendering.

## Task 3 — Regression and packet compatibility

- Do not add new required `ApplicationPacket` fields in this PR.
- Keep packet hashing stable except for recruiter-document content that legitimately changes because the service now uses the strategy-aware composer.
- Run full pytest, compile, diff/privacy guards, recruiter previews, and offline runtime matrix on Python 3.12/3.13.

## Acceptance criteria

- `scanability_score` is no longer hard-coded.
- The score is deterministic for identical inputs.
- At least `ceil(min_scanability_score * core_message_count)` core messages must be recoverable in the fast-scan view.
- A recruiter document that passes semantic and renderer QA but fails narrative QA cannot reach `PREPARED`.
- No Gmail/send behavior changes.
