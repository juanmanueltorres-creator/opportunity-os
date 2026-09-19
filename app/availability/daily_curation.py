from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json

from pydantic import Field, field_validator

from app.availability.verification_queue import (
    VerificationQueueItem,
    VerificationQueuePolicy,
    VerificationQueueService,
)
from app.availability.verification_review_session import (
    VerificationReviewSession,
    VerificationReviewSessionPolicy,
    VerificationReviewSessionService,
)
from app.curation.repository import SQLiteCurationLedgerRepository
from app.radar.community_digest import CommunityDigestPolicy
from app.radar.community_digest_preview import (
    CommunityDigestPreview,
    CommunityDigestPreviewService,
)
from app.radar.community_digest_renderer import CommunityDigestRenderOptions
from app.radar.models import StrictRadarModel


DAILY_CURATION_VERSION = "daily-curation-run-v1"
_FULL_QUEUE_MAX = 2_147_483_647


@dataclass(frozen=True)
class DailyCurationPolicy:
    review_batch_size: int = 5
    held_items_limit: int = 20
    queue_policy: VerificationQueuePolicy = field(
        default_factory=VerificationQueuePolicy
    )
    digest_policy: CommunityDigestPolicy = field(
        default_factory=CommunityDigestPolicy
    )
    publication_cooldown_days: int = 30

    def __post_init__(self) -> None:
        if not 1 <= self.review_batch_size <= 20:
            raise ValueError("review_batch_size must be within 1..20")
        if not 1 <= self.held_items_limit <= 100:
            raise ValueError("held_items_limit must be within 1..100")
        if not 1 <= self.publication_cooldown_days <= 365:
            raise ValueError(
                "publication_cooldown_days must be within 1..365"
            )


class DailyCurationHeld(StrictRadarModel):
    total_count: int = Field(ge=0)
    shown_count: int = Field(ge=0)
    omitted_count: int = Field(ge=0)
    items: list[VerificationQueueItem] = Field(default_factory=list)
    reason_counts: dict[str, int] = Field(default_factory=dict)


class DailyCurationPublicationMemory(StrictRadarModel):
    cooldown_days: int = Field(ge=1, le=365)
    exclusion_ids: list[str] = Field(default_factory=list)
    exclusion_count: int = Field(ge=0)


