from pathlib import Path

import pymupdf
from pypdf import PdfReader

from app.cv.models import CVClaim, CVDocumentModel, ClaimProvenance, RenderedCVArtifact
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterExperienceEntry,
    RecruiterRenderMetrics,
    RecruiterRenderResult,
    TechnologyGroup,
)
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.recruiter_qa import RecruiterQualityQA
from app.cv.renderers.rendercv_typst import RenderCVTypstRenderer


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


def _golden_source_document() -> CVDocumentModel:
    claims = [
        CVClaim(claim_id="fact:name", section="headline", kind="identity", text="Alex Example"),
        CVClaim(
            claim_id="fact:role",
            section="headline",
            kind="headline",
            text="Software & Operations Developer",
        ),
        CVClaim(
            claim_id="fact:email",
            section="headline",
            kind="contact",
            text="alex@example.test",
        ),
        CVClaim(
            claim_id="approved:summary",
            section="summary",
            kind="summary",
            text="Builds software and operational workflows.",
        ),
        CVClaim(claim_id="fact:python", section="skills", kind="skill", text="Python"),
        CVClaim(
            claim_id="fact:project-1",
            section="projects",
            kind="project",
            text="Mapping Console",
        ),
        CVClaim(
            claim_id="fact:project-2",
            section="projects",
            kind="project",
            text="Fleet Simulator",
        ),
        CVClaim(
            claim_id="fact:employment-1",
            section="experience",
            kind="organization",
            text="Example Labs | 2024–Present",
        ),
        CVClaim(
            claim_id="approved:employment-1-bullet",
            section="experience",
            kind="bullet",
            text="Improved inventory and workflow visibility.",
        ),
        CVClaim(
            claim_id="fact:education",
            section="education",
            kind="education",
            text="BSc Applied Sciences",
        ),
        CVClaim(
            claim_id="fact:language",
            section="languages",
            kind="language",
            text="Spanish — Native",
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


def _golden_recruiter_document() -> RecruiterDocumentModel:
    return RecruiterDocumentModel(
        source_cv_document_version="cvdoc-v1",
        language="en",
        identity_claim_id="fact:name",
        headline_claim_id="fact:role",
        contact_claim_ids=["fact:email"],
        profile_claim_ids=["approved:summary"],
        technology_groups=[
            TechnologyGroup(
                label_id="software_data",
                skill_claim_ids=["fact:python"],
            )
        ],
        selected_project_claim_ids=["fact:project-1", "fact:project-2"],
        experience_entries=[
            RecruiterExperienceEntry(
                primary_claim_id="fact:employment-1",
                bullet_claim_ids=["approved:employment-1-bullet"],
            )
        ],
        education_claim_ids=["fact:education"],
        language_claim_ids=["fact:language"],
        link_claim_ids=["fact:github"],
    )


def _write_pdf(path: Path, *, pages: list[str]) -> None:
    document = pymupdf.open()
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


def test_substantive_one_page_with_large_bottom_void_is_hard_recruiter_failure(tmp_path):
    pdf = tmp_path / "underfilled.pdf"
    source_document = _golden_source_document()
    recruiter_document = _golden_recruiter_document()
    claim_by_id = {claim.claim_id: claim.text for claim in source_document.claims}
    compact_text = "\n".join(
        claim_by_id[claim_id].replace("–", "-").replace("—", "-")
        for claim_id in recruiter_document.all_claim_ids()
    )
    _write_pdf(pdf, pages=[compact_text])

    result = RecruiterQualityQA().evaluate(
        render_result=_render_result(pdf),
        recruiter_document=recruiter_document,
        source_document=source_document,
        policy=load_recruiter_policy("config/recruiter_policy.yaml"),
    )

    assert result.valid is False
    assert "recruiter_content_underfilled" in {issue.code for issue in result.errors}


def test_real_rendercv_pdf_survives_qa_and_two_independent_extractors(tmp_path):
    policy = load_recruiter_policy("config/recruiter_policy.yaml")
    source_document = _golden_source_document()
    recruiter_document = _golden_recruiter_document()
    render_result = RenderCVTypstRenderer().render(
        recruiter_document=recruiter_document,
        source_document=source_document,
        output_path=tmp_path / "golden.pdf",
        policy=policy,
    )

    qa_result = RecruiterQualityQA().evaluate(
        render_result=render_result,
        recruiter_document=recruiter_document,
        source_document=source_document,
        policy=policy,
    )

    assert qa_result.valid is True
    assert qa_result.page_count == 1

    pypdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(render_result.artifact.path).pages
    )
    with pymupdf.open(render_result.artifact.path) as document:
        pymupdf_text = "\n".join(page.get_text() for page in document)

    for expected in (
        "Alex Example",
        "alex@example.test",
        "Python",
        "Example Labs",
    ):
        assert expected in pypdf_text
        assert expected in pymupdf_text
