from pathlib import Path

import pymupdf

from app.cv.models import CVClaim, CVDocumentModel, ClaimProvenance, RenderedCVArtifact
from app.cv.recruiter_models import RecruiterDocumentModel, RecruiterRenderMetrics, RecruiterRenderResult
from app.cv.recruiter_qa import RecruiterQualityQA
from app.cv.render_policy import RenderPolicy


def test_letter_page_is_not_rejected_when_render_policy_requests_letter(tmp_path: Path) -> None:
    pdf = tmp_path / "letter.pdf"
    document = pymupdf.open()
    page = document.new_page(width=612.0, height=792.0)
    page.insert_text((48, 72), "Alex Example\nSoftware Developer\nalex@example.test", fontsize=10)
    document.save(pdf)
    document.close()

    source = CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=[
            CVClaim(claim_id="fact:name", section="headline", kind="identity", text="Alex Example"),
            CVClaim(claim_id="fact:role", section="headline", kind="headline", text="Software Developer"),
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
    render = RecruiterRenderResult(
        artifact=RenderedCVArtifact(
            path=str(pdf),
            sha256="c" * 64,
            renderer_version="fixture",
        ),
        metrics=RecruiterRenderMetrics(
            body_font_size=9.4,
            headline_line_count=1,
            overflow_detected=False,
        ),
    )
    policy = RenderPolicy(
        version="render-policy-v1",
        page_size="LETTER",
        preferred_pages=1,
        max_pages=1,
        min_body_font_pt=9.0,
        preferred_body_font_pt=9.4,
    )

    result = RecruiterQualityQA().evaluate(
        render_result=render,
        recruiter_document=recruiter,
        source_document=source,
        policy=policy,
    )

    assert "recruiter_page_size_invalid" not in {issue.code for issue in result.errors}
