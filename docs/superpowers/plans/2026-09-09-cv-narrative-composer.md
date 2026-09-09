# CV Narrative Composer — PR2 Implementation Plan

**Date:** 2026-09-09
**Base:** `main` at `aca84eeda0dc1cfb948769abb54f745218db750e`
**Target branch:** `feat/cv-narrative-composer`
**Parent design:** `docs/superpowers/specs/2026-09-09-cv-strategy-narrative-design.md`
**Execution mode:** inline, TDD, GitHub Actions as verification environment

## Goal

Add a strategy-aware recruiter-document composer that ranks existing validated claims against `CVStrategy`, while preserving provenance, existing `RecruiterDocumentModel`, current renderer compatibility, and the legacy recruiter composer.

PR2 must make narrative selection measurably better without changing the production PDF preparation path yet.

## Non-goals

PR2 MUST NOT:

- wire the new composer into `CVPreparationService`;
- change renderer behavior or PDF templates;
- add narrative QA gates (PR3);
- split narrative/render policy (PR4);
- change `ApplicationPacket`;
- mint or rewrite recruiter-visible claim text;
- add user-private track configuration to the public repository;
- replace or delete `compose_recruiter_document()`.

## Existing contracts to preserve

- `CVDocumentModel` remains the source of visible claim text and provenance.
- `ValidationResult.validated_claim_ids` remains the authority boundary for visible claims.
- `EvidenceSelection` remains the support/gap boundary.
- `CVStrategy` supplies `must_show_fact_ids`, `supporting_fact_ids`, `optional_fact_ids`, core messages, positioning, and target context.
- `RecruiterDocumentModel` remains renderer-compatible and stores claim IDs only.
- `RecruiterPolicy` caps remain authoritative for this PR.

## Proposed public API

Create:

```python
from app.cv.narrative.composer import compose_strategy_recruiter_document

recruiter = compose_strategy_recruiter_document(
    document=document,
    validation=validation,
    selection=selection,
    strategy=strategy,
    policy=recruiter_policy,
)
```

The function returns the existing `RecruiterDocumentModel`.

## Ranking contract

PR2 intentionally avoids introducing unversioned numeric narrative weights. V1 uses a deterministic lexicographic ranking derived from already-versioned strategy inputs.

For a claim with provenance:

1. strategy bucket:
   - must-show facts;
   - supporting facts;
   - optional facts;
   - structural/context-only claim;
2. number of strategy core messages supported by claim fact/evidence provenance, descending;
3. direct requirement support from `EvidenceSelection`, supported before unsupported/context;
4. canonical source order for chronology/presentation stability;
5. claim ID as final deterministic tie-break.

Unsupported seniority is not ranked; strategy construction already rejects unsupported positioning. The narrative composer additionally requires the strategy positioning to resolve to an existing validated headline claim.

## Safety invariants

The new composer MUST fail closed when:

- semantic validation is invalid;
- strategy application track differs from `EvidenceSelection.application_track_id`;
- strategy fact buckets reference facts outside `selection.selected_fact_ids`;
- strategy positioning cannot resolve to a validated `headline/headline` claim with overlapping positioning provenance.

The new composer MUST NOT select any claim outside `validated_claim_ids`.

Every output claim ID MUST already exist in the semantic document; therefore PR2 cannot create new recruiter-facing wording.

---

## Task 1 — Narrative ranking contract

**Create:**
- `app/cv/narrative/__init__.py`
- `app/cv/narrative/ranking.py`
- `tests/test_cv_narrative_ranking.py`

### RED tests

Write tests for a public ranking helper with an explainable result object/function surface.

Required cases:

1. a claim backed by a `must_show_fact_id` outranks a claim backed only by a `supporting_fact_id`;
2. supporting outranks optional;
3. within the same bucket, a claim overlapping more `CoreMessage` fact/evidence refs ranks first;
4. within the same bucket/core-message count, a requirement-supported claim ranks before context-only;
5. final ties use canonical source order and then claim ID;
6. a claim with no provenance is treated as context-only and never promoted;
7. ranking never accepts claims outside the supplied validated set.

