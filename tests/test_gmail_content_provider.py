import base64

import httpx
import pytest

from app.adapters.gmail_content.provider import (
    GmailProviderError,
    GmailRestContentProvider,
)


def b64url(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def _message_payload() -> dict[str, object]:
    return {
        "id": "m1",
        "threadId": "t1",
        "internalDate": "1788264000000",
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "text/plain",
            "filename": "",
            "headers": [
                {"name": "From", "value": "recruiter@example.test"},
                {"name": "To", "value": "owner@example.test"},
                {"name": "Subject", "value": "Interview"},
            ],
            "body": {
                "data": b64url("We would like to invite you to an interview."),
            },
        },
        "snippet": "must not survive",
    }


@pytest.mark.asyncio
async def test_get_message_content_uses_one_full_message_read_and_bearer_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_message_payload(), request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GmailRestContentProvider(client, access_token="test-token")
        content = await provider.get_message_content("m1")

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "GET"
    assert request.url.path == "/gmail/v1/users/me/messages/m1"
    assert request.url.params["format"] == "full"
    assert "metadataHeaders" not in request.url.params
    assert request.headers["Authorization"] == "Bearer test-token"
    assert content.message.message_id == "m1"
    assert content.current_message_text == "We would like to invite you to an interview."
    rendered = content.model_dump_json()
    assert "test-token" not in rendered
    assert "snippet" not in rendered


@pytest.mark.asyncio
async def test_message_id_is_url_escaped_and_only_message_surface_exists() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_message_payload(), request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GmailRestContentProvider(client, access_token="test-token")
        await provider.get_message_content(" m/1 ")

    assert seen[0].url.path == "/gmail/v1/users/me/messages/m/1"
    assert not hasattr(provider, "get_thread")
    assert not hasattr(provider, "list_messages")
    assert not hasattr(provider, "search")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "gmail_unauthorized"),
        (403, "gmail_forbidden"),
        (404, "gmail_not_found"),
        (429, "gmail_rate_limited"),
        (500, "gmail_provider_error"),
    ],
)
async def test_provider_maps_http_failures_without_leaking_response_body(
    status: int,
    code: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"error": "private provider detail"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GmailRestContentProvider(client, access_token="test-token")
        with pytest.raises(GmailProviderError) as exc_info:
            await provider.get_message_content("m1")

    assert exc_info.value.code == code
    assert str(exc_info.value) == code
    assert "private provider detail" not in str(exc_info.value)
    assert "test-token" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_provider_maps_timeout_to_bounded_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private timeout detail", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GmailRestContentProvider(client, access_token="test-token")
        with pytest.raises(GmailProviderError) as exc_info:
            await provider.get_message_content("m1")

    assert exc_info.value.code == "gmail_timeout"
    assert str(exc_info.value) == "gmail_timeout"


@pytest.mark.asyncio
async def test_provider_maps_invalid_json_to_bounded_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not-json",
            headers={"content-type": "application/json"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GmailRestContentProvider(client, access_token="test-token")
        with pytest.raises(GmailProviderError) as exc_info:
            await provider.get_message_content("m1")

    assert exc_info.value.code == "gmail_payload_invalid"


def test_provider_rejects_empty_access_token() -> None:
    client = httpx.AsyncClient()
    try:
        with pytest.raises(ValueError, match="access_token"):
            GmailRestContentProvider(client, access_token="   ")
    finally:
        import asyncio

        asyncio.run(client.aclose())


@pytest.mark.asyncio
async def test_provider_rejects_empty_message_id_before_network() -> None:
    async with httpx.AsyncClient() as client:
        provider = GmailRestContentProvider(client, access_token="test-token")
        with pytest.raises(ValueError, match="message_id"):
            await provider.get_message_content("   ")
