from pathlib import Path

import pymupdf

from app.cv.models import CVClaim, CVDocumentModel, ClaimProvenance, RenderedCVArtifact
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterRenderMetrics,
    RecruiterRenderResult,
)
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.recruiter_qa import RecruiterQualityQA


def test_sparse_one_page_pdf_is_blocked_by_recruiter_density_gate(tmp_path: Path) -> None:
    source = CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=[
            CVClaim(claim_id="fact:name", section="headline", kind="identity", text="Alex Example"),
            CVClaim(claim_id="fact:role", section="headline", kind="headline", text="Operations Analyst"),
            CVClaim(claim_id="fact:email", section="headline", kind="contact", text="alex@example.test"),
        ],
        entries=[],
        provenance_map={
            "fact:name": ClaimProvenance(fact_ids=["fact:name"]),
            "fact:role": ClaimProvenance(fact_ids=["fact:role"]),
            "fact:email": ClaimProvenance(fact_ids=["fact:email"]),
        },
    )
    recruiter = RecruiterDocumentModel(
        source_cv_document_version="cvdoc-v1",
        language="en",
        identity_claim_id="fact:name",
        headline_claim_id="fact:role",
        contact_claim_ids=["fact:email"],
    )

    pdf = tmp_path / "sparse.pdf"
    document = pymupdf.open()
    page = document.new_page(width=595.28, height=841.89)
    page.insert_text(
        (48, 72),
        "Alex Example\nOperations Analyst\nalex@example.test",
        fontsize=10,
    )
    document.save(pdf)
    document.close()

    render_result = RecruiterRenderResult(
        artifact=RenderedCVArtifact(
            path=str(pdf),
            sha256="a" * 64,
            renderer_version="rendercv-typst-v1",
        ),
        metrics=RecruiterRenderMetrics(
            body_font_size=9.4,
            headline_line_count=1,
            overflow_detected=False,
        ),
    )

    result = RecruiterQualityQA().evaluate(
        render_result=render_result,
        recruiter_document=recruiter,
        source_document=source,
        policy=load_recruiter_policy("config/recruiter_policy.yaml"),
    )

    assert result.valid is False
    assert "recruiter_page_underutilized" in {issue.code for issue in result.errors}
