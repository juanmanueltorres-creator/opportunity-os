import httpx
import pytest

from app.adapters.gmail_read.provider import GmailProviderError, GmailRestReadProvider


def _message_payload(message_id: str = "m1", thread_id: str = "t1") -> dict[str, object]:
    return {
        "id": message_id,
        "threadId": thread_id,
        "internalDate": "1788019200000",
        "labelIds": ["SENT"],
        "payload": {
            "headers": [
                {"name": "From", "value": "owner@example.test"},
                {"name": "To", "value": "person@example.test"},
                {"name": "Subject", "value": "Hello"},
            ]
        },
        "snippet": "must not enter normalized model",
    }


@pytest.mark.asyncio
async def test_get_message_uses_metadata_read_endpoint_and_bearer_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_message_payload(), request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GmailRestReadProvider(client, access_token="test-token")
        message = await provider.get_message("m1")

    assert message.message_id == "m1"
    assert message.from_address == "owner@example.test"
    assert len(seen) == 1
    request = seen[0]
    assert request.method == "GET"
    assert request.url.path == "/gmail/v1/users/me/messages/m1"
    assert request.url.params["format"] == "metadata"
    assert set(request.url.params.get_list("metadataHeaders")) == {
        "From",
        "To",
        "Cc",
        "Subject",
        "In-Reply-To",
        "References",
    }
    assert request.headers["Authorization"] == "Bearer test-token"
    assert "test-token" not in message.model_dump_json()


@pytest.mark.asyncio
async def test_get_thread_uses_metadata_read_endpoint() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"id": "t1", "messages": [_message_payload()]},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GmailRestReadProvider(client, access_token="test-token")
        thread = await provider.get_thread("t1")

    assert thread.thread_id == "t1"
    assert len(thread.messages) == 1
    assert seen[0].url.path == "/gmail/v1/users/me/threads/t1"
    assert seen[0].url.params["format"] == "metadata"


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
async def test_provider_maps_http_failures_without_response_body(
    status: int,
    code: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"error": "secret provider detail"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GmailRestReadProvider(client, access_token="test-token")
        with pytest.raises(GmailProviderError) as exc_info:
            await provider.get_message("m1")

    assert exc_info.value.code == code
    assert str(exc_info.value) == code
    assert "secret provider detail" not in str(exc_info.value)
    assert "test-token" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_provider_maps_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timeout detail", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GmailRestReadProvider(client, access_token="test-token")
        with pytest.raises(GmailProviderError) as exc_info:
            await provider.get_message("m1")

    assert exc_info.value.code == "gmail_timeout"
    assert str(exc_info.value) == "gmail_timeout"


@pytest.mark.asyncio
async def test_provider_maps_malformed_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not-json",
            headers={"content-type": "application/json"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GmailRestReadProvider(client, access_token="test-token")
        with pytest.raises(GmailProviderError) as exc_info:
            await provider.get_message("m1")

    assert exc_info.value.code == "gmail_payload_invalid"


def test_provider_rejects_empty_access_token() -> None:
    client = httpx.AsyncClient()
    try:
        with pytest.raises(ValueError, match="access_token"):
            GmailRestReadProvider(client, access_token="   ")
    finally:
        import asyncio

        asyncio.run(client.aclose())
