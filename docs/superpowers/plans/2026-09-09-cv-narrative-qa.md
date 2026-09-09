# CV Narrative QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic pre-render Narrative QA layer that rejects strategy-incoherent recruiter documents before they can become authoritative.

**Architecture:** `NarrativeQualityQA` evaluates an existing `RecruiterDocumentModel` against `CVStrategy`, `CVDocumentModel` provenance, and versioned `NarrativePolicy`. It produces metrics plus bounded `ValidationIssue` errors/warnings and never rewrites recruiter-visible text. PR3 remains parallel to production orchestration; service/renderer/packet wiring is deferred.

**Tech Stack:** Python 3.12/3.13, Pydantic v2, PyYAML, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-09-cv-narrative-qa-design.md`

## Global Constraints

- `CVDocumentModel` remains the canonical visible-claim/provenance source.
- `RecruiterDocumentModel` remains claim-ID-only and renderer-compatible.
- `CVStrategy` is editorial intent, not authority to mint text.
- Narrative QA must be deterministic and renderer-independent.
- Narrative QA must not call an LLM or infer private user-specific identities.
- No `CVPreparationService`, renderer, CLI, `ApplicationPacket`, legacy recruiter composer, or PDF behavior changes in PR3.
- All public fixtures are synthetic.
- Production code changes follow RED → verified failure → minimal GREEN.

---

### Task 1: Versioned QA policy and result contract

**Files:**
- Modify: `app/cv/strategy/policy.py`
- Modify: `config/narrative_policy.yaml`
- Create: `app/cv/narrative/models.py`
- Modify: `app/cv/narrative/__init__.py`
- Modify: `tests/test_cv_strategy_policy.py`
- Create: `tests/test_cv_narrative_qa_models.py`

**Interfaces:**
- Consumes: existing `NarrativePolicy`, `StrictCVModel`, `ValidationIssue`.
- Produces: `NarrativeQAResult`; policy fields `max_off_strategy_claim_ratio`, `max_competing_identity_signals`, `min_scanability_score`, `generic_language_phrases`.

- [ ] **Step 1: Write failing policy/model tests**

Add tests asserting:

```python
policy = NarrativePolicy.model_validate(_payload_with_qa_fields())
assert policy.max_off_strategy_claim_ratio == 0.35
assert policy.max_competing_identity_signals == 1
assert policy.min_scanability_score == 0.67
assert set(policy.generic_language_phrases) == {"en", "es"}
```

Add invalid-bound tests:

```python
payload["max_off_strategy_claim_ratio"] = 1.1
with pytest.raises(ValueError):
    NarrativePolicy.model_validate(payload)
```

and exact-language-key validation:

```python
payload["generic_language_phrases"] = {"en": ["passionate"]}
with pytest.raises(ValueError, match="generic_language_phrases"):
    NarrativePolicy.model_validate(payload)
```

Add result-model test:

```python
result = NarrativeQAResult(
    valid=True,
    core_message_coverage={"positioning": 1.0},
    off_strategy_claim_ratio=0.0,
    competing_identity_count=0,
    scanability_score=1.0,
)
assert result.errors == []
assert result.warnings == []
```

Expected RED: missing policy fields / missing `app.cv.narrative.models`.

- [ ] **Step 2: Run CI and confirm RED for the intended missing contract**

Run via PR CI and inspect `pytest` logs. Do not implement until failures are attributable to absent QA policy/model surface rather than test syntax.

- [ ] **Step 3: Implement minimal policy/model contract**

Extend `NarrativePolicy` with defaults:

```python
max_off_strategy_claim_ratio: float = Field(default=0.35, ge=0, le=1)
max_competing_identity_signals: int = Field(default=1, ge=0)
min_scanability_score: float = Field(default=0.67, ge=0, le=1)
generic_language_phrases: dict[str, list[str]] = Field(
    default_factory=lambda: {"en": [], "es": []}
)
```

In `validate_contract`, require exact phrase keys `{"en", "es"}`, non-empty normalized phrases, and no duplicates within a language.

Create:

```python
class NarrativeQAResult(StrictCVModel):
    valid: bool
    core_message_coverage: dict[str, float] = Field(default_factory=dict)
    off_strategy_claim_ratio: float = Field(ge=0, le=1)
    competing_identity_count: int = Field(ge=0)
    scanability_score: float = Field(ge=0, le=1)
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
```

Export `NarrativeQAResult` from `app.cv.narrative`.

Add explicit QA fields/phrases to `config/narrative_policy.yaml`.

- [ ] **Step 4: Run focused and full tests**

```bash
python -m pytest tests/test_cv_strategy_policy.py tests/test_cv_narrative_qa_models.py -q
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```text
feat: add narrative QA policy contract
```

