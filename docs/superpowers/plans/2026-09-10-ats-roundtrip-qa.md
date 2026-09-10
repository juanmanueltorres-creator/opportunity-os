# ATS Round-Trip QA Implementation Plan

> **For coding agents:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add deterministic section-aware PDF parsing and semantic ATS recoverability QA after rendering, block unrecoverable outputs, and persist the result in `ApplicationPacket`.

**Architecture:** Keep RenderCV/Typst as the artifact source. Add `app/cv/ats/` with parser protocol, deterministic PyMuPDF parser, versioned thresholds, and category-aware semantic comparison. Run ATS QA after structural and visual QA. Treat it as a recoverability proxy, never vendor ATS emulation. Preserve historical packet compatibility while making ATS QA authoritative on new preparations.

**Tech Stack:** Python 3.12/3.13, Pydantic, PyMuPDF, YAML, pytest.

## Task 1 — ATS models and versioned policy

Create `app/cv/ats/__init__.py`, `app/cv/ats/models.py`, `app/cv/ats/policy.py`, `config/ats_roundtrip_policy.yaml`, `tests/test_cv_ats_models.py`, and `tests/test_cv_ats_policy.py`.

Start RED. Tests must require:
- `ParsedResume`: parser version, identity, headline, contacts, structured section text, visible links, link URIs, and full extracted text.
- `ATSCategoryRecovery`: expected/recovered claim IDs and bounded recovery ratio.
- `ATSRoundTripQAResult`: valid flag, parser/policy versions, per-category recovery, aggregate ratio, errors, warnings.
- versioned ATS policy with thresholds: identity 1.0, contact 1.0, experience 1.0, skills 0.9, education 1.0, links 1.0.

Run `pytest -q tests/test_cv_ats_models.py tests/test_cv_ats_policy.py`, confirm expected missing-module failure, implement minimum code, rerun GREEN, then commit `feat: add ATS round-trip models and policy`.

## Task 2 — Deterministic local PDF parser

Create `app/cv/ats/parser.py` and `tests/test_cv_ats_parser.py`.

Start RED with synthetic PDFs generated via PyMuPDF. Cover EN/ES renderer headings, preamble identity/headline/contact extraction, section segmentation, URI annotation extraction, and fail-closed unreadable/empty PDF behavior.

Implement:
```python
class ResumeParserAdapter(Protocol):
    def parse(self, pdf_path: str | Path) -> ParsedResume: ...
```

`LocalResumeParser` version is `local-pymupdf-sections-v1`. Use extractable PDF text only; no OCR. Segment known EN/ES sections deterministically and collect `page.get_links()` URI targets. Run `pytest -q tests/test_cv_ats_parser.py` RED→GREEN and commit `feat: add deterministic resume PDF parser`.

## Task 3 — Category-aware semantic recovery

Create `app/cv/ats/roundtrip_qa.py`, `tests/test_cv_ats_roundtrip_qa.py`, and `tests/fixtures/cv_quality/ats_extraction_loss/fixture.json`.

Start RED. Compare expected recruiter claims against their parsed semantic category, not the global PDF text:
- identity: identity + headline, required 100%;
- contact: all contact claim IDs;
- experience: experience primary claim IDs;
- skills: flattened technology-group skill IDs;
- education: education claim IDs;
- links: visible links plus URI targets.

Categories with no expected claims do not penalize aggregate recovery. Normalization removes soft hyphens, normalizes en/em dashes to `-`, collapses whitespace, and case-folds. Required issue-code families include `ats_roundtrip_identity_missing`, `ats_roundtrip_contact_recovery_low`, `ats_roundtrip_experience_recovery_low`, `ats_roundtrip_skill_recovery_low`, `ats_roundtrip_education_recovery_low`, and `ats_roundtrip_link_recovery_low`.

Run `pytest -q tests/test_cv_ats_roundtrip_qa.py` RED→GREEN and commit `feat: add ATS semantic recovery comparison`.

## Task 4 — Gate preparation and persist the ATS result

Modify `app/cv/models.py` and `app/cv/service.py`; add `tests/test_cv_service_ats_roundtrip.py` and extend `tests/test_cv_models.py` only where needed.

Start RED. Tests must prove:
- historical packet fixtures remain valid when both ATS fields are absent;
- `ats_policy_version` and typed `ats_qa` are present together on the new path;
- ATS parsing/QA runs after structural + visual QA and before `PREPARED`;
- parser/internal QA errors map to `BLOCKED_RENDER` with `ats_roundtrip_qa_failed`;
- category recovery failures preserve precise `ats_roundtrip_*` issue codes;
- successful preparation persists ATS policy/result;
- packet hash changes if ATS QA changes.

Wire defaults `LocalResumeParser`, `ATSRoundTripQA`, and loaded versioned policy. Pipeline: `render -> structural QA -> visual QA -> parse -> ATS round-trip QA -> PREPARED`. ATS failures are non-reducible in PR9; do not delete supported content to satisfy parsing. Extend `_packet_content_payload` to hash ATS policy/result. Run focused tests RED→GREEN and commit `feat: gate CV preparation on ATS recoverability`.

## Task 5 — Lock the public boundary and verify

Extend `tests/test_cv_release_contract.py` so documentation must describe ATS QA as a `recoverability proxy` and must not claim commercial ATS emulation/ranking guarantees. The approved spec already contains the desired wording, so only edit documentation if the test proves a gap.

Run:
```bash
pytest -q tests/test_cv_*.py tests/test_recruiter_*.py tests/test_json_resume_adapter.py tests/test_render_policy*.py
pytest -q
python -m compileall -q app
git diff --check origin/main...HEAD
```

Verify no user-private files are tracked. Then create draft PR `feat: add ATS round-trip recoverability QA` against `main`, explicitly stating that this is a recoverability proxy rather than vendor ATS emulation and that Gmail/outreach/send behavior is untouched. Keep the PR draft until the complete GitHub Actions workflow is green.