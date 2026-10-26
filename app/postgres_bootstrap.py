"""Fail-closed PostgreSQL composition root for the full Opportunity OS API.

Selecting OPPORTUNITY_STORAGE_BACKEND=postgres at import time replaces all
default SQLite repository construction with PostgreSQL adapters. The legacy
SQLite composition remains available only when explicitly selected.
"""
from __future__ import annotations

import hmac
import os

from fastapi import Request
from fastapi.responses import JSONResponse

from app.repositories.postgres import (
    PostgresOpportunityRepository, PostgresAvailabilityRepository,
    PostgresEnrichmentRepository,
)
from app.repositories.postgres_history import PostgresApplicationHistory
from app.relationships.postgres_repository import PostgresRelationshipRepository
from app.relationships.context import SQLiteRelationshipMemory
from app.relationships.service import RelationshipService
from app.curation.postgres_repository import PostgresCurationLedgerRepository
from app.operator_bridge.service import OperatorBridgeService
from app.postgres_workflow_api import app as private_storage_api


def create_postgres_app():
    # Import lazily: app.main imports this factory only after create_app exists.
    from app.main import create_app

    if not os.getenv("OPPORTUNITY_POSTGRES_WRITE_DSN"):
        raise RuntimeError("PostgreSQL write connection required; SQLite fallback disabled")
    if not os.getenv("OPPORTUNITY_POSTGRES_DSN"):
        raise RuntimeError("PostgreSQL read connection required; SQLite fallback disabled")

    relationships = PostgresRelationshipRepository()
    app = create_app(
        repository=PostgresOpportunityRepository(),
        availability_repository=PostgresAvailabilityRepository(),
        enrichment_repository=PostgresEnrichmentRepository(),
        curation_ledger_repository=PostgresCurationLedgerRepository(),
        relationship_memory=SQLiteRelationshipMemory(relationships),
        operator_bridge_service=OperatorBridgeService(
            relationships, RelationshipService(relationships)
        ),
        application_history=PostgresApplicationHistory(),
    )

    @app.middleware("http")
    async def private_auth(request: Request, call_next):
        # Only the liveness endpoint is public. Includes Swagger/OpenAPI and
        # nested /storage paths; the private subapp validates its own token too.
        if request.url.path == "/health":
            return await call_next(request)
        token = os.getenv("OPPORTUNITY_API_TOKEN", "")
        if len(token) < 32:
            return JSONResponse(status_code=503, content={"detail":"Private API token missing"})
        authorization = request.headers.get("authorization", "")
        if not hmac.compare_digest(authorization, "Bearer " + token):
            return JSONResponse(status_code=401, content={"detail":"Unauthorized"})
        return await call_next(request)

    # New history CRUD and filters, in addition to the original radar routes.
    # This is a separate prefix so existing endpoint contracts are untouched.
    app.mount("/storage", private_storage_api)
    return app
