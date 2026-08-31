# Opportunity OS V0.2F Language Decision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make application language deterministic, auditable, and consistent across canonical CV preparation, outreach briefs, and Gmail draft snapshots.

**Architecture:** Add a pure deterministic language resolver in `app/radar/language.py`, persist its `LanguageDecision` in `ApplicationPacket`, and propagate that decision through CV composition and outreach. Draft registration adds a fail-closed invariant for declared language plus a conservative lexical safety check over subject/body.

**Tech Stack:** Python 3.12/3.13, Pydantic v2, pytest, RenderCV/Typst, PyMuPDF.

**Spec:** `docs/superpowers/specs/2026-08-31-opportunity-os-v0.2f-language-decision-design.md`

## Global Constraints

- Supported output languages are exactly `es` and `en`.
- Canonical CLI accepts `--language auto|es|en`; default is `auto`.
- No LLM language classifier, machine translation, or new runtime dependency.
- Company nationality is never an automatic language signal.
- `English required` alone must not flip otherwise Spanish outreach to English.
- `ApplicationPacket` is the canonical language source after `PREPARED`.
- Clear language contradictions fail closed; ambiguous text does not.
- No changes to scoring, contact resolution, approval semantics, send gates, or recruiter PDF layout policy.
- Offline runtime verification must remain exact-SHA and index-free.

---

### Task 1: Deterministic Language Resolver

**Files:**
- Create: `app/radar/language.py`
- Modify: `app/radar/models.py`
- Create: `tests/test_radar_language.py`

**Interfaces:**
- Produces: `LanguageDecision`, `resolve_output_language(assessment, override=None)`, `detect_text_language(text)`.
- Consumes: `RadarAssessment`, `Opportunity.title`, `Opportunity.description`, enrichment country/region, opportunity location.

- [ ] **Step 1: Write failing resolver/model tests**

Cover: Canals-like English posting, Spanish Argentina posting, ambiguous technical Argentina posting, ambiguous international remote fallback, ES/EN overrides, and Spanish posting containing `English required`.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_radar_language.py`

Expected: FAIL because `LanguageDecision` / resolver do not exist.

- [ ] **Step 3: Implement minimal resolver**

Add the exact model types from the spec and frozen lexical/market constants. Normalize Unicode/case/punctuation, count only frozen recruiting markers, apply the documented `>=3 hits` and `>=2 lead` threshold, then market fallback and English fallback.

- [ ] **Step 4: Run GREEN**

Run: `pytest -q tests/test_radar_language.py tests/test_radar_models.py`

Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -am "feat: add auditable language resolver"` plus new files.

---

### Task 2: Canonical CV Preparation and Packet Propagation

**Files:**
- Modify: `app/application/prepare.py`
- Modify: `app/cv/models.py`
- Modify: `app/cv/service.py`
- Modify: `tests/test_application_prepare_cli.py`
- Modify: `tests/test_cv_service.py`
- Modify focused packet-construction tests/fixtures that require the new model field.

**Interfaces:**
- Consumes: `LanguageDecision` from Task 1.
- Produces: required `language_decision` on `ApplicationPacket`; CLI `--language auto|es|en`; response fields `language` and `language_basis`.

- [ ] **Step 1: Write failing service/CLI tests**

Test that Spanish/English decisions drive `packet.cv_document.language`, packet hash changes when the decision changes, CLI auto resolves language, CLI override wins, and invalid CLI values are rejected.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_cv_service.py tests/test_application_prepare_cli.py`

Expected: FAIL on missing packet field/CLI argument/propagation.

- [ ] **Step 3: Implement minimal propagation**

Add `language_decision: LanguageDecision` to `ApplicationPacket`; require it in `CVPreparationService.prepare`; pass `language=language_decision.language` to `compose_cv`; include serialized decision in `_packet_content_payload`; change CLI policy factory to structural-only language placeholder and pass the resolved decision explicitly; add CLI output metadata.

- [ ] **Step 4: Run GREEN**

Run: `pytest -q tests/test_cv_service.py tests/test_application_prepare_cli.py tests/test_cv_models.py`

Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -am "feat: propagate language decision through application packet"`

---

### Task 3: Outreach and Draft Language Safety

