from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Protocol

from app.models.domain import Opportunity, SearchIntent
from app.radar.models import DailyRadarBatch, RadarAssessment, SourceDiagnostic, Tier
from app.radar.ranking import RadarPolicy

QUALIFYING_TIERS: frozenset[Tier] = frozenset({"HIGH", "MEDIUM"})
_TIER_ORDER: dict[Tier, int] = {"HIGH": 0, "MEDIUM": 1, "STRETCH": 2, "DISCARD": 3}


@dataclass(frozen=True)
class RadarRunMetadata:
    profile_fingerprint: str
    scoring_version: str
    extractor_version: str
    alias_registry_version: str
    taxonomy_versions: dict[str, str] = field(default_factory=dict)
    source_diagnostics: tuple[SourceDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "profile_fingerprint",
            "scoring_version",
            "extractor_version",
            "alias_registry_version",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")


class ApplicationHistory(Protocol):
    def was_applied(self, opportunity: Opportunity) -> bool: ...

    def last_company_role_contact_at(
        self,
        company: str,
        title: str,
    ) -> datetime | None: ...


def select_daily_batch(
    ranked_items: list[RadarAssessment],
    policy: RadarPolicy,
    history: ApplicationHistory,
    *,
    now: datetime,
    metadata: RadarRunMetadata,
) -> DailyRadarBatch:
    generated_at = _require_aware(now)
    _validate_versions(ranked_items, metadata)

    eligible = [item for item in ranked_items if _is_selectable(item)]
    eligible.sort(key=lambda item: _selection_key(item, policy))

    selected: list[RadarAssessment] = []
    seen_ids: set[str] = set()
    seen_source_requisitions: set[tuple[str, str]] = set()
    company_counts: dict[str, int] = {}

    for item in eligible:
        opportunity = item.opportunity
        source_identity = (
            _normalize(opportunity.source),
            _normalize(opportunity.source_id),
        )
        company_key = _normalize(opportunity.company)

        if opportunity.id in seen_ids or source_identity in seen_source_requisitions:
            continue
        if history.was_applied(opportunity):
            continue
        if _is_inside_cooldown(opportunity, policy, history, generated_at):
            continue
        if company_counts.get(company_key, 0) >= policy.max_per_company:
            continue

        selected.append(item)
        seen_ids.add(opportunity.id)
        seen_source_requisitions.add(source_identity)
        company_counts[company_key] = company_counts.get(company_key, 0) + 1

        if len(selected) >= policy.max_items:
            break

    tier_counts = _count_tiers(selected)
    intent_counts = _count_intents(selected)
    policy_payload = asdict(policy)

    return DailyRadarBatch(
        batch_id=_batch_id(
            generated_at=generated_at,
            metadata=metadata,
            policy_payload=policy_payload,
            selected=selected,
        ),
        generated_at=generated_at,
        policy=policy_payload,
        profile_fingerprint=metadata.profile_fingerprint,
        scoring_version=metadata.scoring_version,
        extractor_version=metadata.extractor_version,
        alias_registry_version=metadata.alias_registry_version,
        taxonomy_versions=dict(metadata.taxonomy_versions),
        items=selected,
        count=len(selected),
        high_count=tier_counts.get("HIGH", 0),
        medium_count=tier_counts.get("MEDIUM", 0),
        intent_counts=intent_counts,
        tier_counts=tier_counts,
        source_diagnostics=list(metadata.source_diagnostics),
    )


def _is_selectable(item: RadarAssessment) -> bool:
    if not item.eligibility.eligible:
        return False
    return _best_qualifying_tier(item) in QUALIFYING_TIERS


def _best_qualifying_tier(item: RadarAssessment) -> Tier | None:
    tiers = [tier for tier in item.intent_tiers.values() if tier in QUALIFYING_TIERS]
    if not tiers:
        return None
    return min(tiers, key=lambda tier: _TIER_ORDER[tier])


def _selection_key(item: RadarAssessment, policy: RadarPolicy) -> tuple[object, ...]:
    best_tier = _best_qualifying_tier(item)
    if best_tier is None:
        return (99, 99, 0.0, 0.0, 0.0, 1, 0.0, item.opportunity.id)

    preferred_intent = _preferred_intent_for_tier(item, policy, best_tier)
    mode_rank = _mode_rank(preferred_intent, policy)
    fit = _fit_for_intent(item, preferred_intent)
    published = item.opportunity.published_at
    published_unknown = 1 if published is None else 0
    published_sort = -published.timestamp() if published is not None else 0.0

    return (
        _TIER_ORDER[best_tier],
        mode_rank,
        -item.priority_score,
        -fit,
        -item.confidence_score,
        published_unknown,
        published_sort,
        item.opportunity.id,
    )


def _preferred_intent_for_tier(
    item: RadarAssessment,
    policy: RadarPolicy,
    tier: Tier,
) -> SearchIntent | None:
    career_at_tier = item.intent_tiers.get("CAREER") == tier
    income_at_tier = item.intent_tiers.get("INCOME_NOW") == tier

    if policy.selection_mode == "income_first":
        if income_at_tier:
            return "INCOME_NOW"
        if career_at_tier:
            return "CAREER"
    elif policy.selection_mode == "career_first":
        if career_at_tier:
            return "CAREER"
        if income_at_tier:
            return "INCOME_NOW"
    else:
        if item.selected_intent is not None and item.intent_tiers.get(item.selected_intent) == tier:
            return item.selected_intent
        if career_at_tier:
            return "CAREER"
        if income_at_tier:
            return "INCOME_NOW"
    return None


def _mode_rank(intent: SearchIntent | None, policy: RadarPolicy) -> int:
    if policy.selection_mode == "balanced" or intent is None:
        return 0
    if policy.selection_mode == "income_first":
        return 0 if intent == "INCOME_NOW" else 1
    return 0 if intent == "CAREER" else 1


def _fit_for_intent(item: RadarAssessment, intent: SearchIntent | None) -> float:
    if intent == "INCOME_NOW":
        return item.income_viability or 0.0
    if intent == "CAREER":
        return item.career_match or 0.0
    available = [value for value in (item.career_match, item.income_viability) if value is not None]
    return max(available, default=0.0)


def _is_inside_cooldown(
    opportunity: Opportunity,
    policy: RadarPolicy,
    history: ApplicationHistory,
    now: datetime,
) -> bool:
    if policy.company_role_cooldown_days <= 0:
        return False

    last_contact = history.last_company_role_contact_at(
        opportunity.company,
        opportunity.title,
    )
    if last_contact is None or last_contact.tzinfo is None or last_contact.utcoffset() is None:
        return False

    normalized_contact = last_contact.astimezone(timezone.utc)
    return now - normalized_contact < timedelta(days=policy.company_role_cooldown_days)


def _count_tiers(items: list[RadarAssessment]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        tier = _best_qualifying_tier(item)
        if tier is not None:
            counts[tier] = counts.get(tier, 0) + 1
    return counts


def _count_intents(items: list[RadarAssessment]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if item.selected_intent is not None:
            counts[item.selected_intent] = counts.get(item.selected_intent, 0) + 1
    return counts


def _batch_id(
    *,
    generated_at: datetime,
    metadata: RadarRunMetadata,
    policy_payload: dict[str, object],
    selected: list[RadarAssessment],
) -> str:
    payload = {
        "generated_at": generated_at.isoformat(),
        "profile_fingerprint": metadata.profile_fingerprint,
        "scoring_version": metadata.scoring_version,
        "extractor_version": metadata.extractor_version,
        "alias_registry_version": metadata.alias_registry_version,
        "taxonomy_versions": metadata.taxonomy_versions,
        "policy": policy_payload,
        "opportunity_ids": [item.opportunity.id for item in selected],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"radar-{digest[:16]}"


def _validate_versions(
    items: list[RadarAssessment],
    metadata: RadarRunMetadata,
) -> None:
    for item in items:
        if item.scoring_version != metadata.scoring_version:
            raise ValueError("mixed scoring versions are not allowed in one radar batch")
        if item.extractor_version != metadata.extractor_version:
            raise ValueError("mixed extractor versions are not allowed in one radar batch")
        if item.alias_registry_version != metadata.alias_registry_version:
            raise ValueError("mixed alias registry versions are not allowed in one radar batch")
        if item.taxonomy_versions != metadata.taxonomy_versions:
            raise ValueError("mixed taxonomy versions are not allowed in one radar batch")


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())
