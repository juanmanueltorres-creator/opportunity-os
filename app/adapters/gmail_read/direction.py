from __future__ import annotations

from collections.abc import Iterable

from app.adapters.gmail_read.models import GmailMessageEnvelope


def normalize_owned_addresses(addresses: Iterable[str]) -> frozenset[str]:
    normalized = frozenset(
        value.strip().lower() for value in addresses if value.strip()
    )
    if not normalized:
        raise ValueError("owned_addresses must contain at least one address")
    return normalized


def _is_owned(address: str, owned: frozenset[str]) -> bool:
    return address.strip().lower() in owned


def _recipients(message: GmailMessageEnvelope) -> tuple[str, ...]:
    return (*message.to_addresses, *message.cc_addresses)


def is_outbound(message: GmailMessageEnvelope, owned: frozenset[str]) -> bool:
    return (
        "SENT" in message.label_ids
        and _is_owned(message.from_address, owned)
        and any(not _is_owned(address, owned) for address in _recipients(message))
    )


def is_inbound(message: GmailMessageEnvelope, owned: frozenset[str]) -> bool:
    return (
        not _is_owned(message.from_address, owned)
        and any(_is_owned(address, owned) for address in _recipients(message))
    )
