from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Literal

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.connectors.ashby import AshbyConnector
from app.connectors.base import JobConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.lever import LeverConnector
from app.connectors.remotive import RemotiveConnector
from app.models.domain import Opportunity


class StrictSourceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RemotiveSourceConfig(StrictSourceModel):
    type: Literal["remotive"]
    enabled: bool = True


class GreenhouseSourceConfig(StrictSourceModel):
    type: Literal["greenhouse"]
    enabled: bool = True
    company_name: str = Field(min_length=1)
    board_token: str = Field(min_length=1)


class LeverSourceConfig(StrictSourceModel):
    type: Literal["lever"]
    enabled: bool = True
    company_name: str = Field(min_length=1)
    site: str = Field(min_length=1)


class AshbySourceConfig(StrictSourceModel):
    type: Literal["ashby"]
    enabled: bool = True
    company_name: str = Field(min_length=1)
    board_name: str = Field(min_length=1)


SourceConfig = RemotiveSourceConfig | GreenhouseSourceConfig | LeverSourceConfig | AshbySourceConfig


class SourceRegistry(StrictSourceModel):
    sources: list[SourceConfig] = Field(default_factory=list)


@dataclass(frozen=True)
class ConfiguredConnector:
    name: str
    connector: JobConnector


class ManualOpportunityInput(StrictSourceModel):
    source: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    company: str | None = Field(default=None, min_length=1)
    organization: str | None = Field(default=None, min_length=1)
    raw_description: str = Field(min_length=1)
    location: str | None = None
    remote_policy: str | None = None
    published_at: datetime | None = None
    application_deadline: datetime | None = None

    @field_validator("published_at", "application_deadline")
    @classmethod
    def require_aware_dates(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def require_company_or_organization(self) -> "ManualOpportunityInput":
        if not (self.company or self.organization):
            raise ValueError("company or organization is required")
        return self

    def to_opportunity(self, now: datetime) -> Opportunity:
        discovered_at = _aware_utc(now, field_name="now")
        company = (self.company or self.organization or "").strip()
        source = self.source.strip()
        source_url = self.source_url.strip()
        title = self.title.strip()
        description = self.raw_description.strip()

        if self.application_deadline is not None:
            deadline = self.application_deadline.astimezone(timezone.utc).date().isoformat()
            description = f"{description}\n\nApplication deadline: {deadline}"

        identity_payload = "\n".join(
            [source.casefold(), source_url, company.casefold(), title.casefold()]
        )
        digest = hashlib.sha256(identity_payload.encode("utf-8")).hexdigest()[:20]
        source_id = f"manual-{digest}"

        return Opportunity(
            id=f"{source}:{source_id}",
            source=source,
            source_id=source_id,
            source_url=source_url,
            company=company,
            title=title,
            description=description,
            discovered_at=discovered_at,
            location=_optional_text(self.location),
            remote_policy=_optional_text(self.remote_policy),
            published_at=self.published_at,
        )


def load_source_config(path: str | Path) -> SourceRegistry:
    source_path = Path(path)
    try:
        payload = yaml.safe_load(source_path.read_text(encoding="utf-8"))
        return SourceRegistry.model_validate(payload)
    except (OSError, yaml.YAMLError, ValidationError, TypeError) as exc:
        raise ValueError(f"Invalid source registry: {source_path}") from exc


def build_connectors(
    registry: SourceRegistry,
    client: httpx.AsyncClient,
    timeout_seconds: float,
) -> list[ConfiguredConnector]:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    configured: list[ConfiguredConnector] = []
    for source in registry.sources:
        if not source.enabled:
            continue
        if isinstance(source, RemotiveSourceConfig):
            configured.append(
                ConfiguredConnector(
                    name="remotive",
                    connector=RemotiveConnector(client, timeout_seconds=timeout_seconds),
                )
            )
        elif isinstance(source, GreenhouseSourceConfig):
            configured.append(
                ConfiguredConnector(
                    name=f"greenhouse:{source.board_token}",
                    connector=GreenhouseConnector(
                        client,
                        board_token=source.board_token,
                        company_name=source.company_name,
                        timeout_seconds=timeout_seconds,
                    ),
                )
            )
        elif isinstance(source, LeverSourceConfig):
            configured.append(
                ConfiguredConnector(
                    name=f"lever:{source.site}",
                    connector=LeverConnector(
                        client,
                        site=source.site,
                        company_name=source.company_name,
                        timeout_seconds=timeout_seconds,
                    ),
                )
            )
        elif isinstance(source, AshbySourceConfig):
            configured.append(
                ConfiguredConnector(
                    name=f"ashby:{source.board_name}",
                    connector=AshbyConnector(
                        client,
                        board_name=source.board_name,
                        company_name=source.company_name,
                        timeout_seconds=timeout_seconds,
                    ),
                )
            )
    return configured


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    clean = value.strip()
    return clean or None
