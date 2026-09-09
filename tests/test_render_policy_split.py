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
from app.cv.render_policy import RenderPolicy


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


def _two_page_render_result(path: Path) -> RecruiterRenderResult:
    document = pymupdf.open()
    first = document.new_page(width=595.28, height=841.89)
    first.insert_text(
        (48, 72),
        "Alex Example\nSoftware Developer\nalex@example.test",
        fontsize=10,
    )
    second = document.new_page(width=595.28, height=841.89)
    second.insert_text((48, 72), "Additional context", fontsize=10)
    document.save(path)
    document.close()
    return RecruiterRenderResult(
        artifact=RenderedCVArtifact(
            path=str(path),
            sha256="a" * 64,
            renderer_version="rendercv-typst-v1",
        ),
        metrics=RecruiterRenderMetrics(
            body_font_size=9.4,
            headline_line_count=1,
            overflow_detected=False,
        ),
    )


def test_recruiter_policy_contains_no_physical_render_fields() -> None:
    policy = load_recruiter_policy("config/recruiter_policy.yaml")

    assert not hasattr(policy, "max_pages")
    assert not hasattr(policy, "min_body_font_pt")
    assert not hasattr(policy, "preferred_body_font_pt")


def test_two_pages_can_be_within_render_policy_but_above_preference(tmp_path: Path) -> None:
    render_policy = RenderPolicy(
        version="render-policy-v1",
        page_size="A4",
        preferred_pages=1,
        max_pages=2,
        min_body_font_pt=9.0,
        preferred_body_font_pt=9.4,
    )

    result = RecruiterQualityQA().evaluate(
        render_result=_two_page_render_result(tmp_path / "two-page.pdf"),
        recruiter_document=_recruiter_document(),
        source_document=_source_document(),
        policy=render_policy,
    )

    assert result.valid is True
    assert "recruiter_preferred_page_count_exceeded" in {
        issue.code for issue in result.warnings
    }
