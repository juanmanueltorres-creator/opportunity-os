import base64

import pytest

from app.adapters.gmail_content.models import GmailContentError, MAX_MESSAGE_TEXT_BYTES
from app.adapters.gmail_content.normalizer import normalize_full_message_payload


def b64url(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def _headers() -> list[dict[str, str]]:
    return [
        {"name": "From", "value": "recruiter@example.test"},
        {"name": "To", "value": "owner@example.test"},
        {"name": "Subject", "value": "Interview update"},
    ]


def _part(
    mime_type: str,
    text: str | None = None,
    *,
    filename: str = "",
    disposition: str | None = None,
    data: str | None = None,
) -> dict[str, object]:
    headers: list[dict[str, str]] = []
    if disposition is not None:
        headers.append({"name": "Content-Disposition", "value": disposition})
    body: dict[str, object] = {}
    if data is not None:
        body["data"] = data
    elif text is not None:
        body["data"] = b64url(text)
    return {
        "mimeType": mime_type,
        "filename": filename,
        "headers": headers,
        "body": body,
    }


def _payload(
    *,
    root_mime_type: str = "multipart/alternative",
    parts: list[dict[str, object]] | None = None,
    root_body: dict[str, object] | None = None,
) -> dict[str, object]:
    provider_payload: dict[str, object] = {
        "mimeType": root_mime_type,
        "headers": _headers(),
        "filename": "",
        "body": root_body or {},
    }
    if parts is not None:
        provider_payload["parts"] = parts
    return {
        "id": "m1",
        "threadId": "t1",
        "internalDate": "1788264000000",
        "labelIds": ["INBOX"],
        "payload": provider_payload,
        "snippet": "must never enter transient normalized content",
    }


def _normalize(payload: dict[str, object]):
    return normalize_full_message_payload(payload)


def test_recursive_multipart_prefers_usable_plain_text_over_html() -> None:
    payload = _payload(
        parts=[
            {
                "mimeType": "multipart/mixed",
                "filename": "",
                "headers": [],
                "body": {},
                "parts": [
                    _part("text/html", "<p>HTML fallback</p>"),
                    _part("text/plain", "We would like to invite you to an interview."),
                ],
            }
        ]
    )

    content = _normalize(payload)

    assert content.message.message_id == "m1"
    assert content.message.subject == "Interview update"
    assert content.current_message_text == "We would like to invite you to an interview."
    rendered = content.model_dump(mode="json")
    assert "snippet" not in rendered
    assert "raw" not in rendered


def test_html_only_fallback_keeps_visible_text_and_drops_script_and_style() -> None:
    payload = _payload(
        parts=[
            _part(
                "text/html",
                "<style>.secret{display:none}</style><p>Hello <b>Juan</b></p>"
                "<script>privateToken()</script><div>Interview tomorrow</div>",
            )
        ]
    )

    content = _normalize(payload)

    assert "Hello Juan" in content.current_message_text
    assert "Interview tomorrow" in content.current_message_text
    assert "privateToken" not in content.current_message_text
    assert "display:none" not in content.current_message_text


@pytest.mark.parametrize(
    "ignored",
    [
        _part("text/plain", "secret attachment text", filename="notes.txt"),
        _part(
            "text/plain",
            "secret attachment text",
            disposition='attachment; filename="notes.txt"',
        ),
    ],
)
def test_attachment_like_text_parts_are_excluded(ignored: dict[str, object]) -> None:
    payload = _payload(
        parts=[
            ignored,
            _part("text/plain", "Current recruiter message"),
        ]
    )

    content = _normalize(payload)

    assert content.current_message_text == "Current recruiter message"
    assert "secret attachment text" not in content.current_message_text


@pytest.mark.parametrize(
    "marker",
    [
        "On Mon, Aug 31, 2026 at 10:00 AM Juan wrote:",
        "El lun, 31 ago 2026 Juan escribió:",
        "-----Original Message-----",
    ],
)
def test_known_quote_markers_remove_historical_thread_text(marker: str) -> None:
    payload = _payload(
        parts=[
            _part(
                "text/plain",
                f"Unfortunately, we will not be moving forward.\n\n{marker}\n"
                "We would like to invite you to an interview.",
            )
        ]
    )

    content = _normalize(payload)

    assert content.current_message_text == "Unfortunately, we will not be moving forward."
    assert "invite you to an interview" not in content.current_message_text


def test_standard_signature_delimiter_removes_following_signature() -> None:
    payload = _payload(
        parts=[
            _part(
                "text/plain",
                "Would Tuesday work for an interview?\n\n-- \nRecruiter Name\n555-1234",
            )
        ]
    )

    content = _normalize(payload)

    assert content.current_message_text == "Would Tuesday work for an interview?"
    assert "Recruiter Name" not in content.current_message_text


def test_invalid_decoded_utf8_is_gmail_payload_invalid() -> None:
    payload = _payload(parts=[_part("text/plain", data="____")])

    with pytest.raises(GmailContentError) as exc_info:
        _normalize(payload)

    assert exc_info.value.code == "gmail_payload_invalid"
    assert str(exc_info.value) == "gmail_payload_invalid"


@pytest.mark.parametrize(
    "part",
    [
        _part("text/plain"),
        _part("text/plain", data=""),
        _part("text/html", "   "),
    ],
)
def test_supported_text_part_without_usable_data_is_missing_usable_body(
    part: dict[str, object],
) -> None:
    payload = _payload(parts=[part])

    with pytest.raises(GmailContentError) as exc_info:
        _normalize(payload)

    assert exc_info.value.code == "missing_usable_body"


def test_payload_without_supported_text_mime_candidate_is_unsupported_mime() -> None:
    payload = _payload(
        root_mime_type="multipart/mixed",
        parts=[
            _part("application/pdf", data=b64url("fake pdf")),
            _part("image/png", data=b64url("fake image")),
        ],
    )

    with pytest.raises(GmailContentError) as exc_info:
        _normalize(payload)

    assert exc_info.value.code == "unsupported_mime"


def test_only_quoted_history_is_ambiguous_instead_of_classified() -> None:
    payload = _payload(
        parts=[
            _part(
                "text/plain",
                "On Mon, Aug 31, 2026 at 10:00 AM Juan wrote:\n"
                "We would like to invite you to an interview.",
            )
        ]
    )

    with pytest.raises(GmailContentError) as exc_info:
        _normalize(payload)

    assert exc_info.value.code == "quoted_content_ambiguous"


def test_current_message_text_over_256_kib_fails_without_truncation() -> None:
    text = "x" * (MAX_MESSAGE_TEXT_BYTES + 1)
    payload = _payload(parts=[_part("text/plain", text)])

    with pytest.raises(GmailContentError) as exc_info:
        _normalize(payload)

    assert exc_info.value.code == "content_too_large"
