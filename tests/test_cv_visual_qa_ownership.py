from pathlib import Path

import pymupdf

from app.cv.models import CVClaim, CVDocumentModel, ClaimProvenance, RenderedCVArtifact
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterRenderMetrics,
    RecruiterRenderResult,
)
from app.cv.recruiter_qa import RecruiterQualityQA
from app.cv.render_policy import load_render_policy


OLD_VISUAL_CODES = {
    "recruiter_content_underfilled",
    "recruiter_isolated_footer_detected",
    "recruiter_headline_too_tall",
}


def _source_document() -> CVDocumentModel:
    claims = [
        CVClaim(claim_id="fact:name", section="headline", kind="identity", text="Alex Example"),
        CVClaim(claim_id="fact:role", section="headline", kind="headline", text="Software Developer"),
        CVClaim(claim_id="fact:email", section="headline", kind="contact", text="alex@example.test"),
        CVClaim(claim_id="fact:summary", section="summary", kind="summary", text="Builds reliable software."),
        CVClaim(claim_id="fact:skill", section="skills", kind="skill", text="Python"),
        CVClaim(claim_id="fact:project", section="projects", kind="project", text="Fleet Simulator"),
        CVClaim(claim_id="fact:experience", section="experience", kind="organization", text="Example Labs"),
        CVClaim(claim_id="fact:education", section="education", kind="education", text="Applied Sciences"),
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
        profile_claim_ids=["fact:summary"],
        selected_project_claim_ids=["fact:project"],
        education_claim_ids=["fact:education"],
        language_claim_ids=["fact:skill", "fact:experience"],
        link_claim_ids=[],
    )


def _render_result(path: Path, *, headline_lines: int = 1) -> RecruiterRenderResult:
    return RecruiterRenderResult(
        artifact=RenderedCVArtifact(
            path=str(path),
            sha256="d" * 64,
            renderer_version="ownership-fixture",
        ),
        metrics=RecruiterRenderMetrics(
            body_font_size=9.4,
            headline_line_count=headline_lines,
            overflow_detected=False,
        ),
    )


def _write_pdf(path: Path, *, isolated_bottom: bool = False) -> None:
    source = _source_document()
    recruiter = _recruiter_document()
    claim_by_id = {claim.claim_id: claim.text for claim in source.claims}
    document = pymupdf.open()
    page = document.new_page(width=595.28, height=841.89)
    y = 60
    for claim_id in recruiter.all_claim_ids():
        page.insert_text((48, y), claim_by_id[claim_id], fontsize=10)
        y += 18
    if isolated_bottom:
        page.insert_text((48, 800), "isolated visual note", fontsize=9.4)
    document.save(path)
    document.close()


def _technical_result(path: Path, *, headline_lines: int = 1):
    return RecruiterQualityQA().evaluate(
        render_result=_render_result(path, headline_lines=headline_lines),
        recruiter_document=_recruiter_document(),
        source_document=_source_document(),
        policy=load_render_policy("config/render_policy.yaml"),
    )


def test_underfill_is_not_owned_by_recruiter_technical_qa(tmp_path):
    pdf = tmp_path / "underfilled.pdf"
    _write_pdf(pdf)

    result = _technical_result(pdf)
    codes = {issue.code for issue in result.errors}

    assert OLD_VISUAL_CODES.isdisjoint(codes)
    assert result.valid is True


def test_isolated_bottom_block_is_not_owned_by_recruiter_technical_qa(tmp_path):
    pdf = tmp_path / "isolated.pdf"
    _write_pdf(pdf, isolated_bottom=True)

    result = _technical_result(pdf)
    codes = {issue.code for issue in result.errors}

    assert OLD_VISUAL_CODES.isdisjoint(codes)
    assert result.valid is True


def test_headline_height_is_not_owned_by_recruiter_technical_qa(tmp_path):
    pdf = tmp_path / "headline.pdf"
    _write_pdf(pdf)

    result = _technical_result(pdf, headline_lines=3)
    codes = {issue.code for issue in result.errors}

    assert OLD_VISUAL_CODES.isdisjoint(codes)
    assert result.valid is True
