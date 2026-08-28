from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import FastAPI

from app.api.routes import RadarServiceProtocol, create_api_router
from app.connectors.base import JobConnector
from app.models.domain import CandidateProfile
from app.profiles import load_profile
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.service import RadarService
from app.radar.sources import SourceRegistry, build_connectors, load_source_config
from app.radar.taxonomy import AliasRegistry, TaxonomyResolver
from app.repositories.enrichments import SQLiteEnrichmentRepository
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


def _load_source_registry() -> SourceRegistry:
    path = Path(os.getenv("OPPORTUNITY_SOURCES_PATH", "sources.local.yaml"))
    if not path.exists():
        return SourceRegistry(sources=[])
    return load_source_config(path)


def _taxonomy_path() -> Path | None:
    raw = os.getenv("OPPORTUNITY_TAXONOMY_PATH", "").strip()
    return Path(raw) if raw else None


def _alias_registry_path() -> Path:
    return Path(
        os.getenv(
            "OPPORTUNITY_ALIAS_REGISTRY_PATH",
            "data/skill_aliases.yaml",
        )
    )


def create_app(
    repository: SQLiteOpportunityRepository | None = None,
    profile: CandidateProfile | None = None,
    remotive_connector: JobConnector | None = None,
    radar_service: RadarServiceProtocol | None = None,
    enable_default_radar: bool = True,
) -> FastAPI:
    resolved_repository = repository or SQLiteOpportunityRepository(
        os.getenv("OPPORTUNITY_DB_PATH", "opportunities.db")
    )
    resolved_profile = profile if profile is not None else _load_default_profile()
    timeout_seconds = _http_timeout_seconds()

    owned_http_client: httpx.AsyncClient | None = None
    resolved_radar_service = radar_service
    if resolved_radar_service is None and enable_default_radar:
        enrichment_repository = SQLiteEnrichmentRepository(resolved_repository.path)
        alias_registry = AliasRegistry.load(_alias_registry_path())
        resolver = TaxonomyResolver(
            alias_registry=alias_registry,
            taxonomy_path=_taxonomy_path(),
        )
        source_registry = _load_source_registry()
        owned_http_client = httpx.AsyncClient()
        resolved_radar_service = RadarService(
            opportunity_repository=resolved_repository,
            enrichment_repository=enrichment_repository,
            connectors=build_connectors(
                source_registry,
                owned_http_client,
                timeout_seconds=timeout_seconds,
            ),
            extractor=RuleBasedRequirementExtractor(),
            resolver=resolver,
        )
    else:
        enrichment_repository = None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        resolved_repository.initialize()
        if enrichment_repository is not None:
            enrichment_repository.initialize()
        try:
            yield
        finally:
            if owned_http_client is not None:
                await owned_http_client.aclose()

    api = FastAPI(title="Opportunity OS", version="0.2.0c1", lifespan=lifespan)

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "opportunity-os"}

    api.include_router(
        create_api_router(
            repository=resolved_repository,
            profile=resolved_profile,
            remotive_connector=remotive_connector,
            timeout_seconds=timeout_seconds,
            radar_service=resolved_radar_service,
        )
    )
    return api


app = create_app()
