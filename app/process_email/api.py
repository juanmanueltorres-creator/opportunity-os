from fastapi import APIRouter, HTTPException

from app.process_email.models import ProcessEmailPreview, ProcessEmailSelection
from app.process_email.service import ProcessEmailService


def create_process_email_router(service: ProcessEmailService | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/process-email", tags=["process-email"])

    @router.post("/preview", response_model=ProcessEmailPreview)
    async def preview_process_email(
        selection: ProcessEmailSelection,
    ) -> ProcessEmailPreview:
        if service is None:
            raise HTTPException(status_code=503, detail="process_email_unavailable")
        return await service.preview(selection)

    return router
