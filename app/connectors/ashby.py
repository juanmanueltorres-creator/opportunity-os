from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.connectors.base import ConnectorError, ConnectorPayloadError, ConnectorTimeoutError
from app.models.domain import Opportunity


class AshbyConnector:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        board_name: str,
        company_name: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not board_name.strip() or not company_name.strip():
            raise ValueError("board_name and company_name are required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.client = client
        self.board_name = board_name.strip()
        self.company_name = company_name.strip()
        self.timeout_seconds = timeout_seconds

    async def fetch(self) -> list[Opportunity]:
        url = (
            "https://api.ashbyhq.com/posting-api/job-board/"
            f"{quote(self.board_name, safe='')}"
        )
        try:
            response = await self.client.get(url, timeout=self.timeout_seconds)
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
                if raw.get("isListed") is False:
                    continue

                job_url = str(raw["jobUrl"])
                source_id = urlparse(job_url).path.rstrip("/").split("/")[-1]
                if not source_id:
                    raise ValueError("job URL must contain an identifier")

                description = raw.get("descriptionPlain") or raw.get("descriptionHtml")
                if not isinstance(description, str) or not description.strip():
                    raise ValueError("description is required")

                published_raw = raw.get("publishedAt")
                published_at = None
                if published_raw not in (None, ""):
                    if not isinstance(published_raw, str):
                        raise TypeError("publishedAt must be a string")
                    published_at = datetime.fromisoformat(
                        published_raw.replace("Z", "+00:00")
                    )
                    if published_at.tzinfo is None or published_at.utcoffset() is None:
                        published_at = published_at.replace(tzinfo=timezone.utc)
                    published_at = published_at.astimezone(timezone.utc)

                location_raw = raw.get("location")
                location = (
                    str(location_raw).strip()
                    if location_raw not in (None, "")
                    else None
                )
                workplace_raw = raw.get("workplaceType")
                if workplace_raw not in (None, ""):
                    remote_policy = str(workplace_raw).strip().casefold()
                elif raw.get("isRemote") is True:
                    remote_policy = "remote"
                else:
                    remote_policy = None

                jobs.append(
                    Opportunity(
                        id=f"ashby:{source_id}",
                        source="ashby",
                        source_id=source_id,
                        source_url=job_url,
                        company=company_name,
                        title=str(raw["title"]),
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
