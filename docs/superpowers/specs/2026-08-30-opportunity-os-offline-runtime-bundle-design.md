# Opportunity OS Offline Runtime Bundle Design

## Problem

The end-to-end autonomous run can complete discovery, screening, private evidence audit and contact discovery, but fails closed before recruiter PDF generation when the execution container does not already contain RenderCV/Typst and cannot reach PyPI/GitHub from the shell. CI succeeds only because it installs the project online before rendering.

This means the canonical recruiter renderer is correct but its runtime is not portable.

## Goal

Produce a versioned, SHA-bound Linux x86_64 / Python 3.12 runtime artifact that allows Opportunity OS to install and execute the canonical RenderCV/Typst recruiter pipeline without network package downloads.

## Non-goals

Do not change Radar scoring, EvidenceSelector, CVComposer, ClaimValidator, RecruiterDocumentComposer, RecruiterDocumentValidator, RecruiterQualityQA, outreach authorization, Gmail behavior or private candidate data handling. Do not add a fallback to ReportLab/ATS rendering.

## Artifact contract

CI produces `opportunity-os-runtime-linux-x86_64-py312.zip` containing:

```text
opportunity-os-runtime/
  source/
    app/
    config/
    scripts/
    pyproject.toml
  wheelhouse/
    *.whl
  bin/
    typst
  bootstrap_offline.sh
  runtime_manifest.json
  SHA256SUMS
```

The artifact must exclude private/local files, generated real applications, credentials and PDFs.

## Build contract

The online build job may access package indexes. It must:

1. run on Ubuntu with Python 3.12;
2. build/download all wheels needed to install `source/` with `pip --no-index --find-links wheelhouse`;
3. locate the Typst executable used by the installed RenderCV environment and copy it to `bin/typst`;
4. copy only the source/config/scripts required to run Opportunity OS;
5. write `runtime_manifest.json` with git SHA, schema version, Python major/minor, platform, RenderCV version, Typst version, PyMuPDF version, Typst SHA256, source SHA256, build timestamp and expected renderer version;
6. write `SHA256SUMS` covering bundled files;
7. zip and upload the artifact for 90 days.

## Offline bootstrap contract

`bootstrap_offline.sh` must:

- require Python 3.12;
- verify `runtime_manifest.json` and `SHA256SUMS` before installation;
- create a clean virtual environment;
- set `PIP_NO_INDEX=1`;
- install only from `wheelhouse/`;
- prepend bundled `bin/` to `PATH`;
- verify Python, RenderCV and Typst availability;
- run a fictional recruiter preview through the canonical renderer and RecruiterQualityQA;
- verify one A4 page, extractable text and URI annotations.

Any missing wheel, checksum mismatch, missing Typst binary, version mismatch, render failure or recruiter QA failure is a hard failure.

## SHA binding

The manifest records the exact Opportunity OS git SHA. Consumers must compare the artifact SHA with the repository revision they intend to execute. A mismatch is fail-closed.

## Offline CI acceptance

A separate CI job must download the freshly built artifact and validate it in a clean environment without using pip cache or online package installation. The bootstrap must run with `PIP_NO_INDEX=1` and no dependency download step. The test succeeds only if the bundled runtime installs and renders the fictional recruiter fixture through `RecruiterQualityQA`.

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

When package indexes are unavailable, agents must use a runtime bundle whose manifest SHA matches the target repo revision. If no matching artifact exists, they stop fail-closed. They must not hand-build recruiter PDFs or silently switch renderers.
