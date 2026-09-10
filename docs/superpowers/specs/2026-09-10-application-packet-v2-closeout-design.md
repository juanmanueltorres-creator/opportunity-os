# ApplicationPacket v2 Close-Out Design

**Date:** 2026-09-10
**Status:** Approved for implementation
**Scope:** Opportunity-OS CV preparation packet persistence and auditability
**Base:** `main@c0532fd9e163f73b7ef18d3a5b199a8d3b97800a`

## 1. Problem

The CV pipeline already computes and enforces strategy, narrative QA, layout selection, structural QA, visual QA, and ATS round-trip QA before returning `PREPARED`. The current `ApplicationPacket` persists the semantic CV/recruiter document and ATS QA, but not the complete authoritative strategy/layout/narrative/visual decision state that produced the final PDF.

That leaves a reproducibility gap: two prepared artifacts can differ because of strategy, layout, or QA state without the packet itself preserving all of those authoritative inputs/results.

The original CV strategy/narrative architecture requires these stages to become auditable once authoritative.

## 2. Goal

Introduce a backward-compatible `ApplicationPacket` v2 that persists the authoritative CV strategy, policy/layout versions, and QA results that actually passed the preparation pipeline, and incorporates them into packet hashing.

Historical packets must continue to validate without silent reinterpretation.

## 3. Non-goals

This close-out does **not** change:

- CAREER ranking or requirement scoring;
- evidence selection or provenance semantics;
- recruiter composition or reduction behavior;
- renderer selection or default renderer behavior;
- RenderCV/Typst or ReportLab rendering logic;
- Gmail, outreach, application submission, or external actions;
- ATS thresholds or visual/narrative QA policy semantics.

## 4. Versioning model

`ApplicationPacket` gains:

```text
packet_schema_version
strategy_version
strategy
narrative_policy_version
layout_profile_id
layout_profile_version
narrative_qa
visual_qa
```

Existing fields remain, including:

```text
ats_policy_version
ats_qa
```

Supported schema versions:

- `application-packet-v1`: historical shape. Absence of `packet_schema_version` is interpreted as v1 for backward compatibility.
- `application-packet-v2`: authoritative strategy/layout/QA shape. New packets prepared by `CVPreparationService` use v2.

V1 remains readable. New preparation never emits v1.

## 5. Typed boundaries

The v2 fields are typed projections of existing canonical models:

- `strategy` → `CVStrategy`
- `narrative_qa` → `NarrativeQAResult`
- `visual_qa` → `VisualQAResult`
- `ats_qa` → `ATSRoundTripQAResult` (existing behavior)

To avoid circular imports from `app.cv.models`, runtime validators may lazily import these types, matching the current `recruiter_document` / `ats_qa` pattern.

## 6. V2 invariants

For `application-packet-v2`:

1. all v2 audit fields must be present;
2. `strategy_version == strategy.strategy_version`;
3. `narrative_policy_version` must equal the version used by the preparation service;
4. `layout_profile_id` and `layout_profile_version` must match the selected `LayoutProfile`;
5. `narrative_qa.valid`, `visual_qa.valid`, and `ats_qa.valid` must all be true in a `PREPARED` packet;
6. `ats_policy_version == ats_qa.policy_version` remains enforced;
7. historical v1 packets may omit all v2 fields and continue to validate;
8. partially populated v2 audit bundles fail closed.

## 7. Authoritative values from CVPreparationService

The packet stores the exact values that reached the successful end of the preparation pipeline:

- the `CVStrategy` built for the opportunity;
- the current narrative policy version;
- the selected `LayoutProfile` id/version;
- the narrative QA result corresponding to the final recruiter document;
- the visual QA result corresponding to the final rendered PDF;
- the ATS round-trip QA result corresponding to that PDF.

If the reduction loop changes the recruiter document, narrative QA must be re-evaluated as it is today; the packet must persist the **final successful** narrative QA result, not a stale pre-reduction result.

## 8. Hashing

V1 historical behavior remains readable; the service's new v2 packet hash includes all authoritative v2 fields:

```text
packet_schema_version
strategy_version
strategy
narrative_policy_version
layout_profile_id
layout_profile_version
narrative_qa
visual_qa
ats_policy_version
ats_qa
```

The hash continues to exclude non-semantic runtime values already excluded today, such as application id, creation time, and output path.

A change in strategy, selected layout, narrative QA, visual QA, or ATS QA must change the v2 packet hash.

## 9. Compatibility

Backward compatibility is structural, not a migration rewrite:

- payloads with no `packet_schema_version` and no v2 bundle validate as v1;
- explicit `application-packet-v1` payloads also validate as v1;
- v1 payloads must not be forced to fabricate strategy/layout/QA fields;
- v2 payloads require the complete bundle;
- no historical packet file is rewritten by this change.

## 10. Tests

Required regression coverage:

1. an existing/historical packet without v2 fields still validates as v1;
2. an explicit v1 packet validates without the v2 bundle;
3. v2 rejects an incomplete audit bundle;
4. v2 rejects strategy/layout/ATS version mismatches;
5. `CVPreparationService` emits v2 and persists the actual successful strategy/layout/narrative/visual/ATS results;
6. the final narrative QA result is the one associated with the final recruiter document after any reduction;
7. changing each authoritative v2 audit component changes the packet hash;
8. id/time/path remain excluded from the hash;
9. full existing semantic, narrative, structural, visual, ATS, offline-runtime, and privacy test suites stay green.

## 11. Documentation close-out

After implementation, the original architecture spec is updated from proposed status to implemented status and records that:

- strategy/narrative/layout/visual/ATS stages are authoritative;
- JSON Resume interoperability is implemented;
- the optional ReportLab human-first renderer is implemented while RenderCV/Typst remains the default;
- ApplicationPacket v2 closes the auditability requirement;
- ATS QA remains a recoverability proxy, not a commercial ATS guarantee.

## 12. Success criteria

This close-out is complete when a newly prepared packet is sufficient to identify the exact versioned strategy/layout/QA state that produced its recruiter PDF, those values affect the packet hash, historical v1 packets remain valid, and the full repository CI is green.
