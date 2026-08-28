from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI

from app.api.routes import create_api_router
from app.connectors.base import JobConnector
from app.models.domain import CandidateProfile
from app.profiles import load_profile
from app.repositories.opportunities import SQLiteOpportunityRepository


def _load_default_profile() -> CandidateProfile | None:
    profile_path = Path(os.getenv("OPPORTUNITY_PROFILE_PATH", "profile.local.yaml"))
    if not profile_path.exists():
        return None
    return load_profile(profile_path)


def _http_timeout_seconds() -> float:
    raw = os.getenv("HTTP_TIMEOUT_SECONDS", "10")
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise ValueError("HTTP_TIMEOUT_SECONDS must be numeric") from exc
    if timeout <= 0:
        raise ValueError("HTTP_TIMEOUT_SECONDS must be positive")
    return timeout


def create_app(
    repository: SQLiteOpportunityRepository | None = None,
    profile: CandidateProfile | None = None,
    remotive_connector: JobConnector | None = None,
) -> FastAPI:
    resolved_repository = repository or SQLiteOpportunityRepository(
        os.getenv("OPPORTUNITY_DB_PATH", "opportunities.db")
    )
    resolved_profile = profile if profile is not None else _load_default_profile()
    timeout_seconds = _http_timeout_seconds()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        resolved_repository.initialize()
        yield

    api = FastAPI(title="Opportunity OS", version="0.1.0", lifespan=lifespan)

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "opportunity-os"}

    api.include_router(
        create_api_router(
            repository=resolved_repository,
            profile=resolved_profile,
            remotive_connector=remotive_connector,
            timeout_seconds=timeout_seconds,
        )
    )
    return api


app = create_app()
