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
- T3 formatting check: `git diff --check` — exit 0, no output.
- T3 local preview: served with `python -m http.server 4173 --directory site`; `browser.mjs http://localhost:4173/ --script <temporary content-based QA script>` returned HTTP 200, 275 results, 111 company rows, and 30 rendered vacancy cards. Console errors/warnings: 0; failed requests: 0. Browser interaction check: metadata query `GIS` returned 5 companies; selecting RYZ Labs showed 20 results and every existing vacancy card matched; the no-coordinates state appeared; source links were HTTPS with `rel="noopener noreferrer"`; reset restored 275 results.
- Native RDD assessment: `gentle-ai review assess --cwd <repo> --agent codex --base-ref a07614248d2fb0904c5784d1f89f22b520cd5a4a --committed-only --json` with the explicit pre-existing-untracked exclusion returned `risk=medium`, `changed_paths=4`, `changed_lines=316`, `review_due=false`, `review_due_reason=under_budget`. The `.atl/` inventory was excluded and left untouched; the medium slice remains pending for the next delivery-boundary assessment.
- Work-unit commit: `feat(site): add feed-derived company directory` (final commit SHA is included in the delivery handoff).

## Next step
Next: mirror this full progress document to Engram. No source implementation remains for T1–T3.
