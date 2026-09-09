from pathlib import Path

from app.cv.recruiter_models import RecruiterQAResult
from app.cv.render_policy import RenderPolicy
from app.cv.service import CVPreparationService
from test_cv_service import LANGUAGE_DECISION, NOW, _assessment, _inputs, _resolver


class CapturingRecruiterQA:
    def __init__(self) -> None:
        self.policy = None

    def evaluate(self, render_result, recruiter_document, source_document, policy):
        self.policy = policy
        return RecruiterQAResult(valid=True, page_count=1)


def test_service_passes_injected_render_policy_to_recruiter_qa(tmp_path: Path) -> None:
    master, catalog, policy = _inputs()
    render_policy = RenderPolicy(
        version="render-policy-v1",
        page_size="A4",
        preferred_pages=1,
        max_pages=1,
        min_body_font_pt=9.0,
        preferred_body_font_pt=9.4,
    )
    recruiter_qa = CapturingRecruiterQA()

    result = CVPreparationService(
        taxonomy_resolver=_resolver(),
        id_factory=lambda: "app-render-policy",
        recruiter_qa=recruiter_qa,
        render_policy=render_policy,
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
    assert recruiter_qa.policy is render_policy
