from datetime import datetime, timezone

import pytest

from app.operator_bridge.models import (
    ObservationSemanticProvenance,
    OperatorObservation,
    observation_sha256,
)
from app.operator_bridge.normalizer import normalize_observation, relationship_event_id

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def _observation(kind: str, **updates) -> OperatorObservation:
    values = {
        "observation_id": f"obs-{kind.lower()}",
        "source_type": "EMAIL_PROVIDER",
        "source_name": "gmail",
        "source_ref": f"message:{kind.lower()}",
        "kind": kind,
        "account_id": "example-co",
        "observed_at": NOW,
        "reason": "normalized fact",
    }
    values.update(updates)
    return OperatorObservation(**values)


def _semantic_provenance() -> ObservationSemanticProvenance:
    return ObservationSemanticProvenance(
        producer="PROCESS_EMAIL_CLASSIFIER",
        producer_version="deterministic-process-email-v1",
        policy_version="es-en-2026-09-v1",
        classification="INTERVIEW_PROPOSED",
        reason_code="INTERVIEW_INVITATION_EXPLICIT",
    )


@pytest.mark.parametrize(
    ("observation_kind", "event_kind"),
    [
        ("CONTACT_VERIFIED", "CONTACT_VERIFIED"),
        ("MESSAGE_SENT", "CONTACTED"),
        ("REPLY_RECEIVED", "REPLIED"),
        ("PROCESS_OPENED", "PROCESS_OPENED"),
        ("PROCESS_UPDATED", "PROCESS_UPDATED"),
        ("PROCESS_CLOSED", "PROCESS_CLOSED"),
    ],
)
def test_normalizer_maps_supported_observation_kinds(
    observation_kind: str,
    event_kind: str,
) -> None:
    updates = {"contact_id": "contact-1"} if observation_kind == "CONTACT_VERIFIED" else {}
    observation = _observation(observation_kind, **updates)

    event = normalize_observation(observation)

    assert event.kind == event_kind
    assert event.account_id == observation.account_id
    assert event.contact_id == observation.contact_id
    assert event.occurred_at == observation.observed_at
    assert event.reason == observation.reason
    assert event.source_ref == observation.source_ref


def test_relationship_event_id_depends_only_on_source_identity() -> None:
    first = _observation("REPLY_RECEIVED", observation_id="provider-123", reason="first fact")
    changed_semantics = first.model_copy(update={"reason": "different fact"})

    assert relationship_event_id(first) == relationship_event_id(changed_semantics)
    assert relationship_event_id(first).startswith("opobs-")
    assert len(relationship_event_id(first)) == len("opobs-") + 64


def test_semantic_provenance_does_not_change_relationship_event_identity() -> None:
    plain = _observation("PROCESS_OPENED", observation_id="same-process-fact")
    classified = plain.model_copy(
        update={"semantic_provenance": _semantic_provenance()}
    )

    assert relationship_event_id(plain) == relationship_event_id(classified)


def test_normalized_event_carries_only_allowlisted_bridge_metadata() -> None:
    observation = _observation(
        "PROCESS_OPENED",
        observation_id="process-1",
        process_label="Backend Engineer",
    )

    event = normalize_observation(observation)

    assert event.metadata == {
        "operator_source_type": "EMAIL_PROVIDER",
        "operator_source_name": "gmail",
        "operator_observation_id": "process-1",
        "operator_observation_sha256": observation_sha256(observation),
        "process_label": "Backend Engineer",
    }


def test_normalized_event_copies_only_typed_semantic_provenance() -> None:
    observation = _observation(
        "PROCESS_OPENED",
        observation_id="gmail-message:m1:process-signal:INTERVIEW_PROPOSED",
        semantic_provenance=_semantic_provenance(),
    )

    event = normalize_observation(observation)

    assert event.metadata == {
        "operator_source_type": "EMAIL_PROVIDER",
        "operator_source_name": "gmail",
        "operator_observation_id": "gmail-message:m1:process-signal:INTERVIEW_PROPOSED",
        "operator_observation_sha256": observation_sha256(observation),
        "semantic_producer": "PROCESS_EMAIL_CLASSIFIER",
        "semantic_producer_version": "deterministic-process-email-v1",
        "semantic_policy_version": "es-en-2026-09-v1",
        "semantic_classification": "INTERVIEW_PROPOSED",
        "semantic_reason_code": "INTERVIEW_INVITATION_EXPLICIT",
    }
    rendered = str(event.metadata).lower()
    for forbidden in ("body", "subject", "evidence_text", "literal recruiter sentence"):
        assert forbidden not in rendered


def test_account_level_message_sent_adds_official_channel_only() -> None:
    observation = _observation("MESSAGE_SENT", contact_id=None)

    event = normalize_observation(observation)

    assert event.kind == "CONTACTED"
    assert event.contact_id is None
    assert event.metadata["official_channel"] == "operator_observation"
    assert set(event.metadata) == {
        "operator_source_type",
        "operator_source_name",
        "operator_observation_id",
        "operator_observation_sha256",
        "official_channel",
    }


def test_contact_verified_requires_contact_id() -> None:
    observation = _observation("CONTACT_VERIFIED", contact_id=None)

    with pytest.raises(ValueError, match="CONTACT_VERIFIED requires contact_id"):
        normalize_observation(observation)


def test_process_label_is_not_emitted_for_non_process_observation() -> None:
    observation = _observation(
        "REPLY_RECEIVED",
        process_label="should not leak",
    )

    event = normalize_observation(observation)

    assert "process_label" not in event.metadata


def test_normalizer_is_deterministic_and_performs_no_provider_enrichment() -> None:
    observation = _observation("REPLY_RECEIVED", contact_id="contact-1")

    first = normalize_observation(observation)
    second = normalize_observation(observation.model_copy())

    assert first == second
    assert first.event_id == relationship_event_id(observation)
