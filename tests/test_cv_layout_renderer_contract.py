from pathlib import Path

import pytest
from pypdf import PdfReader

from app.cv.layout import LayoutProfile, load_layout_profiles
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.renderers.rendercv_typst import RenderCVTypstRenderer
from test_recruiter_renderer import _recruiter_document, _source_document


def test_renderer_accepts_selected_layout_profile(tmp_path: Path) -> None:
    profile = load_layout_profiles("config/layout_profiles.yaml")["technical_clean"]
    result = RenderCVTypstRenderer().render(
        recruiter_document=_recruiter_document(),
        source_document=_source_document(),
        output_path=tmp_path / "technical.pdf",
        policy=load_recruiter_policy("config/recruiter_policy.yaml"),
        layout_profile=profile,
    )
    assert Path(result.artifact.path).is_file()


def test_renderer_rejects_missing_design(tmp_path: Path) -> None:
    profile = LayoutProfile(
        version="layout-profile-v1",
        id="technical_clean",
        design_path="config/layouts/missing.yaml",
        density="comfortable",
        emphasis="technical",
    )
    with pytest.raises(ValueError, match="RenderCV/Typst render failed"):
        RenderCVTypstRenderer().render(
            _recruiter_document(),
            _source_document(),
            tmp_path / "missing.pdf",
            load_recruiter_policy("config/recruiter_policy.yaml"),
            profile,
        )


def test_same_content_is_extractable_across_all_profiles(tmp_path: Path) -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    renderer = RenderCVTypstRenderer()
    policy = load_recruiter_policy("config/recruiter_policy.yaml")
    expected = ["Alex Example", "Software & Operations Developer", "Python", "SQL"]
    for profile in profiles.values():
        result = renderer.render(
            _recruiter_document(),
            _source_document(),
            tmp_path / f"{profile.id}.pdf",
            policy,
            profile,
        )
        text = "\n".join(
            page.extract_text() or "" for page in PdfReader(result.artifact.path).pages
        )
        assert all(value in text for value in expected)
