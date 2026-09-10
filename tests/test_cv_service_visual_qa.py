from __future__ import annotations

import hashlib
from pathlib import Path

from app.cv.models import RenderedCVArtifact, ValidationIssue
from app.cv.narrative.models import NarrativeQAResult
from app.cv.recruiter_models import RecruiterQAResult, RecruiterRenderMetrics, RecruiterRenderResult
from app.cv.service import CVPreparationService
from app.cv.visual_models import VisualMetrics, VisualQAResult
from app.cv.visual_policy import load_visual_policy
from test_cv_service import LANGUAGE_DECISION, NOW, _assessment, _inputs, _resolver


class CapturingRenderer:
    renderer_version = "visual-gate-fixture"

    def __init__(self) -> None:
        self.profile_ids: list[str] = []

    def render(self, recruiter_document, source_document, output_path, policy, layout_profile):
        self.profile_ids.append(layout_profile.id)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"fictional-render-{len(self.profile_ids)}".encode()
        path.write_bytes(payload)
        return RecruiterRenderResult(
            artifact=RenderedCVArtifact(
                path=str(path),
                sha256=hashlib.sha256(payload).hexdigest(),
                renderer_version=self.renderer_version,
            ),
            metrics=RecruiterRenderMetrics(
                body_font_size=9.4,
                headline_line_count=1,
                overflow_detected=False,
            ),
        )


class PassingRecruiterQA:
    def evaluate(self, render_result, recruiter_document, source_document, render_policy):
        return RecruiterQAResult(valid=True, page_count=1, extracted_text="fixture")


def _metrics() -> VisualMetrics:
    return VisualMetrics(
        page_count=1,
        content_bottom_ratio=0.75,
        largest_internal_gap_ratio=0.05,
        nonempty_line_count=24,
        lines_per_page_inch=2.1,
        max_text_block_lines=3,
        max_text_block_chars=120,
        headline_line_count=1,
        body_font_size=9.4,
        observed_font_size_levels=[9.4, 12.0, 16.0],
    )


def _visual_result(*, errors=(), warnings=()) -> VisualQAResult:
    return VisualQAResult(
        valid=not errors,
        metrics=_metrics(),
        errors=list(errors),
        warnings=list(warnings),
    )


class PassingVisualQA:
    def __init__(self, *, warnings=()) -> None:
        self.calls = 0
        self.profile_ids: list[str] = []
        self.warnings = list(warnings)

    def evaluate(self, render_result, recruiter_document, source_document, layout_profile, policy):
        self.calls += 1
        self.profile_ids.append(layout_profile.id)
        return _visual_result(warnings=self.warnings)


class FailingVisualQA:
    def __init__(self, *codes: str) -> None:
        self.calls = 0
        self.codes = codes

    def evaluate(self, render_result, recruiter_document, source_document, layout_profile, policy):
        self.calls += 1
        return _visual_result(
            errors=[ValidationIssue(code=code, message="fictional visual failure") for code in self.codes]
        )


class FailOnceVisualQA:
    def __init__(self, code: str) -> None:
        self.code = code
        self.calls = 0
        self.profile_ids: list[str] = []

    def evaluate(self, render_result, recruiter_document, source_document, layout_profile, policy):
        self.calls += 1
        self.profile_ids.append(layout_profile.id)
        if self.calls == 1:
            return _visual_result(
                errors=[ValidationIssue(code=self.code, message="fictional reducible visual failure")]
            )
        return _visual_result()


class RaisingVisualQA:
    def evaluate(self, render_result, recruiter_document, source_document, layout_profile, policy):
        raise ValueError("private extracted visual detail must not escape")