class DailyCurationRun(StrictRadarModel):
    run_version: str = DAILY_CURATION_VERSION
    run_id: str = Field(min_length=1)
    generated_at: datetime
    review: VerificationReviewSession
    publishable: CommunityDigestPreview
    held: DailyCurationHeld
    publication_memory: DailyCurationPublicationMemory
    counts: dict[str, int] = Field(default_factory=dict)
    external_actions: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("external_actions")
    @classmethod
    def require_no_external_actions(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("external_actions must be empty")
        return value


class DailyCurationService:
    def __init__(
        self,
        *,
        queue_service: VerificationQueueService,
        review_session_service: VerificationReviewSessionService,
        digest_preview_service: CommunityDigestPreviewService,
        curation_ledger_repository: SQLiteCurationLedgerRepository | None = None,
    ) -> None:
        self.queue_service = queue_service
        self.review_session_service = review_session_service
        self.digest_preview_service = digest_preview_service
        self.curation_ledger_repository = curation_ledger_repository

    def run(
        self,
        *,
        now: datetime,
        policy: DailyCurationPolicy | None = None,
        render_options: CommunityDigestRenderOptions | None = None,
    ) -> DailyCurationRun:
        generated_at = _aware_utc(now)
        resolved = policy or DailyCurationPolicy()

        full_queue_policy = _queue_policy(
            resolved.queue_policy,
            max_items=_FULL_QUEUE_MAX,
        )
        full_queue = self.queue_service.build(
            now=generated_at,
            policy=full_queue_policy,
        )
        held_ids = {item.opportunity_id for item in full_queue.items}

        publication_exclusion_ids: set[str] = set()
        if self.curation_ledger_repository is not None:
            publication_exclusion_ids = (
                self.curation_ledger_repository
                .list_recently_published_opportunity_ids(
                    since=generated_at
                    - timedelta(days=resolved.publication_cooldown_days),
                    until=generated_at,
                )
            )

        editorial_exclusion_ids = held_ids | publication_exclusion_ids

        review = self.review_session_service.build(
            now=generated_at,
            policy=VerificationReviewSessionPolicy(
                batch_size=resolved.review_batch_size,
                queue_policy=_queue_policy(
                    resolved.queue_policy,
                    max_items=max(
                        resolved.review_batch_size,
                        resolved.queue_policy.max_items,
                    ),
                ),
            ),
        )
        expected_review_ids = [
            item.opportunity_id
            for item in full_queue.items[: resolved.review_batch_size]
        ]
        actual_review_ids = [card.opportunity_id for card in review.cards]
        if actual_review_ids != expected_review_ids:
            raise RuntimeError(
                "curation snapshot changed during review projection"
            )

        publishable = self.digest_preview_service.preview(
            now=generated_at,
            policy=resolved.digest_policy,
            render_options=render_options,
            excluded_opportunity_ids=editorial_exclusion_ids,
        )

        publishable_ids = {
            item.opportunity_id
            for item in publishable.digest.items
        }
        held_overlap = publishable_ids & held_ids
        if held_overlap:
            raise RuntimeError(
                "publishable digest overlaps verification-held opportunities"
            )
        publication_overlap = publishable_ids & publication_exclusion_ids
        if publication_overlap:
            raise RuntimeError(
                "publishable digest overlaps recently published opportunities"
            )

        held_items = full_queue.items[: resolved.held_items_limit]
        held = DailyCurationHeld(
            total_count=full_queue.count,
            shown_count=len(held_items),
            omitted_count=max(0, full_queue.count - len(held_items)),
            items=held_items,
            reason_counts=dict(full_queue.reason_counts),
        )
        publication_memory = DailyCurationPublicationMemory(
            cooldown_days=resolved.publication_cooldown_days,
            exclusion_ids=sorted(publication_exclusion_ids),
            exclusion_count=len(publication_exclusion_ids),
        )
        counts = {
            "review": review.count,
            "publishable": publishable.digest.count,
            "held": full_queue.count,
            "held_shown": len(held_items),
            "recently_published": len(publication_exclusion_ids),
        }
        return DailyCurationRun(
            run_id=_run_id(
                generated_at=generated_at,
                policy=resolved,
                review=review,
                publishable=publishable,
                held=held,
                publication_memory=publication_memory,
            ),
            generated_at=generated_at,
            review=review,
            publishable=publishable,
            held=held,
            publication_memory=publication_memory,
            counts=counts,
            external_actions=[],
        )


def _queue_policy(
    policy: VerificationQueuePolicy,
    *,
    max_items: int,
) -> VerificationQueuePolicy:
    return VerificationQueuePolicy(
        max_items=max_items,
        candidate_lookback_days=policy.candidate_lookback_days,
        deadline_soon_days=policy.deadline_soon_days,
        standard_reverify_after_days=policy.standard_reverify_after_days,
        fast_market_reverify_after_days=policy.fast_market_reverify_after_days,
        fast_market_max_age_days=policy.fast_market_max_age_days,
    )


def _run_id(
    *,
    generated_at: datetime,
    policy: DailyCurationPolicy,
    review: VerificationReviewSession,
    publishable: CommunityDigestPreview,
    held: DailyCurationHeld,
    publication_memory: DailyCurationPublicationMemory,
) -> str:
    payload = {
        "run_version": DAILY_CURATION_VERSION,
        "generated_at": generated_at.isoformat(),
        "policy": {
            "review_batch_size": policy.review_batch_size,
            "held_items_limit": policy.held_items_limit,
            "queue_policy": asdict(policy.queue_policy),
            "digest_policy": asdict(policy.digest_policy),
            "publication_cooldown_days": policy.publication_cooldown_days,
        },
        "review_session_id": review.session_id,
        "publishable_digest_id": publishable.digest.digest_id,
        "held_ids": [item.opportunity_id for item in held.items],
        "held_total_count": held.total_count,
        "held_reason_counts": held.reason_counts,
        "publication_memory": publication_memory.model_dump(
            mode="json",
            exclude_none=False,
        ),
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"daily-curation-{digest[:20]}"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)
