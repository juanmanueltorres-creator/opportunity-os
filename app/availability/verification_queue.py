from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import Field, field_validator

from app.availability.models import AvailabilityState, OpportunityAvailability
from app.availability.repository import SQLiteAvailabilityRepository
from app.models.domain import Opportunity
from app.radar.models import OpportunityEnrichment, StrictRadarModel
from app.radar.source_catalog import SourceCatalog, SourceCatalogEntry
from app.radar.extractor import RuleBasedRequirementExtractor
from app.repositories.opportunities import SQLiteOpportunityRepository


VerificationReason = Literal[
    "DISCOVERY_ONLY_NEEDS_OFFICIAL_SOURCE",
    "DEADLINE_SOON_UNVERIFIED",
    "FAST_MARKET_UNVERIFIED",
    "SOURCE_REQUIRES_VERIFICATION",
    "VERIFICATION_STALE",
]
VerificationAction = Literal[
    "FIND_OFFICIAL_SOURCE",
    "VERIFY_CURRENT_SOURCE",
    "REVERIFY_CURRENT_SOURCE",
]

_CLOSED_STATUSES = {"closed", "expired", "filled", "inactive"}


@dataclass(frozen=True)
class VerificationQueuePolicy:
    max_items: int = 20
    candidate_lookback_days: int = 90
    deadline_soon_days: int = 2
    standard_reverify_after_days: int = 7
    fast_market_reverify_after_days: int = 2
    fast_market_max_age_days: int = 14

    def __post_init__(self) -> None:
        if self.max_items < 1:
            raise ValueError("max_items must be positive")
        if self.candidate_lookback_days < 1:
            raise ValueError("candidate_lookback_days must be positive")
        if self.deadline_soon_days < 0:
            raise ValueError("deadline_soon_days must not be negative")
        if self.standard_reverify_after_days < 1:
            raise ValueError("standard_reverify_after_days must be positive")
        if self.fast_market_reverify_after_days < 1:
            raise ValueError("fast_market_reverify_after_days must be positive")
        if self.fast_market_max_age_days < 1:
            raise ValueError("fast_market_max_age_days must be positive")


class VerificationQueueItem(StrictRadarModel):
    opportunity_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    source_key: str | None = None
    source_category: str | None = None
    availability_state: AvailabilityState
    last_seen_at: datetime | None = None
    last_verified_at: datetime | None = None
    application_deadline: datetime | None = None
    freshness_policy: str = Field(min_length=1)
    priority_score: int = Field(ge=0, le=100)
    reason_codes: list[VerificationReason] = Field(min_length=1)
    suggested_action: VerificationAction

    @field_validator(
        "last_seen_at",
        "last_verified_at",
        "application_deadline",
    )
    @classmethod
    def datetimes_must_be_aware(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)


class VerificationQueue(StrictRadarModel):
    generated_at: datetime
    policy: dict[str, int]
    inspected_count: int = Field(ge=0)
    items: list[VerificationQueueItem] = Field(default_factory=list)
    count: int = Field(ge=0)
    reason_counts: dict[str, int] = Field(default_factory=dict)

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone(timezone.utc)


class VerificationQueueService:
    def __init__(
        self,
        *,
        opportunity_repository: SQLiteOpportunityRepository,
        availability_repository: SQLiteAvailabilityRepository,
        extractor: RuleBasedRequirementExtractor,
        source_catalog: SourceCatalog | None,
    ) -> None:
        self.opportunity_repository = opportunity_repository
        self.availability_repository = availability_repository
        self.extractor = extractor
        self.source_catalog = source_catalog

    def build(
        self,
        *,
        now: datetime,
        policy: VerificationQueuePolicy | None = None,
    ) -> VerificationQueue:
        generated_at = _aware_utc(now)
        resolved_policy = policy or VerificationQueuePolicy()
        opportunities = self.opportunity_repository.list_radar_candidates(
            now=generated_at,
            lookback_days=resolved_policy.candidate_lookback_days,
        )

        items: list[VerificationQueueItem] = []
        for opportunity in opportunities:
            enrichment = self.extractor.extract(opportunity)
            availability = self.availability_repository.get(opportunity.id)
            source_entry = (
                self.source_catalog.resolve(
                    opportunity.source,
                    opportunity.source_url,
                )
                if self.source_catalog is not None
                else None
            )
            item = _queue_item(
                opportunity=opportunity,
                enrichment=enrichment,
                availability=availability,
                source_entry=source_entry,
                now=generated_at,
                policy=resolved_policy,
            )
            if item is not None:
                items.append(item)

        items.sort(key=_queue_sort_key)
        selected = items[: resolved_policy.max_items]
        reason_counts: dict[str, int] = {}
        for item in selected:
            for reason in item.reason_codes:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1

        return VerificationQueue(
            generated_at=generated_at,
            policy=asdict(resolved_policy),
            inspected_count=len(opportunities),
            items=selected,
            count=len(selected),
            reason_counts=reason_counts,
        )


