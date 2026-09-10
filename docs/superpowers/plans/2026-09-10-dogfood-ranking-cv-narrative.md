# Dogfood Ranking & CV Narrative Amendment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop quantified experience uncertainty from creating false CAREER eliminations and preserve up to two provenance-backed narrative bullets for high-value CV entries.

**Architecture:** Keep eligibility unchanged. Refine requirement extraction and CAREER scoring so experience duration can be satisfied, partial, unknown, or unsupported without adding a new public API enum; represent the distinction through deterministic multipliers and explicit risks/gaps. Extend recruiter/narrative composition policy from one bullet to up to two, then make reduction remove lower-value content before the primary-project second bullet.

**Tech Stack:** Python 3.12+, Pydantic, PyYAML, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-10-dogfood-ranking-cv-narrative-design.md`

## Global Constraints

- Do not change eligibility hard-fail semantics.
- Do not invent or estimate candidate years.
- Unknown duration must not score as zero when verified relevant capability evidence exists.
- Preferred experience must never create a mandatory experience risk.
- Keep one-page/ATS/provenance QA intact.
- No new public recommendation enum.
- All CV bullets must already be validated and provenance-backed.

---

### Task 1: Requirement modality for numeric experience

**Files:**
- Modify: `tests/fixtures/radar_requirement_cases.yaml`
- Modify: `app/radar/extractor.py`

**Interfaces:**
- Consumes: `RuleBasedRequirementExtractor.extract(Opportunity)`.
- Produces: `Requirement(kind="experience", importance="mandatory"|"preferred", provenance=...)` with posting modality preserved.

- [ ] **Step 1: Add failing bilingual fixture cases** for `3+ years preferred`, `Ideally 3 years`, `3 años deseables`, `será un plus contar con 3 años`, `Minimum 3 years required`, and `mínimo 3 años excluyente`.
- [ ] **Step 2: Run** `python -m pytest tests/test_radar_extractor.py -v` and confirm failures are caused by missing/incorrect modality parsing.
- [ ] **Step 3: Extend preferred cue vocabulary** with `ideally`, `idealmente`, `preferentemente`, `a plus`, `desirable`, `valoramos`, plus common plural variants where needed. Preserve explicit mandatory cues.
- [ ] **Step 4: Make sentence parsing strip a trailing cue after a recognized leading cue** so values such as `Minimum 3 years required` normalize to the experience term rather than retaining helper words.
- [ ] **Step 5: Re-run extractor tests** and confirm all fixtures pass.
- [ ] **Step 6: Commit** with `fix(radar): preserve experience requirement modality`.

### Task 2: Non-binary experience support and CAREER ranking

**Files:**
- Modify: `tests/test_radar_dogfood_regressions.py`
- Modify: `tests/test_radar_ranking.py` only if ranking regression coverage needs a direct assertion.
- Modify: `app/radar/scoring.py`
- Modify: `app/radar/ranking.py`

**Interfaces:**
- Consumes: quantified `Requirement(kind="experience")` plus `CandidateTrack.evidence`.
- Produces internal support multiplier:
  - satisfied: `1.0`
  - partial: `min(evidenced_years / required_years, 1.0)`
  - unknown with relevant verified evidence: `0.5`
  - unsupported: `0.0`
- Produces risks: `experience_duration_unverified` for UNKNOWN mandatory duration and `experience_duration_below_posting` for PARTIAL mandatory duration.

- [ ] **Step 1: Replace the old regression that asserts a mandatory unverified duration caps CAREER at STRETCH** with a failing test asserting normal tier classification is preserved.
- [ ] **Step 2: Add failing tests** for partial verified duration (`2` vs `3` years), unknown duration with relevant verified project/experience evidence, unsupported experience, and preferred duration not emitting mandatory risks.
- [ ] **Step 3: Run** `python -m pytest tests/test_radar_dogfood_regressions.py tests/test_radar_ranking.py -v` and confirm expected failures.
- [ ] **Step 4: Introduce a focused internal experience support helper** in `app/radar/scoring.py` that examines only verified project/experience evidence, never sums overlapping durations, uses the maximum relevant explicit duration, and returns the deterministic multiplier/status.
- [ ] **Step 5: Update CAREER strengths/gaps/risks** so SATISFIED is a strength; PARTIAL and UNKNOWN remain gaps with explicit risks; UNSUPPORTED remains a gap. Preferred experience must not emit mandatory risks.
- [ ] **Step 6: Remove the ranking override** in `app/radar/ranking.py` that mutates HIGH/MEDIUM to STRETCH solely because `mandatory_experience_unverified` is present.
- [ ] **Step 7: Re-run targeted Radar tests** and then `python -m pytest -v`.
- [ ] **Step 8: Commit** with `fix(radar): treat experience duration as graded evidence`.

### Task 3: Preserve two provenance-backed CV bullets

**Files:**
- Modify: `tests/test_recruiter_composer.py`
- Modify/add the narrative composer regression test file that currently covers `compose_strategy_recruiter_document`.
- Modify: `app/cv/recruiter_policy.py`
- Modify: `config/recruiter_policy.yaml`
- Modify: `app/cv/recruiter_composer.py`
- Modify: `app/cv/narrative/composer.py`

**Interfaces:**
- `RecruiterPolicy.max_project_bullets: int` defaults/configures to `2`.
- `RecruiterPolicy.max_experience_bullets` accepts/configures up to `2`.
- Project/experience composition returns at most the configured number of unused provenance-overlapping ranked bullets.

- [ ] **Step 1: Add failing recruiter-composer tests** where one project and one experience entry each have two approved overlapping bullets; assert both are selected in deterministic order and an unrelated bullet is excluded.
- [ ] **Step 2: Add the equivalent failing strategy/narrative-composer test** to prove the newer strategy path preserves the same semantics.
- [ ] **Step 3: Run the targeted CV tests** and confirm they fail because only one bullet is currently returned.
- [ ] **Step 4: Extend `RecruiterPolicy`** with `max_project_bullets` (`0..2`, default `2`), widen `max_experience_bullets` to `0..2`, and set both to `2` in `config/recruiter_policy.yaml`.
- [ ] **Step 5: Change bullet association helpers** in both composer paths to collect up to the configured cap instead of returning/breaking after the first overlap. Continue respecting `used_bullets` and validated provenance.
- [ ] **Step 6: Re-run targeted CV composition tests** and confirm they pass.
- [ ] **Step 7: Commit** with `feat(cv): preserve project and experience narrative depth`.

### Task 4: Reduction priority and full verification

**Files:**
- Modify: `tests/test_recruiter_composer.py`
- Modify: `app/cv/recruiter_composer.py`

**Interfaces:**
- `reduce_recruiter_document(...)` remains deterministic and preserves the legacy `selected_project_claim_ids` mirror.

- [ ] **Step 1: Add failing reduction tests** proving that optional links, redundant skills, tertiary projects, lower-priority experience rows, and extra education are removed before the second bullet of the primary project; when bullet trimming is needed, trim secondary/lower-priority entries first.
- [ ] **Step 2: Run** `python -m pytest tests/test_recruiter_composer.py -v` and confirm the new reduction-order test fails.
- [ ] **Step 3: Extend `_reduce_once`** with deterministic secondary-bullet trimming after existing lower-value categories. Preserve at least one bullet per entry and make the primary-project second bullet the last narrative-depth fallback.
- [ ] **Step 4: Re-run targeted tests** and confirm pass.
- [ ] **Step 5: Run full verification:** `python -m pytest -v`, `python -m compileall app`, `git diff --check origin/main...HEAD`, and the existing recruiter preview render job through GitHub Actions.
- [ ] **Step 6: Inspect the PR diff** for unintended API/schema changes and confirm no private/generated files are tracked.
- [ ] **Step 7: Commit** with `test: lock dogfood ranking and CV narrative regressions` if any final test-only adjustments are needed.
