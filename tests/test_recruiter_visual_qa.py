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


def _source_document() -> CVDocumentModel:
    claims = [
        CVClaim(claim_id="fact:name", section="headline", kind="identity", text="Alex Example"),
        CVClaim(claim_id="fact:role", section="headline", kind="headline", text="Software Developer"),
        CVClaim(claim_id="fact:email", section="headline", kind="contact", text="alex@example.test"),
        CVClaim(claim_id="fact:summary", section="summary", kind="summary", text="Builds reliable software."),
        CVClaim(claim_id="fact:python", section="skills", kind="skill", text="Python"),
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
        link_claim_ids=[],
    ).model_copy(
        update={
            "technology_groups": [],
            "experience_entries": [],
        }
    )


def _render_result(path: Path) -> RecruiterRenderResult:
    return RecruiterRenderResult(
        artifact=RenderedCVArtifact(
            path=str(path),
            sha256="b" * 64,
            renderer_version="visual-regression-fixture",
        ),
        metrics=RecruiterRenderMetrics(
            body_font_size=9.4,
            headline_line_count=1,
            overflow_detected=False,
        ),
    )


def test_isolated_bottom_note_is_hard_recruiter_failure(tmp_path):
    source_document = _source_document()
    recruiter_document = _recruiter_document()
    pdf = tmp_path / "isolated-footer.pdf"

    document = pymupdf.open()
    page = document.new_page(width=595.28, height=841.89)
    claim_by_id = {claim.claim_id: claim.text for claim in source_document.claims}
    visible_claims = "\n".join(
        claim_by_id[claim_id]
        for claim_id in recruiter_document.all_claim_ids()
    )
    page.insert_textbox(
        pymupdf.Rect(48, 60, 548, 260),
        visible_claims,
        fontsize=10,
    )
    page.insert_text(
        (330, 810),
        "CV adapted to Example - verified evidence only",
        fontsize=7,
    )
    document.save(pdf)
    document.close()

    result = RecruiterQualityQA().evaluate(
        render_result=_render_result(pdf),
        recruiter_document=recruiter_document,
        source_document=source_document,
        policy=load_recruiter_policy("config/recruiter_policy.yaml"),
    )

    assert result.valid is False
    assert "recruiter_isolated_footer_detected" in {
        issue.code for issue in result.errors
    }
