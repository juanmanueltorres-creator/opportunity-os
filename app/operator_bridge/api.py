from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.operator_bridge.models import (
    ObservationImportRequest,
    ObservationImportResult,
    ObservationPreview,
    OperatorObservation,
)
from app.operator_bridge.service import OperatorBridgeService


def create_operator_router(service: OperatorBridgeService | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/operator")

    @router.post("/observations/preview", response_model=ObservationPreview)
    def preview_observation(observation: OperatorObservation) -> ObservationPreview:
        if service is None:
            raise HTTPException(
                status_code=503,
                detail="relationship_storage_unavailable",
            )
        return service.preview(observation)

    @router.post("/observations/import", response_model=ObservationImportResult)
    def import_observation(request: ObservationImportRequest) -> ObservationImportResult:
        if service is None:
            raise HTTPException(
                status_code=503,
                detail="relationship_storage_unavailable",
            )
        return service.import_observation(
            request,
            processed_at=datetime.now(timezone.utc),
        )

    return router
