# Opportunity OS Agent Runbook

DO NOT reconstruct CV generation from memory.
DO NOT hand-build recruiter PDFs when the canonical command is available.
PREPARED requires exactly one recruiter-quality A4 page.
PREPARED != APPROVE != SEND.
Private candidate snapshots and generated artifacts never enter the public repo.

## Purpose

This runbook is the authoritative fresh-context path for preparing a recruiter-facing CV with Opportunity OS V0.2B2. The preparation command is intentionally fail-closed: it consumes an already serialized `RadarAssessment`, verified private facts, verified private evidence, and the checked-in recruiter policy. It does not infer a missing track, score, intent, requirement, employer, skill, metric, or application state.

The canonical preparation flow is:

```text
RadarAssessment
-> EvidenceSelector
-> CVComposer
-> ClaimValidator
-> RecruiterDocumentComposer
-> RecruiterDocumentValidator
-> RenderCV/Typst one-page renderer
-> RecruiterQualityQA
-> ApplicationPacket
```

`ClaimValidator` remains the semantic authority. Recruiter composition may select, group, order, or omit validated claims, but it may not create new candidate-specific claims.

## Prerequisites

With package-index access, use Python 3.12+ and install the project with the same dependency set used by CI:

```bash
python -m pip install -e ".[dev]"
```

The recruiter path requires RenderCV/Typst plus PyMuPDF and PyPDF extraction support. Do not create a separate ad-hoc rendering environment.

## Offline runtime artifact

When the shell cannot reach PyPI/GitHub for package installation, do not reconstruct the recruiter renderer manually. Use a SHA-bound offline runtime artifact produced by this repository's CI.

The first runtime format supports Linux x86_64 on Python 3.12 and 3.13. Determine both values before selecting an artifact:

```bash
python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
# Obtain the exact Opportunity OS repository SHA through the available GitHub/repository channel.
```

Select the artifact matching the interpreter minor:

```text
opportunity-os-runtime-linux-x86_64-py312.zip
opportunity-os-runtime-linux-x86_64-py313.zip
```

The artifact is valid only for the exact git SHA stored in its `runtime_manifest.json`. Unpack it, then invoke its bootstrap with the SHA you intend to execute:

```bash
bash opportunity-os-runtime/bootstrap_offline.sh \
  opportunity-os-runtime \
  <exact-opportunity-os-git-sha>
```

The bootstrap is fail-closed. Before installing anything it verifies `SHA256SUMS`, the manifest SHA, the Python minor, the bundled source hash, and the project/typst wheel hashes. It then creates a clean virtual environment with `PIP_NO_INDEX=1`, installs only from the bundled wheelhouse, verifies Opportunity OS/RenderCV/typst-py/PyMuPDF/renderer versions, and renders fictional recruiter fixtures through the canonical renderer and `RecruiterQualityQA`.

A successful bootstrap proves that the artifact can execute the canonical recruiter renderer without package-index access. It does not contain candidate facts, evidence, real CVs, opportunities, Gmail state, Apollo data, or approval/send authority.

After bootstrap succeeds, materialize the authorized private inputs separately and run the canonical preparation command with the bundle's `.venv` Python and SHA-bound source tree. Private inputs never become part of the reusable runtime artifact.

If no artifact matches both the current Python minor and the exact target git SHA, stop fail-closed. Do not:

- hand-build a recruiter PDF with ReportLab/HTML/another renderer;
- reuse an older `ats-pdf` `ApplicationPacket` as if it came from the current renderer;
- switch silently to an obsolete renderer;
- edit a PDF after a blocked canonical preparation and call it `PREPARED`;
- fabricate a successful `ApplicationPacket`.

## Required private inputs

The canonical command expects these private inputs to exist locally and remain untracked:

```text
<private-radar-assessment.json>
profile/master_facts.local.yaml
profile/evidence_catalog.local.yaml
```

The first file must serialize a complete `RadarAssessment`, including the selected intent and the winning track produced by Radar. A raw `Opportunity` JSON is not sufficient and is rejected rather than supplemented with guessed scoring or track data.

Private candidate facts and evidence must be built from defensible sources. Unsupported requirements remain unresolved gaps; they are not promoted into claims.

## Obtaining a RadarAssessment

Use the existing Radar pipeline or an explicitly reviewed private serialization of its typed `RadarAssessment` result. The assessment must preserve the opportunity snapshot, enrichment, eligibility, intent, track, scoring versions, confidence, and requirement provenance expected by the domain model.

Do not hand-author a replacement assessment merely to make CV preparation pass. If the selected intent or winning track is missing, let the preparation path fail closed.