---

### Task 2: Core-message, off-strategy, identity, and generic-language QA

**Files:**
- Create: `app/cv/narrative/qa.py`
- Create: `tests/test_cv_narrative_qa.py`
- Modify: `app/cv/narrative/__init__.py`

**Interfaces:**
- Consumes: `RecruiterDocumentModel`, `CVDocumentModel`, `CVStrategy`, `NarrativePolicy`.
- Produces: `NarrativeQualityQA.evaluate(...) -> NarrativeQAResult`.

- [ ] **Step 1: Write failing evaluator tests**

Synthetic fixture requirements:

- validated semantic document with identity, positioning headline, two summary claims, skills, two projects, experience title/bullet, education/language;
- strategy with two core messages and disjoint must/supporting/optional fact buckets;
- recruiter document containing only source claim IDs.

Required tests:

```python
def test_all_core_messages_have_visible_provenance_coverage(): ...
def test_missing_core_message_is_hard_error(): ...
def test_off_strategy_editorial_ratio_excludes_structural_chronology(): ...
def test_off_strategy_ratio_above_policy_is_hard_error(): ...
def test_off_strategy_profile_claim_counts_as_competing_identity_signal(): ...
def test_competing_identity_limit_is_hard_error(): ...
def test_generic_phrase_emits_warning_without_independent_failure(): ...
def test_headline_must_match_strategy_positioning(): ...
def test_headline_must_overlap_positioning_core_message_provenance(): ...
```

Expected RED: `NarrativeQualityQA` does not exist.

- [ ] **Step 2: Confirm RED in CI**

Expected collection/import failure or missing evaluator symbol. Fix test syntax only if necessary; do not add production behavior before intended RED is observed.

- [ ] **Step 3: Implement deterministic helpers and evaluator**

Public signature:

```python
class NarrativeQualityQA:
    def evaluate(
        self,
        *,
        recruiter_document: RecruiterDocumentModel,
        source_document: CVDocumentModel,
        strategy: CVStrategy,
        policy: NarrativePolicy,
    ) -> NarrativeQAResult:
        ...
```

Implement helpers for:

```python
_claim_by_id(source_document)
_visible_claim_ids(recruiter_document)
_strategy_fact_ids(strategy)
_strategy_evidence_ids(strategy)
_claim_supports_strategy(claim_id, source_document, strategy)
_editorial_claim_ids(recruiter_document)
_core_message_coverage(...)
_competing_identity_claim_ids(...)
_generic_claim_warnings(...)
```

Core-message coverage uses message `fact_ids` as denominator and visible provenance fact overlap as numerator. Zero coverage creates `narrative_core_message_uncovered`.

Editorial denominator contains profile claims, skill claims, project primary/bullets, and experience bullets only. Claims with no strategy/core-message provenance are off-strategy. Ratio above policy creates `narrative_off_strategy_ratio_exceeded`.

Competing identity signals are off-strategy `profile_claim_ids`. Count above policy creates `narrative_competing_identity_limit_exceeded`.

Headline normalized text must equal `strategy.positioning`; otherwise `narrative_positioning_mismatch`. Its provenance must overlap the positioning core message selected by `message.id == "positioning"` or normalized `message.message == strategy.positioning`; otherwise `narrative_positioning_unsupported`.

Generic phrase matches on editorial claim text produce `narrative_generic_claim_detected` warnings with `claim_id`, never echoing claim text in the message.

- [ ] **Step 4: Run focused and full tests**

