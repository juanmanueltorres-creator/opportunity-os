from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import FastAPI

from app.adapters.gmail_read.api import create_gmail_read_router
from app.availability.daily_curation import DailyCurationService
from app.availability.daily_curation_operator_view import (
    DailyCurationOperatorViewService,
)
from app.availability.repository import SQLiteAvailabilityRepository
from app.availability.refresh_curation_operator import (
    RefreshCurationOperatorService,
)
from app.availability.review_evidence_draft import ReviewEvidenceDraftService
from app.availability.verification_service import AvailabilityVerificationService
from app.availability.verification_queue import VerificationQueueService
from app.availability.verification_review_session import (
    VerificationReviewSessionService,
)
from app.curation.repository import SQLiteCurationLedgerRepository
from app.curation.service import CurationLedgerService
from app.adapters.gmail_read.service import GmailReadService
from app.api.routes import (
    AvailabilityVerificationServiceProtocol,
    CommunityDigestPreviewServiceProtocol,
    CurationLedgerServiceProtocol,
    DailyCurationOperatorViewServiceProtocol,
    DailyCurationServiceProtocol,
    ReviewEvidenceDraftServiceProtocol,
    VerificationQueueServiceProtocol,
    VerificationReviewSessionServiceProtocol,
    RadarServiceProtocol,
    RefreshCurationOperatorServiceProtocol,
    SourceRefreshServiceProtocol,
    TargetRadarServiceProtocol,
    create_api_router,
)
from app.connectors.base import JobConnector
from app.models.domain import CandidateProfile
from app.operator_bridge.api import create_operator_router
from app.operator_bridge.service import OperatorBridgeService
from app.process_email.api import create_process_email_router
from app.process_email.service import ProcessEmailService
from app.profiles import load_profile
from app.radar.community_digest_preview import CommunityDigestPreviewService
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.service import RadarService
from app.radar.source_refresh import SourceRefreshService
from app.radar.source_catalog import SourceCatalog, load_source_catalog
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


def _availability_verification_enabled() -> bool:
    raw = os.getenv(
        "OPPORTUNITY_AVAILABILITY_VERIFICATION_ENABLED",
        "false",
    ).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(
        "OPPORTUNITY_AVAILABILITY_VERIFICATION_ENABLED must be boolean"
    )


def _source_refresh_enabled() -> bool:
    raw = os.getenv(
        "OPPORTUNITY_SOURCE_REFRESH_ENABLED",
        "false",
    ).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("OPPORTUNITY_SOURCE_REFRESH_ENABLED must be boolean")


def _gmail_read_enabled() -> bool:
    raw = os.getenv("OPPORTUNITY_GMAIL_READ_ENABLED", "false").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("OPPORTUNITY_GMAIL_READ_ENABLED must be boolean")


def _process_email_enabled() -> bool:
    raw = os.getenv("OPPORTUNITY_PROCESS_EMAIL_ENABLED", "false").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("OPPORTUNITY_PROCESS_EMAIL_ENABLED must be boolean")


def _load_source_registry() -> SourceRegistry:
    path = Path(os.getenv("OPPORTUNITY_SOURCES_PATH", "sources.local.yaml"))
    if not path.exists():
        return SourceRegistry(sources=[])
    return load_source_config(path)


