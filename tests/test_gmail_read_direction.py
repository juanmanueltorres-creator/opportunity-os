from datetime import datetime, timezone

import pytest

from app.adapters.gmail_read.direction import (
    is_inbound,
    is_outbound,
    normalize_owned_addresses,
)
from app.adapters.gmail_read.models import GmailMessageEnvelope

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def message(
    *,
    sender: str,
    to: tuple[str, ...],
    labels: tuple[str, ...],
    cc: tuple[str, ...] = (),
) -> GmailMessageEnvelope:
    return GmailMessageEnvelope(
        message_id="m1",
        thread_id="t1",
        internal_date=NOW,
        label_ids=labels,
        from_address=sender,
        to_addresses=to,
        cc_addresses=cc,
    )


def test_owned_addresses_are_normalized() -> None:
    assert normalize_owned_addresses({" OWNER@Example.Test "}) == frozenset(
        {"owner@example.test"}
    )


def test_empty_owned_addresses_are_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="owned_addresses must contain at least one address",
    ):
        normalize_owned_addresses(set())


def test_inbound_requires_external_sender_and_owned_recipient() -> None:
    owned = frozenset({"owner@example.test"})

    assert is_inbound(
        message(
            sender="recruiter@example.test",
            to=("owner@example.test",),
            labels=("INBOX",),
        ),
        owned,
    )
    assert not is_inbound(
        message(
            sender="owner@example.test",
            to=("owner@example.test",),
            labels=("INBOX",),
        ),
        owned,
    )


def test_inbound_accepts_owned_cc_recipient() -> None:
    owned = frozenset({"owner@example.test"})

    assert is_inbound(
        message(
            sender="recruiter@example.test",
            to=("other@example.test",),
            cc=("owner@example.test",),
            labels=("INBOX",),
        ),
        owned,
    )


def test_outbound_requires_sent_label_owned_sender_and_external_recipient() -> None:
    owned = frozenset({"owner@example.test"})

    assert is_outbound(
        message(
            sender="owner@example.test",
            to=("recruiter@example.test",),
            labels=("SENT",),
        ),
        owned,
    )
    assert not is_outbound(
        message(
            sender="owner@example.test",
            to=("owner@example.test",),
            labels=("SENT",),
        ),
        owned,
    )
    assert not is_outbound(
        message(
            sender="owner@example.test",
            to=("recruiter@example.test",),
            labels=("INBOX",),
        ),
        owned,
    )
