from __future__ import annotations

import base64
from binascii import Error as BinasciiError
from html.parser import HTMLParser
import re
from typing import Any

from app.adapters.gmail_content.models import (
    GmailContentEnvelope,
    GmailContentError,
    MAX_MESSAGE_TEXT_BYTES,
)
from app.adapters.gmail_read.normalizer import normalize_message_payload

_QUOTE_MARKERS = (
    re.compile(r"(?im)^On .+ wrote:\s*$"),
    re.compile(r"(?im)^El .+ escribió:\s*$"),
    re.compile(r"(?im)^-----Original Message-----\s*$"),
)
_SIGNATURE_MARKER = re.compile(r"(?m)^-- \s*$")
_BLOCK_TAGS = {"p", "div", "br", "li", "tr"}


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth == 0 and normalized in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style"}:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if self._skip_depth == 0 and normalized in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def _payload_root(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise GmailContentError("gmail_payload_invalid")
    root = payload.get("payload")
    if not isinstance(root, dict):
        raise GmailContentError("gmail_payload_invalid")
    return root


def _content_disposition(part: dict[str, Any]) -> str | None:
    raw_headers = part.get("headers", [])
    if raw_headers is None:
        return None
    if not isinstance(raw_headers, list):
        raise GmailContentError("gmail_payload_invalid")
    for raw in raw_headers:
        if not isinstance(raw, dict):
            raise GmailContentError("gmail_payload_invalid")
        name = raw.get("name")
        value = raw.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            raise GmailContentError("gmail_payload_invalid")
        if name.strip().lower() == "content-disposition":
            return value.strip().lower()
    return None


def _attachment_like(part: dict[str, Any]) -> bool:
    filename = part.get("filename", "")
    if not isinstance(filename, str):
        raise GmailContentError("gmail_payload_invalid")
    if filename.strip():
        return True
    disposition = _content_disposition(part)
    return disposition is not None and disposition.startswith("attachment")


def _decode_data(data: str) -> str:
    try:
        padding = "=" * (-len(data) % 4)
        raw = base64.b64decode(
            (data + padding).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
        return raw.decode("utf-8", errors="strict")
    except (UnicodeEncodeError, UnicodeDecodeError, BinasciiError, ValueError) as exc:
        raise GmailContentError("gmail_payload_invalid") from exc


def _html_to_text(value: str) -> str:
    parser = _VisibleTextParser()
    try:
        parser.feed(value)
        parser.close()
    except Exception as exc:
        raise GmailContentError("gmail_payload_invalid") from exc
    return parser.text()


def _normalize_visible_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in value.split("\n")]
    result: list[str] = []
    previous_blank = False
    for line in lines:
        if not line:
            if result and not previous_blank:
                result.append("")
            previous_blank = True
            continue
        result.append(line)
        previous_blank = False
    while result and result[-1] == "":
        result.pop()
    return "\n".join(result).strip()


def _strip_history_and_signature(value: str) -> str:
    earliest: int | None = None
    for marker in _QUOTE_MARKERS:
        match = marker.search(value)
        if match is not None and (earliest is None or match.start() < earliest):
            earliest = match.start()
    if earliest is not None:
        value = value[:earliest]

    signature = _SIGNATURE_MARKER.search(value)
    if signature is not None:
        value = value[: signature.start()]

    normalized = _normalize_visible_text(value)
    if not normalized:
        raise GmailContentError("quoted_content_ambiguous")
    return normalized


def _walk_parts(part: object) -> tuple[list[str], list[str], bool]:
    plain: list[str] = []
    html: list[str] = []
    supported_exists = False

    def visit(current: object) -> None:
        nonlocal supported_exists
        if not isinstance(current, dict):
            raise GmailContentError("gmail_payload_invalid")
        if _attachment_like(current):
            return

        mime_type = current.get("mimeType", "")
        if not isinstance(mime_type, str):
            raise GmailContentError("gmail_payload_invalid")
        mime_type = mime_type.strip().lower()

        if mime_type in {"text/plain", "text/html"}:
            supported_exists = True
            body = current.get("body", {})
            if not isinstance(body, dict):
                raise GmailContentError("gmail_payload_invalid")
            data = body.get("data")
            if data is not None and not isinstance(data, str):
                raise GmailContentError("gmail_payload_invalid")
            if isinstance(data, str) and data:
                decoded = _decode_data(data)
                if mime_type == "text/html":
                    decoded = _html_to_text(decoded)
                if decoded.strip():
                    if mime_type == "text/plain":
                        plain.append(decoded)
                    else:
                        html.append(decoded)

        children = current.get("parts", [])
        if children is None:
            return
        if not isinstance(children, list):
            raise GmailContentError("gmail_payload_invalid")
        for child in children:
            visit(child)

    visit(part)
    return plain, html, supported_exists


def normalize_full_message_payload(payload: object) -> GmailContentEnvelope:
    try:
        message = normalize_message_payload(payload)
    except ValueError as exc:
        raise GmailContentError("gmail_payload_invalid") from exc

    plain_candidates, html_candidates, supported_exists = _walk_parts(
        _payload_root(payload)
    )
    candidates = plain_candidates if plain_candidates else html_candidates

    if not candidates:
        if supported_exists:
            raise GmailContentError("missing_usable_body")
        raise GmailContentError("unsupported_mime")

    current_message_text = _strip_history_and_signature(candidates[0])
    if len(current_message_text.encode("utf-8")) > MAX_MESSAGE_TEXT_BYTES:
        raise GmailContentError("content_too_large")

    return GmailContentEnvelope(
        message=message,
        current_message_text=current_message_text,
    )
