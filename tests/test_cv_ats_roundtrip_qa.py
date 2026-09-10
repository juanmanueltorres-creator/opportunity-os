from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from app.cv.ats.models import ParsedResume
from app.cv.ats.policy import ATSRoundTripPolicy
from app.cv.models import CVClaim, CVDocumentModel, ClaimProvenance
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterExperienceEntry,
    TechnologyGroup,
)


def _qa():
    try:
        module = importlib.import_module("app.cv.ats.roundtrip_qa")
    except ModuleNotFoundError as exc:
        if exc.name == "app.cv.ats.roundtrip_qa":
            pytest.fail("ATS round-trip QA is not implemented")
        raise
    return module.ATSRoundTripQA()


def _policy() -> ATSRoundTripPolicy:
    return ATSRoundTripPolicy.model_validate(
        {
            "version": "ats-roundtrip-policy-v1",
            "thresholds": {
                "identity": 1.0,
                "contact": 1.0,
                "experience": 1.0,
                "skills": 0.9,
                "education": 1.0,
                "links": 1.0,
            },
        }
    )


def _source_document() -> CVDocumentModel:
    claims = [
        CVClaim(
            claim_id="fact:name",
            section="headline",
            kind="identity",
            text="Alex Example",
        ),
        CVClaim(
            claim_id="fact:role",
            section="headline",
            kind="headline",
            text="Software Developer",
        ),
        CVClaim(
            claim_id="fact:email",
            section="headline",
            kind="contact",
            text="alex@example.test",
        ),
        CVClaim(
            claim_id="fact:employment",
            section="experience",
            kind="organization",
            text="Example Labs | 2024–Present",
        ),
        CVClaim(
            claim_id="fact:python",
            section="skills",
            kind="skill",
            text="Python",
        ),
        CVClaim(
            claim_id="fact:sql",
            section="skills",
            kind="skill",
            text="SQL",
        ),
        CVClaim(
            claim_id="fact:education",
            section="education",
            kind="education",
            text="BSc Applied Sciences",
        ),
        CVClaim(
            claim_id="fact:github",
            section="links",
            kind="link",
            text="github.com/example",
        ),
    ]
    return CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=claims,
        entries=[],
        provenance_map={
            claim.claim_id: ClaimProvenance(fact_ids=[claim.claim_id])
            for claim in claims
        },
    )


def _recruiter_document(*, include_links: bool = True) -> RecruiterDocumentModel:
    return RecruiterDocumentModel(
        source_cv_document_version="cvdoc-v1",
        language="en",
        identity_claim_id="fact:name",
        headline_claim_id="fact:role",
        contact_claim_ids=["fact:email"],
        profile_claim_ids=[],
        technology_groups=[
            TechnologyGroup(
                label_id="software_data",
                skill_claim_ids=["fact:python", "fact:sql"],
            )
        ],
        project_entries=[],
        experience_entries=[
            RecruiterExperienceEntry(
                primary_claim_id="fact:employment",
                bullet_claim_ids=[],
            )
        ],
        education_claim_ids=["fact:education"],
        language_claim_ids=[],
        link_claim_ids=["fact:github"] if include_links else [],
    )


def _parsed_resume(**updates) -> ParsedResume:
    payload = {
        "parser_version": "local-pymupdf-sections-v1",
        "identity": "Alex Example",
        "headline": "Software Developer",
        "contacts": ["alex@example.test"],
        "profile": [],
        "technology": ["Python, SQL"],
        "projects": [],
        "experience": ["Example Labs | 2024-Present"],
        "education": ["BSc Applied Sciences"],
        "languages": [],
        "links": ["github.com/example"],
        "link_uris": ["https://github.com/example"],
        "extracted_text": "synthetic resume",
    }
    payload.update(updates)
    return ParsedResume.model_validate(payload)


def _evaluate(parsed: ParsedResume, *, include_links: bool = True):
    return _qa().evaluate(
        recruiter_document=_recruiter_document(include_links=include_links),
        source_document=_source_document(),
        parsed_resume=parsed,
        policy=_policy(),
    )


def test_full_category_recovery_passes() -> None:
    result = _evaluate(_parsed_resume())

    assert result.valid is True
    assert result.aggregate_recovery_ratio == 1.0
    assert set(result.categories) == {
        "identity",
        "contact",
        "experience",
        "skills",
        "education",
        "links",
    }
    assert all(category.recovery_ratio == 1.0 for category in result.categories.values())
    assert result.errors == []


def test_identity_and_headline_are_critical_preamble_recovery() -> None:
    result = _evaluate(_parsed_resume(headline="Different Role"))

    assert result.valid is False
    assert result.categories["identity"].recovery_ratio == 0.5
    assert [issue.code for issue in result.errors] == ["ats_roundtrip_identity_missing"]


def test_skill_recovery_is_scoped_to_technology_section() -> None:
    parsed = _parsed_resume(
        technology=["Python"],
        experience=["Example Labs | 2024-Present; SQL"],
    )

    result = _evaluate(parsed)

    assert result.valid is False
    assert result.categories["skills"].recovery_ratio == 0.5
    assert "fact:sql" not in result.categories["skills"].recovered_claim_ids
    assert "ats_roundtrip_skill_recovery_low" in [issue.code for issue in result.errors]


def test_normalization_survives_soft_hyphen_dash_case_and_line_wraps() -> None:
    parsed = _parsed_resume(
        identity="ALEX EXAMPLE",
        headline="software developer",
        experience=["Example Labs | 2024—", "Present"],
        education=["BSc Applied", "Sciences"],
        technology=["Py\u00adthon", "SQL"],
    )

    result = _evaluate(parsed)

    assert result.valid is True
    assert result.categories["experience"].recovery_ratio == 1.0
    assert result.categories["skills"].recovery_ratio == 1.0


def test_absent_expected_category_does_not_reduce_aggregate_recovery() -> None:
    result = _evaluate(
        _parsed_resume(links=[], link_uris=[]),
        include_links=False,
    )

    assert result.valid is True
    assert result.categories["links"].expected_claim_ids == []
    assert result.categories["links"].recovery_ratio == 1.0
    assert result.aggregate_recovery_ratio == 1.0


def test_link_can_recover_from_pdf_uri_annotation() -> None:
    result = _evaluate(_parsed_resume(links=[], link_uris=["https://github.com/example"]))

    assert result.valid is True
    assert result.categories["links"].recovered_claim_ids == ["fact:github"]


def test_extraction_loss_fixture_fails_with_expected_issue_code() -> None:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "cv_quality"
        / "ats_extraction_loss"
        / "fixture.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    result = _evaluate(_parsed_resume(technology=fixture["parsed_technology"]))

    assert result.valid is False
    assert fixture["expected_issue_code"] in [issue.code for issue in result.errors]
