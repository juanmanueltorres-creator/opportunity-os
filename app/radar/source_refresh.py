from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Literal

from pydantic import Field, field_validator

from app.availability.repository import SQLiteAvailabilityRepository
from app.connectors.base import ConnectorError
from app.radar.models import StrictRadarModel
from app.radar.sources import ConfiguredConnector
from app.repositories.opportunities import SQLiteOpportunityRepository
from app.services.ingestion import ingest


RefreshSourceStatus = Literal["ok", "error"]
SOURCE_REFRESH_VERSION = "source-refresh-run-v1"


class SourceRefreshDiagnostic(StrictRadarModel):
    source: str = Field(min_length=1)
    status: RefreshSourceStatus
    fetched: int = Field(ge=0)
    created: int = Field(ge=0)
    existing: int = Field(ge=0)
    seen_recorded: int = Field(ge=0)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class SourceRefreshRun(StrictRadarModel):
    run_version: str = SOURCE_REFRESH_VERSION
    run_id: str = Field(min_length=1)
    generated_at: datetime
    requested_sources: list[str] = Field(default_factory=list)
    configured_sources: list[str] = Field(default_factory=list)
    diagnostics: list[SourceRefreshDiagnostic] = Field(default_factory=list)
    source_count: int = Field(ge=0)
    ok_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    fetched_count: int = Field(ge=0)
    created_count: int = Field(ge=0)
    existing_count: int = Field(ge=0)
    seen_recorded_count: int = Field(ge=0)
    closure_inference: bool = False
    external_actions: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("external_actions")
    @classmethod
    def no_downstream_external_actions(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("external_actions must be empty")
        return value


class SourceRefreshService:
    def __init__(
        self,
        *,
        opportunity_repository: SQLiteOpportunityRepository,
        availability_repository: SQLiteAvailabilityRepository,
        connectors: list[ConfiguredConnector],
    ) -> None:
        names = [item.name for item in connectors]
        if len(names) != len(set(names)):
            raise ValueError("configured connector names must be unique")
        self.opportunity_repository = opportunity_repository
        self.availability_repository = availability_repository
        self.connectors = list(connectors)

    @property
    def configured_source_names(self) -> list[str]:
        return [item.name for item in self.connectors]

    async def run(
        self,
        *,
        now: datetime,
        source_names: list[str] | None = None,
    ) -> SourceRefreshRun:
        generated_at = _aware_utc(now)
        configured = self.configured_source_names
        selected = _select_connectors(self.connectors, source_names)
        requested = (
            [item.name for item in selected]
            if source_names is None
            else list(source_names)
        )

        diagnostics: list[SourceRefreshDiagnostic] = []
        for item in selected:
            try:
                result = await ingest(
                    item.connector,
                    self.opportunity_repository,
                    availability_repository=self.availability_repository,
                    observed_at=generated_at,
                )
            except ConnectorError:
                diagnostics.append(
                    SourceRefreshDiagnostic(
                        source=item.name,
                        status="error",
                        fetched=0,
                        created=0,
                        existing=0,
                        seen_recorded=0,
                        code="source_unavailable",
                        message="Source unavailable",
                    )
                )
                continue

            diagnostics.append(
                SourceRefreshDiagnostic(
                    source=item.name,
                    status="ok",
                    fetched=result.created + result.existing,
                    created=result.created,
                    existing=result.existing,
                    seen_recorded=result.created + result.existing,
                    code="source_refreshed",
                    message="Source refreshed",
                )
            )

        totals = {
            "source_count": len(diagnostics),
            "ok_count": sum(item.status == "ok" for item in diagnostics),
            "error_count": sum(item.status == "error" for item in diagnostics),
            "fetched_count": sum(item.fetched for item in diagnostics),
            "created_count": sum(item.created for item in diagnostics),
            "existing_count": sum(item.existing for item in diagnostics),
            "seen_recorded_count": sum(
                item.seen_recorded for item in diagnostics
            ),
        }
        return SourceRefreshRun(
            run_id=_run_id(
                generated_at=generated_at,
                requested_sources=requested,
                configured_sources=configured,
                diagnostics=diagnostics,
            ),
            generated_at=generated_at,
            requested_sources=requested,
            configured_sources=configured,
            diagnostics=diagnostics,
            closure_inference=False,
            external_actions=[],
            **totals,
        )


def _select_connectors(
    connectors: list[ConfiguredConnector],
    source_names: list[str] | None,
) -> list[ConfiguredConnector]:
    if source_names is None:
        return list(connectors)

    normalized = [name.strip() for name in source_names]
    if any(not name for name in normalized):
        raise ValueError("source names must not be blank")
    if len(normalized) != len(set(normalized)):
        raise ValueError("source names must be unique")

    by_name = {item.name: item for item in connectors}
    unknown = [name for name in normalized if name not in by_name]
    if unknown:
        raise ValueError("requested source is not configured")

    return [by_name[name] for name in normalized]


def _run_id(
    *,
    generated_at: datetime,
    requested_sources: list[str],
    configured_sources: list[str],
    diagnostics: list[SourceRefreshDiagnostic],
) -> str:
    payload = {
        "run_version": SOURCE_REFRESH_VERSION,
        "generated_at": generated_at.isoformat(),
        "requested_sources": requested_sources,
        "configured_sources": configured_sources,
        "diagnostics": [
            item.model_dump(mode="json", exclude_none=False)
            for item in diagnostics
        ],
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"source-refresh-{digest[:20]}"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)
