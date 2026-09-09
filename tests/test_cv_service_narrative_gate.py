from pathlib import Path

from app.cv.models import ValidationIssue
from app.cv.narrative.models import NarrativeQAResult
from app.cv.service import CVPreparationService
from app.cv.strategy.policy import load_narrative_policy
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


def _service(*, narrative_qa, recruiter_renderer=None) -> CVPreparationService:
    kwargs = {
        "taxonomy_resolver": _resolver(),
        "id_factory": lambda: "app-narrative",
        "narrative_policy": load_narrative_policy("config/narrative_policy.yaml"),
        "narrative_qa": narrative_qa,
    }
    if recruiter_renderer is not None:
        kwargs["recruiter_renderer"] = recruiter_renderer
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
