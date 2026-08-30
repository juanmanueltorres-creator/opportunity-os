from pathlib import Path

import fitz

from app.cv.models import CVClaim, CVDocumentModel, ClaimProvenance, RenderedCVArtifact
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterRenderMetrics,
    RecruiterRenderResult,
)
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.recruiter_qa import RecruiterQualityQA


def _source_document() -> CVDocumentModel:
    claims = [
        CVClaim(claim_id="fact:name", section="headline", kind="identity", text="Alex Example"),
        CVClaim(claim_id="fact:role", section="headline", kind="headline", text="Software Developer"),
        CVClaim(claim_id="fact:email", section="headline", kind="contact", text="alex@example.test"),
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


def _recruiter_document() -> RecruiterDocumentModel:
    return RecruiterDocumentModel(
        source_cv_document_version="cvdoc-v1",
        language="en",
        identity_claim_id="fact:name",
        headline_claim_id="fact:role",
        contact_claim_ids=["fact:email"],
    )


def _write_pdf(path: Path, *, pages: list[str]) -> None:
    document = fitz.open()
    for page_text in pages:
        page = document.new_page(width=595.28, height=841.89)
        if page_text:
            page.insert_text((48, 72), page_text, fontsize=10)
    document.save(path)
    document.close()


def _render_result(path: Path, *, body_font_size: float = 9.4) -> RecruiterRenderResult:
    return RecruiterRenderResult(
        artifact=RenderedCVArtifact(
            path=str(path),
            sha256="a" * 64,
            renderer_version="rendercv-typst-v1",
        ),
        metrics=RecruiterRenderMetrics(
            body_font_size=body_font_size,
            headline_line_count=1,
            overflow_detected=False,
        ),
    )


def _evaluate(path: Path, *, body_font_size: float = 9.4):
    return RecruiterQualityQA().evaluate(
        render_result=_render_result(path, body_font_size=body_font_size),
        recruiter_document=_recruiter_document(),
        source_document=_source_document(),
        policy=load_recruiter_policy("config/recruiter_policy.yaml"),
    )


def test_two_page_pdf_is_hard_recruiter_failure(tmp_path):
    pdf = tmp_path / "two-pages.pdf"
    _write_pdf(
        pdf,
        pages=[
            "Alex Example\nSoftware Developer\nalex@example.test",
            "spillover",
        ],
    )

    result = _evaluate(pdf)

    assert result.valid is False
    assert result.page_count == 2
    assert "recruiter_one_page_failed" in {issue.code for issue in result.errors}


def test_body_font_below_nine_points_is_hard_recruiter_failure(tmp_path):
    pdf = tmp_path / "small-font.pdf"
    _write_pdf(pdf, pages=["Alex Example\nSoftware Developer\nalex@example.test"])

    result = _evaluate(pdf, body_font_size=8.9)

    assert result.valid is False
    assert "recruiter_body_font_too_small" in {issue.code for issue in result.errors}


def test_blank_nonextractable_pdf_is_hard_recruiter_failure(tmp_path):
    pdf = tmp_path / "blank.pdf"
    _write_pdf(pdf, pages=[""])

    result = _evaluate(pdf)

    assert result.valid is False
    assert "recruiter_text_not_extractable" in {issue.code for issue in result.errors}
