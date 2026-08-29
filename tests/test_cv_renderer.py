from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4

from app.cv.models import (
    CVClaim,
    CVDocumentModel,
    ClaimProvenance,
    ValidationIssue,
    ValidationResult,
)
from app.cv.renderer import ATSRenderer


def _document() -> CVDocumentModel:
    claims = [
        CVClaim(
            claim_id="claim-name",
            section="headline",
            kind="identity",
            text="Alex Example",
        ),
        CVClaim(
            claim_id="claim-role",
            section="headline",
            kind="headline",
            text="GIS Developer",
        ),
        CVClaim(
            claim_id="claim-skill",
            section="skills",
            kind="skill",
            text="PostGIS",
        ),
    ]
    return CVDocumentModel(
        document_version="cv-doc-v1",
        language="en",
        claims=claims,
        entries=[],
        provenance_map={
            claim.claim_id: ClaimProvenance(fact_ids=[f"fact-{claim.claim_id}"])
            for claim in claims
        },
    )


def _valid_validation() -> ValidationResult:
    return ValidationResult(
        valid=True,
        validated_claim_ids=["claim-name", "claim-role", "claim-skill"],
    )


def _invalid_validation() -> ValidationResult:
    return ValidationResult(
        valid=False,
        errors=[
            ValidationIssue(
                code="claim_validation_failed",
                message="document is not validated",
            )
        ],
    )


def test_renderer_v2_contract() -> None:
    renderer = ATSRenderer()

    assert renderer.renderer_version == "ats-pdf-v2"
    assert renderer.page_size == A4
    assert renderer.body_font_name == "Helvetica"
    assert renderer.bold_font_name == "Helvetica-Bold"
    assert renderer.body_font_size >= 9.0
    assert renderer.name_font_size >= renderer.body_font_size + 6.0
    assert renderer.max_pages == 2


def test_renderer_rejects_invalid_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="validated"):
        ATSRenderer().render(
            _document(),
            _invalid_validation(),
            tmp_path / "cv.pdf",
        )


def test_pdf_contains_selectable_candidate_text(tmp_path: Path) -> None:
    artifact = ATSRenderer().render(
        _document(),
        _valid_validation(),
        tmp_path / "cv.pdf",
    )

    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(artifact.path).pages
    )

    assert "Alex Example" in text
    assert "GIS Developer" in text
    assert "PostGIS" in text
    assert artifact.path == str(tmp_path / "cv.pdf")
    assert len(artifact.sha256) == 64
    assert artifact.renderer_version == "ats-pdf-v2"


def test_identical_document_produces_identical_pdf_bytes(tmp_path: Path) -> None:
    renderer = ATSRenderer()
    document = _document()
    validation = _valid_validation()

    first = renderer.render(document, validation, tmp_path / "a.pdf")
    second = renderer.render(document, validation, tmp_path / "b.pdf")

    assert Path(first.path).read_bytes() == Path(second.path).read_bytes()
    assert first.sha256 == second.sha256
