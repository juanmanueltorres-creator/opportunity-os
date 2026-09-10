# Dogfood Ranking & CV Narrative Amendment — Design

**Status:** Approved
**Date:** 2026-09-10
**Scope:** Radar requirement handling, CAREER ranking, and recruiter CV narrative composition.

## Problem

Real-world dogfood exposed two false-negative / information-loss behaviors.

1. Quantified experience requirements behave as implicit hard gates. When exact duration cannot be verified, experience gets zero credit, `mandatory_experience_unverified` is emitted, HIGH/MEDIUM CAREER tiers are forced to STRETCH, and downstream CV preparation is blocked even though eligibility itself passed.
2. Recruiter CV composition preserves only one bullet per project/experience entry, flattening the strongest engineering narrative into generic keyword evidence.

## Design principles

- Truth before optimization.
- No invented years, skills, employers, tools, or outcomes.
- Unsupported requirements remain explicit gaps.
- Deterministic generation from approved facts/evidence.
- Track boundaries remain enforced.
- One-page, ATS-friendly recruiter CV remains the default.
- Human approval remains required for external actions.
- Lack of evidence is not automatically evidence of incompatibility.
- Tailoring changes emphasis, not professional identity.

## Experience requirement semantics

Experience-duration support is not binary. The CAREER pipeline distinguishes:

- `SATISFIED`: verified relevant evidence demonstrates duration >= requested duration.
- `PARTIAL`: verified relevant evidence demonstrates some duration but less than requested; use the evidenced/requested ratio as bounded partial credit.
- `UNKNOWN`: relevant verified capability evidence exists but exact duration cannot be safely established. This remains an explicit gap/risk but is not scored as zero capability.
- `UNSUPPORTED`: there is no relevant verified capability evidence.

No new public recommendation enum is introduced. Existing APPLY semantics plus explicit gaps are sufficient.

## Ranking semantics

Remove the forced rule:

`mandatory_experience_unverified => HIGH/MEDIUM -> STRETCH`

Unknown mandatory duration remains visible as a risk/gap but does not override the calculated CAREER tier. True eligibility incompatibilities continue to hard-fail through eligibility.

Preferred experience requirements must never create mandatory experience risk, force STRETCH, prevent CAREER selection, or block CV generation.

## Requirement importance extraction

Explicit preferred cues include, at minimum:

English: `preferred`, `ideally`, `nice to have`, `a plus`, `desirable`.
Spanish: `deseable`, `idealmente`, `preferentemente`, `será un plus`, `valoramos`.

Explicit mandatory cues remain mandatory, including `required`, `must`, `minimum`, `requerido`, `obligatorio`, `excluyente`, `mínimo`.

Numeric duration alone must not upgrade a requirement to mandatory merely because a number was detected.

## CV narrative composition

For selected projects with sufficient approved evidence, preserve up to two ranked, provenance-overlapping bullets. Prefer complementary narrative depth over breadth:

1. problem / purpose / engineering decision;
2. implementation / evidence / outcome.

Experience entries follow the same policy: up to two bullets when approved evidence exists, with page reduction allowed to remove lower-value secondary bullets when necessary.

The deterministic reduction order becomes:

1. optional duplicate links;
2. redundant/lower-relevance skills;
3. project entries beyond the top two;
4. lower-priority experience entries;
5. extra education entries;
6. secondary bullets on lower-priority entries;
7. second bullet of the primary project only as a late fallback.

The reducer must preserve provenance and keep legacy project ID fields synchronized.

## Tests

### Radar

Add fixtures/regressions for:

- `3+ years preferred`;
- `Ideally 3 years`;
- `3 años deseables`;
- `será un plus contar con 3 años`;
- `Minimum 3 years required`;
- `mínimo 3 años excluyente`;
- partial verified duration;
- unknown duration with relevant verified capability;
- unsupported experience;
- mandatory duration can remain a gap without forcing STRETCH;
- true eligibility incompatibility still hard-fails.

### CV

Add regressions proving:

- two relevant bullets can attach to a primary project;
- unrelated bullets cannot attach through accidental provenance;
- two experience bullets can attach when policy permits;
- deterministic reduction drops lower-value content before primary-project narrative;
- semantic/provenance invariants remain valid.

## Non-goals

- Do not weaken truth/provenance rules.
- Do not invent or estimate years.
- Do not let an LLM decide whether experience is real.
- Do not remove ATS or one-page QA.
- Do not make every opportunity APPLY.
- Do not remove STRETCH as a category.
- Do not introduce automatic sending/application submission.

## Success criteria

The amendment succeeds when desired/unknown experience duration no longer creates false eliminations, true incompatibilities still fail deterministically, and generated CVs preserve approved engineering narrative without violating provenance or page/ATS constraints.
