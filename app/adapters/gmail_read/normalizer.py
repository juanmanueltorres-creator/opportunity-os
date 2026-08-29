from __future__ import annotations

from datetime import datetime, timezone
from email.utils import getaddresses
from typing import Any

from app.adapters.gmail_read.models import GmailMessageEnvelope, GmailThreadEnvelope

_ALLOWED_HEADERS = {
    "from",
    "to",
    "cc",
    "subject",
    "in-reply-to",
    "references",
}


def _require_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    provider_payload = payload.get("payload")
    if not isinstance(provider_payload, dict):
        raise ValueError("payload must contain Gmail metadata")
    raw_headers = provider_payload.get("headers", [])
    if not isinstance(raw_headers, list):
        raise ValueError("payload headers must be a list")

    result: dict[str, str] = {}
    for raw in raw_headers:
        if not isinstance(raw, dict):
            raise ValueError("payload header must be an object")
        name = raw.get("name")
        value = raw.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            raise ValueError("payload header name/value must be strings")
        normalized_name = name.strip().lower()
        if normalized_name in _ALLOWED_HEADERS and normalized_name not in result:
            result[normalized_name] = value.strip()
    return result


def _addresses(value: str | None) -> tuple[str, ...]:
    if value is None or not value.strip():
        return ()
    parsed = []
    for _, address in getaddresses([value]):
        normalized = address.strip().lower()
        if normalized:
            parsed.append(normalized)
    return tuple(parsed)


def _references(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(part for part in value.split() if part)


def _internal_date(value: object) -> datetime:
    try:
        milliseconds = int(_require_string(value, field="internalDate"))
    except (TypeError, ValueError) as exc:
        raise ValueError("internalDate must be milliseconds since epoch") from exc
    if milliseconds < 0:
        raise ValueError("internalDate must be milliseconds since epoch")
    try:
        return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("internalDate must be milliseconds since epoch") from exc


def normalize_message_payload(payload: object) -> GmailMessageEnvelope:
    if not isinstance(payload, dict):
        raise ValueError("Gmail message payload must be an object")

    message_id = _require_string(payload.get("id"), field="id")
    thread_id = _require_string(payload.get("threadId"), field="threadId")
    headers = _headers(payload)

    from_addresses = _addresses(headers.get("from"))
    if len(from_addresses) != 1:
        raise ValueError("from header must contain exactly one usable address")

    raw_labels = payload.get("labelIds", [])
    if not isinstance(raw_labels, list) or not all(
        isinstance(label, str) and label.strip() for label in raw_labels
    ):
        raise ValueError("labelIds must be a list of non-empty strings")

    subject = headers.get("subject") or None
    in_reply_to = headers.get("in-reply-to") or None

    return GmailMessageEnvelope(
        message_id=message_id,
        thread_id=thread_id,
        internal_date=_internal_date(payload.get("internalDate")),
        label_ids=tuple(label.strip() for label in raw_labels),
        from_address=from_addresses[0],
        to_addresses=_addresses(headers.get("to")),
        cc_addresses=_addresses(headers.get("cc")),
        subject=subject,
        in_reply_to=in_reply_to,
        references=_references(headers.get("references")),
    )


def normalize_thread_payload(payload: object) -> GmailThreadEnvelope:
    if not isinstance(payload, dict):
        raise ValueError("Gmail thread payload must be an object")

    thread_id = _require_string(payload.get("id"), field="thread id")
    raw_messages = payload.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise ValueError("Gmail thread must contain messages")

    messages = tuple(normalize_message_payload(item) for item in raw_messages)
    if any(message.thread_id != thread_id for message in messages):
        raise ValueError("message thread does not match selected Gmail thread")

    return GmailThreadEnvelope(thread_id=thread_id, messages=messages)
