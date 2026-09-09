from pathlib import Path

from app.cv.models import RenderedCVArtifact, ValidationIssue
from app.cv.recruiter_models import (
    RecruiterQAResult,
    RecruiterRenderMetrics,
    RecruiterRenderResult,
)
from app.cv.service import CVPreparationService
from test_cv_service import LANGUAGE_DECISION, NOW, _assessment, _inputs, _resolver


class CapturingRenderer:
    renderer_version = "capturing-layout-v1"

    def __init__(self) -> None:
        self.profile_ids: list[str] = []

    def render(
        self,
        recruiter_document,
        source_document,
        output_path,
        policy,
        layout_profile,
    ):
        self.profile_ids.append(layout_profile.id)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = b"fictional layout-aware recruiter pdf"
        path.write_bytes(payload)
        import hashlib

        return RecruiterRenderResult(
            artifact=RenderedCVArtifact(
                path=str(path),
                sha256=hashlib.sha256(payload).hexdigest(),
                renderer_version=self.renderer_version,
            ),
            metrics=RecruiterRenderMetrics(
                body_font_size=10.0,
                headline_line_count=1,
                overflow_detected=False,
            ),
        )


class PassingRecruiterQA:
    def evaluate(self, render_result, recruiter_document, source_document, render_policy):
        return RecruiterQAResult(
            valid=True,
            page_count=1,
            extracted_text="fictional layout-aware recruiter output",
        )


class FailOnceRecruiterQA:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, render_result, recruiter_document, source_document, render_policy):
        self.calls += 1
        if self.calls == 1:
            return RecruiterQAResult(
                valid=False,
                page_count=2,
                errors=[
                    ValidationIssue(
                        code="recruiter_one_page_failed",
                        message="fictional reducible overflow",
                    )
                ],
            )
        return RecruiterQAResult(
            valid=True,
            page_count=1,
            extracted_text="fictional reduced recruiter output",
        )


def _prepare(service: CVPreparationService, tmp_path: Path):
    master, catalog, policy = _inputs()
    return service.prepare(
        assessment=_assessment(),
        master_facts=master,
        evidence_catalog=catalog,
        policy=policy,
        output_root=tmp_path,
        now=NOW,
        language_decision=LANGUAGE_DECISION,
    )


def test_service_passes_injected_track_layout_to_renderer(tmp_path: Path) -> None:
    renderer = CapturingRenderer()
    result = _prepare(
        CVPreparationService(
            taxonomy_resolver=_resolver(),
            id_factory=lambda: "app-layout-map",
            recruiter_renderer=renderer,
            recruiter_qa=PassingRecruiterQA(),
            track_layout_map={"tech": "technical_clean"},
        ),
        tmp_path,
    )

    assert result.status == "PREPARED"
    assert renderer.profile_ids == ["technical_clean"]


def test_service_without_mapping_uses_compact_ats(tmp_path: Path) -> None:
    renderer = CapturingRenderer()
    result = _prepare(
        CVPreparationService(
            taxonomy_resolver=_resolver(),
            id_factory=lambda: "app-layout-default",
            recruiter_renderer=renderer,
            recruiter_qa=PassingRecruiterQA(),
        ),
        tmp_path,
    )

    assert result.status == "PREPARED"
    assert renderer.profile_ids == ["compact_ats"]


def test_service_invalid_mapped_profile_blocks_before_render(tmp_path: Path) -> None:
    renderer = CapturingRenderer()
    result = _prepare(
        CVPreparationService(
            taxonomy_resolver=_resolver(),
            id_factory=lambda: "app-layout-missing",
            recruiter_renderer=renderer,
            recruiter_qa=PassingRecruiterQA(),
            track_layout_map={"tech": "missing_profile"},
        ),
        tmp_path,
    )

    assert result.status == "BLOCKED_RENDER"
    assert result.packet is None
    assert result.errors[0].code == "layout_profile_unavailable"
    assert renderer.profile_ids == []
    assert list(tmp_path.rglob("*.pdf")) == []


def test_reduction_reuses_same_selected_layout_profile(tmp_path: Path) -> None:
    renderer = CapturingRenderer()
    qa = FailOnceRecruiterQA()
    result = _prepare(
        CVPreparationService(
            taxonomy_resolver=_resolver(),
            id_factory=lambda: "app-layout-reduction",
            recruiter_renderer=renderer,
            recruiter_qa=qa,
            track_layout_map={"tech": "operations_clean"},
        ),
        tmp_path,
    )

    assert result.status == "PREPARED"
    assert qa.calls == 2
    assert renderer.profile_ids == ["operations_clean", "operations_clean"]
