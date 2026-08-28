from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from app.connectors.base import ConnectorError, JobConnector
from app.connectors.remotive import RemotiveConnector
from app.matching.scorer import assess_opportunity
from app.models.domain import CandidateProfile, Opportunity, OpportunityAssessment
from app.repositories.opportunities import SQLiteOpportunityRepository
from app.services.ingestion import ingest


class IngestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created: int
    existing: int


def create_api_router(
    *,
    repository: SQLiteOpportunityRepository,
    profile: CandidateProfile | None,
    remotive_connector: JobConnector | None,
    timeout_seconds: float,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/opportunities", response_model=list[Opportunity])
    def list_opportunities() -> list[Opportunity]:
        return repository.list()

    @router.get("/opportunities/{opportunity_id}", response_model=Opportunity)
    def get_opportunity(opportunity_id: str) -> Opportunity:
        opportunity = repository.get(opportunity_id)
        if opportunity is None:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        return opportunity

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

    return router
