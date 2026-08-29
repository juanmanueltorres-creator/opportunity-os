from datetime import datetime, timedelta, timezone

import pytest

from app.adapters.gmail_read.models import (
    GmailMessageEnvelope,
    GmailReadSelection,
    GmailThreadEnvelope,
)
from app.adapters.gmail_read.provider import GmailProviderError
from app.adapters.gmail_read.service import GmailReadService

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
OWNED = "owner@example.test"
EXTERNAL = "recruiter@example.test"


class FakeGmailProvider:
    def __init__(
        self,
        *,
        message: GmailMessageEnvelope | None = None,
        thread: GmailThreadEnvelope | None = None,
        error: str | None = None,
    ) -> None:
        self.message = message
        self.thread = thread
        self.error = error

    async def get_message(self, message_id: str) -> GmailMessageEnvelope:
        if self.error:
            raise GmailProviderError(self.error)
        assert self.message is not None
        assert self.message.message_id == message_id
        return self.message

    async def get_thread(self, thread_id: str) -> GmailThreadEnvelope:
        if self.error:
            raise GmailProviderError(self.error)
        assert self.thread is not None
        assert self.thread.thread_id == thread_id
        return self.thread


def _message(
    message_id: str,
    *,
    when: datetime = NOW,
    sender: str = OWNED,
    to: tuple[str, ...] = (EXTERNAL,),
    cc: tuple[str, ...] = (),
    labels: tuple[str, ...] = ("SENT",),
    thread_id: str = "t1",
) -> GmailMessageEnvelope:
    return GmailMessageEnvelope(
        message_id=message_id,
        thread_id=thread_id,
        internal_date=when,
        label_ids=labels,
        from_address=sender,
        to_addresses=to,
        cc_addresses=cc,
    )


@pytest.mark.asyncio
async def test_selected_sent_message_becomes_message_sent_observation() -> None:
    provider = FakeGmailProvider(message=_message("m1"))
    service = GmailReadService(provider, owned_addresses={" OWNER@example.test "})

    result = await service.observe(
        GmailReadSelection(
            account_id="example-co",
            contact_id="contact-1",
            message_id="m1",
            selected_by="operator",
        )
    )

    assert result.status == "OBSERVATION_READY"
    assert result.errors == []
    assert result.external_actions == []
    assert result.source_ref == "gmail:message:m1"
    assert result.observation is not None
    assert result.observation.observation_id == "gmail-message:m1:message-sent"
    assert result.observation.source_type == "EMAIL_PROVIDER"
    assert result.observation.source_name == "gmail"
    assert result.observation.source_ref == "gmail:message:m1"
    assert result.observation.kind == "MESSAGE_SENT"
    assert result.observation.account_id == "example-co"
    assert result.observation.contact_id == "contact-1"
    assert result.observation.observed_at == NOW
    assert result.observation.reason == "selected Gmail message is confirmed in Sent"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        _message("m1", labels=("INBOX",)),
        _message("m1", sender=EXTERNAL, to=(OWNED,), labels=("INBOX",)),
        _message("m1", to=(OWNED,)),
    ],
)
async def test_selected_message_fails_closed_when_sent_direction_is_ambiguous(
    message: GmailMessageEnvelope,
) -> None:
    service = GmailReadService(FakeGmailProvider(message=message), owned_addresses={OWNED})
    result = await service.observe(
        GmailReadSelection(
            account_id="example-co",
            message_id="m1",
            selected_by="operator",
        )
    )
    assert result.status == "AMBIGUOUS"
    assert result.observation is None
    assert result.errors == ["ambiguous_message_direction"]
    assert result.external_actions == []


@pytest.mark.asyncio
async def test_selected_thread_becomes_latest_defensible_reply_observation() -> None:
    outbound = _message("m1", when=NOW - timedelta(hours=3))
    first_reply = _message(
        "m2",
        when=NOW - timedelta(hours=2),
        sender=EXTERNAL,
        to=(OWNED,),
        labels=("INBOX",),
    )
    second_reply = _message(
        "m3",
        when=NOW - timedelta(hours=1),
        sender="manager@example.test",
        to=(OWNED,),
        labels=("INBOX",),
    )
    thread = GmailThreadEnvelope(
        thread_id="t1",
        messages=(second_reply, outbound, first_reply),
    )
    service = GmailReadService(FakeGmailProvider(thread=thread), owned_addresses={OWNED})

    result = await service.observe(
        GmailReadSelection(
            account_id="example-co",
            thread_id="t1",
            selected_by="operator",
        )
    )

    assert result.status == "OBSERVATION_READY"
    assert result.source_ref == "gmail:thread:t1:message:m3"
    assert result.observation is not None
    assert result.observation.observation_id == "gmail-message:m3:reply-received"
    assert result.observation.kind == "REPLY_RECEIVED"
    assert result.observation.observed_at == second_reply.internal_date
    assert (
        result.observation.reason
        == "selected Gmail thread contains inbound reply after prior outbound message"
    )


@pytest.mark.asyncio
async def test_thread_with_inbound_only_is_not_a_reply() -> None:
    inbound = _message(
        "m1",
        sender=EXTERNAL,
        to=(OWNED,),
        labels=("INBOX",),
    )
    thread = GmailThreadEnvelope(thread_id="t1", messages=(inbound,))
    service = GmailReadService(FakeGmailProvider(thread=thread), owned_addresses={OWNED})

    result = await service.observe(
        GmailReadSelection(
            account_id="example-co",
            thread_id="t1",
            selected_by="operator",
        )
    )

    assert result.status == "AMBIGUOUS"
    assert result.observation is None
    assert result.errors == ["reply_without_prior_outbound"]


@pytest.mark.asyncio
async def test_thread_requires_strictly_later_inbound_reply() -> None:
    outbound = _message("m1", when=NOW)
    inbound_same_time = _message(
        "m2",
        when=NOW,
        sender=EXTERNAL,
        to=(OWNED,),
        labels=("INBOX",),
    )
    thread = GmailThreadEnvelope(thread_id="t1", messages=(outbound, inbound_same_time))
    service = GmailReadService(FakeGmailProvider(thread=thread), owned_addresses={OWNED})

    result = await service.observe(
        GmailReadSelection(
            account_id="example-co",
            thread_id="t1",
            selected_by="operator",
        )
    )
    assert result.status == "AMBIGUOUS"
    assert result.observation is None
    assert result.errors == ["reply_without_prior_outbound"]


@pytest.mark.asyncio
async def test_provider_failure_returns_provider_error_without_observation() -> None:
    service = GmailReadService(
        FakeGmailProvider(error="gmail_rate_limited"),
        owned_addresses={OWNED},
    )
    result = await service.observe(
        GmailReadSelection(
            account_id="example-co",
            message_id="m1",
            selected_by="operator",
        )
    )
    assert result.status == "PROVIDER_ERROR"
    assert result.observation is None
    assert result.errors == ["gmail_rate_limited"]
    assert result.external_actions == []


def test_service_requires_at_least_one_owned_address() -> None:
    with pytest.raises(ValueError, match="owned_addresses"):
        GmailReadService(FakeGmailProvider(), owned_addresses=set())