Expected first run: RED because `app.cv.narrative.ranking` does not exist.

### GREEN implementation

Implement a small deterministic rank representation, for example:

```python
class NarrativeClaimRank(StrictCVModel):
    claim_id: str
    bucket_rank: int
    core_message_hits: int
    requirement_supported: bool
    source_order: int

    @property
    def sort_key(self) -> tuple[int, int, int, int, str]: ...
```

Or an equivalent immutable helper.

Add helpers to:

- derive strategy bucket from `ClaimProvenance.fact_ids`;
- count overlaps with strategy `CoreMessage.fact_ids` and `evidence_ids`;
- derive requirement-supported claim IDs from `EvidenceSelection` without treating `UNKNOWN` as support;
- sort only validated claims.

No generic-language or identity-noise heuristics in PR2; those belong to PR3 QA.

### Verification

Run via CI:

```bash
python -m pytest tests/test_cv_narrative_ranking.py -q
python -m pytest -q
```

Commit when GREEN:

```text
feat: add deterministic narrative claim ranking
```

---

## Task 2 — Strategy-aware recruiter composer core

**Create:**
- `app/cv/narrative/composer.py`
- `tests/test_cv_narrative_composer.py`

**Modify:**
- `app/cv/narrative/__init__.py`

### RED tests

Build synthetic fixtures with at least:

- two project claims where legacy source/support ordering conflicts with strategy priority;
- two skill claims in the same recruiter skill group;
- two experience claims and provenance-linked bullets;
- a validated positioning headline;
- one unvalidated injected claim.

Required cases:

1. must-show strategy project outranks a merely requirement-supported optional project;
2. within a strategy bucket, stronger core-message overlap wins;
3. unvalidated injected claims never appear;
4. skill grouping still obeys `RecruiterPolicy` caps and visible-text deduplication;
5. project bullets attach only through overlapping fact provenance;
6. experience bullets attach only through overlapping fact provenance;
7. output contains no claim ID absent from the source semantic document;
8. output is deterministic for identical document/strategy inputs.

Expected first run: RED because `compose_strategy_recruiter_document()` does not exist.

### GREEN implementation

Implement:

```python
def compose_strategy_recruiter_document(
    *,
    document: CVDocumentModel,
    validation: ValidationResult,
    selection: EvidenceSelection,
    strategy: CVStrategy,
    policy: RecruiterPolicy,
) -> RecruiterDocumentModel:
    ...
```

Composition rules:

- identity and contact remain required structural context;
- headline MUST be the validated claim resolving `strategy.positioning`;
- summary/profile claims use narrative ranking;
- skills are ranked first, then grouped using existing recruiter skill-group membership rules;
- projects are ranked before policy truncation;
- project bullet selection ranks eligible overlapping bullets and picks the strongest one under current model cap;
- experience primaries are ranked before policy truncation, preserving lower-ranked chronology/context only within remaining capacity;
- experience bullets use the same provenance-overlap safety rule;
- education/language/link claims remain structural/contextual, with deterministic ordering;
- existing `RecruiterPolicy` caps remain unchanged.

Do not call or mutate the legacy composer. Keep both paths independently testable.

### Positioning resolution

Because `CVStrategy` intentionally does not mint a new claim ID, resolve positioning by requiring all of:

- claim is validated;
- `claim.section == "headline"`;
- `claim.kind == "headline"`;
- normalized `claim.text == strategy.positioning`;
- claim provenance overlaps the positioning core-message facts/evidence.

If no claim satisfies the contract, raise a bounded `ValueError`, e.g. `narrative_positioning_claim_unresolved`.

### Verification

