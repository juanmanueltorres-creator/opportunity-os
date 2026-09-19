from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Protocol

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.availability.daily_curation import (
    DailyCurationPolicy,
    DailyCurationRun,
)
from app.availability.daily_curation_operator_view import (
    DailyCurationOperatorView,
    DailyCurationOperatorViewOptions,
)
from app.availability.models import OpportunityAvailability
from app.availability.refresh_curation_operator import (
    RefreshCurationOperatorRun,
)
from app.availability.repository import SQLiteAvailabilityRepository
from app.availability.review_evidence_draft import (
    ReviewEvidenceDraft,
    ReviewEvidenceDraftRequest,
)
from app.availability.verification_models import (
    VerificationConfirmRequest,
    VerificationConfirmResult,
    VerificationEvidence,
    VerificationPreview,
)
from app.availability.verification_queue import (
    VerificationQueue,
    VerificationQueuePolicy,
)
from app.availability.verification_review_session import (
    VerificationReviewSession,
    VerificationReviewSessionPolicy,
)
from app.curation.models import (
    CurationChangeBrief,
    CurationPublicationCoverage,
    CurationRunDelta,
    CurationRunHistory,
    CurationRunRecordResult,
    PublicationCheckpointConfirmRequest,
    PublicationCheckpointEvidence,
    PublicationCheckpointPreview,
    PublicationConfirmResult,
)
from app.connectors.base import ConnectorError, JobConnector
from app.connectors.remotive import RemotiveConnector
from app.matching.scorer import assess_opportunity
from app.models.domain import CandidateProfile, Opportunity, OpportunityAssessment
from app.radar.community_digest import CommunityDigestPolicy
from app.radar.community_digest_preview import CommunityDigestPreview
from app.radar.community_digest_renderer import CommunityDigestRenderOptions
from app.radar.models import DailyRadarBatch
from app.radar.source_refresh import SourceRefreshRun
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
from app.targets.models import TargetAccountBatch, TargetRadarRunRequest


class IngestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created: int
    existing: int


class CurationLedgerServiceProtocol(Protocol):
    def latest_publication_coverage(
        self,
    ) -> CurationPublicationCoverage: ...

    def latest_change_brief(
        self,
        *,
        format: Literal["markdown", "plain"] = "markdown",
    ) -> CurationChangeBrief: ...

    def latest_delta(self) -> CurationRunDelta: ...

    def history(
        self,
        *,
        limit: int = 20,
    ) -> CurationRunHistory: ...

    def record_run(
        self,
        run: RefreshCurationOperatorRun,
        *,
        recorded_at: datetime,
    ) -> CurationRunRecordResult: ...

    def preview_publication(
        self,
        evidence: PublicationCheckpointEvidence,
    ) -> PublicationCheckpointPreview: ...

    def confirm_publication(
        self,
        request: PublicationCheckpointConfirmRequest,
        *,
        processed_at: datetime,
    ) -> PublicationConfirmResult: ...


class RefreshCurationOperatorServiceProtocol(Protocol):
    async def run(
        self,
        *,
        now: datetime,
        source_names: list[str] | None = None,
        policy: DailyCurationPolicy | None = None,
        digest_render_options: CommunityDigestRenderOptions | None = None,
        view_options: DailyCurationOperatorViewOptions | None = None,
    ) -> RefreshCurationOperatorRun: ...


class SourceRefreshServiceProtocol(Protocol):
    async def run(
        self,
        *,
        now: datetime,
        source_names: list[str] | None = None,
    ) -> SourceRefreshRun: ...


class SourceRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )


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


class DailyCurationOperatorViewServiceProtocol(Protocol):
    def build(
        self,
        *,
        now: datetime,
        policy: DailyCurationPolicy | None = None,
        digest_render_options: CommunityDigestRenderOptions | None = None,
        view_options: DailyCurationOperatorViewOptions | None = None,
    ) -> DailyCurationOperatorView: ...


class DailyCurationServiceProtocol(Protocol):
    def run(
        self,
        *,
        now: datetime,
        policy: DailyCurationPolicy | None = None,
        render_options: CommunityDigestRenderOptions | None = None,
    ) -> DailyCurationRun: ...


class DailyCurationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_batch_size: int = Field(default=5, ge=1, le=20)
    held_items_limit: int = Field(default=20, ge=1, le=100)

    candidate_lookback_days: int = Field(default=90, ge=1, le=365)
    deadline_soon_days: int = Field(default=2, ge=0, le=30)
    standard_reverify_after_days: int = Field(default=7, ge=1, le=365)
    fast_market_reverify_after_days: int = Field(default=2, ge=1, le=90)
    fast_market_max_age_days: int = Field(default=14, ge=1, le=90)

    digest_max_items: int = Field(default=10, ge=1, le=50)
    digest_max_per_source: int | None = Field(default=2, ge=1)
    digest_max_per_bucket: int | None = Field(default=None, ge=1)
    digest_min_freshness_score: float = Field(default=20.0, ge=0, le=100)
    publication_cooldown_days: int = Field(default=30, ge=1, le=365)

    format: Literal["whatsapp", "markdown"] = "whatsapp"
    timezone_name: str = Field(default="UTC", min_length=1)
    title: str = Field(
        default="Oportunidades y proyectos — Equipo Geoespacial",
        min_length=1,
    )
    include_intro: bool = True
    include_footer: bool = True


class DailyCurationOperatorViewRequest(DailyCurationRequest):
    view_title: str = Field(
        default="Opportunity OS — Daily Curation",
        min_length=1,
    )
    view_format: Literal["markdown", "plain"] = "markdown"
    include_review_checklists: bool = True
    include_held_details: bool = True


class RefreshCurationOperatorRequest(DailyCurationOperatorViewRequest):
    sources: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )


class ReviewEvidenceDraftServiceProtocol(Protocol):
    def build(
        self,
        request: ReviewEvidenceDraftRequest,
        *,
        now: datetime,
    ) -> ReviewEvidenceDraft: ...


class VerificationReviewSessionServiceProtocol(Protocol):
    def build(
        self,
        *,
        now: datetime,
        policy: VerificationReviewSessionPolicy | None = None,
    ) -> VerificationReviewSession: ...


class VerificationReviewSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_size: int = Field(default=5, ge=1, le=20)
    candidate_lookback_days: int = Field(default=90, ge=1, le=365)
    deadline_soon_days: int = Field(default=2, ge=0, le=30)
    standard_reverify_after_days: int = Field(default=7, ge=1, le=365)
    fast_market_reverify_after_days: int = Field(default=2, ge=1, le=90)
    fast_market_max_age_days: int = Field(default=14, ge=1, le=90)


class VerificationQueueServiceProtocol(Protocol):
    def build(
        self,
        *,
        now: datetime,
        policy: VerificationQueuePolicy | None = None,
    ) -> VerificationQueue: ...


class VerificationQueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_items: int = Field(default=20, ge=1, le=100)
    candidate_lookback_days: int = Field(default=90, ge=1, le=365)
    deadline_soon_days: int = Field(default=2, ge=0, le=30)
    standard_reverify_after_days: int = Field(default=7, ge=1, le=365)
    fast_market_reverify_after_days: int = Field(default=2, ge=1, le=90)
    fast_market_max_age_days: int = Field(default=14, ge=1, le=90)


class AvailabilityVerificationServiceProtocol(Protocol):
    def preview(
        self,
        evidence: VerificationEvidence,
    ) -> VerificationPreview: ...

    def confirm(
        self,
        request: VerificationConfirmRequest,
        *,
        processed_at: datetime,
    ) -> VerificationConfirmResult: ...


class CommunityDigestPreviewServiceProtocol(Protocol):
    def preview(
        self,
        *,
        now: datetime,
        policy: CommunityDigestPolicy | None = None,
        render_options: CommunityDigestRenderOptions | None = None,
        excluded_opportunity_ids: set[str] | None = None,
    ) -> CommunityDigestPreview: ...


class CommunityDigestPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["whatsapp", "markdown"] = "whatsapp"
    timezone_name: str = Field(default="UTC", min_length=1)
    title: str = Field(
        default="Oportunidades y proyectos — Equipo Geoespacial",
        min_length=1,
    )
    include_intro: bool = True
    include_footer: bool = True
    max_items: int = Field(default=10, ge=1, le=50)
    max_per_source: int | None = Field(default=2, ge=1)
    max_per_bucket: int | None = Field(default=None, ge=1)
    min_freshness_score: float = Field(default=20.0, ge=0, le=100)


class TargetRadarServiceProtocol(Protocol):
    def run(
        self,
        profile: CandidateProfile,
        *,
        now: datetime,
        current_reasons: dict[str, str] | None = None,
    ) -> TargetAccountBatch: ...


