from __future__ import annotations

from app.adapters.gmail_read.direction import (
    is_inbound,
    is_outbound,
    normalize_owned_addresses,
)
from app.adapters.gmail_read.models import (
    GmailMessageEnvelope,
    GmailObservationResult,
    GmailReadSelection,
    GmailThreadEnvelope,
)
from app.adapters.gmail_read.provider import GmailProviderError, GmailReadProvider
from app.operator_bridge.models import OperatorObservation

_MESSAGE_SENT_REASON = "selected Gmail message is confirmed in Sent"
_REPLY_RECEIVED_REASON = (
    "selected Gmail thread contains inbound reply after prior outbound message"
)


class GmailReadService:
    def __init__(
        self,
        provider: GmailReadProvider,
        *,
        owned_addresses: set[str] | frozenset[str],
    ) -> None:
        self.provider = provider
        self.owned_addresses = normalize_owned_addresses(owned_addresses)

    @staticmethod
    def _selection_ref(selection: GmailReadSelection) -> str:
        if selection.message_id is not None:
            return f"gmail:message:{selection.message_id}"
        return f"gmail:thread:{selection.thread_id}"

    async def observe(self, selection: GmailReadSelection) -> GmailObservationResult:
        try:
            if selection.message_id is not None:
                message = await self.provider.get_message(selection.message_id)
                return self._observe_message(selection, message)

            if selection.thread_id is None:
                return GmailObservationResult(
                    status="INVALID_SELECTION",
                    errors=["invalid_selection"],
                )
            thread = await self.provider.get_thread(selection.thread_id)
            return self._observe_thread(selection, thread)
        except GmailProviderError as exc:
            return GmailObservationResult(
                status="PROVIDER_ERROR",
                source_ref=self._selection_ref(selection),
                errors=[exc.code],
                external_actions=[],
            )

    def _observe_message(
        self,
        selection: GmailReadSelection,
        message: GmailMessageEnvelope,
    ) -> GmailObservationResult:
        source_ref = f"gmail:message:{message.message_id}"
        if not is_outbound(message, self.owned_addresses):
            return GmailObservationResult(
                status="AMBIGUOUS",
                source_ref=source_ref,
                errors=["ambiguous_message_direction"],
                external_actions=[],
            )

        observation = OperatorObservation(
            observation_id=f"gmail-message:{message.message_id}:message-sent",
            source_type="EMAIL_PROVIDER",
            source_name="gmail",
            source_ref=source_ref,
            kind="MESSAGE_SENT",
            account_id=selection.account_id,
            contact_id=selection.contact_id,
            observed_at=message.internal_date,
            reason=_MESSAGE_SENT_REASON,
        )
        return GmailObservationResult(
            status="OBSERVATION_READY",
            observation=observation,
            source_ref=source_ref,
            external_actions=[],
        )

    def _observe_thread(
        self,
        selection: GmailReadSelection,
        thread: GmailThreadEnvelope,
    ) -> GmailObservationResult:
        ordered = sorted(
            thread.messages,
            key=lambda message: (message.internal_date, message.message_id),
        )
        outbound = [
            message
            for message in ordered
            if is_outbound(message, self.owned_addresses)
        ]
        inbound = [
            message
            for message in ordered
            if is_inbound(message, self.owned_addresses)
        ]

        qualifying = [
            candidate
            for candidate in inbound
            if any(
                prior.internal_date < candidate.internal_date
                for prior in outbound
            )
        ]
        if not qualifying:
            return GmailObservationResult(
                status="AMBIGUOUS",
                source_ref=f"gmail:thread:{thread.thread_id}",
                errors=["reply_without_prior_outbound"],
                external_actions=[],
            )

        reply = max(
            qualifying,
            key=lambda message: (message.internal_date, message.message_id),
        )
        source_ref = f"gmail:thread:{thread.thread_id}:message:{reply.message_id}"
        observation = OperatorObservation(
            observation_id=f"gmail-message:{reply.message_id}:reply-received",
            source_type="EMAIL_PROVIDER",
            source_name="gmail",
            source_ref=source_ref,
            kind="REPLY_RECEIVED",
            account_id=selection.account_id,
            contact_id=selection.contact_id,
            observed_at=reply.internal_date,
            reason=_REPLY_RECEIVED_REASON,
        )
        return GmailObservationResult(
            status="OBSERVATION_READY",
            observation=observation,
            source_ref=source_ref,
            external_actions=[],
        )
