from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.connectors.base import ConnectorError, ConnectorPayloadError, ConnectorTimeoutError
from app.models.domain import Opportunity


class LeverConnector:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        site: str,
        company_name: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not site.strip() or not company_name.strip():
            raise ValueError("site and company_name are required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.client = client
        self.site = site.strip()
        self.company_name = company_name.strip()
        self.timeout_seconds = timeout_seconds

    async def fetch(self) -> list[Opportunity]:
        url = f"https://api.lever.co/v0/postings/{quote(self.site, safe='')}"
        try:
            response = await self.client.get(
                url,
                params={"mode": "json"},
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
            if not isinstance(payload, list):
                raise TypeError("payload must be a list")

            jobs: list[Opportunity] = []
            for raw in payload:
                if not isinstance(raw, dict):
                    raise TypeError("job must be an object")
                categories = raw.get("categories")
                if categories is not None and not isinstance(categories, dict):
                    raise TypeError("categories must be an object")
                categories = categories or {}

                description = raw.get("descriptionPlain") or raw.get("description")
                if not isinstance(description, str) or not description.strip():
                    raise ValueError("description is required")

                published_at = None

                location_value = categories.get("location")
                location = (
                    str(location_value).strip()
                    if location_value not in (None, "")
                    else None
                )
                workplace = raw.get("workplaceType")
                remote_policy = (
                    str(workplace).strip().casefold()
                    if workplace not in (None, "")
                    else None
                )
                source_id = str(raw["id"])
                jobs.append(
                    Opportunity(
                        id=f"lever:{source_id}",
                        source="lever",
                        source_id=source_id,
                        source_url=str(raw["hostedUrl"]),
                        company=company_name,
                        title=str(raw["text"]),
                        description=description,
                        discovered_at=discovered_at,
                        location=location,
                        remote_policy=remote_policy,
                        published_at=published_at,
                    )
                )
            return jobs
        except (KeyError, TypeError, ValueError) as exc:
            raise ConnectorPayloadError("Invalid upstream job payload") from exc
