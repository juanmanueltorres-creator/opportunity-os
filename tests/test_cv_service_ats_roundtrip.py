from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.cv.ats.models import ATSRoundTripQAResult, ParsedResume
from app.cv.ats.policy import load_ats_roundtrip_policy
from app.cv.models import ApplicationPacket, RenderedCVArtifact, ValidationIssue
from app.cv.recruiter_models import RecruiterQAResult, RecruiterRenderMetrics, RecruiterRenderResult
from app.cv.service import CVPreparationService
from app.cv.visual_models import VisualMetrics, VisualQAResult
from test_cv_models import sample_packet
from test_cv_service import LANGUAGE_DECISION, NOW, _assessment, _inputs, _resolver


class RecordingRenderer:
    renderer_version = "ats-gate-fixture"

    def __init__(self, events: list[str] | None = None) -> None:
        self.events = events

    def render(self, recruiter_document, source_document, output_path, policy, layout_profile):
        if self.events is not None:
            self.events.append("render")
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = b"deterministic-ats-gate-fixture"
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


class RecordingRecruiterQA:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def evaluate(self, render_result, recruiter_document, source_document, render_policy):
        self.events.append("structural")
        return RecruiterQAResult(valid=True, page_count=1, extracted_text="fixture")


class RecordingVisualQA:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def evaluate(self, render_result, recruiter_document, source_document, layout_profile, policy):
        self.events.append("visual")
        return VisualQAResult(
            valid=True,
            metrics=VisualMetrics(
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
            ),
        )


class RecordingParser:
    parser_version = "fixture-parser-v1"

    def __init__(self, events: list[str] | None = None, *, error: Exception | None = None) -> None:
        self.events = events
        self.error = error

    def parse(self, pdf_path):
        if self.events is not None:
            self.events.append("parse")
        if self.error is not None:
            raise self.error
        return ParsedResume(
            parser_version=self.parser_version,
            identity="Alex Example",
            headline="GIS Developer",
            contacts=["alex@example.test"],
            technology=["PostGIS"],
            extracted_text="fixture",
        )


class RecordingATSQA:
    def __init__(self, result: ATSRoundTripQAResult, events: list[str] | None = None, *, error: Exception | None = None) -> None:
        self.result = result
        self.events = events
        self.error = error

    def evaluate(self, *, recruiter_document, source_document, parsed_resume, policy):
        if self.events is not None:
            self.events.append("ats")
        if self.error is not None:
            raise self.error
        return self.result


def _ats_result(*, aggregate: float = 1.0, errors=(), warnings=()) -> ATSRoundTripQAResult:
    policy = load_ats_roundtrip_policy("config/ats_roundtrip_policy.yaml")
    return ATSRoundTripQAResult(
        valid=not errors,
        parser_version="fixture-parser-v1",
        policy_version=policy.version,
        categories={},
        aggregate_recovery_ratio=aggregate,
        errors=list(errors),
        warnings=list(warnings),
    )


