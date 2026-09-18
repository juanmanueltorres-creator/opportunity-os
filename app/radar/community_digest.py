from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from app.availability.models import AvailabilityState, OpportunityAvailability
from app.models.domain import Opportunity
from app.radar.models import OpportunityEnrichment, RadarAssessment, StrictRadarModel


DigestBucket = Literal[
    "FREELANCE",
    "ENTRY_LEVEL",
    "GEOSCIENCE_MINING",
    "GEOAI_DATA",
    "GEO_CORE",
    "SENIOR",
    "GENERAL",
]

_CLOSED_STATUSES = {"closed", "expired", "filled", "inactive"}
_DISCOVERY_ONLY_CATEGORIES = {"COMMUNITY_SIGNAL", "DISCOVERY_INDEX"}

_ENTRY_TERMS = (
    "apprentice",
    "early career",
    "graduate",
    "intern",
    "internship",
    "jovem aprendiz",
    "junior",
    "pasantia",
    "pasantía",
    "practica profesional",
    "práctica profesional",
    "trainee",
)
_GEONSCIENCE_MINING_TERMS = (
    "exploration",
    "exploracion",
    "exploración",
    "geologia",
    "geología",
    "geologist",
    "geologo",
    "geólogo",
    "geoscience",
    "hidrogeologia",
    "hidrogeología",
    "hydrogeology",
    "mine",
    "mining",
    "mineria",
    "minería",
)
_GEOAI_DATA_TERMS = (
    "artificial intelligence",
    "data engineer",
    "data engineering",
    "deep learning",
    "geoai",
    "geospatial developer",
    "machine learning",
    "postgis",
    "python",
    "spatial data",
)
_GEO_CORE_TERMS = (
    "arcgis",
    "cartografia",
    "cartografía",
    "earth observation",
    "geospatial",
    "gis",
    "geomatics",
    "geomatica",
    "geomática",
    "photogrammetry",
    "qgis",
    "remote sensing",
    "teledeteccion",
    "teledetección",
)
_SENIOR_TERMS = (
    " lead ",
    " principal ",
    " senior ",
    " sr ",
)


@dataclass(frozen=True)
class CommunityDigestPolicy:
    max_items: int = 10
    max_per_source: int | None = 2
    max_per_bucket: int | None = None
    min_freshness_score: float = 20.0

    def __post_init__(self) -> None:
        if self.max_items < 1:
            raise ValueError("max_items must be positive")
        if self.max_per_source is not None and self.max_per_source < 1:
            raise ValueError("max_per_source must be positive when configured")
        if self.max_per_bucket is not None and self.max_per_bucket < 1:
            raise ValueError("max_per_bucket must be positive when configured")
        if not 0.0 <= self.min_freshness_score <= 100.0:
            raise ValueError("min_freshness_score must be within 0..100")


class CommunityDigestCandidate(StrictRadarModel):
    opportunity: Opportunity
    enrichment: OpportunityEnrichment
    availability: OpportunityAvailability | None = None


class CommunityDigestItem(StrictRadarModel):
    opportunity_id: str = Field(min_length=1)
    bucket: DigestBucket
    bucket_tags: list[DigestBucket] = Field(default_factory=list)
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    source_category: str | None = None
    source_reliability: str = Field(min_length=1)
    source_freshness_quality: str = Field(min_length=1)
    channel_tags: list[str] = Field(default_factory=list)
    location: str | None = None
    remote_policy: str | None = None
    published_at: datetime | None = None
    application_deadline: datetime | None = None
    availability_state: AvailabilityState = "UNVERIFIED"
    last_verified_at: datetime | None = None
    verification_source: str | None = None
    freshness_score: float = Field(ge=0, le=100)
    selection_score: float = Field(ge=0, le=100)

    @field_validator("published_at", "application_deadline", "last_verified_at")
    @classmethod
    def dates_must_be_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)


class CommunityDigest(StrictRadarModel):
    digest_id: str = Field(min_length=1)
    generated_at: datetime
    policy: dict[str, object] = Field(default_factory=dict)
    items: list[CommunityDigestItem] = Field(default_factory=list)
    count: int = Field(ge=0)
    bucket_counts: dict[str, int] = Field(default_factory=dict)

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone(timezone.utc)


