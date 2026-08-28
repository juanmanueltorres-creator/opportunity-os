from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import ValidationError

from app.connectors.base import ConnectorError, ConnectorPayloadError, ConnectorTimeoutError
from app.models.domain import Opportunity

REMOTIVE_JOBS_URL = "https://remotive.com/api/remote-jobs"


class RemotiveConnector:
    def __init__(self, client: httpx.AsyncClient, timeout_seconds: float = 10.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.client = client
        self.timeout_seconds = timeout_seconds

    async def fetch(self) -> list[Opportunity]:
        try:
            response = await self.client.get(
                REMOTIVE_JOBS_URL,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ConnectorTimeoutError("Upstream job source timed out") from exc
        except httpx.HTTPError as exc:
            raise ConnectorError("Upstream job source unavailable") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorPayloadError("Invalid upstream job payload") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise ConnectorPayloadError("Invalid upstream job payload")

        discovered_at = datetime.now(timezone.utc)
        normalized: list[Opportunity] = []
        try:
            for raw_job in payload["jobs"]:
                normalized.append(self._normalize_job(raw_job, discovered_at))
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise ConnectorPayloadError("Invalid upstream job payload") from exc

        return normalized

    @staticmethod
    def _normalize_job(raw_job: Any, discovered_at: datetime) -> Opportunity:
        if not isinstance(raw_job, dict):
            raise TypeError("job must be an object")

        source_id = str(raw_job["id"])
        published_at = RemotiveConnector._parse_datetime(raw_job.get("publication_date"))
        location = RemotiveConnector._optional_text(raw_job.get("candidate_required_location"))
        compensation = RemotiveConnector._optional_text(raw_job.get("salary"))

        return Opportunity(
            id=f"remotive:{source_id}",
            source="remotive",
            source_id=source_id,
            source_url=str(raw_job["url"]),
            company=str(raw_job["company_name"]),
            title=str(raw_job["title"]),
            description=str(raw_job["description"]),
            discovered_at=discovered_at,
            location=location,
            remote_policy="remote",
            published_at=published_at,
            required_skills=[],
            preferred_skills=[],
            compensation=compensation,
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise TypeError("publication_date must be a string")

        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