```bash
python -m pytest tests/test_cv_narrative_composer.py -q
python -m pytest tests/test_recruiter_composer.py tests/test_cv_narrative_composer.py -q
python -m pytest -q
```

Commit when GREEN:

```text
feat: compose recruiter documents from CV strategy
```

---

## Task 3 — Fail-closed integration guards

**Modify:**
- `tests/test_cv_narrative_composer.py`
- `app/cv/narrative/composer.py` only if RED tests require it

### RED tests

Add explicit failure tests:

1. invalid semantic `ValidationResult` -> `narrative_requires_valid_semantic_document`;
2. strategy/selection track mismatch -> `narrative_strategy_track_mismatch`;
3. strategy bucket fact not present in `selection.selected_fact_ids` -> `narrative_strategy_fact_outside_selection`;
4. positioning text exists only in an unvalidated headline -> unresolved positioning failure;
5. strategy positioning equals target vacancy title but no validated candidate headline matches -> unresolved positioning failure.

These tests protect against a future caller bypassing the strategy builder or constructing strategy data manually.

### GREEN implementation

Add only the minimum validation needed to satisfy the tests. Do not broaden PR2 into narrative QA.

### Verification

```bash
python -m pytest tests/test_cv_narrative_composer.py -q
python -m pytest -q
```

Commit when GREEN:

```text
fix: harden strategy-aware narrative composition
```

---

## Task 4 — Legacy comparison/regression fixture

**Create:**
- `tests/test_cv_narrative_composer_regression.py`

No production changes expected unless a genuine defect is exposed.

### Contract fixture

Create a fictional semantic CV where:

- legacy ordering chooses a source-order or generic supported project first;
- strategy marks another project as must-show/core-message evidence;
- both documents are valid and renderer-compatible.

Assert:

```text
legacy first project != strategy first project
strategy first project == must-show project
```

Also assert:

- every strategy-aware output ID belongs to the validated semantic document;
- legacy `compose_recruiter_document()` output remains byte/model deterministic against the existing fixture;
- `reduce_recruiter_document()` can reduce the strategy-aware output without any API change;
- no service/renderer/ApplicationPacket files are changed in PR2.

### Final verification

Fresh CI on final SHA must pass:

```bash
python -m pytest -q
python -m compileall app
git diff --check origin/main...HEAD
```

Repository CI must also pass existing recruiter preview generation and offline runtime verification for Python 3.12 and 3.13.

Commit:

```text
test: prove strategy-aware recruiter ordering
```

---

## PR2 acceptance checklist

Reject PR2 unless all are true:

- [ ] legacy `compose_recruiter_document()` remains available and behavior-compatible;
- [ ] new composer consumes `CVStrategy` explicitly;
- [ ] new composer selects only validated existing claims;
- [ ] strategy must-show/supporting/optional buckets affect selection before recruiter caps;
- [ ] core-message overlap affects ordering deterministically;
- [ ] requirement support is secondary to explicit strategy bucket priority;
- [ ] positioning resolves to an existing validated evidence-backed headline claim;
- [ ] strategy/selection track mismatches fail closed;
- [ ] strategy facts outside selected evidence fail closed;
- [ ] project/experience bullet association still requires overlapping provenance;
- [ ] no recruiter-facing text is invented or rewritten;
- [ ] no renderer, service, CLI, packet, or PDF behavior changes are included;
- [ ] synthetic fixtures only; no private candidate data committed;
- [ ] full repository test suite passes;
- [ ] recruiter previews still render;
- [ ] offline runtime verifies in Python 3.12 and 3.13.

## Deferred

- Narrative QA / scanability / off-strategy ratio: PR3.
- Narrative-vs-render policy split: PR4.
- Layout profiles: PR5.
- Visual QA: PR6.
- JSON Resume: PR7.
- Second renderer: PR8.
- ATS round-trip recoverability: PR9.
- Production `CVPreparationService` switchover will occur only after strategy-aware composition and narrative QA have both proven safe.