def build_community_digest(
    assessments: list[RadarAssessment | CommunityDigestCandidate],
    *,
    now: datetime,
    policy: CommunityDigestPolicy | None = None,
) -> CommunityDigest:
    resolved_policy = policy or CommunityDigestPolicy()
    generated_at = _aware_utc(now)

    candidates: list[CommunityDigestItem] = []
    for assessment in assessments:
        item = _project_item(assessment, generated_at)
        if item is None:
            continue
        if item.freshness_score < resolved_policy.min_freshness_score:
            continue
        candidates.append(item)

    candidates.sort(key=_selection_key)

    selected: list[CommunityDigestItem] = []
    seen_opportunities: set[str] = set()
    source_counts: dict[str, int] = {}
    bucket_counts: dict[str, int] = {}

    for item in candidates:
        if item.opportunity_id in seen_opportunities:
            continue

        source_key = _url_host(item.source_url)
        if (
            resolved_policy.max_per_source is not None
            and source_key is not None
            and source_counts.get(source_key, 0) >= resolved_policy.max_per_source
        ):
            continue
        if (
            resolved_policy.max_per_bucket is not None
            and bucket_counts.get(item.bucket, 0) >= resolved_policy.max_per_bucket
        ):
            continue

        selected.append(item)
        seen_opportunities.add(item.opportunity_id)
        if source_key is not None:
            source_counts[source_key] = source_counts.get(source_key, 0) + 1
        bucket_counts[item.bucket] = bucket_counts.get(item.bucket, 0) + 1

        if len(selected) >= resolved_policy.max_items:
            break

    policy_payload = asdict(resolved_policy)
    return CommunityDigest(
        digest_id=_digest_id(generated_at, policy_payload, selected),
        generated_at=generated_at,
        policy=policy_payload,
        items=selected,
        count=len(selected),
        bucket_counts=bucket_counts,
    )


def _project_item(
    assessment: RadarAssessment | CommunityDigestCandidate,
    now: datetime,
) -> CommunityDigestItem | None:
    opportunity = assessment.opportunity
    enrichment = assessment.enrichment
    availability = getattr(assessment, "availability", None)

    if _normalize(opportunity.status) in _CLOSED_STATUSES:
        return None
    if (
        availability is not None
        and availability.availability_state == "VERIFIED_CLOSED"
    ):
        return None

    deadline = (
        enrichment.application_deadline.value
        if enrichment.application_deadline is not None
        else None
    )
    if deadline is not None and now.date() > deadline.astimezone(timezone.utc).date():
        return None

    source_category = (
        str(enrichment.source_category.value)
        if enrichment.source_category is not None
        else None
    )
    if source_category in _DISCOVERY_ONLY_CATEGORIES:
        return None

    freshness_score = _freshness_score(assessment, now)
    bucket_tags = _bucket_tags(assessment)
    bucket = _primary_bucket(bucket_tags)
    source_url = (
        str(enrichment.canonical_url.value)
        if enrichment.canonical_url is not None
        else opportunity.source_url
    )
    selection_score = _selection_score(assessment, freshness_score)

    return CommunityDigestItem(
        opportunity_id=opportunity.id,
        bucket=bucket,
        bucket_tags=bucket_tags,
        title=opportunity.title,
        company=opportunity.company,
        source_url=source_url,
        source_category=source_category,
        source_reliability=enrichment.source_reliability,
        source_freshness_quality=enrichment.source_freshness_quality,
        channel_tags=list(enrichment.channel_tags),
        location=opportunity.location,
        remote_policy=opportunity.remote_policy,
        published_at=opportunity.published_at,
        application_deadline=deadline,
        availability_state=(
            availability.availability_state
            if availability is not None
            else "UNVERIFIED"
        ),
        last_verified_at=(
            availability.last_verified_at
            if availability is not None
            else None
        ),
        verification_source=(
            availability.verification_source
            if availability is not None
            else None
        ),
        freshness_score=freshness_score,
        selection_score=selection_score,
    )


def _bucket_tags(
    assessment: RadarAssessment | CommunityDigestCandidate,
) -> list[DigestBucket]:
    opportunity = assessment.opportunity
    enrichment = assessment.enrichment
    source_category = (
        str(enrichment.source_category.value)
        if enrichment.source_category is not None
        else ""
    )
    channel_tags = {_normalize(tag) for tag in enrichment.channel_tags}
    corpus = " ".join(
        [
            opportunity.title,
            opportunity.description,
            *opportunity.required_skills,
            *opportunity.preferred_skills,
            *(requirement.value for requirement in enrichment.requirements),
        ]
    )
    normalized = f" {_normalize(corpus)} "

    tags: list[DigestBucket] = []
    if (
        source_category == "FREELANCE_MARKETPLACE"
        or "freelance" in channel_tags
        or "project" in channel_tags
    ):
        tags.append("FREELANCE")
    if _contains_any(normalized, _ENTRY_TERMS):
        tags.append("ENTRY_LEVEL")
    if _contains_any(normalized, _GEONSCIENCE_MINING_TERMS):
        tags.append("GEOSCIENCE_MINING")
    if _contains_any(normalized, _GEOAI_DATA_TERMS):
        tags.append("GEOAI_DATA")
    if _contains_any(normalized, _GEO_CORE_TERMS):
        tags.append("GEO_CORE")
    if _contains_any(normalized, _SENIOR_TERMS):
        tags.append("SENIOR")
    if not tags:
        tags.append("GENERAL")
    return tags


