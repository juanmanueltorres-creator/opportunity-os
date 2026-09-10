from __future__ import annotations

from pathlib import Path

from app.cv.narrative.models import NarrativeQAResult
from app.cv.recruiter_models import RecruiterQAResult
from app.cv.models import ValidationIssue
from test_cv_service_ats_roundtrip import (
    RecordingATSQA,
    RecordingParser,
    _ats_result,
    _prepare,
    _service,
)
from test_cv_service_narrative_gate import (
    PassingVisualQA,
    _service as _narrative_service,
)
from test_cv_service_ats_roundtrip import RecordingRenderer
from test_cv_service import LANGUAGE_DECISION, NOW, _assessment, _inputs


def test_successful_preparation_emits_complete_v2_audit_bundle(tmp_path: Path) -> None:
    ats_result = _ats_result(aggregate=0.97)
    service = _service(
        parser=RecordingParser(),
        ats_qa=RecordingATSQA(ats_result),
    )

    result = _prepare(service, tmp_path)

    assert result.status == "PREPARED"
    assert result.packet is not None
    packet = result.packet
    assert packet.packet_schema_version == "application-packet-v2"
    assert packet.strategy is not None
    assert packet.strategy_version == packet.strategy.strategy_version
    assert packet.strategy.target_role == _assessment().opportunity.title
    assert packet.strategy.target_company == _assessment().opportunity.company
    assert packet.narrative_policy_version == service.narrative_policy.version
    assert packet.layout_profile_id == "technical_clean"
    assert packet.layout_profile_version == service.layout_profiles["technical_clean"].version
    assert packet.narrative_qa is not None and packet.narrative_qa.valid
    assert packet.visual_qa is not None and packet.visual_qa.valid
    assert packet.ats_policy_version == ats_result.policy_version
    assert packet.ats_qa == ats_result


def test_reduction_persists_narrative_qa_from_final_recruiter_document(
    monkeypatch,
    tmp_path: Path,
) -> None:
    master, catalog, policy = _inputs()

    class DistinctNarrativeQA:
        def __init__(self) -> None:
            self.calls = 0
            self.results: list[NarrativeQAResult] = []

        def evaluate(self, **kwargs):
            self.calls += 1
            result = NarrativeQAResult(
                valid=True,
                core_message_coverage={"positioning": 1.0},
                off_strategy_claim_ratio=0.0,
                competing_identity_count=0,
                scanability_score=0.80 if self.calls == 1 else 0.99,
                warnings=(
                    [
                        ValidationIssue(
                            code="narrative_initial_fixture_warning",
                            message="initial recruiter document fixture warning",
                        )
                    ]
                    if self.calls == 1
                    else []
                ),
            )
            self.results.append(result)
            return result

    class ReduceOnceRecruiterQA:
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
                            message="fixture reducible overflow",
                        )
                    ],
                )
            return RecruiterQAResult(valid=True, page_count=1)

    def remove_contact(document, recruiter_policy, step):
        return document.model_copy(update={"contact_claim_ids": []})

    narrative_qa = DistinctNarrativeQA()
    monkeypatch.setattr("app.cv.service.reduce_recruiter_document", remove_contact)
    service = _narrative_service(
        narrative_qa=narrative_qa,
        recruiter_renderer=RecordingRenderer(),
        recruiter_qa=ReduceOnceRecruiterQA(),
        visual_qa=PassingVisualQA(),
    )

    result = service.prepare(
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
    assert len(narrative_qa.results) == 2
    assert result.packet.packet_schema_version == "application-packet-v2"
    assert result.packet.narrative_qa == narrative_qa.results[-1]
    assert result.packet.narrative_qa != narrative_qa.results[0]
    assert result.packet.narrative_qa.scanability_score == 0.99
