from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import FastAPI

from app.api.routes import RadarServiceProtocol, TargetRadarServiceProtocol, create_api_router
from app.connectors.base import JobConnector
from app.models.domain import CandidateProfile
from app.operator_bridge.api import create_operator_router
from app.operator_bridge.service import OperatorBridgeService
from app.profiles import load_profile
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.service import RadarService
from app.radar.sources import SourceRegistry, build_connectors, load_source_config
from app.radar.taxonomy import AliasRegistry, TaxonomyResolver
from app.relationships.context import (
    EmptyRelationshipMemory,
    RelationshipMemory,
    SQLiteRelationshipMemory,
)
from app.relationships.repository import SQLiteRelationshipRepository
from app.relationships.service import RelationshipService
from app.repositories.enrichments import SQLiteEnrichmentRepository
from app.repositories.opportunities import SQLiteOpportunityRepository
from app.targets.registry import load_target_registry
from app.targets.service import TargetRadarService


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


def _operator_import_enabled() -> bool:
    raw = os.getenv("OPPORTUNITY_OPERATOR_IMPORT_ENABLED", "false").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("OPPORTUNITY_OPERATOR_IMPORT_ENABLED must be boolean")


def _load_source_registry() -> SourceRegistry:
    path = Path(os.getenv("OPPORTUNITY_SOURCES_PATH", "sources.local.yaml"))
    if not path.exists():
        return SourceRegistry(sources=[])
    return load_source_config(path)


def _relationship_path() -> Path:
    return Path(
        os.getenv(
            "OPPORTUNITY_RELATIONSHIPS_PATH",
            "state/relationships.local.sqlite3",
        )
    )


def _load_default_relationship_memory() -> RelationshipMemory:
    path = _relationship_path()
    if not path.exists():
        return EmptyRelationshipMemory()
    repository = SQLiteRelationshipRepository(path)
    repository.initialize()
    return SQLiteRelationshipMemory(repository)


def _load_operator_bridge_service() -> OperatorBridgeService | None:
    path = _relationship_path()
    if not path.exists():
        return None
    repository = SQLiteRelationshipRepository(path)
    repository.initialize()
    relationships = RelationshipService(repository)
    return OperatorBridgeService(repository, relationships)


def _load_default_target_service(
    relationship_memory: RelationshipMemory,
) -> TargetRadarService | None:
    path = Path(os.getenv("OPPORTUNITY_TARGETS_PATH", "targets.local.yaml"))
    if not path.exists():
        return None
    return TargetRadarService(
        targets=load_target_registry(path),
        relationship_memory=relationship_memory,
    )


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
    target_service: TargetRadarServiceProtocol | None = None,
    enable_default_targets: bool = True,
    relationship_memory: RelationshipMemory | None = None,
    enable_default_relationships: bool = True,
    operator_bridge_service: OperatorBridgeService | None = None,
    enable_operator_import: bool | None = None,
) -> FastAPI:
    resolved_repository = repository or SQLiteOpportunityRepository(
        os.getenv("OPPORTUNITY_DB_PATH", "opportunities.db")
    )
    resolved_profile = profile if profile is not None else _load_default_profile()
    timeout_seconds = _http_timeout_seconds()

    if relationship_memory is not None:
        resolved_relationship_memory = relationship_memory
    elif enable_default_relationships:
        resolved_relationship_memory = _load_default_relationship_memory()
    else:
        resolved_relationship_memory = EmptyRelationshipMemory()

    operator_enabled = (
        enable_operator_import
        if enable_operator_import is not None
        else _operator_import_enabled()
    )
    resolved_operator_bridge_service = operator_bridge_service
    if operator_enabled and resolved_operator_bridge_service is None:
        resolved_operator_bridge_service = _load_operator_bridge_service()

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

    resolved_target_service = target_service
    if resolved_target_service is None and enable_default_targets:
        resolved_target_service = _load_default_target_service(
            resolved_relationship_memory
        )

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
            target_service=resolved_target_service,
            relationship_memory=resolved_relationship_memory,
        )
    )
    if operator_enabled:
        api.include_router(create_operator_router(resolved_operator_bridge_service))
    return api


app = create_app()
