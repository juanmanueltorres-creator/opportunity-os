# Opportunity OS Offline Runtime Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify SHA-bound offline runtime artifacts that can install Opportunity OS and execute the canonical RenderCV/Typst recruiter pipeline without package-network access.

**Architecture:** Keep application semantics unchanged. Add build/verification scripts that assemble a public source subset plus a complete wheelhouse containing the prebuilt Opportunity OS wheel and the platform-specific typst-py compiler wheel, then validate each artifact in a second clean CI job using `PIP_NO_INDEX=1`. The runtime is immutable infrastructure keyed to the exact git SHA and Python minor; private candidate inputs remain external.

**Tech Stack:** Python 3.12/3.13, Bash, pip/wheel, RenderCV 2.x, typst-py, PyMuPDF, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-30-opportunity-os-offline-runtime-bundle-design.md`

## Global Constraints

- Canonical renderer remains RenderCV/Typst; no ATS/ReportLab fallback.
- Runtime artifacts target Linux x86_64 for Python 3.12 and Python 3.13.
- Runtime manifest is bound to the exact git SHA and Python minor.
- Offline bootstrap must use `PIP_NO_INDEX=1` and bundled wheels only.
- The Typst compiler runtime is the `typst` Python wheel actually used by RenderCV 2.8; do not introduce an unrelated external CLI compiler path.
- Private/local inputs and real generated CVs must never enter the artifact.
- Existing application/evidence/outreach semantics remain unchanged.

---

### Task 1: Runtime manifest and privacy contract

**Files:**
- Create: `scripts/runtime_bundle.py`
- Create: `tests/test_runtime_bundle.py`

**Interfaces:**
- Produces: `build_runtime_manifest(root: Path, git_sha: str, built_at: str) -> dict[str, object]`
- Produces: `validate_bundle_source_paths(paths: Iterable[Path]) -> None`
- Produces: `write_sha256sums(root: Path, output_path: Path) -> None`

- [x] **Step 1: Write failing tests** asserting the manifest contains schema/git/python/platform/RenderCV/Typst/PyMuPDF/renderer fields and that `.env`, `*.local.yaml`, `artifacts/applications/**`, PDF/DOCX and local SQLite paths are rejected.
- [x] **Step 2: Run** the tests and confirm RED because the module does not exist.
- [x] **Step 3: Implement minimal deterministic manifest/checksum/privacy helpers.**
- [x] **Step 4: Run** the full CI suite and confirm GREEN after fixing dotfile normalization.
- [x] **Step 5: Commit** the runtime manifest contract.

### Task 2: Build the offline bundle

**Files:**
- Modify: `scripts/runtime_bundle.py`
- Create: `scripts/build_offline_runtime.sh`
- Test: `tests/test_runtime_bundle.py`

**Interfaces:**
- Produces bundle root with `source/`, `wheelhouse/`, `runtime_manifest.json`, `SHA256SUMS`, `bootstrap_offline.sh` and a Python-minor-specific ZIP artifact.

- [x] **Step 1: Add RED tests** for source allow-listing, required fictional fixture inclusion and project-wheel/typst-wheel discovery.
- [x] **Step 2: Confirm RED** before source/wheel helpers existed.
- [x] **Step 3: Implement source copying** for public `app/`, `config/`, `data/`, `scripts/`, `pyproject.toml`, and only the two recruiter fictional fixtures; reject private/generated paths and ignore Python cache files.
- [x] **Step 4: Implement build shell script** that builds the project wheel from the exact SHA, resolves/downloads all binary-compatible dependencies into `wheelhouse`, requires a Linux x86_64 typst-py wheel, writes manifest/checksums and archives the runtime.
- [x] **Step 5: Confirm builder works for Python 3.12 and 3.13 in CI.**
- [x] **Step 6: Publish the matrix artifacts with 90-day retention.**

### Task 3: Offline bootstrap and recruiter smoke test

**Files:**
- Create: `scripts/bootstrap_offline_runtime.sh`
- Create: `scripts/verify_offline_runtime.py`
- Modify: `tests/test_runtime_bundle.py`

**Interfaces:**
- `bootstrap_offline_runtime.sh <bundle-root> <expected-git-sha>` verifies checksums/SHA/Python, creates `.venv`, installs the project wheel from wheelhouse with no index, verifies installed versions and invokes `verify_offline_runtime.py`.
- `verify_offline_runtime.py` renders fictional recruiter fixtures through the canonical renderer and `RecruiterQualityQA` and checks A4/text/URI annotations.

- [x] **Step 1: Add RED tests** for checksum/SHA/no-index bootstrap and A4/text/link verification.
- [x] **Step 2: Confirm RED** because bootstrap/verifier files did not exist.
- [x] **Step 3: Implement bootstrap** with strict `set -euo pipefail`, checksum verification before execution, manifest SHA binding, Python-minor binding, isolated venv and local-wheel-only installation.
- [x] **Step 4: Verify installed Opportunity OS, RenderCV, typst-py, PyMuPDF and renderer versions against the manifest.**
- [x] **Step 5: Implement fictional recruiter verification** reusing the checked-in preview path and canonical QA; assert exactly one A4 page, selectable text and email/web URI annotations.
- [x] **Step 6: Confirm normal suite GREEN with 523 tests.**

### Task 4: Two-stage GitHub Actions acceptance

**Files:**
- Modify: `.github/workflows/tests.yml`

**Interfaces:**
- `build-offline-runtime` matrix uploads py312 and py313 artifacts.
- `verify-offline-runtime` matrix downloads only the matching artifact and runs its bootstrap on a fresh runner, with pip cache disabled and `PIP_NO_INDEX=1`.

- [x] **Step 1: Add build matrix** after normal pytest checks and upload both ZIPs with 90-day retention.
- [x] **Step 2: Add dependent clean verification matrix** using fresh runners and artifact download only.
- [x] **Step 3: Ensure no online package-install commands exist in verification jobs**; setup-python only supplies the requested interpreter.
- [x] **Step 4: Use the first matrix failure to fix ephemeral `__pycache__` handling rather than weakening acceptance.**
- [x] **Step 5: Confirm py312 build, py313 build, py312 offline verify and py313 offline verify all GREEN.**

### Task 5: Agent runbook

**Files:**
- Modify: `docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md`

**Interfaces:**
- Documents deterministic offline execution and fail-closed behavior.

- [x] **Step 1: Add runtime-artifact section** covering Python-minor selection, exact git SHA binding, checksum verification, offline bootstrap and later private input materialization.
- [x] **Step 2: State explicit prohibition** on manual recruiter PDF reconstruction, obsolete packet reuse and renderer fallback when no matching runtime exists.
- [ ] **Step 3: Run final documentation/privacy checks and full suite on the final branch head.**

### Task 6: Final verification and PR

**Files:** none beyond prior tasks.

- [ ] **Step 1: Run full GitHub Actions suite** on the final branch head.
- [ ] **Step 2: Confirm normal tests, compile, whitespace, private-file guard, recruiter previews, py312/py313 runtime build and clean offline verification all pass.**
- [ ] **Step 3: Inspect branch diff against `main` for scope leakage.**
- [ ] **Step 4: Open PR against `main` with exact head SHA and acceptance evidence.**
