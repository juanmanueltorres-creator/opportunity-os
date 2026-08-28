from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib import import_module

from app.models.domain import Opportunity
from app.radar.models import (
    ConfidenceAssessment,
    EligibilityResult,
    OpportunityEnrichment,
    RadarAssessment,
)
from app.radar.ranking import RadarPolicy

NOW = datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc)


class FakeHistory:
    def __init__(
        self,
        *,
        applied_ids: set[str] | None = None,
        contacts: dict[tuple[str, str], datetime] | None = None,
    ) -> None:
        self.applied_ids = applied_ids or set()
        self.contacts = contacts or {}

    def was_applied(self, opportunity: Opportunity) -> bool:
        return opportunity.id in self.applied_ids

    def last_company_role_contact_at(
        self,
        company: str,
        title: str,
    ) -> datetime | None:
        key = (company.casefold().strip(), title.casefold().strip())
        return self.contacts.get(key)


def _selector_module():
    return import_module("app.radar.selector")


def _metadata():
    module = _selector_module()
    return module.RadarRunMetadata(
        profile_fingerprint="profile:test-v1",
        scoring_version="v0.2a1",
        extractor_version="rules-v1",
        alias_registry_version="1",
        taxonomy_versions={"esco": "1.2.1"},
    )


def _confidence(score: float) -> ConfidenceAssessment:
    return ConfidenceAssessment(
        score=score,
        requirement_extraction_quality=score,
        skill_normalization_coverage=score,
        evidence_traceability=score,
        seniority_location_legal_clarity=score,
        source_freshness_completeness=score,
    )


def _assessment(
    item_id: str,
    *,
    company: str | None = None,
    title: str | None = None,
    tier: str = "HIGH",
    selected_intent: str | None = "INCOME_NOW",
    career_match: float | None = None,
    income_viability: float | None = 85.0,
    confidence: float = 80.0,
    priority: float = 84.0,
    published_at: datetime | None = NOW - timedelta(days=1),
    discovery_origin: str = "targeted",
) -> RadarAssessment:
    opportunity = Opportunity(
        id=item_id,
        source="manual",
        source_id=item_id,
        source_url=f"https://example.com/jobs/{item_id}",
        company=company or f"Company {item_id}",
        title=title or f"Role {item_id}",
        description="Role description",
        discovered_at=NOW - timedelta(hours=1),
        published_at=published_at,
    )
    enrichment = OpportunityEnrichment(
        opportunity_id=item_id,
        extractor_version="rules-v1",
        taxonomy_versions={"esco": "1.2.1"},
        created_at=NOW,
    )
    intent_tiers: dict[str, str] = {}
    if career_match is not None:
        intent_tiers["CAREER"] = tier
    if income_viability is not None:
        intent_tiers["INCOME_NOW"] = tier

    return RadarAssessment(
        opportunity=opportunity,
        enrichment=enrichment,
        eligibility=EligibilityResult(eligible=tier not in {"DISCARD"}),
        career_match=career_match,
        income_viability=income_viability,
        confidence_score=confidence,
        confidence_breakdown=_confidence(confidence),
        tier=tier,
        intent_tiers=intent_tiers,
        discovery_origin=discovery_origin,
        priority_score=priority,
        selected_intent=selected_intent,
        scoring_version="v0.2a1",
        extractor_version="rules-v1",
        alias_registry_version="1",
        taxonomy_versions={"esco": "1.2.1"},
    )


def _select(items: list[RadarAssessment], *, policy: RadarPolicy | None = None, history: FakeHistory | None = None):
    module = _selector_module()
    return module.select_daily_batch(
        items,
        policy or RadarPolicy(),
        history or FakeHistory(),
        now=NOW,
        metadata=_metadata(),
    )


def test_twenty_one_qualified_items_are_capped_at_twenty() -> None:
    batch = _select([_assessment(f"job-{index:02d}") for index in range(21)])
    assert batch.count == 20
    assert len(batch.items) == 20


def test_seven_qualified_items_return_only_seven() -> None:
    batch = _select([_assessment(f"job-{index:02d}") for index in range(7)])
    assert batch.count == 7


def test_stretch_never_pads_daily_capacity() -> None:
    items = [_assessment(f"high-{index}") for index in range(3)]
    items.extend(
        _assessment(
            f"stretch-{index}",
            tier="STRETCH",
            selected_intent=None,
            income_viability=60.0,
        )
        for index in range(20)
    )
    batch = _select(items)
    assert [item.opportunity.id for item in batch.items] == [
        "high-0",
        "high-1",
        "high-2",
    ]


