from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import secrets
from typing import Literal

from pydantic import Field, field_validator

from app.availability.models import AvailabilityState
from app.availability.verification_models import VerificationEvidenceKind
from app.availability.verification_queue import (
    VerificationAction,
    VerificationQueue,
    VerificationQueueItem,
    VerificationQueuePolicy,
    VerificationQueueService,
)
from app.radar.models import StrictRadarModel


ReviewCheckCode = Literal[
    "LOCATE_OFFICIAL_SOURCE",
    "MATCH_ROLE_IDENTITY",
    "CONFIRM_LISTING_LOADS",
    "CONFIRM_APPLICATION_ACTIONABLE",
    "CONFIRM_DEADLINE",
    "CONFIRM_STILL_OPEN",
    "CAPTURE_EVIDENCE_URL",
]

REVIEW_SESSION_VERSION = "verification-review-session-v2"

_REVIEW_CARD_KEY_TEXT = os.getenv("OPPORTUNITY_REVIEW_CARD_SIGNING_KEY", "")
_REVIEW_CARD_SIGNING_KEY = (
    hashlib.sha256(_REVIEW_CARD_KEY_TEXT.encode("utf-8")).digest()
    if _REVIEW_CARD_KEY_TEXT
    else secrets.token_bytes(32)
)

@dataclass(frozen=True)
class VerificationReviewSessionPolicy:
    batch_size: int = 5
    queue_policy: VerificationQueuePolicy = field(
        default_factory=VerificationQueuePolicy
    )

    def __post_init__(self) -> None:
        if not 1 <= self.batch_size <= 20:
            raise ValueError("batch_size must be within 1..20")


