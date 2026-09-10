from __future__ import annotations

import importlib

import pytest


def _models_module():
    try:
        return importlib.import_module("app.cv.ats.models")
    except ModuleNotFoundError as exc:
        if exc.name in {"app.cv.ats", "app.cv.ats.models"}:
            pytest.fail("ATS round-trip models are not implemented")
        raise


def test_parsed_resume_preserves_structured_recovery_sections() -> None:
    models = _models_module()
    parsed = models.ParsedResume(
        parser_version="local-pymupdf-sections-v1",
        identity="Alex Example",
        headline="Software Developer",
        contacts=["alex@example.test"],
        profile=["Builds auditable systems."],
        technology=["Python, SQL"],
        projects=["Mapping Console"],
        experience=["Example Labs"],
        education=["BSc Applied Sciences"],
        languages=["Spanish — Native"],
        links=["github.com/example"],
        link_uris=["https://github.com/example"],
        extracted_text="Alex Example\nSoftware Developer",
    )

    assert parsed.identity == "Alex Example"
    assert parsed.experience == ["Example Labs"]
    assert parsed.link_uris == ["https://github.com/example"]


def test_category_recovery_ratio_is_bounded() -> None:
    models = _models_module()

    with pytest.raises(ValueError):
        models.ATSCategoryRecovery(
            expected_claim_ids=["fact:name"],
            recovered_claim_ids=["fact:name"],
            recovery_ratio=1.01,
        )


def test_roundtrip_result_cannot_be_valid_with_errors() -> None:
    models = _models_module()

    with pytest.raises(ValueError):
        models.ATSRoundTripQAResult(
            valid=True,
            parser_version="local-pymupdf-sections-v1",
            policy_version="ats-roundtrip-policy-v1",
            categories={},
            aggregate_recovery_ratio=1.0,
            errors=[{"code": "ats_roundtrip_identity_missing", "message": "identity missing"}],
            warnings=[],
        )
