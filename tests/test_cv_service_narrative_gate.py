import hashlib
from pathlib import Path

from app.cv.models import RenderedCVArtifact, ValidationIssue
from app.cv.narrative.models import NarrativeQAResult
from app.cv.recruiter_models import (
    RecruiterQAResult,
    RecruiterRenderMetrics,
    RecruiterRenderResult,
)
from app.cv.service import CVPreparationService
from app.cv.strategy.policy import load_narrative_policy
from app.cv.visual_models import VisualMetrics, VisualQAResult
from cv_ats_test_doubles import PassingATSParser, PassingATSQA
from test_cv_service import LANGUAGE_DECISION, NOW, _assessment, _inputs, _resolver


class RendererMustNotRun:
    renderer_version = "never"

    def render(self, *args, **kwargs):
        raise AssertionError("renderer must not run after narrative validation failure")


class FailingNarrativeQA:
    def evaluate(self, **kwargs):
        return NarrativeQAResult(
            valid=False,
            core_message_coverage={"positioning": 1.0, "requirement:postgis": 0.0},
            off_strategy_claim_ratio=0.0,
            competing_identity_count=0,
            scanability_score=0.5,
            errors=[
                ValidationIssue(
                    code="narrative_scanability_below_threshold",
                    message="fictional narrative hard failure",
                )
            ],
        )


class WarningNarrativeQA:
    def evaluate(self, **kwargs):
        return NarrativeQAResult(
            valid=True,
            core_message_coverage={"positioning": 1.0, "requirement:postgis": 1.0},
            off_strategy_claim_ratio=0.0,
            competing_identity_count=0,
            scanability_score=1.0,
            warnings=[
                ValidationIssue(
                    code="narrative_generic_claim_detected",
                    message="fictional narrative warning",
                )
            ],
        )


class PassingVisualQA:
    def evaluate(self, render_result, recruiter_document, source_document, layout_profile, policy):
        return VisualQAResult(
            valid=True,
            metrics=VisualMetrics(
                page_count=1,
                content_bottom_ratio=0.75,
                largest_internal_gap_ratio=0.10,
                nonempty_line_count=20,
                lines_per_page_inch=2.5,
                max_text_block_lines=4,
                max_text_block_chars=120,
                headline_line_count=1,
                body_font_size=9.4,
                observed_font_size_levels=[9.4, 12.0],
            ),
        )


def _service(
    *,
    narrative_qa,
    recruiter_renderer=None,
    recruiter_qa=None,
    visual_qa=None,
) -> CVPreparationService:
    kwargs = {
        "taxonomy_resolver": _resolver(),
        "id_factory": lambda: "app-narrative",
        "narrative_policy": load_narrative_policy("config/narrative_policy.yaml"),
        "narrative_qa": narrative_qa,
    }
    if recruiter_renderer is not None:
        kwargs["recruiter_renderer"] = recruiter_renderer
        kwargs["ats_parser"] = PassingATSParser()
        kwargs["ats_qa"] = PassingATSQA()
    if recruiter_qa is not None:
        kwargs["recruiter_qa"] = recruiter_qa
    if visual_qa is not None:
        kwargs["visual_qa"] = visual_qa
    return CVPreparationService(**kwargs)


def test_narrative_hard_failure_blocks_before_renderer(tmp_path: Path) -> None:
    master, catalog, policy = _inputs()

    result = _service(
        narrative_qa=FailingNarrativeQA(),
        recruiter_renderer=RendererMustNotRun(),
    ).prepare(
        assessment=_assessment(),
        master_facts=master,
        evidence_catalog=catalog,
        policy=policy,
        output_root=tmp_path,
        now=NOW,
        language_decision=LANGUAGE_DECISION,
    )

    assert result.status == "BLOCKED_VALIDATION"
    assert result.packet is None
    assert "narrative_scanability_below_threshold" in {
        issue.code for issue in result.errors
    }
    assert list(tmp_path.rglob("*.pdf")) == []


def test_narrative_warning_is_preserved_without_blocking(tmp_path: Path) -> None:
    master, catalog, policy = _inputs()

    result = _service(narrative_qa=WarningNarrativeQA()).prepare(
        assessment=_assessment(),
        master_facts=master,
        evidence_catalog=catalog,
        policy=policy,
        output_root=tmp_path,
        now=NOW,
        language_decision=LANGUAGE_DECISION,
    )

    assert result.status == "PREPARED"
    assert result.packet is not None
    assert "narrative_generic_claim_detected" in {
        issue.code for issue in result.warnings
    }


def test_reduction_rechecks_narrative_and_preserves_earlier_warnings(
    monkeypatch,
    tmp_path: Path,
) -> None:
    master, catalog, policy = _inputs()

    class CountingNarrativeQA:
        def __init__(self) -> None:
            self.calls = 0

        def evaluate(self, **kwargs):
            self.calls += 1
            warnings = []
            if self.calls == 1:
                warnings = [
                    ValidationIssue(
                        code="narrative_initial_warning",
                        message="warning from original recruiter document",
                    )
                ]
            return NarrativeQAResult(
                valid=True,
                core_message_coverage={"positioning": 1.0, "requirement:postgis": 1.0},
                off_strategy_claim_ratio=0.0,
                competing_identity_count=0,
                scanability_score=1.0,
                warnings=warnings,
            )

    class CountingRenderer:
        renderer_version = "rendercv-typst-v1"

        def __init__(self) -> None:
            self.calls = 0

        def render(
            self,
            recruiter_document,
            source_document,
            output_path,
            recruiter_policy,
            layout_profile,
        ):
            self.calls += 1
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = f"fictional recruiter pdf {self.calls}".encode()
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
                    overflow_detected=self.calls == 1,
                ),
            )

    class ReduceOnceRecruiterQA:
        def __init__(self) -> None:
            self.calls = 0

        def evaluate(self, render_result, recruiter_document, source_document, recruiter_policy):
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
            return RecruiterQAResult(valid=True, page_count=1)

    def remove_contact(document, recruiter_policy, step):
        return document.model_copy(update={"contact_claim_ids": []})

    narrative_qa = CountingNarrativeQA()
    renderer = CountingRenderer()
    recruiter_qa = ReduceOnceRecruiterQA()
    monkeypatch.setattr("app.cv.service.reduce_recruiter_document", remove_contact)

    result = _service(
        narrative_qa=narrative_qa,
        recruiter_renderer=renderer,
        recruiter_qa=recruiter_qa,
        visual_qa=PassingVisualQA(),
    ).prepare(
        assessment=_assessment(),
        master_facts=master,
        evidence_catalog=catalog,
        policy=policy,
        output_root=tmp_path,
        now=NOW,
        language_decision=LANGUAGE_DECISION,
    )

    assert result.status == "PREPARED"
    assert result.packet is not None
    assert narrative_qa.calls == 2
    assert renderer.calls == 2
    assert "narrative_initial_warning" in {warning.code for warning in result.warnings}
