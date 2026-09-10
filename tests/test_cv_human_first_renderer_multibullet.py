from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from app.cv.ats.parser import LocalResumeParser
from app.cv.ats.policy import load_ats_roundtrip_policy
from app.cv.ats.roundtrip_qa import ATSRoundTripQA
from app.cv.layout import load_layout_profiles
from app.cv.models import CVClaim, CVDocumentModel, ClaimProvenance
from app.cv.recruiter_models import RecruiterExperienceEntry, RecruiterProjectEntry
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.recruiter_qa import RecruiterQualityQA
from app.cv.render_policy import load_render_policy
from app.cv.renderers.reportlab_human import ReportLabHumanRenderer
from app.cv.visual_policy import load_visual_policy
from app.cv.visual_qa import VisualQualityQA
from test_recruiter_renderer import _recruiter_document, _source_document


def _two_bullet_documents() -> tuple[object, CVDocumentModel]:
    source = _source_document()
    project_second = CVClaim(
        claim_id="approved:project-1-bullet-2",
        section="projects",
        kind="bullet",
        text="Connected React, FastAPI and PostGIS into one inspectable delivery path.",
    )
    experience_second = CVClaim(
        claim_id="approved:employment-1-bullet-2",
        section="experience",
        kind="bullet",
        text="Turned recurring operational decisions into a deterministic workflow.",
    )

    payload = source.model_dump(mode="python")
    payload["claims"] = [
        *payload["claims"],
        project_second.model_dump(mode="python"),
        experience_second.model_dump(mode="python"),
    ]
    payload["provenance_map"] = {
        **payload["provenance_map"],
        project_second.claim_id: ClaimProvenance(
            fact_ids=["fact:project-1", "fact:python"],
        ).model_dump(mode="python"),
        experience_second.claim_id: ClaimProvenance(
            fact_ids=["fact:employment-1"],
        ).model_dump(mode="python"),
    }
    source_document = CVDocumentModel.model_validate(payload)

    recruiter_document = _recruiter_document().model_copy(
        update={
            "project_entries": [
                RecruiterProjectEntry(
                    primary_claim_id="fact:project-1",
                    bullet_claim_ids=[
                        "approved:project-1-bullet",
                        project_second.claim_id,
                    ],
                ),
                RecruiterProjectEntry(primary_claim_id="fact:project-2"),
            ],
            "experience_entries": [
                RecruiterExperienceEntry(
                    primary_claim_id="fact:employment-1",
                    bullet_claim_ids=[
                        "approved:employment-1-bullet",
                        experience_second.claim_id,
                    ],
                )
            ],
        }
    )
    return recruiter_document, source_document


def test_human_renderer_preserves_two_bullet_dogfood_contract_and_shared_qa(
    tmp_path: Path,
) -> None:
    recruiter_document, source_document = _two_bullet_documents()
    profile = load_layout_profiles("config/layout_profiles.yaml")["technical_clean"]

    result = ReportLabHumanRenderer().render(
        recruiter_document=recruiter_document,
        source_document=source_document,
        output_path=tmp_path / "human-two-bullets.pdf",
        policy=load_recruiter_policy("config/recruiter_policy.yaml"),
        layout_profile=profile,
    )

    text = "\n".join(page.extract_text() or "" for page in PdfReader(result.artifact.path).pages)
    project_first = "Auditable spatial workflows with deterministic map state."
    project_second = "Connected React, FastAPI and PostGIS into one inspectable delivery path."
    experience_first = "Improved inventory and workflow visibility."
    experience_second = "Turned recurring operational decisions into a deterministic workflow."

    for expected in (project_first, project_second, experience_first, experience_second):
        assert expected in text

    assert text.index(project_first) < text.index(project_second)
    assert text.index(experience_first) < text.index(experience_second)

    structural = RecruiterQualityQA().evaluate(
        result,
        recruiter_document,
        source_document,
        load_render_policy("config/render_policy.yaml"),
    )
    assert structural.valid, [issue.code for issue in structural.errors]

    visual = VisualQualityQA().evaluate(
        result,
        recruiter_document,
        source_document,
        profile,
        load_visual_policy("config/visual_policy.yaml"),
    )
    assert visual.valid, [issue.code for issue in visual.errors]

    parsed = LocalResumeParser().parse(result.artifact.path)
    ats = ATSRoundTripQA().evaluate(
        recruiter_document=recruiter_document,
        source_document=source_document,
        parsed_resume=parsed,
        policy=load_ats_roundtrip_policy("config/ats_roundtrip_policy.yaml"),
    )
    assert ats.valid, [issue.code for issue in ats.errors]
