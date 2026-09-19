from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from pydantic import Field, field_validator

from app.availability.daily_curation import DailyCurationPolicy
from app.availability.daily_curation_operator_view import (
    DailyCurationOperatorView,
    DailyCurationOperatorViewOptions,
    DailyCurationOperatorViewService,
)
from app.radar.community_digest_renderer import CommunityDigestRenderOptions
from app.radar.models import StrictRadarModel
from app.radar.source_refresh import SourceRefreshRun, SourceRefreshService


REFRESH_CURATION_OPERATOR_VERSION = "refresh-curation-operator-run-v1"


class RefreshCurationOperatorRun(StrictRadarModel):
    run_version: str = REFRESH_CURATION_OPERATOR_VERSION
    run_id: str = Field(min_length=1)
    generated_at: datetime
    source_refresh: SourceRefreshRun
    operator_view: DailyCurationOperatorView
    partial_source_failure: bool
    external_reads: list[str] = Field(default_factory=list)
    external_actions: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("external_actions")
    @classmethod
    def require_no_downstream_external_actions(
        cls,
        value: list[str],
    ) -> list[str]:
        if value:
            raise ValueError("external_actions must be empty")
        return value


class RefreshCurationOperatorService:
    def __init__(
        self,
        *,
        source_refresh_service: SourceRefreshService,
        operator_view_service: DailyCurationOperatorViewService,
    ) -> None:
        self.source_refresh_service = source_refresh_service
        self.operator_view_service = operator_view_service

    async def run(
        self,
        *,
        now: datetime,
        source_names: list[str] | None = None,
        policy: DailyCurationPolicy | None = None,
        digest_render_options: CommunityDigestRenderOptions | None = None,
        view_options: DailyCurationOperatorViewOptions | None = None,
    ) -> RefreshCurationOperatorRun:
        generated_at = _aware_utc(now)

        source_refresh = await self.source_refresh_service.run(
            now=generated_at,
            source_names=source_names,
        )

        operator_view = self.operator_view_service.build(
            now=generated_at,
            policy=policy,
            digest_render_options=digest_render_options,
            view_options=view_options,
        )

        if operator_view.generated_at != generated_at:
            raise RuntimeError("operator view snapshot timestamp mismatch")

        return RefreshCurationOperatorRun(
            run_id=refresh_curation_run_id(
                source_refresh=source_refresh,
                operator_view=operator_view,
            ),
            generated_at=generated_at,
            source_refresh=source_refresh,
            operator_view=operator_view,
            partial_source_failure=source_refresh.error_count > 0,
            external_reads=list(source_refresh.external_reads),
            external_actions=[],
        )


def refresh_curation_run_id(
    *,
    source_refresh: SourceRefreshRun,
    operator_view: DailyCurationOperatorView,
) -> str:
    payload = {
        "run_version": REFRESH_CURATION_OPERATOR_VERSION,
        "source_refresh": source_refresh.model_dump(
            mode="json",
            exclude_none=False,
        ),
        "operator_view": operator_view.model_dump(
            mode="json",
            exclude_none=False,
        ),
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"refresh-curation-{digest[:20]}"

def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)
