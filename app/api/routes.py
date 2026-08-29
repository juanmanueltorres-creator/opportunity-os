from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from app.connectors.base import ConnectorError, JobConnector
from app.connectors.remotive import RemotiveConnector
from app.matching.scorer import assess_opportunity
from app.models.domain import CandidateProfile, Opportunity, OpportunityAssessment
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
from app.targets.models import TargetAccountBatch


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


class TargetRadarServiceProtocol(Protocol):
    def run(
        self,
        profile: CandidateProfile,
        *,
        now: datetime,
    ) -> TargetAccountBatch: ...


def create_api_router(
    *,
    repository: SQLiteOpportunityRepository,
    profile: CandidateProfile | None,
    remotive_connector: JobConnector | None,
    timeout_seconds: float,
    radar_service: RadarServiceProtocol | None = None,
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
                result = await ingest(remotive_connector, repository)
            else:
                async with httpx.AsyncClient() as client:
                    result = await ingest(
                        RemotiveConnector(client, timeout_seconds=timeout_seconds),
                        repository,
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

    @router.post("/targets/radar/run", response_model=TargetAccountBatch)
    def run_target_radar() -> TargetAccountBatch:
        if profile is None:
            raise HTTPException(status_code=503, detail="Candidate profile unavailable")
        if target_service is None:
            raise HTTPException(
                status_code=503,
                detail="Target account registry unavailable",
            )
        return target_service.run(
            profile,
            now=datetime.now(timezone.utc),
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
    def get_relationship_context(account_id: str) -> RelationshipContext:
        return resolved_relationship_memory.context_for(
            account_id,
            now=datetime.now(timezone.utc),
        )

    return router
