# Opportunity OS Offline Runtime Bundle Design

## Problem

The end-to-end autonomous run can complete discovery, screening, private evidence audit and contact discovery, but fails closed before recruiter PDF generation when the execution container does not already contain RenderCV/Typst and cannot reach PyPI/GitHub from the shell. CI succeeds only because it installs the project online before rendering.

The observed blocked agent runtime was Python 3.13.5. Normal Opportunity OS CI currently runs Python 3.12. A portable solution therefore has to cover both supported execution minors rather than producing a bundle that only works inside the existing CI interpreter.

This means the canonical recruiter renderer is correct but its runtime was not portable.

## Goal

Produce versioned, SHA-bound Linux x86_64 runtime artifacts for Python 3.12 and 3.13 that allow Opportunity OS to install and execute the canonical RenderCV/Typst recruiter pipeline without network package downloads.

## Non-goals

Do not change Radar scoring, EvidenceSelector, CVComposer, ClaimValidator, RecruiterDocumentComposer, RecruiterDocumentValidator, RecruiterQualityQA, outreach authorization, Gmail behavior or private candidate data handling. Do not add a fallback to ReportLab/ATS rendering.

## Compiler reality

RenderCV 2.8 compiles PDFs in-process through the `typst` Python package (typst-py). The canonical Opportunity OS renderer also calls RenderCV in-process. Therefore the portable compiler runtime is the platform-specific `typst` wheel, not an external `typst` CLI binary. The bundle must preserve and verify that exact wheel rather than inventing a second compiler path.

## Artifact contract

CI produces two artifacts for the same repository SHA:

- `opportunity-os-runtime-linux-x86_64-py312.zip`
- `opportunity-os-runtime-linux-x86_64-py313.zip`

Each ZIP contains:

```text
opportunity-os-runtime/
  source/
    app/
    config/
    data/
    scripts/
    tests/fixtures/recruiter_software.json
    tests/fixtures/recruiter_tech_operations.json
    pyproject.toml
  wheelhouse/
    opportunity_os-*.whl
    rendercv-*.whl
    typst-*.whl
    ...all transitive wheels...
  bootstrap_offline.sh
  runtime_manifest.json
  SHA256SUMS
```

The artifact must exclude private/local files, generated real applications, credentials, Python cache files and real PDFs.

## Build contract

The online build matrix may access package indexes. For each Python minor (3.12 and 3.13), it must:

1. run on Ubuntu/Linux x86_64 with the matching Python minor;
2. build an Opportunity OS wheel from the exact checked-out SHA;
3. resolve/download all runtime wheels required by that wheel;
4. require a compatible Linux x86_64 `typst` wheel and fail if it is absent;
5. copy only public `app/`, `config/`, `data/`, `scripts/`, `pyproject.toml` and the two fictional recruiter fixtures required to audit and smoke-test the runtime;
6. exclude ephemeral `__pycache__`/`.pyc` files while still rejecting private/generated paths;
7. write `runtime_manifest.json` with git SHA, schema version, Python major/minor, platform, Opportunity OS version, RenderCV version, Typst version, PyMuPDF version, renderer version, project-wheel SHA256, Typst-wheel SHA256, source SHA256 and build timestamp;
8. write `SHA256SUMS` covering bundled files;
9. zip and upload the artifact for 90 days.

## Offline bootstrap contract

`bootstrap_offline.sh` must:

- require an expected repository git SHA;
- require that the current interpreter minor matches the artifact manifest (`3.12` or `3.13`);
- verify `runtime_manifest.json` and `SHA256SUMS` before installation;
- verify source/project-wheel/typst-wheel hashes from the manifest;
- create a clean virtual environment;
- set `PIP_NO_INDEX=1` and disable pip version checks;
- install the bundled Opportunity OS wheel and all dependencies only from `wheelhouse/` using `--no-index --find-links`;
- execute with the SHA-bound bundled source tree on `PYTHONPATH`, preserving the renderer's source-relative config/data lookup;
- verify installed Opportunity OS, RenderCV, typst-py, PyMuPDF and renderer versions against the manifest;
- run fictional recruiter previews through the canonical renderer and `RecruiterQualityQA`;
- verify one A4 page, extractable text and real `mailto:`/`https://` URI annotations.

Any missing wheel, checksum mismatch, SHA mismatch, Python-minor mismatch, version mismatch, import failure, render failure or recruiter QA failure is a hard failure.

## SHA binding

The manifest records the exact Opportunity OS git SHA. Consumers must compare the artifact SHA with the repository revision they intend to execute. A mismatch is fail-closed.

## Offline CI acceptance

A separate verification matrix downloads each freshly built artifact and validates it on a fresh runner. The verification jobs do not check out the repository, do not use pip cache, do not install from package indexes, and run with `PIP_NO_INDEX=1` plus local `--no-index --find-links` installation.

GitHub-hosted runners do not provide a simple supported network-off switch for an individual step, so the enforceable package-network boundary is: fresh runner, no checkout as a code source, no pip cache, `PIP_NO_INDEX=1`, `--no-index`, local `--find-links`, and no online package-install command in the verification job.

The test succeeds only if the bundled runtime installs and renders the fictional recruiter fixtures through the canonical `RenderCVTypstRenderer` and `RecruiterQualityQA` under both Python 3.12 and Python 3.13.

## Privacy

The bundle must never contain:

- `.env`;
- `*.local.yaml`;
- `profile/master_facts.local.yaml`;
- `profile/evidence_catalog.local.yaml`;
- local SQLite state;
- `artifacts/applications/**`;
- real CV/PDF/DOCX artifacts;
- credentials or connector tokens.

Private facts/evidence are materialized separately at execution time from an authorized private source.

## Agent runbook behavior

When package indexes are unavailable, agents must select the runtime bundle matching both their Python minor and the target repository SHA. The bootstrap verifies that binding before installation.

If no matching artifact exists, the agent stops fail-closed. It must not hand-build recruiter PDFs, reuse an obsolete ATS packet, silently switch renderers or invent a successful `PREPARED` state.
