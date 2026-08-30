from pathlib import Path

from pypdf import PdfReader

from app.cv.models import CVClaim, CVDocumentModel, ClaimProvenance
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterExperienceEntry,
    TechnologyGroup,
)
from app.cv.recruiter_policy import load_recruiter_policy


def _source_document() -> CVDocumentModel:
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
        CVClaim(claim_id="fact:sql", section="skills", kind="skill", text="SQL"),
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


def _recruiter_document() -> RecruiterDocumentModel:
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
                skill_claim_ids=["fact:python", "fact:sql"],
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


def test_rendercv_runtime_is_importable():
    import rendercv
    import typst

    assert rendercv is not None
    assert typst is not None


def test_rendercv_renderer_outputs_one_a4_page_with_extractable_text(tmp_path):
    from app.cv.renderers.rendercv_typst import RenderCVTypstRenderer

    result = RenderCVTypstRenderer().render(
        recruiter_document=_recruiter_document(),
        source_document=_source_document(),
        output_path=tmp_path / "cv.pdf",
        policy=load_recruiter_policy("config/recruiter_policy.yaml"),
    )

    reader = PdfReader(result.artifact.path)
    assert len(reader.pages) == 1
    assert "Alex Example" in (reader.pages[0].extract_text() or "")
    assert Path(result.artifact.path).exists()
    assert result.metrics.body_font_size >= 9.0


def test_identical_recruiter_document_produces_identical_pdf_bytes(tmp_path):
    from app.cv.renderers.rendercv_typst import RenderCVTypstRenderer

    renderer = RenderCVTypstRenderer()
    policy = load_recruiter_policy("config/recruiter_policy.yaml")
    source_document = _source_document()
    recruiter_document = _recruiter_document()

    first = renderer.render(
        recruiter_document=recruiter_document,
        source_document=source_document,
        output_path=tmp_path / "a.pdf",
        policy=policy,
    )
    second = renderer.render(
        recruiter_document=recruiter_document,
        source_document=source_document,
        output_path=tmp_path / "b.pdf",
        policy=policy,
    )

    assert (tmp_path / "a.pdf").read_bytes() == (tmp_path / "b.pdf").read_bytes()
    assert first.artifact.sha256 == second.artifact.sha256