def _service(*, parser, ats_qa, events: list[str] | None = None, application_id: str = "app-ats") -> CVPreparationService:
    policy = load_ats_roundtrip_policy("config/ats_roundtrip_policy.yaml")
    event_log = events if events is not None else []
    return CVPreparationService(
        taxonomy_resolver=_resolver(),
        id_factory=lambda: application_id,
        recruiter_renderer=RecordingRenderer(event_log),
        recruiter_qa=RecordingRecruiterQA(event_log),
        visual_qa=RecordingVisualQA(event_log),
        ats_parser=parser,
        ats_qa=ats_qa,
        ats_policy=policy,
        track_layout_map={"tech": "technical_clean"},
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


def test_historical_packet_remains_valid_without_ats_fields() -> None:
    payload = sample_packet().model_dump(mode="json", exclude_none=True)

    restored = ApplicationPacket.model_validate(payload)

    assert "ats_policy_version" not in restored.model_dump(mode="json", exclude_none=True)
    assert "ats_qa" not in restored.model_dump(mode="json", exclude_none=True)


def test_ats_packet_fields_are_typed_and_must_be_present_together() -> None:
    base = sample_packet().model_dump(mode="json", exclude_none=True)
    ats_result = _ats_result()
    policy = load_ats_roundtrip_policy("config/ats_roundtrip_policy.yaml")

    with pytest.raises(ValidationError):
        ApplicationPacket.model_validate({**base, "ats_policy_version": policy.version})
    with pytest.raises(ValidationError):
        ApplicationPacket.model_validate({**base, "ats_qa": ats_result.model_dump(mode="json")})

    packet = ApplicationPacket.model_validate(
        {
            **base,
            "ats_policy_version": policy.version,
            "ats_qa": ats_result.model_dump(mode="json"),
        }
    )
    assert packet.ats_policy_version == policy.version
    assert packet.ats_qa is not None
    assert packet.ats_qa.parser_version == "fixture-parser-v1"


def test_ats_gate_runs_after_structural_and_visual_qa_before_prepared(tmp_path: Path) -> None:
    events: list[str] = []
    parser = RecordingParser(events)
    ats_qa = RecordingATSQA(_ats_result(), events)

    result = _prepare(_service(parser=parser, ats_qa=ats_qa, events=events), tmp_path)

    assert result.status == "PREPARED"
    assert events == ["render", "structural", "visual", "parse", "ats"]


def test_ats_parser_exception_is_bounded_and_removes_pdf(tmp_path: Path) -> None:
    parser = RecordingParser(error=ValueError("private parser internals must not escape"))
    result = _prepare(_service(parser=parser, ats_qa=RecordingATSQA(_ats_result())), tmp_path)

    assert result.status == "BLOCKED_RENDER"
    assert [item.code for item in result.errors] == ["ats_roundtrip_qa_failed"]
    assert "private parser internals" not in result.errors[0].message
    assert list(tmp_path.rglob("*.pdf")) == []


def test_ats_qa_exception_is_bounded_and_removes_pdf(tmp_path: Path) -> None:
    ats_qa = RecordingATSQA(
        _ats_result(),
        error=ValueError("private QA internals must not escape"),
    )
    result = _prepare(_service(parser=RecordingParser(), ats_qa=ats_qa), tmp_path)

    assert result.status == "BLOCKED_RENDER"
    assert [item.code for item in result.errors] == ["ats_roundtrip_qa_failed"]
    assert "private QA internals" not in result.errors[0].message
    assert list(tmp_path.rglob("*.pdf")) == []


def test_ats_recovery_failure_preserves_precise_issue_code_and_removes_pdf(tmp_path: Path) -> None:
    error = ValidationIssue(
        code="ats_roundtrip_skill_recovery_low",
        message="ATS round-trip recovery below threshold for skills",
    )
    result = _prepare(
        _service(
            parser=RecordingParser(),
            ats_qa=RecordingATSQA(_ats_result(aggregate=0.8, errors=[error])),
        ),
        tmp_path,
    )

    assert result.status == "BLOCKED_RENDER"
    assert [item.code for item in result.errors] == ["ats_roundtrip_skill_recovery_low"]
    assert list(tmp_path.rglob("*.pdf")) == []


def test_successful_preparation_persists_ats_policy_and_result(tmp_path: Path) -> None:
    qa_result = _ats_result(aggregate=0.97)
    result = _prepare(
        _service(parser=RecordingParser(), ats_qa=RecordingATSQA(qa_result)),
        tmp_path,
    )

    assert result.status == "PREPARED"
    assert result.packet is not None
    assert result.packet.ats_policy_version == qa_result.policy_version
    assert result.packet.ats_qa == qa_result


def test_packet_hash_changes_when_ats_result_changes(tmp_path: Path) -> None:
    first = _prepare(
        _service(
            parser=RecordingParser(),
            ats_qa=RecordingATSQA(_ats_result(aggregate=1.0)),
            application_id="app-hash",
        ),
        tmp_path / "first",
    )
    second = _prepare(
        _service(
            parser=RecordingParser(),
            ats_qa=RecordingATSQA(_ats_result(aggregate=0.99)),
            application_id="app-hash",
        ),
        tmp_path / "second",
    )

    assert first.status == second.status == "PREPARED"
    assert first.packet is not None and second.packet is not None
    assert first.packet.cv_sha256 == second.packet.cv_sha256
    assert first.packet.packet_sha256 != second.packet.packet_sha256