def _load_default_source_catalog() -> SourceCatalog | None:
    path = Path(
        os.getenv(
            "OPPORTUNITY_SOURCE_CATALOG_PATH",
            "config/source_catalog.yaml",
        )
    )
    if not path.exists():
        return None
    return load_source_catalog(path)


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
    community_digest_preview_service: CommunityDigestPreviewServiceProtocol | None = None,
    enable_default_community_digest_preview: bool = True,
    target_service: TargetRadarServiceProtocol | None = None,
    enable_default_targets: bool = True,
    relationship_memory: RelationshipMemory | None = None,
    enable_default_relationships: bool = True,
    operator_bridge_service: OperatorBridgeService | None = None,
    enable_operator_import: bool | None = None,
    gmail_read_service: GmailReadService | None = None,
    enable_gmail_read: bool | None = None,
    process_email_service: ProcessEmailService | None = None,
    enable_process_email: bool | None = None,
    *,
    availability_repository: SQLiteAvailabilityRepository | None = None,
    availability_verification_service: AvailabilityVerificationServiceProtocol | None = None,
    enable_availability_verification: bool | None = None,
    verification_queue_service: VerificationQueueServiceProtocol | None = None,
    enable_default_verification_queue: bool = True,
    verification_review_session_service: VerificationReviewSessionServiceProtocol | None = None,
    enable_default_verification_review_session: bool = True,
    review_evidence_draft_service: ReviewEvidenceDraftServiceProtocol | None = None,
    enable_default_review_evidence_draft: bool = True,
    daily_curation_service: DailyCurationServiceProtocol | None = None,
    enable_default_daily_curation: bool = True,
    daily_curation_operator_view_service: DailyCurationOperatorViewServiceProtocol | None = None,
    enable_default_daily_curation_operator_view: bool = True,
    source_refresh_service: SourceRefreshServiceProtocol | None = None,
    enable_source_refresh: bool | None = None,
    refresh_curation_operator_service: RefreshCurationOperatorServiceProtocol | None = None,
    enable_default_refresh_curation_operator: bool = True,
    curation_ledger_repository: SQLiteCurationLedgerRepository | None = None,
    curation_ledger_service: CurationLedgerServiceProtocol | None = None,
    enable_default_curation_ledger: bool = True,
) -> FastAPI:
    resolved_repository = repository or SQLiteOpportunityRepository(
        os.getenv("OPPORTUNITY_DB_PATH", "opportunities.db")
    )
    resolved_availability_repository = (
        availability_repository
        or SQLiteAvailabilityRepository(resolved_repository.path)
    )
    resolved_profile = profile if profile is not None else _load_default_profile()
    resolved_curation_ledger_repository = (
        curation_ledger_repository
        or (
            SQLiteCurationLedgerRepository(resolved_repository.path)
            if enable_default_curation_ledger
            else None
        )
    )
    resolved_curation_ledger_service = curation_ledger_service
    if (
        resolved_curation_ledger_service is None
        and resolved_curation_ledger_repository is not None
    ):
        resolved_curation_ledger_service = CurationLedgerService(
            repository=resolved_curation_ledger_repository,
        )
    timeout_seconds = _http_timeout_seconds()
    source_refresh_enabled = (
        enable_source_refresh
        if enable_source_refresh is not None
        else _source_refresh_enabled()
    )
    availability_verification_enabled = (
        enable_availability_verification
        if enable_availability_verification is not None
        else _availability_verification_enabled()
    )
    resolved_availability_verification_service = availability_verification_service
    if (
        availability_verification_enabled
        and resolved_availability_verification_service is None
    ):
        resolved_availability_verification_service = AvailabilityVerificationService(
            opportunity_repository=resolved_repository,
            availability_repository=resolved_availability_repository,
        )

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

    gmail_read_enabled = (
        enable_gmail_read
        if enable_gmail_read is not None
        else _gmail_read_enabled()
    )
    process_email_enabled = (
        enable_process_email
        if enable_process_email is not None
        else _process_email_enabled()
    )

    owned_http_client: httpx.AsyncClient | None = None
    resolved_radar_service = radar_service
    resolved_source_refresh_service = source_refresh_service
    resolved_community_digest_preview_service = community_digest_preview_service

    configured_connectors = []
    needs_configured_connectors = (
        (resolved_radar_service is None and enable_default_radar)
        or (
            resolved_source_refresh_service is None
            and source_refresh_enabled
        )
    )
    if needs_configured_connectors:
        source_registry = _load_source_registry()
        owned_http_client = httpx.AsyncClient()
        configured_connectors = build_connectors(
            source_registry,
            owned_http_client,
            timeout_seconds=timeout_seconds,
        )

    if (
        resolved_source_refresh_service is None
        and source_refresh_enabled
    ):
        resolved_source_refresh_service = SourceRefreshService(
            opportunity_repository=resolved_repository,
            availability_repository=resolved_availability_repository,
            connectors=configured_connectors,
        )

    default_extractor: RuleBasedRequirementExtractor | None = None
    needs_default_extractor = (
        (resolved_radar_service is None and enable_default_radar)
        or (
            resolved_community_digest_preview_service is None
            and enable_default_community_digest_preview
        )
    )
    if needs_default_extractor:
        default_extractor = RuleBasedRequirementExtractor(
            source_catalog=_load_default_source_catalog(),
        )

    if resolved_radar_service is None and enable_default_radar:
        enrichment_repository = SQLiteEnrichmentRepository(resolved_repository.path)
        alias_registry = AliasRegistry.load(_alias_registry_path())
        resolver = TaxonomyResolver(
            alias_registry=alias_registry,
            taxonomy_path=_taxonomy_path(),
        )
        if default_extractor is None:
            raise RuntimeError("default extractor unavailable")
        resolved_radar_service = RadarService(
            opportunity_repository=resolved_repository,
            enrichment_repository=enrichment_repository,
            connectors=configured_connectors,
            extractor=default_extractor,
            resolver=resolver,
            availability_repository=resolved_availability_repository,
        )
    else:
        enrichment_repository = None

    if (
        resolved_community_digest_preview_service is None
        and enable_default_community_digest_preview
    ):
        if default_extractor is None:
            default_extractor = RuleBasedRequirementExtractor(
                source_catalog=_load_default_source_catalog(),
            )
        resolved_community_digest_preview_service = CommunityDigestPreviewService(
            opportunity_repository=resolved_repository,
            extractor=default_extractor,
            availability_repository=resolved_availability_repository,
        )

    resolved_verification_queue_service = verification_queue_service
    if (
        resolved_verification_queue_service is None
        and enable_default_verification_queue
    ):
        queue_source_catalog = _load_default_source_catalog()
        queue_extractor = (
            default_extractor
            if default_extractor is not None
            else RuleBasedRequirementExtractor(
                source_catalog=queue_source_catalog,
            )
        )
        resolved_verification_queue_service = VerificationQueueService(
            opportunity_repository=resolved_repository,
            availability_repository=resolved_availability_repository,
            extractor=queue_extractor,
            source_catalog=(
                queue_extractor.source_catalog
                if queue_extractor.source_catalog is not None
                else queue_source_catalog
            ),
        )

    resolved_verification_review_session_service = (
        verification_review_session_service
    )
    if (
        resolved_verification_review_session_service is None
        and enable_default_verification_review_session
        and resolved_verification_queue_service is not None
    ):
        resolved_verification_review_session_service = (
            VerificationReviewSessionService(
                queue_service=resolved_verification_queue_service,
            )
        )

    resolved_review_evidence_draft_service = review_evidence_draft_service
    if (
        resolved_review_evidence_draft_service is None
        and enable_default_review_evidence_draft
    ):
        preview_only_verification_service = (
            resolved_availability_verification_service
            if resolved_availability_verification_service is not None
            else AvailabilityVerificationService(
                opportunity_repository=resolved_repository,
                availability_repository=resolved_availability_repository,
            )
        )
        resolved_review_evidence_draft_service = ReviewEvidenceDraftService(
            opportunity_repository=resolved_repository,
            availability_repository=resolved_availability_repository,
            verification_service=preview_only_verification_service,
        )

    resolved_daily_curation_service = daily_curation_service
    if (
        resolved_daily_curation_service is None
        and enable_default_daily_curation
        and resolved_verification_queue_service is not None
        and resolved_verification_review_session_service is not None
        and resolved_community_digest_preview_service is not None
    ):
        if (
            curation_ledger_service is not None
            and curation_ledger_repository is None
        ):
            raise ValueError(
                "curation_ledger_repository is required when injecting "
                "curation_ledger_service with default daily curation"
            )
        resolved_daily_curation_service = DailyCurationService(
            queue_service=resolved_verification_queue_service,
            review_session_service=(
                resolved_verification_review_session_service
            ),
            digest_preview_service=resolved_community_digest_preview_service,
            curation_ledger_repository=resolved_curation_ledger_repository,
        )

    resolved_daily_curation_operator_view_service = (
        daily_curation_operator_view_service
    )
    if (
        resolved_daily_curation_operator_view_service is None
        and enable_default_daily_curation_operator_view
        and resolved_daily_curation_service is not None
    ):
        resolved_daily_curation_operator_view_service = (
            DailyCurationOperatorViewService(
                daily_curation_service=resolved_daily_curation_service,
            )
        )

    resolved_refresh_curation_operator_service = (
        refresh_curation_operator_service
    )
    if (
        resolved_refresh_curation_operator_service is None
        and enable_default_refresh_curation_operator
        and resolved_source_refresh_service is not None
        and resolved_daily_curation_operator_view_service is not None
    ):
        resolved_refresh_curation_operator_service = (
            RefreshCurationOperatorService(
                source_refresh_service=resolved_source_refresh_service,
                operator_view_service=(
                    resolved_daily_curation_operator_view_service
                ),
            )
        )

    resolved_target_service = target_service
    if resolved_target_service is None and enable_default_targets:
        resolved_target_service = _load_default_target_service(
            resolved_relationship_memory
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        resolved_repository.initialize()
        resolved_availability_repository.initialize()
        if resolved_curation_ledger_repository is not None:
            resolved_curation_ledger_repository.initialize()
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
            availability_repository=resolved_availability_repository,
            availability_verification_service=resolved_availability_verification_service,
            verification_queue_service=resolved_verification_queue_service,
            verification_review_session_service=(
                resolved_verification_review_session_service
            ),
            review_evidence_draft_service=resolved_review_evidence_draft_service,
            daily_curation_service=resolved_daily_curation_service,
            daily_curation_operator_view_service=(
                resolved_daily_curation_operator_view_service
            ),
            source_refresh_service=resolved_source_refresh_service,
            refresh_curation_operator_service=(
                resolved_refresh_curation_operator_service
            ),
            curation_ledger_service=resolved_curation_ledger_service,
            profile=resolved_profile,
            remotive_connector=remotive_connector,
            timeout_seconds=timeout_seconds,
            radar_service=resolved_radar_service,
            community_digest_preview_service=resolved_community_digest_preview_service,
            target_service=resolved_target_service,
            relationship_memory=resolved_relationship_memory,
        )
    )
    if operator_enabled:
        api.include_router(create_operator_router(resolved_operator_bridge_service))
    if gmail_read_enabled:
        api.include_router(create_gmail_read_router(gmail_read_service))
    if process_email_enabled:
        api.include_router(create_process_email_router(process_email_service))
    return api


app = create_app()
