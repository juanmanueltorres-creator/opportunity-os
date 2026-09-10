from __future__ import annotations

import inspect
from pathlib import Path

from pypdf import PdfReader

from app.cv.layout import load_layout_profiles
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.renderers.base import RecruiterRenderer
from test_recruiter_renderer import _recruiter_document, _source_document


def _human_renderer():
    from app.cv.renderers.reportlab_human import ReportLabHumanRenderer

    return ReportLabHumanRenderer()


def _profile(profile_id: str = "technical_clean"):
    return load_layout_profiles("config/layout_profiles.yaml")[profile_id]


def _policy():
    return load_recruiter_policy("config/recruiter_policy.yaml")


def _extract_text(path: str | Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def test_recruiter_renderer_protocol_requires_layout_profile() -> None:
    parameters = inspect.signature(RecruiterRenderer.render).parameters
    assert "layout_profile" in parameters


def test_human_first_renderer_emits_one_page_with_selected_claims(tmp_path: Path) -> None:
    recruiter_document = _recruiter_document()
    source_document = _source_document()

    result = _human_renderer().render(
        recruiter_document=recruiter_document,
        source_document=source_document,
        output_path=tmp_path / "human.pdf",
        policy=_policy(),
        layout_profile=_profile(),
    )

    reader = PdfReader(result.artifact.path)
    assert len(reader.pages) == 1
    assert result.artifact.renderer_version == "reportlab-human-v1"
    assert result.metrics.body_font_size >= 9.0

    extracted = _extract_text(result.artifact.path)
    claims_by_id = {claim.claim_id: claim.text for claim in source_document.claims}
    for claim_id in recruiter_document.all_claim_ids():
        assert claims_by_id[claim_id] in extracted


def test_human_first_renderer_is_byte_deterministic(tmp_path: Path) -> None:
    renderer = _human_renderer()
    recruiter_document = _recruiter_document()
    source_document = _source_document()
    profile = _profile()
    policy = _policy()

    first = renderer.render(
        recruiter_document,
        source_document,
        tmp_path / "first.pdf",
        policy,
        profile,
    )
    second = renderer.render(
        recruiter_document,
        source_document,
        tmp_path / "second.pdf",
        policy,
        profile,
    )

    assert (tmp_path / "first.pdf").read_bytes() == (tmp_path / "second.pdf").read_bytes()
    assert first.artifact.sha256 == second.artifact.sha256
