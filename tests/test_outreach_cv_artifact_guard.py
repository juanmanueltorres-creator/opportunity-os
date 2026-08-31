from __future__ import annotations

from types import SimpleNamespace

from app.cv.hashing import canonical_sha256
from app.outreach.preparation import application_packet_error


def _assessment_and_packet(*, renderer_version: str):
    opportunity_payload = {"id": "opp-1"}
    opportunity = SimpleNamespace(
        id="opp-1",
        model_dump=lambda mode: opportunity_payload,
    )
    assessment = SimpleNamespace(
        opportunity=opportunity,
        selected_intent="CAREER",
        best_career_track="tech",
        best_income_track=None,
        scoring_version="v0.2a1",
        extractor_version="rules-v1",
        alias_registry_version="aliases-v1",
        taxonomy_versions={},
    )
    packet = SimpleNamespace(
        opportunity_id="opp-1",
        opportunity_snapshot_hash=canonical_sha256(opportunity_payload),
        selected_intent="CAREER",
        application_track_id="tech",
        scoring_version="v0.2a1",
        extractor_version="rules-v1",
        alias_registry_version="aliases-v1",
        taxonomy_versions={},
        language_decision=SimpleNamespace(language="en"),
        cv_document=SimpleNamespace(language="en"),
        recruiter_policy_version="recruiter-policy-v1",
        renderer_version=renderer_version,
    )
    return assessment, packet


def test_legacy_cv_renderer_is_rejected_before_outreach() -> None:
    assessment, packet = _assessment_and_packet(renderer_version="ats-pdf-v2")

    assert application_packet_error(assessment, packet) == "cv_renderer_not_allowed"


def test_current_recruiter_renderer_remains_outreach_eligible() -> None:
    assessment, packet = _assessment_and_packet(renderer_version="rendercv-typst-v1")

    assert application_packet_error(assessment, packet) is None
