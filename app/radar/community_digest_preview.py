from __future__ import annotations

from datetime import datetime, timezone

from pydantic import Field, field_validator

from app.availability.repository import SQLiteAvailabilityRepository
from app.radar.community_digest import (
    CommunityDigest,
    CommunityDigestCandidate,
    CommunityDigestPolicy,
    build_community_digest,
)
from app.radar.community_digest_renderer import (
    CommunityDigestRenderOptions,
    DigestRenderFormat,
    render_community_digest,
)
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.models import StrictRadarModel
from app.repositories.opportunities import SQLiteOpportunityRepository


class CommunityDigestPreview(StrictRadarModel):
    generated_at: datetime
    candidate_count: int = Field(ge=0)
    digest: CommunityDigest
    rendered_text: str
    format: DigestRenderFormat

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone(timezone.utc)


class CommunityDigestPreviewService:
    def __init__(
        self,
        *,
        opportunity_repository: SQLiteOpportunityRepository,
        extractor: RuleBasedRequirementExtractor,
        availability_repository: SQLiteAvailabilityRepository | None = None,
        candidate_lookback_days: int = 90,
    ) -> None:
        if candidate_lookback_days < 1:
            raise ValueError("candidate_lookback_days must be positive")
        self.opportunity_repository = opportunity_repository
        self.extractor = extractor
        self.availability_repository = availability_repository
        self.candidate_lookback_days = candidate_lookback_days

    def preview(
        self,
        *,
        now: datetime,
        policy: CommunityDigestPolicy | None = None,
        render_options: CommunityDigestRenderOptions | None = None,
        excluded_opportunity_ids: set[str] | None = None,
        candidate_lookback_days: int | None = None,
    ) -> CommunityDigestPreview:
        generated_at = _aware_utc(now)
        resolved_options = render_options or CommunityDigestRenderOptions()
        lookback_days = (
            self.candidate_lookback_days
            if candidate_lookback_days is None
            else candidate_lookback_days
        )
        if lookback_days < 1:
            raise ValueError("candidate_lookback_days must be positive")

        opportunities = self.opportunity_repository.list_radar_candidates(
            now=generated_at,
            lookback_days=lookback_days,
        )
        excluded = excluded_opportunity_ids or set()
        opportunities = [
            opportunity
            for opportunity in opportunities
            if opportunity.id not in excluded
        ]
        availability_by_id = (
            self.availability_repository.get_many(
                [opportunity.id for opportunity in opportunities]
            )
            if self.availability_repository is not None
            else {}
        )
        candidates = [
            CommunityDigestCandidate(
                opportunity=opportunity,
                enrichment=self.extractor.extract(opportunity),
                availability=availability_by_id.get(opportunity.id),
            )
            for opportunity in opportunities
        ]

        digest = build_community_digest(
            candidates,
            now=generated_at,
            policy=policy,
        )
        rendered = render_community_digest(
            digest,
            options=resolved_options,
        )
        return CommunityDigestPreview(
            generated_at=generated_at,
            candidate_count=len(candidates),
            digest=digest,
            rendered_text=rendered,
            format=resolved_options.format,
        )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)