def _primary_bucket(tags: list[DigestBucket]) -> DigestBucket:
    priority: tuple[DigestBucket, ...] = (
        "FREELANCE",
        "ENTRY_LEVEL",
        "GEOSCIENCE_MINING",
        "GEOAI_DATA",
        "GEO_CORE",
        "SENIOR",
        "GENERAL",
    )
    return next(bucket for bucket in priority if bucket in tags)


def _freshness_score(
    assessment: RadarAssessment | CommunityDigestCandidate,
    now: datetime,
) -> float:
    opportunity = assessment.opportunity
    enrichment = assessment.enrichment
    deadline = (
        enrichment.application_deadline.value
        if enrichment.application_deadline is not None
        else None
    )
    if enrichment.freshness_policy == "deadline_sensitive" and deadline is not None:
        return 100.0 if now.date() <= deadline.astimezone(timezone.utc).date() else 0.0
    if opportunity.published_at is None:
        return 50.0

    age_days = max(
        0.0,
        (now - opportunity.published_at.astimezone(timezone.utc)).total_seconds()
        / 86400.0,
    )
    if enrichment.freshness_policy == "fast_market_project":
        if age_days <= 1:
            return 100.0
        if age_days <= 3:
            return 85.0
        if age_days <= 7:
            return 50.0
        if age_days <= 14:
            return 20.0
        return 0.0

    if age_days <= 7:
        return 100.0
    if age_days <= 30:
        return 75.0
    if age_days <= 90:
        return 25.0
    return 0.0


def _selection_score(
    assessment: RadarAssessment | CommunityDigestCandidate,
    freshness_score: float,
) -> float:
    enrichment = assessment.enrichment
    source_quality = {
        "DIRECT_ATS": 100.0,
        "DIRECT_OFFICIAL": 100.0,
        "AGGREGATOR": 75.0,
        "MANUAL": 60.0,
        "UNKNOWN": 50.0,
    }[enrichment.source_reliability]
    completeness = _actionability_completeness(assessment)
    return round(
        0.55 * freshness_score
        + 0.30 * source_quality
        + 0.15 * completeness,
        1,
    )


def _actionability_completeness(
    assessment: RadarAssessment | CommunityDigestCandidate,
) -> float:
    opportunity = assessment.opportunity
    enrichment = assessment.enrichment
    signals = [
        bool(opportunity.location or opportunity.remote_policy),
        opportunity.published_at is not None,
        enrichment.canonical_url is not None or bool(opportunity.source_url),
        enrichment.source_category is not None,
    ]
    return round(sum(signals) / len(signals) * 100.0, 1)


def _selection_key(item: CommunityDigestItem) -> tuple[object, ...]:
    published = item.published_at
    published_unknown = 1 if published is None else 0
    published_sort = -published.timestamp() if published is not None else 0.0
    verified_rank = 0 if item.availability_state == "VERIFIED_OPEN" else 1
    return (
        -item.selection_score,
        -item.freshness_score,
        verified_rank,
        published_unknown,
        published_sort,
        item.opportunity_id,
    )


def _contains_any(corpus: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        normalized = _normalize(term)
        if not normalized:
            continue
        if re.search(rf"(?<!\w){re.escape(normalized)}(?!\w)", corpus):
            return True
    return False


def _digest_id(
    generated_at: datetime,
    policy: dict[str, object],
    items: list[CommunityDigestItem],
) -> str:
    payload = {
        "generated_at": generated_at.isoformat(),
        "policy": policy,
        "items": [
            {
                "opportunity_id": item.opportunity_id,
                "availability_state": item.availability_state,
                "last_verified_at": (
                    item.last_verified_at.isoformat()
                    if item.last_verified_at is not None
                    else None
                ),
                "verification_source": item.verification_source,
            }
            for item in items
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"community-digest-{digest[:16]}"


def _url_host(value: str) -> str | None:
    try:
        host = (urlsplit(value).hostname or "").casefold()
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())
