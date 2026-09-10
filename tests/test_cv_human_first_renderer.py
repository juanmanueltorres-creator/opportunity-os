from __future__ import annotations

import inspect
from pathlib import Path

from pypdf import PdfReader

from app.cv.ats.parser import LocalResumeParser
from app.cv.ats.policy import load_ats_roundtrip_policy
from app.cv.ats.roundtrip_qa import ATSRoundTripQA
from app.cv.layout import load_layout_profiles
from app.cv.models import CVClaim, CVDocumentModel, ClaimProvenance
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.recruiter_qa import RecruiterQualityQA
from app.cv.render_policy import load_render_policy
from app.cv.renderers.base import RecruiterRenderer
from app.cv.visual_policy import load_visual_policy
from app.cv.visual_qa import VisualQualityQA
from test_recruiter_renderer import _recruiter_document, _source_document


_PROFILE_IDS = ("technical_clean", "operations_clean", "compact_ats")


def _human_renderer():
    from app.cv.renderers.reportlab_human import ReportLabHumanRenderer

    return ReportLabHumanRenderer()


def _profiles():
    return load_layout_profiles("config/layout_profiles.yaml")


def _profile(profile_id: str = "technical_clean"):
    return _profiles()[profile_id]


def _policy():
    return load_recruiter_policy("config/recruiter_policy.yaml")


def _extract_text(path: str | Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def _source_with_unselected_claim() -> CVDocumentModel:
    source = _source_document()
    payload = source.model_dump(mode="python")
    payload["claims"] = [
        *payload["claims"],
        CVClaim(
            claim_id="summary:unselected",
            section="summary",
            kind="summary",
            text="THIS UNSELECTED CLAIM MUST NEVER RENDER",
        ).model_dump(mode="python"),
    ]
    payload["provenance_map"] = {
        **payload["provenance_map"],
        "summary:unselected": ClaimProvenance(
            fact_ids=["fact-unselected"],
        ).model_dump(mode="python"),
    }
    return CVDocumentModel.model_validate(payload)


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


def test_human_first_renderer_passes_shared_quality_contracts(tmp_path: Path) -> None:
    recruiter_document = _recruiter_document()
    source_document = _source_document()
    profile = _profile()
    result = _human_renderer().render(
        recruiter_document,
        source_document,
        tmp_path / "shared-qa.pdf",
        _policy(),
        profile,
    )

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


def test_human_first_layout_profiles_change_presentation_not_content(tmp_path: Path) -> None:
    recruiter_document = _recruiter_document()
    source_document = _source_document()
    claims_by_id = {claim.claim_id: claim.text for claim in source_document.claims}
    hashes: set[str] = set()

    for profile_id in _PROFILE_IDS:
        result = _human_renderer().render(
            recruiter_document,
            source_document,
            tmp_path / f"{profile_id}.pdf",
            _policy(),
            _profile(profile_id),
        )
        hashes.add(result.artifact.sha256)
        extracted = _extract_text(result.artifact.path)
        for claim_id in recruiter_document.all_claim_ids():
            assert claims_by_id[claim_id] in extracted

    assert len(hashes) == len(_PROFILE_IDS)


def test_human_first_renderer_never_leaks_unselected_source_claims(tmp_path: Path) -> None:
    recruiter_document = _recruiter_document()
    source_document = _source_with_unselected_claim()

    result = _human_renderer().render(
        recruiter_document,
        source_document,
        tmp_path / "selected-only.pdf",
        _policy(),
        _profile(),
    )

    extracted = _extract_text(result.artifact.path)
    assert "THIS UNSELECTED CLAIM MUST NEVER RENDER" not in extracted