def _queue_item(
    *,
    opportunity: Opportunity,
    enrichment: OpportunityEnrichment,
    availability: OpportunityAvailability | None,
    source_entry: SourceCatalogEntry | None,
    now: datetime,
    policy: VerificationQueuePolicy,
) -> VerificationQueueItem | None:
    if opportunity.status.casefold() in _CLOSED_STATUSES:
        return None

    state: AvailabilityState = (
        availability.availability_state
        if availability is not None
        else "UNVERIFIED"
    )
    if state == "VERIFIED_CLOSED":
        return None

    deadline = (
        enrichment.application_deadline.value
        if enrichment.application_deadline is not None
        else None
    )
    is_fast_market = (
        source_entry is not None
        and source_entry.freshness_policy == "fast_market_project"
    )
    if deadline is not None and now.date() > deadline.date():
        return None

    if _fast_market_too_old(
        opportunity=opportunity,
        is_fast_market=is_fast_market,
        now=now,
        max_age_days=policy.fast_market_max_age_days,
    ):
        return None

    reasons: list[VerificationReason] = []
    needs_verification = (
        source_entry is None or source_entry.verification_required
    )

    if source_entry is not None and source_entry.authority == "DISCOVERY_ONLY":
        reasons.append("DISCOVERY_ONLY_NEEDS_OFFICIAL_SOURCE")

    if (
        state == "UNVERIFIED"
        and needs_verification
        and deadline is not None
        and deadline.date() <= (
            now + timedelta(days=policy.deadline_soon_days)
        ).date()
    ):
        reasons.append("DEADLINE_SOON_UNVERIFIED")

    if (
        state == "UNVERIFIED"
        and needs_verification
        and is_fast_market
    ):
        reasons.append("FAST_MARKET_UNVERIFIED")

    if (
        state == "UNVERIFIED"
        and needs_verification
        and "DISCOVERY_ONLY_NEEDS_OFFICIAL_SOURCE" not in reasons
    ):
        reasons.append("SOURCE_REQUIRES_VERIFICATION")

    if (
        state == "VERIFIED_OPEN"
        and needs_verification
        and availability is not None
        and availability.last_verified_at is not None
        and _verification_is_stale(
            availability.last_verified_at,
            now=now,
            is_fast_market=is_fast_market,
            policy=policy,
        )
    ):
        reasons.append("VERIFICATION_STALE")

    if not reasons:
        return None

    score = max(_REASON_SCORES[reason] for reason in reasons)
    action: VerificationAction
    if "DISCOVERY_ONLY_NEEDS_OFFICIAL_SOURCE" in reasons:
        action = "FIND_OFFICIAL_SOURCE"
    elif "VERIFICATION_STALE" in reasons:
        action = "REVERIFY_CURRENT_SOURCE"
    else:
        action = "VERIFY_CURRENT_SOURCE"

    source_url = (
        str(enrichment.canonical_url.value)
        if enrichment.canonical_url is not None
        else opportunity.source_url
    )
    source_category = (
        str(enrichment.source_category.value)
        if enrichment.source_category is not None
        else None
    )

    return VerificationQueueItem(
        opportunity_id=opportunity.id,
        title=opportunity.title,
        company=opportunity.company,
        source_url=source_url,
        source_key=source_entry.key if source_entry is not None else None,
        source_category=source_category,
        availability_state=state,
        last_seen_at=(
            availability.last_seen_at if availability is not None else None
        ),
        last_verified_at=(
            availability.last_verified_at if availability is not None else None
        ),
        application_deadline=deadline,
        freshness_policy=enrichment.freshness_policy,
        priority_score=score,
        reason_codes=reasons,
        suggested_action=action,
    )


_REASON_SCORES: dict[VerificationReason, int] = {
    "DISCOVERY_ONLY_NEEDS_OFFICIAL_SOURCE": 100,
    "DEADLINE_SOON_UNVERIFIED": 95,
    "FAST_MARKET_UNVERIFIED": 90,
    "SOURCE_REQUIRES_VERIFICATION": 80,
    "VERIFICATION_STALE": 70,
}


def _verification_is_stale(
    last_verified_at: datetime,
    *,
    now: datetime,
    is_fast_market: bool,
    policy: VerificationQueuePolicy,
) -> bool:
    max_age_days = (
        policy.fast_market_reverify_after_days
        if is_fast_market
        else policy.standard_reverify_after_days
    )
    return now - last_verified_at > timedelta(days=max_age_days)


def _fast_market_too_old(
    *,
    opportunity: Opportunity,
    is_fast_market: bool,
    now: datetime,
    max_age_days: int,
) -> bool:
    if not is_fast_market:
        return False
    if opportunity.published_at is None:
        return False
    return (
        now - opportunity.published_at.astimezone(timezone.utc)
        > timedelta(days=max_age_days)
    )


def _queue_sort_key(item: VerificationQueueItem) -> tuple[object, ...]:
    deadline_unknown = 1 if item.application_deadline is None else 0
    deadline_sort = (
        item.application_deadline.timestamp()
        if item.application_deadline is not None
        else 0.0
    )
    last_seen_unknown = 1 if item.last_seen_at is None else 0
    last_seen_sort = (
        -item.last_seen_at.timestamp()
        if item.last_seen_at is not None
        else 0.0
    )
    return (
        -item.priority_score,
        deadline_unknown,
        deadline_sort,
        last_seen_unknown,
        last_seen_sort,
        item.opportunity_id,
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)