def create_api_router(
    *,
    repository: SQLiteOpportunityRepository,
    availability_repository: SQLiteAvailabilityRepository | None = None,
    availability_verification_service: AvailabilityVerificationServiceProtocol | None = None,
    verification_queue_service: VerificationQueueServiceProtocol | None = None,
    verification_review_session_service: VerificationReviewSessionServiceProtocol | None = None,
    review_evidence_draft_service: ReviewEvidenceDraftServiceProtocol | None = None,
    daily_curation_service: DailyCurationServiceProtocol | None = None,
    daily_curation_operator_view_service: DailyCurationOperatorViewServiceProtocol | None = None,
    source_refresh_service: SourceRefreshServiceProtocol | None = None,
    refresh_curation_operator_service: RefreshCurationOperatorServiceProtocol | None = None,
    curation_ledger_service: CurationLedgerServiceProtocol | None = None,
    profile: CandidateProfile | None = None,
    remotive_connector: JobConnector | None,
    timeout_seconds: float,
    radar_service: RadarServiceProtocol | None = None,
    community_digest_preview_service: CommunityDigestPreviewServiceProtocol | None = None,
    target_service: TargetRadarServiceProtocol | None = None,
    relationship_memory: RelationshipMemory | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    resolved_relationship_memory = relationship_memory or EmptyRelationshipMemory()

    @router.get(
        "/curation/history/publication-coverage",
        response_model=CurationPublicationCoverage,
    )
    def get_latest_publication_coverage() -> CurationPublicationCoverage:
        if curation_ledger_service is None:
            raise HTTPException(
                status_code=503,
                detail="Curation ledger unavailable",
            )
        return curation_ledger_service.latest_publication_coverage()

    @router.get(
        "/curation/history/delta/brief",
        response_model=CurationChangeBrief,
    )
    def get_latest_curation_change_brief(
        format: Literal["markdown", "plain"] = Query(default="markdown"),
    ) -> CurationChangeBrief:
        if curation_ledger_service is None:
            raise HTTPException(
                status_code=503,
                detail="Curation ledger unavailable",
            )
        return curation_ledger_service.latest_change_brief(format=format)

    @router.get(
        "/curation/history/delta",
        response_model=CurationRunDelta,
    )
    def get_latest_curation_delta() -> CurationRunDelta:
        if curation_ledger_service is None:
            raise HTTPException(
                status_code=503,
                detail="Curation ledger unavailable",
            )
        return curation_ledger_service.latest_delta()

    @router.get(
        "/curation/history",
        response_model=CurationRunHistory,
    )
    def get_curation_history(
        limit: int = Query(default=20, ge=1, le=100),
    ) -> CurationRunHistory:
        if curation_ledger_service is None:
            raise HTTPException(
                status_code=503,
                detail="Curation ledger unavailable",
            )
        return curation_ledger_service.history(limit=limit)

    @router.post(
        "/curation/ledger/runs",
        response_model=CurationRunRecordResult,
    )
    def record_curation_run(
        run: RefreshCurationOperatorRun,
    ) -> CurationRunRecordResult:
        if curation_ledger_service is None:
            raise HTTPException(
                status_code=503,
                detail="Curation ledger unavailable",
            )
        return curation_ledger_service.record_run(
            run,
            recorded_at=datetime.now(timezone.utc),
        )

    @router.post(
        "/curation/publication/preview",
        response_model=PublicationCheckpointPreview,
    )
    def preview_publication_checkpoint(
        evidence: PublicationCheckpointEvidence,
    ) -> PublicationCheckpointPreview:
        if curation_ledger_service is None:
            raise HTTPException(
                status_code=503,
                detail="Curation ledger unavailable",
            )
        return curation_ledger_service.preview_publication(evidence)

    @router.post(
        "/curation/publication/confirm",
        response_model=PublicationConfirmResult,
    )
    def confirm_publication_checkpoint(
        request: PublicationCheckpointConfirmRequest,
    ) -> PublicationConfirmResult:
        if curation_ledger_service is None:
            raise HTTPException(
                status_code=503,
                detail="Curation ledger unavailable",
            )
        return curation_ledger_service.confirm_publication(
            request,
            processed_at=datetime.now(timezone.utc),
        )

    @router.post(
        "/curation/daily/refresh-view",
        response_model=RefreshCurationOperatorRun,
    )
    async def refresh_and_build_daily_curation_operator_view(
        request: RefreshCurationOperatorRequest | None = None,
    ) -> RefreshCurationOperatorRun:
        if refresh_curation_operator_service is None:
            raise HTTPException(
                status_code=503,
                detail="Refresh curation operator run unavailable",
            )
        resolved = request or RefreshCurationOperatorRequest()
        try:
            queue_policy = VerificationQueuePolicy(
                max_items=max(resolved.review_batch_size, 20),
                candidate_lookback_days=resolved.candidate_lookback_days,
                deadline_soon_days=resolved.deadline_soon_days,
                standard_reverify_after_days=(
                    resolved.standard_reverify_after_days
                ),
                fast_market_reverify_after_days=(
                    resolved.fast_market_reverify_after_days
                ),
                fast_market_max_age_days=resolved.fast_market_max_age_days,
            )
            digest_policy = CommunityDigestPolicy(
                max_items=resolved.digest_max_items,
                max_per_source=resolved.digest_max_per_source,
                max_per_bucket=resolved.digest_max_per_bucket,
                min_freshness_score=resolved.digest_min_freshness_score,
            )
            policy = DailyCurationPolicy(
                review_batch_size=resolved.review_batch_size,
                held_items_limit=resolved.held_items_limit,
                queue_policy=queue_policy,
                digest_policy=digest_policy,
                publication_cooldown_days=(
                    resolved.publication_cooldown_days
                ),
            )
            digest_render_options = CommunityDigestRenderOptions(
                title=resolved.title,
                timezone_name=resolved.timezone_name,
                include_intro=resolved.include_intro,
                include_footer=resolved.include_footer,
                format=resolved.format,
            )
            view_options = DailyCurationOperatorViewOptions(
                title=resolved.view_title,
                format=resolved.view_format,
                include_checklists=resolved.include_review_checklists,
                include_held_details=resolved.include_held_details,
            )
            return await refresh_curation_operator_service.run(
                now=datetime.now(timezone.utc),
                source_names=resolved.sources,
                policy=policy,
                digest_render_options=digest_render_options,
                view_options=view_options,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid refresh curation operator options",
            ) from exc

    @router.post(
        "/sources/refresh",
        response_model=SourceRefreshRun,
    )
    async def refresh_sources(
        request: SourceRefreshRequest | None = None,
    ) -> SourceRefreshRun:
        if source_refresh_service is None:
            raise HTTPException(
                status_code=503,
                detail="Source refresh unavailable",
            )
        resolved = request or SourceRefreshRequest()
        try:
            return await source_refresh_service.run(
                now=datetime.now(timezone.utc),
                source_names=resolved.sources,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid source refresh options",
            ) from exc

    @router.get("/opportunities", response_model=list[Opportunity])
    def list_opportunities() -> list[Opportunity]:
        return repository.list()

    @router.get("/opportunities/{opportunity_id}", response_model=Opportunity)
    def get_opportunity(opportunity_id: str) -> Opportunity:
        opportunity = repository.get(opportunity_id)
        if opportunity is None:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        return opportunity

    @router.get(
        "/opportunities/{opportunity_id}/availability",
        response_model=OpportunityAvailability,
    )
    def get_opportunity_availability(
        opportunity_id: str,
    ) -> OpportunityAvailability:
        if repository.get(opportunity_id) is None:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        if availability_repository is None:
            raise HTTPException(
                status_code=503,
                detail="Availability memory unavailable",
            )
        state = availability_repository.get(opportunity_id)
        if state is None:
            raise HTTPException(
                status_code=404,
                detail="Availability history not found",
            )
        return state

    @router.post(
        "/curation/daily/view",
        response_model=DailyCurationOperatorView,
    )
    def build_daily_curation_operator_view(
        request: DailyCurationOperatorViewRequest | None = None,
    ) -> DailyCurationOperatorView:
        if daily_curation_operator_view_service is None:
            raise HTTPException(
                status_code=503,
                detail="Daily curation operator view unavailable",
            )
        resolved = request or DailyCurationOperatorViewRequest()
        try:
            queue_policy = VerificationQueuePolicy(
                max_items=max(resolved.review_batch_size, 20),
                candidate_lookback_days=resolved.candidate_lookback_days,
                deadline_soon_days=resolved.deadline_soon_days,
                standard_reverify_after_days=(
                    resolved.standard_reverify_after_days
                ),
                fast_market_reverify_after_days=(
                    resolved.fast_market_reverify_after_days
                ),
                fast_market_max_age_days=resolved.fast_market_max_age_days,
            )
            digest_policy = CommunityDigestPolicy(
                max_items=resolved.digest_max_items,
                max_per_source=resolved.digest_max_per_source,
                max_per_bucket=resolved.digest_max_per_bucket,
                min_freshness_score=resolved.digest_min_freshness_score,
            )
            policy = DailyCurationPolicy(
                review_batch_size=resolved.review_batch_size,
                held_items_limit=resolved.held_items_limit,
                queue_policy=queue_policy,
                digest_policy=digest_policy,
                publication_cooldown_days=(
                    resolved.publication_cooldown_days
                ),
            )
            digest_render_options = CommunityDigestRenderOptions(
                title=resolved.title,
                timezone_name=resolved.timezone_name,
                include_intro=resolved.include_intro,
                include_footer=resolved.include_footer,
                format=resolved.format,
            )
            view_options = DailyCurationOperatorViewOptions(
                title=resolved.view_title,
                format=resolved.view_format,
                include_checklists=resolved.include_review_checklists,
                include_held_details=resolved.include_held_details,
            )
            return daily_curation_operator_view_service.build(
                now=datetime.now(timezone.utc),
                policy=policy,
                digest_render_options=digest_render_options,
                view_options=view_options,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid daily curation operator view options",
            ) from exc

    @router.post(
        "/curation/daily",
        response_model=DailyCurationRun,
    )
    def run_daily_curation(
        request: DailyCurationRequest | None = None,
    ) -> DailyCurationRun:
        if daily_curation_service is None:
            raise HTTPException(
                status_code=503,
                detail="Daily curation unavailable",
            )
        resolved = request or DailyCurationRequest()
        try:
            queue_policy = VerificationQueuePolicy(
                max_items=max(resolved.review_batch_size, 20),
                candidate_lookback_days=resolved.candidate_lookback_days,
                deadline_soon_days=resolved.deadline_soon_days,
                standard_reverify_after_days=(
                    resolved.standard_reverify_after_days
                ),
                fast_market_reverify_after_days=(
                    resolved.fast_market_reverify_after_days
                ),
                fast_market_max_age_days=resolved.fast_market_max_age_days,
            )
            digest_policy = CommunityDigestPolicy(
                max_items=resolved.digest_max_items,
                max_per_source=resolved.digest_max_per_source,
                max_per_bucket=resolved.digest_max_per_bucket,
                min_freshness_score=resolved.digest_min_freshness_score,
            )
            policy = DailyCurationPolicy(
                review_batch_size=resolved.review_batch_size,
                held_items_limit=resolved.held_items_limit,
                queue_policy=queue_policy,
                digest_policy=digest_policy,
                publication_cooldown_days=(
                    resolved.publication_cooldown_days
                ),
            )
            render_options = CommunityDigestRenderOptions(
                title=resolved.title,
                timezone_name=resolved.timezone_name,
                include_intro=resolved.include_intro,
                include_footer=resolved.include_footer,
                format=resolved.format,
            )
            return daily_curation_service.run(
                now=datetime.now(timezone.utc),
                policy=policy,
                render_options=render_options,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid daily curation options",
            ) from exc

    @router.post(
        "/availability/verification/draft",
        response_model=ReviewEvidenceDraft,
    )
    def build_review_evidence_draft(
        request: ReviewEvidenceDraftRequest,
    ) -> ReviewEvidenceDraft:
        if review_evidence_draft_service is None:
            raise HTTPException(
                status_code=503,
                detail="Review evidence draft unavailable",
            )
        return review_evidence_draft_service.build(
            request,
            now=datetime.now(timezone.utc),
        )

    @router.post(
        "/availability/verification/session",
        response_model=VerificationReviewSession,
    )
    def build_availability_verification_session(
        request: VerificationReviewSessionRequest | None = None,
    ) -> VerificationReviewSession:
        if verification_review_session_service is None:
            raise HTTPException(
                status_code=503,
                detail="Availability verification review session unavailable",
            )
        resolved = request or VerificationReviewSessionRequest()
        try:
            queue_policy = VerificationQueuePolicy(
                max_items=max(resolved.batch_size, 20),
                candidate_lookback_days=resolved.candidate_lookback_days,
                deadline_soon_days=resolved.deadline_soon_days,
                standard_reverify_after_days=(
                    resolved.standard_reverify_after_days
                ),
                fast_market_reverify_after_days=(
                    resolved.fast_market_reverify_after_days
                ),
                fast_market_max_age_days=resolved.fast_market_max_age_days,
            )
            policy = VerificationReviewSessionPolicy(
                batch_size=resolved.batch_size,
                queue_policy=queue_policy,
            )
            return verification_review_session_service.build(
                now=datetime.now(timezone.utc),
                policy=policy,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid availability verification review session options",
            ) from exc

    @router.post(
        "/availability/verification/queue",
        response_model=VerificationQueue,
    )
    def build_availability_verification_queue(
        request: VerificationQueueRequest | None = None,
    ) -> VerificationQueue:
        if verification_queue_service is None:
            raise HTTPException(
                status_code=503,
                detail="Availability verification queue unavailable",
            )
        resolved = request or VerificationQueueRequest()
        try:
            policy = VerificationQueuePolicy(
                max_items=resolved.max_items,
                candidate_lookback_days=resolved.candidate_lookback_days,
                deadline_soon_days=resolved.deadline_soon_days,
                standard_reverify_after_days=(
                    resolved.standard_reverify_after_days
                ),
                fast_market_reverify_after_days=(
                    resolved.fast_market_reverify_after_days
                ),
                fast_market_max_age_days=resolved.fast_market_max_age_days,
            )
            return verification_queue_service.build(
                now=datetime.now(timezone.utc),
                policy=policy,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid availability verification queue options",
            ) from exc

    @router.post(
        "/availability/verification/preview",
        response_model=VerificationPreview,
    )
    def preview_availability_verification(
        evidence: VerificationEvidence,
    ) -> VerificationPreview:
        if availability_verification_service is None:
            raise HTTPException(
                status_code=503,
                detail="Availability verification unavailable",
            )
        return availability_verification_service.preview(evidence)

    @router.post(
        "/availability/verification/confirm",
        response_model=VerificationConfirmResult,
    )
    def confirm_availability_verification(
        request: VerificationConfirmRequest,
    ) -> VerificationConfirmResult:
        if availability_verification_service is None:
            raise HTTPException(
                status_code=503,
                detail="Availability verification unavailable",
            )
        return availability_verification_service.confirm(
            request,
            processed_at=datetime.now(timezone.utc),
        )

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
                result = await ingest(
                    remotive_connector,
                    repository,
                    availability_repository=availability_repository,
                    observed_at=datetime.now(timezone.utc),
                )
            else:
                async with httpx.AsyncClient() as client:
                    result = await ingest(
                        RemotiveConnector(client, timeout_seconds=timeout_seconds),
                        repository,
                        availability_repository=availability_repository,
                        observed_at=datetime.now(timezone.utc),
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

    @router.post(
        "/community/digest/preview",
        response_model=CommunityDigestPreview,
    )
    def preview_community_digest(
        request: CommunityDigestPreviewRequest | None = None,
    ) -> CommunityDigestPreview:
        if community_digest_preview_service is None:
            raise HTTPException(
                status_code=503,
                detail="Community digest preview unavailable",
            )

        resolved = request or CommunityDigestPreviewRequest()
        try:
            policy = CommunityDigestPolicy(
                max_items=resolved.max_items,
                max_per_source=resolved.max_per_source,
                max_per_bucket=resolved.max_per_bucket,
                min_freshness_score=resolved.min_freshness_score,
            )
            render_options = CommunityDigestRenderOptions(
                title=resolved.title,
                timezone_name=resolved.timezone_name,
                include_intro=resolved.include_intro,
                include_footer=resolved.include_footer,
                format=resolved.format,
            )
            return community_digest_preview_service.preview(
                now=datetime.now(timezone.utc),
                policy=policy,
                render_options=render_options,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid community digest preview options",
            ) from exc

    @router.post("/targets/radar/run", response_model=TargetAccountBatch)
    def run_target_radar(
        request: TargetRadarRunRequest | None = None,
    ) -> TargetAccountBatch:
        if profile is None:
            raise HTTPException(status_code=503, detail="Candidate profile unavailable")
        if target_service is None:
            raise HTTPException(
                status_code=503,
                detail="Target account registry unavailable",
            )
        now = datetime.now(timezone.utc)
        if request is None or not request.current_reasons:
            return target_service.run(profile, now=now)
        return target_service.run(
            profile,
            now=now,
            current_reasons=request.current_reasons,
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
    def get_relationship_context(
        account_id: str,
        current_reason: str | None = None,
    ) -> RelationshipContext:
        normalized_reason = current_reason.strip() if current_reason is not None else None
        if normalized_reason == "":
            normalized_reason = None
        return resolved_relationship_memory.context_for(
            account_id,
            now=datetime.now(timezone.utc),
            current_reason=normalized_reason,
        )

    return router