class NarrativePassThenFail:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, recruiter_document, source_document, strategy, policy):
        self.calls += 1
        if self.calls == 1:
            return NarrativeQAResult(
                valid=True,
                off_strategy_claim_ratio=0.0,
                competing_identity_count=0,
                scanability_score=1.0,
            )
        return NarrativeQAResult(
            valid=False,
            off_strategy_claim_ratio=0.0,
            competing_identity_count=0,
            scanability_score=0.0,
            errors=[ValidationIssue(code="narrative_regression", message="fictional narrative failure")],
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


def _service(*, visual_qa, renderer=None, narrative_qa=None) -> CVPreparationService:
    kwargs = {
        "taxonomy_resolver": _resolver(),
        "id_factory": lambda: "app-visual",
        "recruiter_renderer": renderer or CapturingRenderer(),
        "recruiter_qa": PassingRecruiterQA(),
        "visual_qa": visual_qa,
        "visual_policy": load_visual_policy("config/visual_policy.yaml"),
        "track_layout_map": {"tech": "technical_clean"},
    }
    if narrative_qa is not None:
        kwargs["narrative_qa"] = narrative_qa
    return CVPreparationService(**kwargs)


def test_visual_pass_is_required_before_prepared(tmp_path: Path) -> None:
    visual = PassingVisualQA()
    result = _prepare(_service(visual_qa=visual), tmp_path)

    assert result.status == "PREPARED"
    assert visual.calls == 1
    assert visual.profile_ids == ["technical_clean"]


def test_visual_warning_propagates_without_blocking(tmp_path: Path) -> None:
    warning = ValidationIssue(code="visual_density_high", message="fictional visual warning")
    result = _prepare(_service(visual_qa=PassingVisualQA(warnings=[warning])), tmp_path)

    assert result.status == "PREPARED"
    assert "visual_density_high" in {item.code for item in result.warnings}


def test_nonreducible_visual_failure_blocks_and_removes_pdf(tmp_path: Path) -> None:
    result = _prepare(
        _service(visual_qa=FailingVisualQA("visual_content_underfilled")),
        tmp_path,
    )

    assert result.status == "BLOCKED_RENDER"
    assert "visual_content_underfilled" in {item.code for item in result.errors}
    assert list(tmp_path.rglob("*.pdf")) == []


def test_visual_qa_exception_is_bounded_and_removes_pdf(tmp_path: Path) -> None:
    result = _prepare(_service(visual_qa=RaisingVisualQA()), tmp_path)

    assert result.status == "BLOCKED_RENDER"
    assert [item.code for item in result.errors] == ["visual_qa_failed"]
    assert "private extracted visual detail" not in result.errors[0].message
    assert list(tmp_path.rglob("*.pdf")) == []


def test_reducible_visual_failure_reduces_and_reuses_same_layout(monkeypatch, tmp_path: Path) -> None:
    def remove_contact(document, recruiter_policy, step):
        return document.model_copy(update={"contact_claim_ids": []})

    monkeypatch.setattr("app.cv.service.reduce_recruiter_document", remove_contact)
    renderer = CapturingRenderer()
    visual = FailOnceVisualQA("visual_overcompressed")
    result = _prepare(_service(visual_qa=visual, renderer=renderer), tmp_path)

    assert result.status == "PREPARED"
    assert visual.calls == 2
    assert visual.profile_ids == ["technical_clean", "technical_clean"]
    assert renderer.profile_ids == ["technical_clean", "technical_clean"]


def test_wall_of_text_severe_is_reducible(monkeypatch, tmp_path: Path) -> None:
    def remove_contact(document, recruiter_policy, step):
        return document.model_copy(update={"contact_claim_ids": []})

    monkeypatch.setattr("app.cv.service.reduce_recruiter_document", remove_contact)
    visual = FailOnceVisualQA("visual_wall_of_text_severe")
    result = _prepare(_service(visual_qa=visual), tmp_path)

    assert result.status == "PREPARED"
    assert visual.calls == 2


def test_mixed_reducible_and_nonreducible_visual_errors_block_without_reduction(monkeypatch, tmp_path: Path) -> None:
    reductions = 0

    def reduction_must_not_run(document, recruiter_policy, step):
        nonlocal reductions
        reductions += 1
        return document

    monkeypatch.setattr("app.cv.service.reduce_recruiter_document", reduction_must_not_run)
    visual = FailingVisualQA("visual_overcompressed", "visual_orphan_heading")
    result = _prepare(_service(visual_qa=visual), tmp_path)

    assert result.status == "BLOCKED_RENDER"
    assert reductions == 0
    assert visual.calls == 1


def test_reduction_rechecks_narrative_before_accepting_visual_retry(monkeypatch, tmp_path: Path) -> None:
    def remove_contact(document, recruiter_policy, step):
        return document.model_copy(update={"contact_claim_ids": []})

    monkeypatch.setattr("app.cv.service.reduce_recruiter_document", remove_contact)
    narrative = NarrativePassThenFail()
    visual = FailOnceVisualQA("visual_overcompressed")
    result = _prepare(
        _service(visual_qa=visual, narrative_qa=narrative),
        tmp_path,
    )

    assert result.status == "BLOCKED_VALIDATION"
    assert "narrative_regression" in {item.code for item in result.errors}
    assert narrative.calls == 2
    assert visual.calls == 1
    assert list(tmp_path.rglob("*.pdf")) == []
