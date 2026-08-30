import json
from pathlib import Path

import pymupdf
import pytest
import yaml
from pypdf import PdfReader

import app.cv.renderers.rendercv_typst as rendercv_renderer_module
from app.cv.models import CVClaim, CVDocumentModel, ClaimProvenance
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterExperienceEntry,
    TechnologyGroup,
)
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.recruiter_qa import RecruiterQualityQA
from app.cv.renderers.rendercv_typst import RenderCVTypstRenderer


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


def _load_golden_fixture(name: str) -> tuple[RecruiterDocumentModel, CVDocumentModel]:
    path = Path("tests/fixtures") / f"{name}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return (
        RecruiterDocumentModel.model_validate(payload["recruiter_document"]),
        CVDocumentModel.model_validate(payload["source_document"]),
    )


def test_rendercv_runtime_is_importable():
    import rendercv
    import typst

    assert rendercv is not None
    assert typst is not None


def test_recruiter_theme_disables_connection_and_external_link_icons():
    design = yaml.safe_load(Path("config/rendercv_one_page.yaml").read_text(encoding="utf-8"))

    assert design["design"]["header"]["connections"]["show_icons"] is False
    assert design["design"]["links"]["show_external_link_icon"] is False


def test_rendercv_28_offline_package_path_contains_local_fontawesome_shim():
    package_path = rendercv_renderer_module._prepare_rendercv_offline_package_path()
    shim = package_path / "preview" / "fontawesome" / "0.6.0"

    assert (shim / "typst.toml").is_file()
    assert (shim / "lib.typ").is_file()
    assert 'name = "fontawesome"' in (shim / "typst.toml").read_text(encoding="utf-8")
    assert 'version = "0.6.0"' in (shim / "typst.toml").read_text(encoding="utf-8")
    assert "fa-icon" in (shim / "lib.typ").read_text(encoding="utf-8")


def test_rendercv_renderer_outputs_one_a4_page_with_extractable_text(tmp_path):
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


def test_golden_fixture_shapes_match_approved_reference_contract() -> None:
    software, software_source = _load_golden_fixture("recruiter_software")
    tech_ops, tech_ops_source = _load_golden_fixture("recruiter_tech_operations")

    assert len(software.technology_groups) == 3
    assert len(software.selected_project_claim_ids) == 4
    assert len(software.experience_entries) == 5
    assert len(software.contact_claim_ids) >= 2

    assert {group.label_id for group in tech_ops.technology_groups} >= {
        "software_data",
        "operations_systems",
    }
    assert 2 <= len(tech_ops.selected_project_claim_ids) <= 4
    assert len(tech_ops.experience_entries) >= 2
    assert len(tech_ops.contact_claim_ids) >= 2

    tech_ops_text = "\n".join(claim.text for claim in tech_ops_source.claims).casefold()
    assert "power bi" not in tech_ops_text
    assert "sap" not in tech_ops_text
    assert software_source.language == "en"


@pytest.mark.parametrize(
    "fixture_name",
    ["recruiter_software", "recruiter_tech_operations"],
)
def test_golden_recruiter_profiles_are_exactly_one_page(fixture_name, tmp_path):
    policy = load_recruiter_policy("config/recruiter_policy.yaml")
    recruiter_document, source_document = _load_golden_fixture(fixture_name)
    render_result = RenderCVTypstRenderer().render(
        recruiter_document=recruiter_document,
        source_document=source_document,
        output_path=tmp_path / f"{fixture_name}.pdf",
        policy=policy,
    )
    qa_result = RecruiterQualityQA().evaluate(
        render_result=render_result,
        recruiter_document=recruiter_document,
        source_document=source_document,
        policy=policy,
    )

    assert qa_result.valid
    assert qa_result.page_count == 1


@pytest.mark.parametrize(
    "fixture_name",
    ["recruiter_software", "recruiter_tech_operations"],
)
def test_golden_ground_truth_survives_two_extractors(fixture_name, tmp_path):
    policy = load_recruiter_policy("config/recruiter_policy.yaml")
    recruiter_document, source_document = _load_golden_fixture(fixture_name)
    output = tmp_path / f"{fixture_name}.pdf"
    RenderCVTypstRenderer().render(
        recruiter_document=recruiter_document,
        source_document=source_document,
        output_path=output,
        policy=policy,
    )

    pypdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(output).pages)
    document = pymupdf.open(output)
    try:
        pymupdf_text = "\n".join(page.get_text() for page in document)
    finally:
        document.close()

    claims_by_id = {claim.claim_id: claim.text for claim in source_document.claims}
    for claim_id in recruiter_document.all_claim_ids():
        ground_truth = claims_by_id[claim_id]
        assert ground_truth in pypdf_text
        assert ground_truth in pymupdf_text

    for group in recruiter_document.technology_groups:
        label = policy.skill_groups[group.label_id].labels[recruiter_document.language]
        assert label in pypdf_text
        assert label in pymupdf_text
