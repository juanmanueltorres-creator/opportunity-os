from pathlib import Path

import pytest
from pydantic import ValidationError

from app.cv.models import RenderedCVArtifact
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterExperienceEntry,
    RecruiterRenderMetrics,
    RecruiterRenderResult,
    TechnologyGroup,
)


def test_recruiter_document_carries_claim_ids_not_free_candidate_text():
    document = RecruiterDocumentModel(
        document_version="recruiter-doc-v1",
        source_cv_document_version="cvdoc-v1",
        language="en",
        identity_claim_id="fact:name",
        headline_claim_id="fact:role",
        contact_claim_ids=["fact:email", "fact:phone"],
        profile_claim_ids=["approved:summary"],
        technology_groups=[
            TechnologyGroup(
                label_id="software_data",
                skill_claim_ids=["fact:python"],
            )
        ],
        selected_project_claim_ids=["fact:project-1"],
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

    assert document.headline_claim_id == "fact:role"
    assert "fact:python" in document.all_claim_ids()
    assert not hasattr(document, "headline_text")


def test_technology_group_rejects_more_than_twenty_four_skill_claims():
    with pytest.raises(ValidationError):
        TechnologyGroup(
            label_id="software_data",
            skill_claim_ids=[f"fact:skill-{index}" for index in range(25)],
        )


def test_experience_entry_rejects_more_than_one_visible_bullet():
    with pytest.raises(ValidationError):
        RecruiterExperienceEntry(
            primary_claim_id="fact:employment-1",
            bullet_claim_ids=["approved:bullet-1", "approved:bullet-2"],
        )


def test_render_metrics_can_represent_subthreshold_font_for_qa():
    metrics = RecruiterRenderMetrics(
        body_font_size=8.9,
        headline_line_count=1,
        overflow_detected=False,
    )

    assert metrics.body_font_size == 8.9


def test_render_result_carries_artifact_and_metrics(tmp_path: Path):
    artifact = RenderedCVArtifact(
        path=str(tmp_path / "cv.pdf"),
        sha256="a" * 64,
        renderer_version="rendercv-typst-v1",
    )
    result = RecruiterRenderResult(
        artifact=artifact,
        metrics=RecruiterRenderMetrics(
            body_font_size=9.4,
            headline_line_count=1,
            overflow_detected=False,
        ),
    )

    assert result.artifact.renderer_version == "rendercv-typst-v1"
    assert result.metrics.body_font_size == 9.4
