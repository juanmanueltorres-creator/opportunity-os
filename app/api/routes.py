from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Protocol

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.availability.models import OpportunityAvailability
from app.availability.repository import SQLiteAvailabilityRepository
from app.connectors.base import ConnectorError, JobConnector
from app.connectors.remotive import RemotiveConnector
from app.matching.scorer import assess_opportunity
from app.models.domain import CandidateProfile, Opportunity, OpportunityAssessment
from app.radar.community_digest import CommunityDigestPolicy
from app.radar.community_digest_preview import CommunityDigestPreview
from app.radar.community_digest_renderer import CommunityDigestRenderOptions
from app.radar.models import DailyRadarBatch
from app.radar.service import RadarSourceError
from app.radar.sources import ManualOpportunityInput
from app.relationships.context import (
    EmptyRelationshipMemory,
    RelationshipMemory,
    build_context_snapshot,
)
from app.relationships.models import RelationshipContext, RelationshipContextSnapshot
from app.repositories.opportunities import SQLiteOpportunityRepository
from app.services.ingestion import ingest
from app.targets.models import TargetAccountBatch, TargetRadarRunRequest


class IngestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created: int
    existing: int


class RadarServiceProtocol(Protocol):
    async def run(
        self,
        profile: CandidateProfile,
        *,
        now: datetime,
    ) -> DailyRadarBatch: ...

    def import_manual(
        self,
        manual: ManualOpportunityInput,
        *,
        now: datetime,
    ) -> Opportunity: ...


class CommunityDigestPreviewServiceProtocol(Protocol):
    def preview(
        self,
        *,
        now: datetime,
        policy: CommunityDigestPolicy | None = None,
        render_options: CommunityDigestRenderOptions | None = None,
    ) -> CommunityDigestPreview: ...


class CommunityDigestPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["whatsapp", "markdown"] = "whatsapp"
    timezone_name: str = Field(default="UTC", min_length=1)
    title: str = Field(
        default="Oportunidades y proyectos — Equipo Geoespacial",
        min_length=1,
    )
    include_intro: bool = True
    include_footer: bool = True
    max_items: int = Field(default=10, ge=1, le=50)
    max_per_source: int | None = Field(default=2, ge=1)
    max_per_bucket: int | None = Field(default=None, ge=1)
    min_freshness_score: float = Field(default=20.0, ge=0, le=100)


class TargetRadarServiceProtocol(Protocol):
    def run(
        self,
        profile: CandidateProfile,
        *,
        now: datetime,
        current_reasons: dict[str, str] | None = None,
    ) -> TargetAccountBatch: ...


