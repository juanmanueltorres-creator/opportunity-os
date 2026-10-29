# Real applications mode
Authorized: local implementation only; preserve design, data and connectors. No submission, upload, push, merge or deploy.
Route: single bounded writer explicitly requested. TDD: enabled for new behavior; runner .venv/Scripts/python.exe -m pytest.
Delivery: ask-on-risk; initial bounded classification increment below 400 lines.
- [ ] R1 Add conservative evidence classification and regression tests.
- [ ] R2 Integrate public requirements and source prioritization.
- [ ] R3 Connect private local CV generation and validate PDF links.
- [ ] R4 Observe real collection and browser application flow; run full tests.
Acceptance: A-F from user request require observed real evidence; no invented shortlist.
Current: implementation starting; all live/PDF/browser proof pending.
Rollback: remove classification helper and its export fields/tests only.

## Recovery and observed progress (2026-10-29)
- R1 partial: conservative classifier integrated; original three tests pass. No official-link checker yet, so no apply-now claims.
- R2 partial: fixed dropped description in JobMatch.as_public_dict; strips scripts/styles/markup, adds explicit unknown requirement fields. Existing generated feed predates this export change and must be regenerated. No UI files changed.
- R3 partial: python -m app.application.selected_job --feed <jobs.json> --job-id <id> inspects real row. Optional --assessment --master-facts --evidence-catalog hands off to existing prepare/CVPreparationService, requiring exact ID/URL match and ignored private output root. Does not manufacture an assessment or facts. Only config/master_facts.example.yaml located; no actual private verified profile established. No PDF generated or verified.
- R4 partial: recovered completed unrestricted collector log: Sources=24 jobs=973 atlas=274 shortlist=33 db=NOT_CONFIGURED. These counts do not prove 33 apply-now jobs. Existing real selected 23people Java row is EXPLORAR, unknown requirements in old feed. Browser launch initially blocked EPERM; elevated retry pending.

## Verification
- New RED observed: missing public_requirements module; then 2 tests GREEN.
- New RED observed: missing selected_job module; then selection test GREEN.
- Focused combined: 6 passed (readiness, public requirements, selection).
- git diff --check passed.
- Previous full suite log: 1562 passed, 7 failed. Exact failures:
  tests/test_api_radar.py::test_radar_run_requires_candidate_profile
  tests/test_api_target_radar.py::test_target_radar_requires_profile
  tests/test_contribution_intake_release_contract.py::test_pyproject_is_unchanged_in_feature_diff
  tests/test_gemini_shortlist_ux.py::test_public_gemini_briefing_has_no_private_password_or_api_call
  tests/test_gemini_shortlist_ux.py::test_browser_script_and_csp_remain_valid
  tests/test_runtime_bundle.py::test_runtime_manifest_is_sha_bound_and_records_renderer_runtime
  tests/test_runtime_bundle.py::test_manifest_is_json_serializable
No base comparison establishes pre-existing causality.
RDD status on (default). No review approval/commit claimed.
Next: regenerate feed with preserved descriptions; verify source diagnostics; add safe assessment/profile selection bridge and link checker; generate real PDF only with verified private facts; finish browser proof and applicable regression tests. A-F NOT complete. No submission/upload/push/merge/deploy.

## Latest observed evidence
Elevated regeneration completed successfully: 973 jobs, 274 atlas rows. Categories: 128 REVISAR, 146 EXPLORAR, zero POSTULAR AHORA. Source statuses in artifacts/daily-radar/jobs.json include Get on Board (7 categories), Muttdata, RYZ Labs, Canals, G2i, Squad, Ardent and other preserved international sources. Public description recovered: 23people Java/ETL row explicitly includes Java, SQL, ETL and basic/technical English requirements; no compatibility inferred.
Browser proof: Playwright/patchright opened the exact Get on Board vacancy, HTTP 200, title matched and Apply now link visible. No submission or sign-in performed. This is an exploratory role, NOT proof of suitable priority application.
Focused regression rerun: 22 passed in 1.54s. No PDF generated: verified private inputs and matching assessment still required; example fixtures must not impersonate candidate facts. No complete browser-to-CV flow claimed.
Review preflight succeeded elevated after denied access; asks for intended-untracked selection. No frozen review or approval, no commit. Implementation remains partial and uncommitted.
