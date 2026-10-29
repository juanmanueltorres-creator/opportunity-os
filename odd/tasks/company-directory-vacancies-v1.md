# Opportunity OS — Company directory with linked vacancies

## Objective
Deliver the first functional exploration increment: a public, feed-derived company directory where every displayed company links to the same real vacancies already rendered by Opportunity OS.

## Problem
The current radar presents vacancies and sources, but it does not provide a company-first way to discover employers, inspect vacancy counts, or narrow the existing vacancy list without risking invented company records or locations.

## Scope
- Keep the existing static public radar, source links, ranking, persistence, application history, CV pipeline, and privacy boundaries intact.
- Derive display-only company groups from the public vacancy feed; do not add a canonical company database in this increment.
- Add search and evidence-bound filters for sector/technology/specialty signals already present in vacancy metadata.
- Add company detail/navigation that filters the existing vacancy list to the selected company and preserves official source links.
- Add a verified-location map surface only when the feed already contains verified coordinates; otherwise show an explicit no-coordinates state rather than a decorative or invented map.
- Do not add Gemini, CV generation, automatic application submission, production changes, or PR #114 merge/copy.

## Constraints
- Authorized branch: `feat/atlas-empresas-local-v1`.
- Public information stays separate from private applications, contacts, and CV data.
- UI artifacts default to English in source, but the existing product is Spanish; user-facing copy extends the existing Spanish interface.
- Visual direction: editorial/cartographic, dark, compact, evidence-labeled; avoid infinite card grids and decorative geography.
- Route: delegated direct. Mapping trigger fired because understanding crossed 4 files; writer trigger fired because implementation spans the static frontend and tests.

## Effective checks
- `python -m pytest -q tests/test_public_snapshot.py tests/test_api_opportunities.py tests/test_target_registry.py tests/test_target_relationship_integration.py`
- `python -m http.server 4173 --directory site` and inspect `http://localhost:4173/` locally.
- `git diff --check`

## Checklist
- [x] T1 — Add a tested, feed-derived company grouping/navigation model in the static frontend without changing persistence.
- [x] T2 — Implement the editorial company directory and linked vacancy navigation, with explicit evidence/empty states and no invented locations.
- [x] T3 — Run focused/full checks and local preview verification; record actual results.

## Acceptance criteria
- Company entries are derived only from current real vacancy records and expose vacancy counts.
- Search/filtering can find company or metadata signals and selecting a company filters the existing vacancy cards.
- Official vacancy links remain available and the UI labels vacancy location separately from company headquarters.
- No public UI reads private application/contact/CV data.
- Existing tests remain green or any unrelated baseline failures are reported by name.

