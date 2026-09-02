from datetime import datetime, timezone

import pytest

from app.process_email.models import (
    EvidenceSpan,
    ProcessClassification,
    ProcessSignal,
)
from app.process_email.projector import ProcessEventProjector
from app.relationships.models import RelationshipAccount

NOW = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)

_REASON_CODE = {
    "APPLICATION_ACKNOWLEDGED": "APPLICATION_RECEIPT_EXPLICIT",
    "INTERVIEW_PROPOSED": "INTERVIEW_INVITATION_EXPLICIT",
    "STAGE_ADVANCED": "STAGE_ADVANCEMENT_EXPLICIT",
    "PROCESS_UPDATED": "PROCESS_RESCHEDULE_EXPLICIT",
    "OFFER_RECEIVED": "OFFER_EXPLICIT",
    "REJECTED": "REJECTION_EXPLICIT",
}


def _signal(kind: str, confidence: str = "HIGH") -> ProcessSignal:
    text = kind.lower().replace("_", " ")
    return ProcessSignal(
        kind=kind,
        confidence=confidence,
        reason_code=_REASON_CODE[kind],
        evidence_spans=[EvidenceSpan(start=0, end=len(text), text=text)],
    )


def _classification(*signals: ProcessSignal) -> ProcessClassification:
    return ProcessClassification(disposition="CLASSIFIED", signals=list(signals))


def _account(*, open_process: bool) -> RelationshipAccount:
    if open_process:
        return RelationshipAccount(
            account_id="example-co",
            company="Example Co",
            relationship_state="PROCESS_OPEN",
            open_process=True,
            updated_at=NOW,
        )
    return RelationshipAccount(
        account_id="example-co",
        company="Example Co",
        relationship_state="PROCESS_CLOSED",
        open_process=False,
        updated_at=NOW,
    )


def _project(
    classification: ProcessClassification,
    *,
    open_process: bool | None,
):
    account = None if open_process is None else _account(open_process=open_process)
    return ProcessEventProjector().project(
        classification=classification,
        account=account,
        account_id="example-co",
        contact_id="contact-1",
        message_id="m1",
        observed_at=NOW,
    )


@pytest.mark.parametrize("open_process", [False, True])
def test_ack_never_drives_relationship_mutation(open_process: bool) -> None:
    projection = _project(
        _classification(_signal("APPLICATION_ACKNOWLEDGED")),
        open_process=open_process,
    )

    assert projection.proposed_observation is None
    assert projection.warnings == []


@pytest.mark.parametrize(
    ("kind", "open_process", "expected_event"),
    [
        ("INTERVIEW_PROPOSED", False, "PROCESS_OPENED"),
        ("INTERVIEW_PROPOSED", True, "PROCESS_UPDATED"),
        ("STAGE_ADVANCED", False, "PROCESS_OPENED"),
        ("STAGE_ADVANCED", True, "PROCESS_UPDATED"),
        ("PROCESS_UPDATED", True, "PROCESS_UPDATED"),
        ("OFFER_RECEIVED", False, "PROCESS_OPENED"),
        ("OFFER_RECEIVED", True, "PROCESS_UPDATED"),
        ("REJECTED", True, "PROCESS_CLOSED"),
    ],
)
def test_mutation_driving_signals_follow_relationship_state(
    kind: str,
    open_process: bool,
    expected_event: str,
) -> None:
    projection = _project(_classification(_signal(kind)), open_process=open_process)

    observation = projection.proposed_observation
    assert observation is not None
    assert observation.kind == expected_event
    assert observation.account_id == "example-co"
    assert observation.contact_id == "contact-1"
    assert observation.observed_at == NOW
    assert observation.source_type == "EMAIL_PROVIDER"
    assert observation.source_name == "gmail"
    assert observation.source_ref == "gmail:message:m1"
    assert observation.process_label is None
    assert projection.warnings == []


def test_update_without_open_process_fails_closed() -> None:
    projection = _project(
        _classification(_signal("PROCESS_UPDATED")),
        open_process=False,
    )

    assert projection.proposed_observation is None
    assert projection.warnings == ["no_open_process_to_update"]


def test_rejection_without_open_process_fails_closed() -> None:
    projection = _project(_classification(_signal("REJECTED")), open_process=False)

    assert projection.proposed_observation is None
    assert projection.warnings == ["no_open_process_to_close"]


def test_low_confidence_only_never_drives_mutation() -> None:
    projection = _project(
        _classification(_signal("PROCESS_UPDATED", confidence="LOW")),
        open_process=True,
    )

    assert projection.proposed_observation is None
    assert projection.warnings == ["low_confidence_only"]


def test_ambiguous_classification_never_drives_mutation() -> None:
    classification = ProcessClassification(
        disposition="AMBIGUOUS",
        signals=[_signal("INTERVIEW_PROPOSED"), _signal("REJECTED")],
        warnings=["conflicting_process_signals"],
    )

    projection = _project(classification, open_process=True)

    assert projection.proposed_observation is None
    assert projection.warnings == ["conflicting_process_signals"]


def test_mutation_signal_requires_known_relationship_account() -> None:
    projection = _project(
        _classification(_signal("INTERVIEW_PROPOSED")),
        open_process=None,
    )

    assert projection.proposed_observation is None
    assert projection.warnings == ["unknown_relationship_account"]


def test_highest_priority_compatible_signal_drives_one_observation() -> None:
    classification = _classification(
        _signal("APPLICATION_ACKNOWLEDGED"),
        _signal("INTERVIEW_PROPOSED"),
        _signal("STAGE_ADVANCED"),
        _signal("OFFER_RECEIVED"),
    )

    projection = _project(classification, open_process=False)

    observation = projection.proposed_observation
    assert observation is not None
    assert observation.observation_id == "gmail-message:m1:process-signal:OFFER_RECEIVED"
    assert observation.kind == "PROCESS_OPENED"
    assert observation.reason == "explicit employment offer observed"
    assert observation.semantic_provenance is not None
    assert observation.semantic_provenance.model_dump() == {
        "producer": "PROCESS_EMAIL_CLASSIFIER",
        "producer_version": "deterministic-process-email-v1",
        "policy_version": "es-en-2026-09-v2",
        "classification": "OFFER_RECEIVED",
        "reason_code": "OFFER_EXPLICIT",
    }


def test_rejection_plus_ack_uses_rejection_as_driver() -> None:
    projection = _project(
        _classification(
            _signal("APPLICATION_ACKNOWLEDGED"),
            _signal("REJECTED"),
        ),
        open_process=True,
    )

    observation = projection.proposed_observation
    assert observation is not None
    assert observation.observation_id == "gmail-message:m1:process-signal:REJECTED"
    assert observation.kind == "PROCESS_CLOSED"
    assert observation.reason == "explicit process rejection observed"
