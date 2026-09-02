from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.operator_bridge.models import OperatorObservation
from app.process_email.models import (
    EvidenceSpan,
    ProcessClassification,
    ProcessEmailPreview,
    ProcessEmailSelection,
    ProcessProjection,
    ProcessSignal,
)

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def _span(text: str = "invite you to an interview") -> EvidenceSpan:
    return EvidenceSpan(start=0, end=len(text), text=text)


def _signal(
    kind: str = "INTERVIEW_PROPOSED",
    *,
    confidence: str = "HIGH",
    reason_code: str = "INTERVIEW_INVITATION_EXPLICIT",
) -> ProcessSignal:
    return ProcessSignal(
        kind=kind,
        confidence=confidence,
        reason_code=reason_code,
        evidence_spans=[_span()],
    )


def _classification(
    *,
    disposition: str = "CLASSIFIED",
    signals: list[ProcessSignal] | None = None,
    warnings: list[str] | None = None,
) -> ProcessClassification:
    return ProcessClassification(
        disposition=disposition,
        classifier_version="deterministic-process-email-v1",
        ruleset_version="es-en-2026-09-v3",
        signals=[_signal()] if signals is None else signals,
        warnings=[] if warnings is None else warnings,
    )


def _observation() -> OperatorObservation:
    return OperatorObservation(
        observation_id="gmail-message:m1:process-signal:INTERVIEW_PROPOSED",
        source_type="EMAIL_PROVIDER",
        source_name="gmail",
        source_ref="gmail:message:m1",
        kind="PROCESS_OPENED",
        account_id="example-co",
        observed_at=NOW,
        reason="explicit interview invitation observed",
    )


def test_evidence_span_requires_valid_offsets() -> None:
    span = EvidenceSpan(start=4, end=12, text="evidence")
    assert span.start == 4
    assert span.end == 12

    with pytest.raises(ValidationError, match="evidence span end"):
        EvidenceSpan(start=4, end=4, text="evidence")
    with pytest.raises(ValidationError):
        EvidenceSpan(start=-1, end=4, text="evidence")


def test_signal_rejects_unbounded_or_freeform_reason_code() -> None:
    with pytest.raises(ValidationError):
        _signal(reason_code="interview because recruiter said so")
    with pytest.raises(ValidationError):
        _signal(reason_code="X" * 81)


def test_models_are_strict_and_reject_raw_source_fields() -> None:
    with pytest.raises(ValidationError):
        ProcessEmailSelection(
            account_id="example-co",
            message_id="m1",
            selected_by="operator",
            body="private body",
        )
    with pytest.raises(ValidationError):
        ProcessSignal(
            kind="INTERVIEW_PROPOSED",
            confidence="HIGH",
            reason_code="INTERVIEW_INVITATION_EXPLICIT",
            evidence_spans=[_span()],
            subject="private subject",
        )


def test_classified_requires_at_least_one_signal() -> None:
    with pytest.raises(ValidationError, match="CLASSIFIED requires signals"):
        _classification(disposition="CLASSIFIED", signals=[])


def test_not_process_requires_empty_signals() -> None:
    classification = _classification(disposition="NOT_PROCESS", signals=[])
    assert classification.signals == []

    with pytest.raises(ValidationError, match="NOT_PROCESS requires empty signals"):
        _classification(disposition="NOT_PROCESS", signals=[_signal()])


def test_ambiguous_may_be_empty_or_keep_conflicting_transient_signals() -> None:
    empty = _classification(disposition="AMBIGUOUS", signals=[])
    assert empty.signals == []

    rejected = _signal(
        "REJECTED",
        reason_code="REJECTION_EXPLICIT",
    )
    interview = _signal()
    conflict = _classification(
        disposition="AMBIGUOUS",
        signals=[rejected, interview],
        warnings=["conflicting_process_signals"],
    )
    assert [signal.kind for signal in conflict.signals] == [
        "REJECTED",
        "INTERVIEW_PROPOSED",
    ]

    with pytest.raises(ValidationError, match="conflicting_process_signals"):
        _classification(
            disposition="AMBIGUOUS",
            signals=[rejected, interview],
            warnings=[],
        )