def create_api_router(
    *,
    repository: SQLiteOpportunityRepository,
    availability_repository: SQLiteAvailabilityRepository | None,
    profile: CandidateProfile | None,
    remotive_connector: JobConnector | None,
    timeout_seconds: float,
    radar_service: RadarServiceProtocol | None = None,
    community_digest_preview_service: CommunityDigestPreviewServiceProtocol | None = None,
    target_service: TargetRadarServiceProtocol | None = None,
    relationship_memory: RelationshipMemory | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    resolved_relationship_memory = relationship_memory or EmptyRelationshipMemory()

    @router.get("/opportunities", response_model=list[Opportunity])
    def list_opportunities() -> list[Opportunity]:
        return repository.list()

    @router.get("/opportunities/{opportunity_id}", response_model=Opportunity)
    def get_opportunity(opportunity_id: str) -> Opportunity:
        opportunity = repository.get(opportunity_id)
        if opportunity is None:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        return opportunity

    @router.get(
        "/opportunities/{opportunity_id}/availability",
        response_model=OpportunityAvailability,
    )
    def get_opportunity_availability(
        opportunity_id: str,
    ) -> OpportunityAvailability:
        if repository.get(opportunity_id) is None:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        if availability_repository is None:
            raise HTTPException(
                status_code=503,
                detail="Availability memory unavailable",
            )
        state = availability_repository.get(opportunity_id)
        if state is None:
            raise HTTPException(
                status_code=404,
                detail="Availability history not found",
            )
        return state

    @router.post("/opportunities/manual", response_model=Opportunity)
    def import_manual_opportunity(manual: ManualOpportunityInput) -> Opportunity:
        if radar_service is None:
            raise HTTPException(status_code=503, detail="Radar service unavailable")
        return radar_service.import_manual(
            manual,
            now=datetime.now(timezone.utc),
        )

    @router.post("/ingest/remotive", response_model=IngestionResponse)
    async def ingest_remotive() -> IngestionResponse:
        try:
            if remotive_connector is not None:
                result = await ingest(
                    remotive_connector,
                    repository,
                    availability_repository=availability_repository,
                    observed_at=datetime.now(timezone.utc),
                )
            else:
                async with httpx.AsyncClient() as client:
                    result = await ingest(
                        RemotiveConnector(client, timeout_seconds=timeout_seconds),
                        repository,
                        availability_repository=availability_repository,
                        observed_at=datetime.now(timezone.utc),
                    )
        except ConnectorError as exc:
            raise HTTPException(
                status_code=502,
                detail="Upstream job source unavailable",
            ) from exc

        return IngestionResponse(created=result.created, existing=result.existing)

    @router.post(
        "/assessments/{opportunity_id}",
        response_model=OpportunityAssessment,
    )
    def assess(opportunity_id: str) -> OpportunityAssessment:
        opportunity = repository.get(opportunity_id)
        if opportunity is None:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        if profile is None:
            raise HTTPException(status_code=503, detail="Candidate profile unavailable")
        return assess_opportunity(opportunity, profile)

    @router.post("/radar/run", response_model=DailyRadarBatch)
    async def run_radar() -> DailyRadarBatch:
        if profile is None:
            raise HTTPException(status_code=503, detail="Candidate profile unavailable")
        if radar_service is None:
            raise HTTPException(status_code=503, detail="Radar service unavailable")
        try:
            return await radar_service.run(
                profile,
                now=datetime.now(timezone.utc),
            )
        except RadarSourceError as exc:
            raise HTTPException(
                status_code=502,
                detail="Radar sources unavailable",
            ) from exc

    @router.post(
        "/community/digest/preview",
        response_model=CommunityDigestPreview,
    )
    def preview_community_digest(
        request: CommunityDigestPreviewRequest | None = None,
    ) -> CommunityDigestPreview:
        if community_digest_preview_service is None:
            raise HTTPException(
                status_code=503,
                detail="Community digest preview unavailable",
            )

        resolved = request or CommunityDigestPreviewRequest()
        try:
            policy = CommunityDigestPolicy(
                max_items=resolved.max_items,
                max_per_source=resolved.max_per_source,
                max_per_bucket=resolved.max_per_bucket,
                min_freshness_score=resolved.min_freshness_score,
            )
            render_options = CommunityDigestRenderOptions(
                title=resolved.title,
                timezone_name=resolved.timezone_name,
                include_intro=resolved.include_intro,
                include_footer=resolved.include_footer,
                format=resolved.format,
            )
            return community_digest_preview_service.preview(
                now=datetime.now(timezone.utc),
                policy=policy,
                render_options=render_options,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid community digest preview options",
            ) from exc

    @router.post("/targets/radar/run", response_model=TargetAccountBatch)
    def run_target_radar(
        request: TargetRadarRunRequest | None = None,
    ) -> TargetAccountBatch:
        if profile is None:
            raise HTTPException(status_code=503, detail="Candidate profile unavailable")
        if target_service is None:
            raise HTTPException(
                status_code=503,
                detail="Target account registry unavailable",
            )
        now = datetime.now(timezone.utc)
        if request is None or not request.current_reasons:
            return target_service.run(profile, now=now)
        return target_service.run(
            profile,
            now=now,
            current_reasons=request.current_reasons,
        )

    @router.get(
        "/relationships/context",
        response_model=RelationshipContextSnapshot,
    )
    def list_relationship_context() -> RelationshipContextSnapshot:
        now = datetime.now(timezone.utc)
        return build_context_snapshot(
            resolved_relationship_memory,
            resolved_relationship_memory.account_ids(),
            now=now,
        )

    @router.get(
        "/relationships/{account_id}/context",
        response_model=RelationshipContext,
    )
    def get_relationship_context(
        account_id: str,
        current_reason: str | None = None,
    ) -> RelationshipContext:
        normalized_reason = current_reason.strip() if current_reason is not None else None
        if normalized_reason == "":
            normalized_reason = None
        return resolved_relationship_memory.context_for(
            account_id,
            now=datetime.now(timezone.utc),
            current_reason=normalized_reason,
        )

    return router
