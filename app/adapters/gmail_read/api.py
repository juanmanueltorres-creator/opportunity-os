from fastapi import APIRouter, HTTPException

from app.adapters.gmail_read.models import GmailObservationResult, GmailReadSelection
from app.adapters.gmail_read.service import GmailReadService


def create_gmail_read_router(service: GmailReadService | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/adapters/gmail")

    @router.post("/observe", response_model=GmailObservationResult)
    async def observe(selection: GmailReadSelection) -> GmailObservationResult:
        if service is None:
            raise HTTPException(status_code=503, detail="gmail_read_unavailable")
        return await service.observe(selection)

    return router
