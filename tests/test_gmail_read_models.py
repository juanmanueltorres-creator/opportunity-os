from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.adapters.gmail_read.models import (
    GmailMessageEnvelope,
    GmailObservationResult,
    GmailReadSelection,
    GmailThreadEnvelope,
)
from app.operator_bridge.models import OperatorObservation

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def _observation() -> OperatorObservation:
    return OperatorObservation(
        observation_id="gmail-message:m1:message-sent",
        source_type="EMAIL_PROVIDER",
        source_name="gmail",
        source_ref="gmail:message:m1",
        kind="MESSAGE_SENT",
        account_id="example-co",
        observed_at=NOW,
        reason="selected Gmail message is confirmed in Sent",
    )


def test_selection_requires_exactly_one_provider_id() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        GmailReadSelection(account_id="example-co", selected_by="operator")

    with pytest.raises(ValidationError, match="exactly one"):
        GmailReadSelection(
            account_id="example-co",
            selected_by="operator",
            message_id="m1",
            thread_id="t1",
        )

    message = GmailReadSelection(
        account_id="example-co",
        selected_by="operator",
        message_id="m1",
    )
    thread = GmailReadSelection(
        account_id="example-co",
        contact_id="contact-1",
        selected_by="operator",
        thread_id="t1",
    )
    assert message.message_id == "m1"
    assert message.thread_id is None
    assert thread.thread_id == "t1"
    assert thread.message_id is None


def test_selection_is_strict_and_bounded() -> None:
    with pytest.raises(ValidationError):
        GmailReadSelection(
            account_id="example-co",
            selected_by="operator",
            message_id="m1",
            mailbox_dump=True,
        )
    with pytest.raises(ValidationError):
        GmailReadSelection(
            account_id="example-co",
            selected_by="x" * 121,
            message_id="m1",
        )


def test_message_envelope_normalizes_time_and_uses_tuple_metadata() -> None:
    envelope = GmailMessageEnvelope(
        message_id="m1",
        thread_id="t1",
        internal_date=datetime(
            2026,
            8,
            29,
            9,
            0,
            tzinfo=timezone(timedelta(hours=-3)),
        ),
        label_ids=["SENT"],
        from_address="owner@example.test",
        to_addresses=["person@example.test"],
        cc_addresses=[],
        references=["<ref-1@example.test>"],
    )
    assert envelope.internal_date == NOW
    assert envelope.label_ids == ("SENT",)
    assert envelope.to_addresses == ("person@example.test",)
    assert envelope.references == ("<ref-1@example.test>",)


def test_envelope_rejects_naive_time_and_raw_body_fields() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        GmailMessageEnvelope(
            message_id="m1",
            thread_id="t1",
            internal_date=datetime(2026, 8, 29, 12, 0),
            label_ids=("SENT",),
            from_address="owner@example.test",
            to_addresses=("person@example.test",),
        )

    with pytest.raises(ValidationError):
        GmailMessageEnvelope(
            message_id="m1",
            thread_id="t1",
            internal_date=NOW,
            label_ids=("SENT",),
            from_address="owner@example.test",
            to_addresses=("person@example.test",),
            body="secret",
        )


def test_thread_requires_messages_to_match_thread_id() -> None:
    message = GmailMessageEnvelope(
        message_id="m1",
        thread_id="other-thread",
        internal_date=NOW,
        label_ids=("INBOX",),
        from_address="person@example.test",
        to_addresses=("owner@example.test",),
    )
    with pytest.raises(ValidationError, match="thread_id"):
        GmailThreadEnvelope(thread_id="t1", messages=(message,))


def test_observation_result_shape_is_strict() -> None:
    ready = GmailObservationResult(
        status="OBSERVATION_READY",
        observation=_observation(),
        source_ref="gmail:message:m1",
    )
    assert ready.provider == "gmail"
    assert ready.external_actions == []

    with pytest.raises(ValidationError, match="observation"):
        GmailObservationResult(status="OBSERVATION_READY")

    with pytest.raises(ValidationError, match="observation"):
        GmailObservationResult(
            status="AMBIGUOUS",
            observation=_observation(),
            errors=["ambiguous_message_direction"],
        )


def test_result_rejects_external_actions() -> None:
    with pytest.raises(ValidationError, match="external_actions"):
        GmailObservationResult(
            status="AMBIGUOUS",
            errors=["ambiguous_message_direction"],
            external_actions=["send_email"],
        )