def test_known_applied_requisition_is_excluded() -> None:
    batch = _select(
        [_assessment("keep"), _assessment("already-applied")],
        history=FakeHistory(applied_ids={"already-applied"}),
    )
    assert [item.opportunity.id for item in batch.items] == ["keep"]


def test_same_requisition_appears_only_once() -> None:
    duplicate = _assessment("duplicate")
    batch = _select([duplicate, duplicate, _assessment("other")])
    assert [item.opportunity.id for item in batch.items].count("duplicate") == 1
    assert batch.count == 2


def test_default_company_cap_is_two() -> None:
    items = [
        _assessment("same-1", company="Same Co"),
        _assessment("same-2", company="Same Co"),
        _assessment("same-3", company="Same Co"),
        _assessment("other-1", company="Other Co"),
    ]
    batch = _select(items)
    assert sum(item.opportunity.company == "Same Co" for item in batch.items) == 2
    assert batch.count == 3


def test_high_precedes_medium_even_when_medium_priority_is_higher() -> None:
    high = _assessment("high", tier="HIGH", priority=75.0, income_viability=76.0)
    medium = _assessment("medium", tier="MEDIUM", priority=99.0, income_viability=70.0)
    batch = _select([medium, high])
    assert [item.opportunity.id for item in batch.items] == ["high", "medium"]


def test_ties_are_deterministic_by_opportunity_id() -> None:
    first = _assessment("a", priority=80.0, income_viability=80.0, confidence=80.0)
    second = _assessment("b", priority=80.0, income_viability=80.0, confidence=80.0)
    assert [item.opportunity.id for item in _select([second, first]).items] == ["a", "b"]
    assert [item.opportunity.id for item in _select([first, second]).items] == ["a", "b"]


def test_income_first_prefers_income_lane_within_same_tier_but_keeps_strong_career() -> None:
    income = _assessment(
        "income",
        tier="HIGH",
        selected_intent="INCOME_NOW",
        income_viability=80.0,
        priority=80.0,
    )
    career = _assessment(
        "career",
        tier="HIGH",
        selected_intent="CAREER",
        career_match=90.0,
        income_viability=None,
        priority=90.0,
    )
    medium_income = _assessment(
        "medium-income",
        tier="MEDIUM",
        selected_intent="INCOME_NOW",
        income_viability=70.0,
        priority=95.0,
    )

    batch = _select([medium_income, career, income])
    assert [item.opportunity.id for item in batch.items] == ["income", "career", "medium-income"]


def test_income_first_uses_income_lane_priority_not_max_cross_lane_priority() -> None:
    inflated_by_career = _assessment(
        "career-inflated",
        tier="HIGH",
        selected_intent="CAREER",
        career_match=99.0,
        income_viability=76.0,
        confidence=80.0,
        priority=95.2,
    )
    stronger_income = _assessment(
        "stronger-income",
        tier="HIGH",
        selected_intent="INCOME_NOW",
        career_match=80.0,
        income_viability=90.0,
        confidence=80.0,
        priority=88.0,
    )

    batch = _select([inflated_by_career, stronger_income])

    assert [item.opportunity.id for item in batch.items] == [
        "stronger-income",
        "career-inflated",
    ]


def test_configured_company_role_cooldown_excludes_recent_contact_only() -> None:
    policy = RadarPolicy(company_role_cooldown_days=14)
    recent = _assessment("recent", company="Example Co", title="Support Analyst")
    fresh = _assessment("fresh", company="Another Co", title="Support Analyst")
    history = FakeHistory(
        contacts={
            ("example co", "support analyst"): NOW - timedelta(days=3),
        }
    )

    batch = _select([recent, fresh], policy=policy, history=history)
    assert [item.opportunity.id for item in batch.items] == ["fresh"]


def test_batch_metadata_is_explicit_and_counts_selected_lanes() -> None:
    batch = _select(
        [
            _assessment("income", selected_intent="INCOME_NOW"),
            _assessment(
                "career",
                selected_intent="CAREER",
                career_match=88.0,
                income_viability=None,
            ),
        ]
    )

    assert batch.profile_fingerprint == "profile:test-v1"
    assert batch.scoring_version == "v0.2a1"
    assert batch.extractor_version == "rules-v1"
    assert batch.alias_registry_version == "1"
    assert batch.taxonomy_versions == {"esco": "1.2.1"}
    assert batch.count == 2
    assert batch.high_count == 2
    assert batch.medium_count == 0
    assert batch.intent_counts == {"INCOME_NOW": 1, "CAREER": 1}
    assert batch.tier_counts == {"HIGH": 2}