from datetime import datetime, timezone

import pytest

from app.adapters.gmail_read.normalizer import (
    normalize_message_payload,
    normalize_thread_payload,
)


def _message_payload(
    *,
    message_id: str = "m1",
    thread_id: str = "t1",
    internal_date: str = "1788019200000",
    labels: list[str] | None = None,
    headers: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "id": message_id,
        "threadId": thread_id,
        "internalDate": internal_date,
        "labelIds": labels if labels is not None else ["SENT"],
        "payload": {
            "headers": headers
            if headers is not None
            else [
                {"name": "From", "value": 'Owner Name <OWNER@Example.Test>'},
                {
                    "name": "To",
                    "value": 'Recruiter <Recruiter@Example.Test>, other@example.test',
                },
                {"name": "Cc", "value": "CC@Example.Test"},
                {"name": "Subject", "value": "Role follow-up"},
                {"name": "In-Reply-To", "value": "<prior@example.test>"},
                {
                    "name": "References",
                    "value": "<root@example.test> <prior@example.test>",
                },
                {"name": "X-Secret-Header", "value": "must-not-survive"},
            ]
        },
        "snippet": "body-like preview that must not survive",
        "raw": "must-not-survive",
    }


def test_normalize_message_payload_keeps_only_allowlisted_metadata() -> None:
    message = normalize_message_payload(_message_payload())

    assert message.message_id == "m1"
    assert message.thread_id == "t1"
    assert message.internal_date == datetime.fromtimestamp(
        1788019200, tz=timezone.utc
    )
    assert message.label_ids == ("SENT",)
    assert message.from_address == "owner@example.test"
    assert message.to_addresses == (
        "recruiter@example.test",
        "other@example.test",
    )
    assert message.cc_addresses == ("cc@example.test",)
    assert message.subject == "Role follow-up"
    assert message.in_reply_to == "<prior@example.test>"
    assert message.references == (
        "<root@example.test>",
        "<prior@example.test>",
    )
    rendered = message.model_dump(mode="json")
    assert "snippet" not in rendered
    assert "raw" not in rendered
    assert "X-Secret-Header" not in str(rendered)


def test_header_names_are_case_insensitive_and_addresses_are_normalized() -> None:
    message = normalize_message_payload(
        _message_payload(
            headers=[
                {"name": "fRoM", "value": "OWNER@EXAMPLE.TEST"},
                {"name": "tO", "value": " Person@Example.Test "},
            ]
        )
    )
    assert message.from_address == "owner@example.test"
    assert message.to_addresses == ("person@example.test",)


def test_message_payload_requires_one_usable_from_address() -> None:
    with pytest.raises(ValueError, match="from"):
        normalize_message_payload(
            _message_payload(headers=[{"name": "To", "value": "person@example.test"}])
        )

    with pytest.raises(ValueError, match="from"):
        normalize_message_payload(
            _message_payload(
                headers=[
                    {
                        "name": "From",
                        "value": "a@example.test, b@example.test",
                    }
                ]
            )
        )


def test_message_payload_rejects_invalid_internal_date() -> None:
    with pytest.raises(ValueError, match="internalDate"):
        normalize_message_payload(_message_payload(internal_date="not-a-number"))


def test_normalize_thread_payload_requires_matching_messages() -> None:
    thread = normalize_thread_payload(
        {
            "id": "t1",
            "messages": [
                _message_payload(message_id="m1", thread_id="t1"),
                _message_payload(message_id="m2", thread_id="t1"),
            ],
        }
    )
    assert thread.thread_id == "t1"
    assert [message.message_id for message in thread.messages] == ["m1", "m2"]

    with pytest.raises(ValueError, match="thread"):
        normalize_thread_payload(
            {
                "id": "t1",
                "messages": [_message_payload(message_id="m2", thread_id="wrong")],
            }
        )