def test_selection_contains_exactly_one_message_identity_surface() -> None:
    selection = ProcessEmailSelection(
        account_id="example-co",
        contact_id="contact-1",
        message_id="m1",
        selected_by="operator",
    )
    assert selection.message_id == "m1"
    assert not hasattr(selection, "thread_id")


def test_projection_keeps_zero_or_one_candidate_observation() -> None:
    empty = ProcessProjection(proposed_observation=None, warnings=[])
    assert empty.proposed_observation is None

    projected = ProcessProjection(
        proposed_observation=_observation(),
        warnings=[],
    )
    assert projected.proposed_observation is not None


def test_preview_normalizes_observed_at_and_requires_empty_external_actions() -> None:
    observed = datetime(
        2026,
        9,
        1,
        9,
        0,
        tzinfo=timezone(timedelta(hours=-3)),
    )
    preview = ProcessEmailPreview(
        status="NOT_PROCESS",
        classifier_version="deterministic-process-email-v1",
        ruleset_version="es-en-2026-09-v3",
        source_ref="gmail:message:m1",
        observed_at=observed,
        signals=[],
        warnings=[],
        external_actions=[],
    )
    assert preview.observed_at == NOW

    with pytest.raises(ValidationError, match="external_actions"):
        ProcessEmailPreview(
            status="NOT_PROCESS",
            classifier_version="deterministic-process-email-v1",
            ruleset_version="es-en-2026-09-v3",
            source_ref="gmail:message:m1",
            observed_at=NOW,
            signals=[],
            warnings=[],
            external_actions=["send_email"],
        )


def test_preview_rejects_naive_observed_at() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        ProcessEmailPreview(
            status="NOT_PROCESS",
            classifier_version="deterministic-process-email-v1",
            ruleset_version="es-en-2026-09-v3",
            source_ref="gmail:message:m1",
            observed_at=datetime(2026, 9, 1, 12, 0),
            signals=[],
            warnings=[],
        )


def test_preview_requires_operator_preview_only_with_candidate() -> None:
    from app.operator_bridge.models import ObservationPreview

    operator_preview = ObservationPreview(
        preview_version="operator-preview-v1",
        status="IMPORTABLE",
        observation_id="gmail-message:m1:process-signal:INTERVIEW_PROPOSED",
        observation_sha256="a" * 64,
        preview_sha256="b" * 64,
        account_id="example-co",
        event_kind="PROCESS_OPENED",
        state_before="UNTOUCHED",
        state_after="PROCESS_OPEN",
        open_process_before=False,
        open_process_after=True,
        source_type="EMAIL_PROVIDER",
        source_name="gmail",
        source_ref="gmail:message:m1",
        reason="explicit interview invitation observed",
    )

    with pytest.raises(ValidationError, match="operator_preview requires proposed_observation"):
        ProcessEmailPreview(
            status="CLASSIFIED",
            classifier_version="deterministic-process-email-v1",
            ruleset_version="es-en-2026-09-v3",
            source_ref="gmail:message:m1",
            observed_at=NOW,
            signals=[_signal()],
            warnings=[],
            operator_preview=operator_preview,
        )


def test_ambiguous_preview_can_never_carry_candidate_observation() -> None:
    with pytest.raises(ValidationError, match="AMBIGUOUS cannot propose observation"):
        ProcessEmailPreview(
            status="AMBIGUOUS",
            classifier_version="deterministic-process-email-v1",
            ruleset_version="es-en-2026-09-v3",
            source_ref="gmail:message:m1",
            observed_at=NOW,
            signals=[_signal("REJECTED", reason_code="REJECTION_EXPLICIT"), _signal()],
            warnings=["conflicting_process_signals"],
            proposed_observation=_observation(),
        )
