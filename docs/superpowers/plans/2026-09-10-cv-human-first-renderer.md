# Human-First CV Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the optional second CV renderer from the approved CV architecture without changing narrative composition, candidate evidence, production renderer selection, or ApplicationPacket behavior.

**Architecture:** Introduce a deterministic ReportLab renderer that consumes the existing `RecruiterDocumentModel`, `CVDocumentModel`, `RecruiterPolicy`, and `LayoutProfile`. It resolves only already-selected claim IDs and converts them into a restrained one-column human-first PDF. RenderCV/Typst remains the production/default renderer; this PR adds an interchangeable adapter and proves it satisfies the existing structural, visual, and ATS-recoverability QA contracts.

**Tech Stack:** Python 3.12+, ReportLab 4.2+, PyMuPDF, pypdf, Pydantic, pytest.

**Spec:** `docs/superpowers/specs/2026-09-09-cv-strategy-narrative-design.md` — PR 8, Optional second renderer.

## Global Constraints

- Consume the existing `RecruiterDocumentModel` and `LayoutProfile`.
- Do not create a duplicate content-composition path: renderer may only resolve and display claim IDs already selected by the recruiter document.
- Do not modify `CVPreparationService`, `ApplicationPacket`, recruiter/narrative composition, reduction policy, Radar ranking, or evidence/provenance semantics in this PR.
- Keep RenderCV/Typst as the default production renderer.
- Preserve deterministic output for identical inputs.
- Use one-column ATS-safe rendering; no photos, charts, skill bars, icons, or decorative constructs that alter extraction order.
- Add no new package dependency; `reportlab>=4.2` is already part of the project runtime.
- Shared QA means existing structural Recruiter QA, Visual QA, and ATS round-trip recoverability QA.

---

### Task 1: Freeze the interchangeable renderer contract

**Files:**
- Modify: `app/cv/renderers/base.py`
- Create: `tests/test_cv_human_first_renderer.py`

**Interfaces:**
- Consumes: `RecruiterDocumentModel`, `CVDocumentModel`, `RecruiterPolicy`, `LayoutProfile`.
- Produces: a `RecruiterRenderer.render(..., layout_profile: LayoutProfile) -> RecruiterRenderResult` protocol compatible with both RenderCV/Typst and the new renderer.

- [ ] **Step 1: Write failing contract tests**

Create tests that import `ReportLabHumanRenderer`, render the existing synthetic recruiter fixture, require a one-page extractable PDF, require all recruiter-selected claim text to survive extraction, and require identical inputs to produce identical bytes/hash.

- [ ] **Step 2: Run tests and verify RED**

Run the full GitHub Actions suite on the test-only commit. Expected: the new tests fail because `app.cv.renderers.reportlab_human` / `ReportLabHumanRenderer` does not yet exist; unrelated tests remain green.

- [ ] **Step 3: Align the base protocol**

Add `layout_profile: LayoutProfile` to `RecruiterRenderer.render(...)`. This is a typing/interface correction only; do not change service wiring.

- [ ] **Step 4: Re-run focused/full tests**

Expected: tests remain RED only for the missing concrete second renderer.

- [ ] **Step 5: Commit**

Commit the contract/test slice separately from production implementation.

---

### Task 2: Implement the deterministic ReportLab human-first renderer

**Files:**
- Create: `app/cv/renderers/reportlab_human.py`
- Optionally modify: `app/cv/renderers/__init__.py` only to export the concrete renderer.
- Test: `tests/test_cv_human_first_renderer.py`

**Interfaces:**
- Class: `ReportLabHumanRenderer`
- Version: `renderer_version = "reportlab-human-v1"`
- Signature: `render(recruiter_document, source_document, output_path, policy, layout_profile) -> RecruiterRenderResult`

- [ ] **Step 1: Resolve visible content strictly by claim ID**

Build `claims_by_id` from `source_document.claims`; every ID referenced by `recruiter_document.all_claim_ids()` must resolve or raise `ValueError`. Never derive new recruiter-facing claim wording from the posting or source document outside those selected IDs.

- [ ] **Step 2: Build one-column sections in recruiter-document order**

Render identity/headline/contact, profile, grouped technology, projects, experience, education, languages, and links. Project/experience loops must iterate every `bullet_claim_id` rather than assume a one-bullet ceiling, so the renderer remains compatible with later narrative-depth changes.

- [ ] **Step 3: Apply presentation-only LayoutProfile differences**

Use `density` and `emphasis` to choose deterministic font sizes/spacing and section emphasis. `compact_ats` stays most conservative; `technical_clean` gives technical/project hierarchy; `operations_clean` gives experience hierarchy. No profile may change selected claim IDs or textual order inside a section.

- [ ] **Step 4: Make PDF bytes deterministic**

Use ReportLab invariant/deterministic canvas metadata, fixed layout values, and no current timestamps/random IDs. Hash the emitted bytes with SHA-256 into `RenderedCVArtifact`.

- [ ] **Step 5: Measure renderer output**

Return `RecruiterRenderMetrics` with the actual configured body font size, deterministic headline line count, and overflow/page-count derived from the rendered artifact rather than guessed from input length.

- [ ] **Step 6: Run tests and verify GREEN**

The renderer contract tests must pass; then run the full suite before proceeding.

- [ ] **Step 7: Commit**

Commit the minimal concrete renderer implementation.

---

### Task 3: Prove the second renderer satisfies shared QA

**Files:**
- Modify: `tests/test_cv_human_first_renderer.py`

**Interfaces:**
- Uses existing `RecruiterQualityQA`, `VisualQualityQA`, `LocalResumeParser`, `ATSRoundTripQA`, and versioned policies from `config/`.

- [ ] **Step 1: Add shared-QA regression tests**

For representative synthetic/golden recruiter documents, render with `ReportLabHumanRenderer` and assert structural Recruiter QA passes, Visual QA passes under the selected layout profile, and ATS round-trip QA passes for identity/contact/experience/critical-skills/education/links.

- [ ] **Step 2: Add layout-profile invariants**

Render the same recruiter/source document with all three profiles. Assert extracted selected claim text remains equivalent while output bytes may differ due to presentation. Ensure no unselected source claim appears merely because it exists in `CVDocumentModel`.

- [ ] **Step 3: Verify multi-bullet forward compatibility**

Construct a local test model (when the model contract permits it) with multiple project/experience bullets and assert renderer iteration preserves every referenced bullet in order. If the current model still caps one bullet, keep the renderer implementation list-based and defer only this assertion until the dogfood branch lands; do not weaken or modify `RecruiterProjectEntry`/`RecruiterExperienceEntry` here.

- [ ] **Step 4: Run complete CI**

Require pytest, compile, whitespace/private-file guards, recruiter previews, and offline-runtime build/verification on Python 3.12 and 3.13.

- [ ] **Step 5: Open a draft PR only**

Open PR8 against `main` with explicit note that production selection is unchanged and that the branch must be resynced/revalidated after the dogfood narrative branch lands before any merge.
