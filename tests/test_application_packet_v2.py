from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.cv.ats.models import ATSRoundTripQAResult
from app.cv.ats.policy import load_ats_roundtrip_policy
from app.cv.layout.models import LAYOUT_PROFILE_VERSION
from app.cv.models import ApplicationPacket
from app.cv.narrative.models import NarrativeQAResult
from app.cv.strategy.models import CoreMessage, CVStrategy, STRATEGY_VERSION
from app.cv.strategy.policy import NARRATIVE_POLICY_VERSION
from app.cv.visual_models import VisualMetrics, VisualQAResult
from test_cv_models import sample_packet


def _strategy() -> CVStrategy:
    return CVStrategy(
        strategy_version=STRATEGY_VERSION,
        application_track_id="tech",
        target_role="Software Developer",
        target_company="Example Labs",
        positioning="Software Developer",
        recruiter_question="Can this candidate deliver auditable software systems?",
        core_messages=[
            CoreMessage(
                id="delivery",
                message="Verified software delivery",
                fact_ids=["skill-python"],
                evidence_ids=["module-tech"],
                importance=1.0,
                reason="Direct verified evidence",
            )
        ],
        must_show_fact_ids=["skill-python"],
        supporting_fact_ids=[],
        optional_fact_ids=[],
        explicit_gaps=[],
        preferred_section_order=["skills", "projects", "experience"],
        preferred_layout_profile_id="technical_clean",
    )


def _narrative_qa(*, valid: bool = True) -> NarrativeQAResult:
    return NarrativeQAResult(
        valid=valid,
        core_message_coverage={"delivery": 1.0},
        off_strategy_claim_ratio=0.0,
        competing_identity_count=0,
        scanability_score=1.0,
    )


def _visual_qa(*, valid: bool = True) -> VisualQAResult:
    return VisualQAResult(
        valid=valid,
        metrics=VisualMetrics(
            page_count=1,
            content_bottom_ratio=0.75,
            largest_internal_gap_ratio=0.05,
            nonempty_line_count=20,
            lines_per_page_inch=2.0,
            max_text_block_lines=3,
            max_text_block_chars=120,
            headline_line_count=1,
            body_font_size=9.7,
            observed_font_size_levels=[9.7, 12.0, 16.0],
        ),
        errors=([] if valid else [{"code": "visual_fixture_failed", "message": "fixture"}]),
    )


def _ats_qa(*, valid: bool = True) -> ATSRoundTripQAResult:
    policy = load_ats_roundtrip_policy("config/ats_roundtrip_policy.yaml")
    return ATSRoundTripQAResult(
        valid=valid,
        parser_version="fixture-parser-v1",
        policy_version=policy.version,
        categories={},
        aggregate_recovery_ratio=1.0 if valid else 0.5,
        errors=([] if valid else [{"code": "ats_roundtrip_fixture_failed", "message": "fixture"}]),
    )


def _v2_payload() -> dict:
    ats_qa = _ats_qa()
    return {
        **sample_packet().model_dump(mode="json", exclude_none=True),
        "packet_schema_version": "application-packet-v2",
        "strategy_version": STRATEGY_VERSION,
        "strategy": _strategy().model_dump(mode="json"),
        "narrative_policy_version": NARRATIVE_POLICY_VERSION,
        "layout_profile_id": "technical_clean",
        "layout_profile_version": LAYOUT_PROFILE_VERSION,
        "narrative_qa": _narrative_qa().model_dump(mode="json"),
        "visual_qa": _visual_qa().model_dump(mode="json"),
        "ats_policy_version": ats_qa.policy_version,
        "ats_qa": ats_qa.model_dump(mode="json"),
    }


def test_historical_packet_without_schema_version_restores_as_v1() -> None:
    payload = sample_packet().model_dump(mode="json", exclude_none=True)
    payload.pop("packet_schema_version", None)

    restored = ApplicationPacket.model_validate(payload)

    assert restored.packet_schema_version == "application-packet-v1"


def test_explicit_v1_packet_accepts_historical_shape() -> None:
    payload = sample_packet().model_dump(mode="json", exclude_none=True)
    payload["packet_schema_version"] = "application-packet-v1"

    restored = ApplicationPacket.model_validate(payload)

    assert restored.packet_schema_version == "application-packet-v1"


def test_v1_rejects_partial_v2_audit_state() -> None:
    payload = sample_packet().model_dump(mode="json", exclude_none=True)
    payload["packet_schema_version"] = "application-packet-v1"
    payload["strategy_version"] = STRATEGY_VERSION

    with pytest.raises(ValidationError):
        ApplicationPacket.model_validate(payload)


def test_v2_requires_complete_audit_bundle() -> None:
    payload = sample_packet().model_dump(mode="json", exclude_none=True)
    payload["packet_schema_version"] = "application-packet-v2"

    with pytest.raises(ValidationError):
        ApplicationPacket.model_validate(payload)


def test_v2_audit_fields_restore_as_typed_models() -> None:
    restored = ApplicationPacket.model_validate(_v2_payload())

    assert restored.packet_schema_version == "application-packet-v2"
    assert restored.strategy.strategy_version == STRATEGY_VERSION
    assert restored.narrative_qa.scanability_score == 1.0
    assert restored.visual_qa.metrics.page_count == 1
    assert restored.ats_qa.valid is True


def test_v2_rejects_strategy_version_mismatch() -> None:
    payload = _v2_payload()
    payload["strategy_version"] = "cv-strategy-v999"

    with pytest.raises(ValidationError):
        ApplicationPacket.model_validate(payload)


def test_v2_rejects_unsupported_narrative_policy_version() -> None:
    payload = _v2_payload()
    payload["narrative_policy_version"] = "narrative-policy-v999"

    with pytest.raises(ValidationError):
        ApplicationPacket.model_validate(payload)


def test_v2_rejects_unsupported_layout_identity_or_version() -> None:
    unsupported_id = _v2_payload()
    unsupported_id["layout_profile_id"] = "decorative_two_column"
    with pytest.raises(ValidationError):
        ApplicationPacket.model_validate(unsupported_id)

    unsupported_version = _v2_payload()
    unsupported_version["layout_profile_version"] = "layout-profile-v999"
    with pytest.raises(ValidationError):
        ApplicationPacket.model_validate(unsupported_version)


def test_v2_rejects_failed_authoritative_qa_result() -> None:
    payload = _v2_payload()
    payload["narrative_qa"] = _narrative_qa(valid=False).model_dump(mode="json")

    with pytest.raises(ValidationError):
        ApplicationPacket.model_validate(payload)