```bash
python -m pytest tests/test_cv_narrative_qa.py -q
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```text
feat: evaluate recruiter narrative coherence
```

---

### Task 3: Ten-second scan proxy and fail-closed guards

**Files:**
- Modify: `app/cv/narrative/qa.py`
- Modify: `tests/test_cv_narrative_qa.py`
- Create: `tests/test_cv_narrative_qa_guards.py`

**Interfaces:**
- Extends `NarrativeQualityQA.evaluate` without changing its signature.
- Produces `scanability_score` and bounded input-validation failures.

- [ ] **Step 1: Write failing scan/guard tests**

Required scan tests:

```python
def test_scan_view_covers_headline_profile_skills_and_first_entry_bullets(): ...
def test_scanability_score_is_fraction_of_core_messages_seen_in_scan(): ...
def test_scanability_below_policy_is_hard_error(): ...
```

Required guard tests:

```python
def test_unknown_recruiter_claim_fails_closed_with_bounded_code(): ...
def test_source_document_version_mismatch_fails_closed(): ...
def test_missing_headline_claim_fails_closed(): ...
```

Expected RED: scan score remains unimplemented/default or invalid inputs are not rejected.

- [ ] **Step 2: Confirm intended RED in CI**

Verify failures are behavior failures, not fixture errors.

- [ ] **Step 3: Implement scan view and guards**

Reduced scan IDs are, in deterministic order:

```text
headline
profile claims
all visible skills
project primary + first project bullet for each entry
experience primary + first experience bullet for each entry
```

A core message is scan-covered if any scan claim provenance overlaps its fact/evidence refs.

```python
scanability_score = scan_covered_messages / len(strategy.core_messages)
```

Below policy threshold creates `narrative_scanability_failed`.

Before metric evaluation, fail closed with bounded `ValueError` strings:

```text
narrative_unknown_claim_reference
narrative_source_document_version_mismatch
narrative_headline_claim_missing
```

Do not include private text in exception strings.

- [ ] **Step 4: Run focused and full tests**

```bash
python -m pytest tests/test_cv_narrative_qa.py tests/test_cv_narrative_qa_guards.py -q
python -m pytest -q
python -m compileall app
```

Expected: PASS.

- [ ] **Step 5: Commit**

```text
feat: add narrative scanability gate
```

---

### Task 4: Strategy-composer regression fixture and PR scope lock

**Files:**
- Create: `tests/test_cv_narrative_qa_regression.py`
- Create: `tests/test_cv_narrative_qa_release_contract.py`

**Interfaces:**
- Consumes the public `compose_strategy_recruiter_document` and `NarrativeQualityQA` APIs.
- No production changes expected.

- [ ] **Step 1: Add regression fixture**

Construct a fictional strategy-aware recruiter document through the PR2 public composer, then evaluate it through Narrative QA. Assert:

```python
assert qa.valid is True
assert all(value > 0 for value in qa.core_message_coverage.values())
assert qa.off_strategy_claim_ratio <= policy.max_off_strategy_claim_ratio
assert qa.competing_identity_count <= policy.max_competing_identity_signals
assert qa.scanability_score >= policy.min_scanability_score
```

Then mutate only the recruiter selection to surface off-strategy profile/project noise and assert the QA fails with the correct narrative issue family without changing source claims.

- [ ] **Step 2: Add release-contract test**

Assert PR3 production imports remain inside narrative/strategy policy boundaries and no production path wires Narrative QA yet. At minimum inspect source text to verify `app/cv/service.py` does not import `NarrativeQualityQA` and legacy `compose_recruiter_document` remains importable.

- [ ] **Step 3: Run final verification**

```bash
python -m pytest -q
python -m compileall app
git diff --check origin/main...HEAD
```

Repository CI must also pass recruiter preview generation and offline runtime build/verify on Python 3.12 and 3.13.

- [ ] **Step 4: Review the complete diff against the spec**

Reject the PR if it modifies service, renderer, CLI, packet schemas, private user data, or legacy composer behavior.

- [ ] **Step 5: Commit**

```text
test: prove narrative QA contract
```

---

## Acceptance checklist

- [ ] Narrative QA is renderer-independent.
- [ ] Every core message must retain visible support.
- [ ] Off-strategy editorial content is measured separately from structural chronology.
- [ ] Top-of-document competing identity signals are bounded.
- [ ] Generic language is surfaced as warnings without hallucinated interpretation.
- [ ] Headline re-checks strategy positioning and provenance.
- [ ] Ten-second scan proxy is deterministic and policy-gated.
- [ ] Unknown recruiter claim references fail closed.
- [ ] No recruiter-visible text is minted or rewritten.
- [ ] No service/renderer/CLI/ApplicationPacket behavior changes.
- [ ] Full test suite, compile, diff check, recruiter previews, and offline 3.12/3.13 verification pass.