## Canonical command

Run exactly one preparation command from the repository root (or the SHA-bound bundled `source/` root when using an offline runtime):

```bash
python -m app.application.prepare \
  --opportunity <private-radar-assessment.json> \
  --master-facts profile/master_facts.local.yaml \
  --evidence-catalog profile/evidence_catalog.local.yaml \
  --recruiter-policy config/recruiter_policy.yaml \
  --output-root artifacts/applications
```

On success, the command prints a JSON result with `status=PREPARED`, the application ID, final PDF path, page count, CV SHA-256, packet SHA-256, unresolved gaps, and warnings. It writes `application_packet.json` beside the generated PDF only after preparation succeeds.

The generated files remain local under:

```text
artifacts/applications/<application_id>/cv.pdf
artifacts/applications/<application_id>/application_packet.json
```

## Fail-closed statuses

`PREPARED` is the only successful preparation state. Important blocked states include `BLOCKED_TRACK_UNAVAILABLE`, `BLOCKED_MISSING_FACTS`, `BLOCKED_VALIDATION`, and `BLOCKED_RENDER`. Invalid serialized input or private configuration returns an explicit CLI error instead of fabricating missing data.

A renderer exception, recruiter validation failure, two-page result, sub-threshold body font, missing extractable text, or other hard RecruiterQualityQA error must not produce a usable packet. Partial PDFs are removed by the preparation service.

Never bypass a blocked state by manually editing a PDF or deleting a requirement from the assessment.

## Exactly one recruiter page

V0.2B2 has no automatic two-page fallback. A `PREPARED` recruiter artifact must be exactly one A4 page and satisfy the checked-in `recruiter-policy-v1` budgets. The bounded reduction loop may remove lower-priority optional recruiter content, but it never weakens claim validation or invents replacement content.

When evidence permits, the intended recruiter shape is compact: strong identity/headline hierarchy, concise profile, grouped technology rows, two to four target-relevant projects, compact experience with no more than one bullet per included role, and education/languages/links as permitted by policy and fit.

## Post-render inspection

After a real private preparation, inspect the actual PDF rather than trusting `PREPARED` as a visual judgment. Confirm one A4 page, no clipping or overlap, selectable/extractable text, readable body size, compact contact information, coherent section hierarchy, and no giant unused lower region. Compare the content against the `ApplicationPacket` and the known evidence rather than against memory.

For ATS smoke checks, candidate ground truth should survive both PyPDF and PyMuPDF extraction. Public golden fixtures exercise this behavior without containing real candidate data.

## ACTIVE_POSTING versus TARGET_ACCOUNT

`ACTIVE_POSTING` means a real published requisition exists and the `RadarAssessment` refers to that opportunity.

`TARGET_ACCOUNT` means an organization is strategically interesting even if no current requisition exists. A target account is not an active posting and must not be converted into a fictional opportunity merely to obtain an `ApplicationPacket`.

Speculative outreach remains a separate workflow. Use the target-account and relationship contracts instead of inventing a vacancy title, job ID, requirements, or posting snapshot.

## Unsupported requirements and unresolved gaps

A target requirement unsupported by verified candidate evidence remains visible in `unresolved_gaps`. It must not appear as a candidate skill, employment claim, metric, certification, tool, or project just because the wording would improve ATS matching.

For example, if Power BI, SAP, a B2B platform, a license, a degree, years of experience, or another requirement is not supported by verified facts/evidence, keep it as a gap. Do not silently substitute related tools or adjacent experience unless the taxonomy/evidence contracts explicitly support that relationship.

## Privacy and repository boundary

Private snapshots and generated application artifacts are intentionally excluded from Git. Public tests may contain only fictional fixtures. Before committing, verify that no `*.local.yaml`, private assessment, generated PDF, private packet, real email address, phone number, or candidate-specific snapshot has entered the repository.

The public repo contains the deterministic machinery, policy, examples, tests, documentation and reusable runtime machinery. Real candidate state stays local.

## Preparation is not outreach authority

The CLI stops at `ApplicationPacket`. It does not create a Gmail draft, approve outreach, request a send, send an email, submit an ATS form, or mark an opportunity as applied.

The downstream boundary remains:

```text
ApplicationPacket
-> verified contact
-> OutreachBrief
-> DraftSnapshot
-> ApprovalRecord
-> explicit SendRequest
-> SendGate
-> provider-confirmed SendReceipt
```

A recruiter-quality CV can be `PREPARED` while outreach remains entirely untouched. That separation is intentional and must be preserved by every agent and operator.
