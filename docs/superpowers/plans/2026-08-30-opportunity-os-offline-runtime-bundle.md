# Opportunity OS Offline Runtime Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a SHA-bound offline runtime artifact that can install Opportunity OS and execute the canonical RenderCV/Typst recruiter pipeline without package-network access.

**Architecture:** Keep application semantics unchanged. Add build/verification scripts that assemble a public source subset plus a complete wheelhouse containing the prebuilt Opportunity OS wheel and the platform-specific typst-py compiler wheel, then validate the artifact in a second clean CI job using `PIP_NO_INDEX=1`. The runtime is immutable infrastructure keyed to the exact git SHA; private candidate inputs remain external.

**Tech Stack:** Python 3.12, Bash, pip/wheel, RenderCV 2.x, typst-py, PyMuPDF, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-30-opportunity-os-offline-runtime-bundle-design.md`

## Global Constraints

- Canonical renderer remains RenderCV/Typst; no ATS/ReportLab fallback.
- Python runtime target is exactly major/minor 3.12 for the first bundle format.
- Runtime artifact target is Linux x86_64.
- Runtime manifest is bound to the exact git SHA.
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
- [x] **Step 2: Run** `python -m pytest tests/test_runtime_bundle.py -v` and confirm RED because the module does not exist.
- [x] **Step 3: Implement minimal deterministic manifest/checksum/privacy helpers** using stdlib plus installed package metadata.
- [x] **Step 4: Run** the full CI suite and confirm GREEN after fixing dotfile normalization.
- [x] **Step 5: Commit** the runtime manifest contract.

### Task 2: Build the offline bundle

**Files:**
- Modify: `scripts/runtime_bundle.py`
- Create: `scripts/build_offline_runtime.sh`
- Test: `tests/test_runtime_bundle.py`

**Interfaces:**
- Consumes Task 1 privacy/manifest helpers.
- Produces bundle root with `source/`, `wheelhouse/`, `runtime_manifest.json`, `SHA256SUMS`, `bootstrap_offline.sh` and the ZIP artifact.

- [ ] **Step 1: Add RED tests** for source allow-listing, required fictional fixture inclusion, project-wheel/typst-wheel discovery and required bundle layout.
- [ ] **Step 2: Run targeted tests** and confirm failure.
- [ ] **Step 3: Implement source copying** for `app/`, `config/`, public `data/`, selected `scripts/`, `pyproject.toml`, and only the two recruiter fictional fixtures required for smoke verification; refuse forbidden paths.
- [ ] **Step 4: Implement build shell script** that builds the project wheel from the exact SHA, resolves/downloads all binary-compatible dependencies into `wheelhouse`, requires a Linux x86_64 typst-py wheel, writes manifest/checksums and archives the runtime.
- [ ] **Step 5: Run targeted tests** and confirm GREEN.
- [ ] **Step 6: Commit** `feat: build hermetic offline runtime bundle`.

### Task 3: Offline bootstrap and recruiter smoke test

**Files:**
- Create: `scripts/bootstrap_offline_runtime.sh`
- Create: `scripts/verify_offline_runtime.py`
- Modify: `tests/test_runtime_bundle.py`

**Interfaces:**
- `bootstrap_offline_runtime.sh [bundle-root] [expected-git-sha?]` verifies checksums, creates `.venv`, installs the project wheel from wheelhouse with no index, checks installed versions and invokes `verify_offline_runtime.py`.
- `verify_offline_runtime.py` renders fictional recruiter fixtures through `RenderCVTypstRenderer` and `RecruiterQualityQA` and checks A4/text/URI annotations.

- [ ] **Step 1: Add RED tests** for checksum verification failure, SHA mismatch and bootstrap flags (`PIP_NO_INDEX=1`, `--no-index`, `--find-links`).
- [ ] **Step 2: Run targeted tests** and confirm RED.
- [ ] **Step 3: Implement bootstrap** with strict `set -euo pipefail`, Python 3.12 check, checksum validation, manifest SHA check, isolated venv and local-wheel-only installation.
- [ ] **Step 4: Verify installed `rendercv`, `typst`, `PyMuPDF` and Opportunity OS versions against the manifest.**
- [ ] **Step 5: Implement fictional recruiter verification** by reusing the two bundled public recruiter fixtures and canonical QA; assert exactly one A4 page, selectable text and email/web URI annotations.
- [ ] **Step 6: Run targeted tests** and confirm GREEN.
- [ ] **Step 7: Commit** `feat: verify recruiter pipeline from offline runtime`.

### Task 4: Two-stage GitHub Actions acceptance

**Files:**
- Modify: `.github/workflows/tests.yml`

**Interfaces:**
- `build-offline-runtime` uploads `opportunity-os-runtime-linux-x86_64-py312` artifact.
- `verify-offline-runtime` downloads that artifact and runs only its bootstrap, with pip cache disabled and `PIP_NO_INDEX=1`.

- [ ] **Step 1: Add build job** after normal pytest checks, invoking `scripts/build_offline_runtime.sh "$GITHUB_SHA"` and uploading the ZIP with 90-day retention.
- [ ] **Step 2: Add dependent clean verification job** using a fresh runner, downloading/unpacking the artifact and running `bootstrap_offline.sh` with `PIP_NO_INDEX=1`.
- [ ] **Step 3: Ensure no online package-install commands exist in verification job**; setup-python is allowed only to provide Python 3.12.
- [ ] **Step 4: Push and inspect CI**; if bundle/bootstrap fails, fix the implementation rather than weakening the acceptance contract.
- [ ] **Step 5: Commit** `ci: verify offline recruiter runtime bundle`.

### Task 5: Agent runbook

**Files:**
- Modify: `docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md`

**Interfaces:**
- Documents deterministic offline execution path and fail-closed behavior.

- [ ] **Step 1: Add runtime-artifact section**: match artifact manifest git SHA to target revision, verify checksums, bootstrap offline, then materialize private facts/evidence separately.
- [ ] **Step 2: State explicit prohibition** on manual recruiter PDF reconstruction and renderer fallback when no matching runtime exists.
- [ ] **Step 3: Run documentation/privacy checks** and full test suite.
- [ ] **Step 4: Commit** `docs: document offline agent runtime`.

### Task 6: Final verification and PR

**Files:** none beyond prior tasks.

- [ ] **Step 1: Run full GitHub Actions suite** on the final branch head.
- [ ] **Step 2: Confirm normal tests, compile, whitespace, private-file guard, recruiter previews, offline runtime build and clean offline verification all pass.**
- [ ] **Step 3: Inspect branch diff against `main` for scope leakage.**
- [ ] **Step 4: Open PR against `main` with exact head SHA and acceptance evidence.**