## Progress
- Audit complete; PR #114 inspected read-only and remains open/unmerged.
- T1: Added `site/company-directory.js`, a pure display-only grouping, metadata search, selection, coordinate-state, and HTTPS source-link model. Company counts are computed from the public vacancy records; no persistence or private data was added.
- T2: Added a compact company-first directory to `site/index.html`. Search matches company names and existing vacancy metadata; selecting a company narrows the existing opportunity list and detail pane, with a reset control. Detail labels identify vacancy location only and show no-map copy when verified coordinates are absent.
- T3 focused tests: `node tests/test_company_directory.mjs` — 6 passed, 0 failed. TDD RED was observed first (5 missing-module assertion failures); an additional regression test exposed null coordinates being coerced to zero, which was fixed and reverified.
- T3 audit suite: `python -m pytest -q tests/test_public_snapshot.py tests/test_api_opportunities.py tests/test_target_registry.py tests/test_target_relationship_integration.py` — 15 passed in 7.53s.
- T3 full suite spot check: `python -m pytest -q` — collection blocked by 17 pre-existing `ModuleNotFoundError: No module named 'pypdf'` errors in CV/recruiter/application tests; no company-directory test failure was observed. The environment also emitted existing unknown `pytest.mark.asyncio` warnings.
- T3 formatting check: `git diff --check` — exit 0, no output.
- T3 local preview: served with `python -m http.server 4173 --directory site`; `browser.mjs http://localhost:4173/ --script <temporary content-based QA script>` returned HTTP 200, 275 results, 111 company rows, and 30 rendered vacancy cards. Console errors/warnings: 0; failed requests: 0. Browser interaction check: metadata query `GIS` returned 5 companies; selecting RYZ Labs showed 20 results and every existing vacancy card matched; the no-coordinates state appeared; source links were HTTPS with `rel="noopener noreferrer"`; reset restored 275 results.
- Native RDD assessment: `gentle-ai review assess --cwd <repo> --agent codex --base-ref a07614248d2fb0904c5784d1f89f22b520cd5a4a --committed-only --json` with the explicit pre-existing-untracked exclusion returned `risk=medium`, `changed_paths=4`, `changed_lines=316`, `review_due=false`, `review_due_reason=under_budget`. The `.atl/` inventory was excluded and left untouched; the medium slice remains pending for the next delivery-boundary assessment.
- Work-unit commit: `feat(site): add feed-derived company directory` (final commit SHA is included in the delivery handoff).
- Follow-up CSP correction: post-commit audit confirmed `index.html` loads `./company-directory.js` while Vercel's `script-src 'unsafe-inline'` omitted `'self'`. Added a regression test first; RED showed the exact CSP mismatch. Updated only `script-src` to `'self' 'unsafe-inline'`; `default-src`, `connect-src`, `style-src`, `base-uri`, `object-src`, and `frame-ancestors` remain unchanged. Focused tests: `node tests/test_company_directory.mjs` — 7 passed, 0 failed. `git diff --check` — exit 0, no output.
- Follow-up commit: `fix(site): allow same-origin company directory script` (final SHA will be included in the delivery handoff).
- Follow-up native assessment: `risk=medium`, `review_due=false`, `review_due_reason=under_budget` against the same `a07614248d2fb0904c5784d1f89f22b520cd5a4a` boundary; pre-existing `.atl/` remained excluded and untouched.

## Continuation scope — Empresas workspace

The next authorized increment keeps the same public feed and display-only company model, but promotes Empresas to the primary workspace:

- Default mode: `Trabajo ahora · Español`.
- Alternate mode: `Explorar todo`.
- Three-column layout: compact company index, selected company record, and linked public vacancies.
- Vacancies requiring advanced English must stay out of the prioritized/default view, while remaining discoverable in `Explorar todo`.
- Remove manual application-follow-up/CRM controls from this public workspace; preserve source links and the existing backend/data boundaries.

## Continuation checklist

- [x] T4 — Add the Spanish-first/default and Explore-all filtering contract to the display-only model with tests.
- [x] T5 — Replace the stacked directory/feed presentation with a responsive three-column Empresas workspace.
- [x] T6 — Run focused/full checks and Playwright validation; record actual results.

## Continuation progress

- T4: Added `buildWorkspace`, `isSpanishFirstVacancy`, and explicit `WORK_NOW_MODE` / `EXPLORE_ALL_MODE` exports in `site/company-directory.js`. The default keeps explicit Spanish work and Spanish listings with unknown work language; `EN` and `BILINGUAL` stay out of the default. `Explorar todo` retains every public record.
- T5: Replaced the stacked directory/feed with a responsive three-column workspace in `site/index.html`: compact company index, evidence-labeled company profile, and linked vacancy cards. The selected company now filters the third column. Removed manual application status controls, local follow-up storage, and CSV follow-up export from the public workspace; Gemini remains an optional public-data briefing action.
- T6 focused checks: `node tests/test_company_directory.mjs` — 9 passed; `node tests/test_company_workspace.mjs` — 2 passed; `git diff --check` — exit 0.
- T6 Playwright: local `python -m http.server 4173 --directory site` plus browser-automation script returned HTTP 200, 0 console errors/warnings, 0 failed requests. Default mode rendered `39 EMPRESAS · 68 VACANTES`; Explore-all rendered `111 EMPRESAS · 275 VACANTES`; selecting BC Tecnología rendered 6 linked company cards and 6 official HTTPS links; returning to default cleared the selection.
- T6 full pytest: delegated run observed 1,559 passed and 7 failures outside the restricted sandbox; the failures were pre-existing/environment-specific (API profile expectations, a prior `pyproject.toml` baseline comparison, Windows encoding, and Linux x86_64 assumptions). The restricted run additionally hit temporary-directory permission errors while tests ran concurrently; no failure implicated the static workspace files.

## Next step
Implement T4, then T5, then verify T6. Keep this document and its Engram mirror synchronized after each task.