**Files:**
- Modify: `app/outreach/models.py`
- Modify: `app/outreach/hashing.py`
- Modify: `app/outreach/preparation.py`
- Modify: `app/outreach/draft.py`
- Modify: `app/outreach/service.py`
- Modify: `tests/test_outreach_preparation.py`
- Modify: `tests/test_outreach_draft.py`
- Modify: `tests/test_outreach_service.py`
- Modify focused outreach model/repository/release tests that construct `DraftSnapshot` or `ApplicationPacket`.

**Interfaces:**
- Consumes: packet language decision and `detect_text_language`.
- Produces: required `DraftSnapshot.language`; `register_draft(..., language=...)`; errors `packet_language_mismatch`, `draft_language_mismatch`, `draft_text_language_mismatch`.

- [ ] **Step 1: Write failing outreach tests**

Cover brief inheritance, packet/CV mismatch blocking, declared draft mismatch, Spanish body falsely declared EN, valid English body, ambiguous technical body, and draft hash sensitivity to language.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_outreach_preparation.py tests/test_outreach_draft.py tests/test_outreach_service.py`

Expected: FAIL on missing invariants and field.

- [ ] **Step 3: Implement minimal safety contract**

Build brief language from `application_packet.language_decision.language`, validate CV/packet consistency, add language to `DraftSnapshot` and draft semantic hash, require declared language in registration, and reject confident lexical mismatch before persistence.

- [ ] **Step 4: Run GREEN**

Run: `pytest -q tests/test_outreach_preparation.py tests/test_outreach_draft.py tests/test_outreach_service.py tests/test_outreach_models.py tests/test_outreach_repository.py`

Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -am "feat: enforce outreach language consistency"`

---

### Task 4: Offline Runtime, Runbook, and Release Verification

**Files:**
- Modify: `scripts/verify_offline_runtime.py`
- Modify: `tests/test_offline_runtime_prepare_contract.py`
- Modify: `tests/test_runtime_bundle.py` only if directly required by verifier contract.
- Modify: `docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md`
- Modify any remaining focused test fixtures for strengthened packet/draft schemas.

**Interfaces:**
- Consumes: CLI language metadata and packet decision.
- Produces: offline verifier assertion `packet.language_decision.language == packet.cv_document.language` and documented agent language policy.

- [ ] **Step 1: Write failing offline contract test**

Require verifier/source contract to check CLI language fields and packet/CV invariant.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_offline_runtime_prepare_contract.py tests/test_runtime_bundle.py`

Expected: FAIL until verifier contract is updated.

- [ ] **Step 3: Implement verifier/runbook changes**

Extend verifier without network/dependency changes. Document auto precedence, override semantics, and fail-closed draft mismatch behavior.

- [ ] **Step 4: Run focused GREEN**

Run: `pytest -q tests/test_offline_runtime_prepare_contract.py tests/test_runtime_bundle.py`

Expected: PASS.

- [ ] **Step 5: Run full local verification**

Run: `pytest -q`

Then: `python -m compileall -q app scripts tests`

Expected: full suite PASS and compile PASS.

- [ ] **Step 6: Commit**

`git commit -am "test: verify language contract in offline runtime"`

---

### Task 5: PR and CI Gate

**Files:** no new production behavior.

**Interfaces:** branch `feat/v0.2f-language-decision` → `main`.

- [ ] **Step 1: Review diff against spec**

Run: `git diff main...HEAD --check` and inspect `git diff --stat main...HEAD`.

- [ ] **Step 2: Push branch and open PR #18**

Title: `feat: add auditable application language decision`

PR body must include RED/GREEN evidence, exact precedence, safety invariants, no-new-dependency statement, and runtime acceptance.

- [ ] **Step 3: Wait for all CI jobs**

Require pytest, compile/whitespace/privacy checks, recruiter previews, offline runtime build py312/py313, and offline verifier py312/py313 to succeed.

- [ ] **Step 4: Review PR feedback and re-run verification after any change**

No merge with unresolved correctness feedback.

- [ ] **Step 5: Merge only after green CI**

After merge, verify the new `main` workflow and exact-SHA offline artifact before using it for future production application runs.
