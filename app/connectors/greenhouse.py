from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.connectors.base import ConnectorError, ConnectorPayloadError, ConnectorTimeoutError
from app.models.domain import Opportunity


class GreenhouseConnector:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        board_token: str,
        company_name: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not board_token.strip() or not company_name.strip():
            raise ValueError("board_token and company_name are required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.client = client
        self.board_token = board_token.strip()
        self.company_name = company_name.strip()
        self.timeout_seconds = timeout_seconds

    async def fetch(self) -> list[Opportunity]:
        url = (
            "https://boards-api.greenhouse.io/v1/boards/"
            f"{quote(self.board_token, safe='')}/jobs"
        )
        try:
            response = await self.client.get(
                url,
                params={"content": "true"},
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

        return self.normalize_payload(
            payload,
            company_name=self.company_name,
            discovered_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def normalize_payload(
        payload: Any,
        *,
        company_name: str,
        discovered_at: datetime,
    ) -> list[Opportunity]:
        try:
            if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
                raise TypeError("jobs must be a list")

            jobs: list[Opportunity] = []
            for raw in payload["jobs"]:
                if not isinstance(raw, dict):
                    raise TypeError("job must be an object")
                location_raw = raw.get("location")
                location = None
                if isinstance(location_raw, dict):
                    name = location_raw.get("name")
                    location = str(name).strip() if name not in (None, "") else None

                content = raw["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("content is required")

                source_id = str(raw["id"])
                jobs.append(
                    Opportunity(
                        id=f"greenhouse:{source_id}",
                        source="greenhouse",
                        source_id=source_id,
                        source_url=str(raw["absolute_url"]),
                        company=company_name,
                        title=str(raw["title"]),
                        description=content,
                        discovered_at=discovered_at,
                        location=location,
                        remote_policy=(
                            "remote"
                            if location is not None and "remote" in location.casefold()
                            else None
                        ),
                        published_at=None,
                    )
                )
            return jobs
        except (KeyError, TypeError, ValueError) as exc:
            raise ConnectorPayloadError("Invalid upstream job payload") from exc
