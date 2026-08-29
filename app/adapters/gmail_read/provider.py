from __future__ import annotations

from typing import Protocol
from urllib.parse import quote

import httpx

from app.adapters.gmail_read.models import GmailMessageEnvelope, GmailThreadEnvelope
from app.adapters.gmail_read.normalizer import (
    normalize_message_payload,
    normalize_thread_payload,
)

_GMAIL_BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"
_METADATA_HEADERS = (
    "From",
    "To",
    "Cc",
    "Subject",
    "In-Reply-To",
    "References",
)


class GmailProviderError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class GmailReadProvider(Protocol):
    async def get_message(self, message_id: str) -> GmailMessageEnvelope: ...

    async def get_thread(self, thread_id: str) -> GmailThreadEnvelope: ...


class GmailRestReadProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        access_token: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        token = access_token.strip()
        if not token:
            raise ValueError("access_token must be non-empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._client = client
        self._access_token = token
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def _params() -> list[tuple[str, str]]:
        return [
            ("format", "metadata"),
            *[("metadataHeaders", header) for header in _METADATA_HEADERS],
        ]

    @staticmethod
    def _status_error(status_code: int) -> str | None:
        if 200 <= status_code < 300:
            return None
        if status_code == 401:
            return "gmail_unauthorized"
        if status_code == 403:
            return "gmail_forbidden"
        if status_code == 404:
            return "gmail_not_found"
        if status_code == 429:
            return "gmail_rate_limited"
        return "gmail_provider_error"

    async def _get_json(self, path: str) -> object:
        try:
            response = await self._client.get(
                f"{_GMAIL_BASE_URL}/{path}",
                params=self._params(),
                headers={"Authorization": f"Bearer {self._access_token}"},
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise GmailProviderError("gmail_timeout") from exc
        except httpx.RequestError as exc:
            raise GmailProviderError("gmail_provider_error") from exc

        error_code = self._status_error(response.status_code)
        if error_code is not None:
            raise GmailProviderError(error_code)

        try:
            return response.json()
        except ValueError as exc:
            raise GmailProviderError("gmail_payload_invalid") from exc

    async def get_message(self, message_id: str) -> GmailMessageEnvelope:
        safe_id = quote(message_id.strip(), safe="")
        if not safe_id:
            raise ValueError("message_id must be non-empty")
        payload = await self._get_json(f"messages/{safe_id}")
        try:
            return normalize_message_payload(payload)
        except ValueError as exc:
            raise GmailProviderError("gmail_payload_invalid") from exc

    async def get_thread(self, thread_id: str) -> GmailThreadEnvelope:
        safe_id = quote(thread_id.strip(), safe="")
        if not safe_id:
            raise ValueError("thread_id must be non-empty")
        payload = await self._get_json(f"threads/{safe_id}")
        try:
            return normalize_thread_payload(payload)
        except ValueError as exc:
            raise GmailProviderError("gmail_payload_invalid") from exc
