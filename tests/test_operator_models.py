from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.operator_bridge.models import (
    PREVIEW_VERSION,
    ObservationImportRequest,
    ObservationPreview,
    ObservationSemanticProvenance,
    OperatorObservation,
    observation_sha256,
)

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def _observation(**updates) -> OperatorObservation:
    values = {
        "observation_id": "gmail-message-1",
        "source_type": "EMAIL_PROVIDER",
        "source_name": "gmail",
        "source_ref": "message:gmail-message-1",
        "kind": "REPLY_RECEIVED",
        "account_id": "example-co",
        "observed_at": NOW,
        "reason": "recruiter replied",
    }
    values.update(updates)
    return OperatorObservation(**values)


def _semantic_provenance(**updates) -> ObservationSemanticProvenance:
    values = {
        "producer": "PROCESS_EMAIL_CLASSIFIER",
        "producer_version": "deterministic-process-email-v1",
        "policy_version": "es-en-2026-09-v1",
        "classification": "INTERVIEW_PROPOSED",
        "reason_code": "INTERVIEW_INVITATION_EXPLICIT",
    }
    values.update(updates)
    return ObservationSemanticProvenance(**values)


def test_operator_observation_is_strict_and_normalizes_time() -> None:
    observation = OperatorObservation(
        observation_id="gmail-message-1",
        source_type="EMAIL_PROVIDER",
        source_name="gmail",
        source_ref="message:gmail-message-1",
        kind="REPLY_RECEIVED",
        account_id="example-co",
        observed_at=datetime(
            2026,
            8,
            29,
            9,
            0,
            tzinfo=timezone(timedelta(hours=-3)),
        ),
        reason="recruiter replied",
    )
    assert observation.observed_at == NOW


def test_operator_observation_rejects_raw_body_and_metadata() -> None:
    base = {
        "observation_id": "obs-1",
        "source_type": "MANUAL",
        "source_name": "manual",
        "source_ref": "manual:obs-1",
        "kind": "PROCESS_OPENED",
        "account_id": "example-co",
        "observed_at": NOW,
    }
    with pytest.raises(ValidationError):
        OperatorObservation(**base, body="secret")
    with pytest.raises(ValidationError):
        OperatorObservation(**base, metadata={"raw_payload": "secret"})


def test_semantic_provenance_is_typed_bounded_and_source_text_free() -> None:
    provenance = _semantic_provenance()
    assert provenance.producer == "PROCESS_EMAIL_CLASSIFIER"
    assert provenance.classification == "INTERVIEW_PROPOSED"

    for extra in (
        {"body": "private body"},
        {"subject": "private subject"},
        {"evidence_text": "literal recruiter sentence"},
        {"metadata": {"raw_payload": "private"}},
    ):
        with pytest.raises(ValidationError):
            ObservationSemanticProvenance(
                producer="PROCESS_EMAIL_CLASSIFIER",
                producer_version="deterministic-process-email-v1",
                policy_version="es-en-2026-09-v1",
                classification="INTERVIEW_PROPOSED",
                reason_code="INTERVIEW_INVITATION_EXPLICIT",
                **extra,
            )


def test_semantic_provenance_rejects_freeform_identifiers() -> None:
    with pytest.raises(ValidationError):
        _semantic_provenance(producer_version="version with spaces")
    with pytest.raises(ValidationError):
        _semantic_provenance(classification="interview proposed")
    with pytest.raises(ValidationError):
        _semantic_provenance(reason_code="X" * 81)


def test_existing_observation_remains_valid_without_semantic_provenance() -> None:
    observation = _observation()
    assert observation.semantic_provenance is None


def test_semantic_provenance_changes_observation_hash_without_changing_identity_fields() -> None:
    plain = _observation()
    classified = plain.model_copy(
        update={"semantic_provenance": _semantic_provenance()}
    )

    assert plain.observation_id == classified.observation_id
    assert plain.source_ref == classified.source_ref
    assert observation_sha256(plain) != observation_sha256(classified)


def test_operator_observation_rejects_naive_time() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        _observation(observed_at=datetime(2026, 8, 29, 12, 0))


def test_operator_observation_reason_is_bounded() -> None:
    with pytest.raises(ValidationError):
        _observation(reason="x" * 281)


def test_same_observation_has_stable_hash() -> None:
    observation = _observation()
    assert observation_sha256(observation) == observation_sha256(observation.model_copy())


def test_import_request_rejects_confirmation_before_observation() -> None:
    observation = _observation()
    with pytest.raises(ValidationError, match="confirmed_at"):
        ObservationImportRequest(
            observation=observation,
            preview_sha256="a" * 64,
            confirmed_by="operator",
            confirmed_at=NOW - timedelta(seconds=1),
        )


def test_preview_rejects_external_actions() -> None:
    with pytest.raises(ValidationError, match="external_actions"):
        ObservationPreview(
            preview_version=PREVIEW_VERSION,
            status="IMPORTABLE",
            observation_id="obs-1",
            observation_sha256="a" * 64,
            preview_sha256="b" * 64,
            account_id="example-co",
            event_kind="REPLIED",
            state_before="CONTACTED",
            state_after="REPLIED",
            open_process_before=False,
            open_process_after=False,
            source_type="EMAIL_PROVIDER",
            source_name="gmail",
            source_ref="message:1",
            reason="recruiter replied",
            errors=[],
            external_actions=["send_email"],
        )