class VerificationReviewCard(StrictRadarModel):
    rank: int = Field(ge=1)
    card_sha256: str = Field(min_length=64, max_length=64)
    opportunity_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    review_url: str = Field(min_length=1)
    source_key: str | None = None
    source_category: str | None = None
    availability_state: AvailabilityState
    last_seen_at: datetime | None = None
    priority_score: int = Field(ge=0, le=100)
    reason_codes: list[str] = Field(min_length=1)
    suggested_action: VerificationAction
    checklist: list[ReviewCheckCode] = Field(min_length=1)
    acceptable_evidence_kinds: list[VerificationEvidenceKind] = Field(min_length=1)
    application_deadline: datetime | None = None
    last_verified_at: datetime | None = None
    verification_preview_endpoint: str = (
        "/api/v1/availability/verification/preview"
    )
    external_actions: list[str] = Field(default_factory=list)

    @field_validator(
        "last_seen_at",
        "application_deadline",
        "last_verified_at",
    )
    @classmethod
    def dates_must_be_aware(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("external_actions")
    @classmethod
    def require_no_external_actions(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("external_actions must be empty")
        return value


class VerificationReviewSession(StrictRadarModel):
    session_version: str = REVIEW_SESSION_VERSION
    session_id: str = Field(min_length=1)
    generated_at: datetime
    queue_inspected_count: int = Field(ge=0)
    queue_count: int = Field(ge=0)
    batch_size: int = Field(ge=1, le=20)
    cards: list[VerificationReviewCard] = Field(default_factory=list)
    count: int = Field(ge=0)
    instructions: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone(timezone.utc)


class VerificationReviewSessionService:
    def __init__(
        self,
        *,
        queue_service: VerificationQueueService,
    ) -> None:
        self.queue_service = queue_service

    def build(
        self,
        *,
        now: datetime,
        policy: VerificationReviewSessionPolicy | None = None,
    ) -> VerificationReviewSession:
        generated_at = _aware_utc(now)
        resolved_policy = policy or VerificationReviewSessionPolicy()
        queue_policy = resolved_policy.queue_policy
        effective_queue_policy = VerificationQueuePolicy(
            max_items=max(
                resolved_policy.batch_size,
                queue_policy.max_items,
            ),
            candidate_lookback_days=queue_policy.candidate_lookback_days,
            deadline_soon_days=queue_policy.deadline_soon_days,
            standard_reverify_after_days=queue_policy.standard_reverify_after_days,
            fast_market_reverify_after_days=queue_policy.fast_market_reverify_after_days,
            fast_market_max_age_days=queue_policy.fast_market_max_age_days,
        )
        queue = self.queue_service.build(
            now=generated_at,
            policy=effective_queue_policy,
        )
        selected = queue.items[: resolved_policy.batch_size]
        cards = [
            build_review_card(rank=index, item=item)
            for index, item in enumerate(selected, start=1)
        ]
        return VerificationReviewSession(
            session_id=_session_id(
                generated_at=generated_at,
                policy=resolved_policy,
                queue=queue,
                cards=cards,
            ),
            generated_at=generated_at,
            queue_inspected_count=queue.inspected_count,
            queue_count=queue.count,
            batch_size=resolved_policy.batch_size,
            cards=cards,
            count=len(cards),
            instructions=[
                "Review each card manually; this session records no verification.",
                "Use the preview endpoint only after collecting supporting evidence.",
                "Rebuild the session if availability or source evidence changes.",
            ],
        )


def build_review_card(
    *,
    rank: int,
    item: VerificationQueueItem,
) -> VerificationReviewCard:
    checklist = _checklist(item)
    evidence_kinds = _acceptable_evidence_kinds(item)
    card_sha256 = _card_sha256(
        item=item,
        checklist=checklist,
        evidence_kinds=evidence_kinds,
    )
    return VerificationReviewCard(
        rank=rank,
        card_sha256=card_sha256,
        opportunity_id=item.opportunity_id,
        title=item.title,
        company=item.company,
        review_url=item.source_url,
        source_key=item.source_key,
        source_category=item.source_category,
        availability_state=item.availability_state,
        last_seen_at=item.last_seen_at,
        priority_score=item.priority_score,
        reason_codes=list(item.reason_codes),
        suggested_action=item.suggested_action,
        checklist=checklist,
        acceptable_evidence_kinds=evidence_kinds,
        application_deadline=item.application_deadline,
        last_verified_at=item.last_verified_at,
        external_actions=[],
    )


def _card_sha256(
    *,
    item: VerificationQueueItem,
    checklist: list[ReviewCheckCode],
    evidence_kinds: list[VerificationEvidenceKind],
) -> str:
    payload = {
        "opportunity_id": item.opportunity_id,
        "title": item.title,
        "company": item.company,
        "review_url": item.source_url,
        "source_key": item.source_key,
        "source_category": item.source_category,
        "availability_state": item.availability_state,
        "last_seen_at": (
            item.last_seen_at.isoformat()
            if item.last_seen_at is not None
            else None
        ),
        "last_verified_at": (
            item.last_verified_at.isoformat()
            if item.last_verified_at is not None
            else None
        ),
        "application_deadline": (
            item.application_deadline.isoformat()
            if item.application_deadline is not None
            else None
        ),
        "priority_score": item.priority_score,
        "reason_codes": list(item.reason_codes),
        "suggested_action": item.suggested_action,
        "checklist": checklist,
        "acceptable_evidence_kinds": evidence_kinds,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hmac.new(
        _REVIEW_CARD_SIGNING_KEY,
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def review_card_sha256(card: VerificationReviewCard) -> str:
    payload = {
        "opportunity_id": card.opportunity_id,
        "title": card.title,
        "company": card.company,
        "review_url": card.review_url,
        "source_key": card.source_key,
        "source_category": card.source_category,
        "availability_state": card.availability_state,
        "last_seen_at": (
            card.last_seen_at.isoformat()
            if card.last_seen_at is not None
            else None
        ),
        "last_verified_at": (
            card.last_verified_at.isoformat()
            if card.last_verified_at is not None
            else None
        ),
        "application_deadline": (
            card.application_deadline.isoformat()
            if card.application_deadline is not None
            else None
        ),
        "priority_score": card.priority_score,
        "reason_codes": list(card.reason_codes),
        "suggested_action": card.suggested_action,
        "checklist": list(card.checklist),
        "acceptable_evidence_kinds": list(card.acceptable_evidence_kinds),
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hmac.new(
        _REVIEW_CARD_SIGNING_KEY,
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _checklist(item: VerificationQueueItem) -> list[ReviewCheckCode]:
    if item.suggested_action == "FIND_OFFICIAL_SOURCE":
        checks: list[ReviewCheckCode] = [
            "LOCATE_OFFICIAL_SOURCE",
            "MATCH_ROLE_IDENTITY",
            "CONFIRM_APPLICATION_ACTIONABLE",
            "CAPTURE_EVIDENCE_URL",
        ]
    elif item.suggested_action == "REVERIFY_CURRENT_SOURCE":
        checks = [
            "CONFIRM_LISTING_LOADS",
            "MATCH_ROLE_IDENTITY",
            "CONFIRM_STILL_OPEN",
            "CONFIRM_APPLICATION_ACTIONABLE",
            "CAPTURE_EVIDENCE_URL",
        ]
    else:
        checks = [
            "CONFIRM_LISTING_LOADS",
            "MATCH_ROLE_IDENTITY",
            "CONFIRM_APPLICATION_ACTIONABLE",
            "CAPTURE_EVIDENCE_URL",
        ]

    if item.application_deadline is not None:
        insert_at = max(0, len(checks) - 1)
        checks.insert(insert_at, "CONFIRM_DEADLINE")

    return checks


def _acceptable_evidence_kinds(
    item: VerificationQueueItem,
) -> list[VerificationEvidenceKind]:
    if item.suggested_action == "FIND_OFFICIAL_SOURCE":
        return ["OFFICIAL_COMPANY_PAGE", "DIRECT_ATS"]
    if item.source_category == "FREELANCE_MARKETPLACE":
        return ["DIRECT_PLATFORM", "MANUAL_REVIEW"]
    if item.source_category in {"JOB_BOARD", "NICHE_JOB_BOARD"}:
        return [
            "OFFICIAL_COMPANY_PAGE",
            "DIRECT_ATS",
            "DIRECT_PLATFORM",
            "MANUAL_REVIEW",
        ]
    return ["OFFICIAL_COMPANY_PAGE", "DIRECT_ATS", "MANUAL_REVIEW"]


def _session_id(
    *,
    generated_at: datetime,
    policy: VerificationReviewSessionPolicy,
    queue: VerificationQueue,
    cards: list[VerificationReviewCard],
) -> str:
    payload = {
        "session_version": REVIEW_SESSION_VERSION,
        "generated_at": generated_at.isoformat(),
        "policy": {
            "batch_size": policy.batch_size,
            "queue_policy": asdict(policy.queue_policy),
        },
        "queue_generated_at": queue.generated_at.isoformat(),
        "cards": [
            {
                "opportunity_id": card.opportunity_id,
                "card_sha256": card.card_sha256,
                "priority_score": card.priority_score,
                "reason_codes": card.reason_codes,
                "suggested_action": card.suggested_action,
                "review_url": card.review_url,
                "source_key": card.source_key,
                "source_category": card.source_category,
                "availability_state": card.availability_state,
                "last_seen_at": (
                    card.last_seen_at.isoformat()
                    if card.last_seen_at is not None
                    else None
                ),
                "application_deadline": (
                    card.application_deadline.isoformat()
                    if card.application_deadline is not None
                    else None
                ),
                "last_verified_at": (
                    card.last_verified_at.isoformat()
                    if card.last_verified_at is not None
                    else None
                ),
            }
            for card in cards
        ],
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"verification-review-{digest[:20]}"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)
