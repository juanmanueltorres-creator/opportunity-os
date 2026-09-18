from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.availability.models import OpportunityAvailability
from app.models.domain import Opportunity
from app.radar.community_digest import (
    CommunityDigestCandidate,
    CommunityDigestPolicy,
    build_community_digest,
)
from app.radar.models import (
    ConfidenceAssessment,
    DerivedValue,
    EligibilityResult,
    OpportunityEnrichment,
    RadarAssessment,
)

NOW = datetime(2026, 9, 18, 15, 0, tzinfo=timezone.utc)


def _derived(value, *, field: str = "source") -> DerivedValue:
    return DerivedValue(
        value=value,
        source_field=field,
        extraction_method="source_structured",
        confidence=1.0,
    )


def _confidence() -> ConfidenceAssessment:
    return ConfidenceAssessment(
        score=80.0,
        requirement_extraction_quality=80.0,
        skill_normalization_coverage=80.0,
        evidence_traceability=80.0,
        seniority_location_legal_clarity=80.0,
        source_freshness_completeness=80.0,
    )


def _assessment(
    item_id: str,
    *,
    title: str = "GIS Analyst",
    description: str = "QGIS geospatial work",
    source_url: str | None = None,
    source_category: str | None = "NICHE_JOB_BOARD",
    channel_tags: list[str] | None = None,
    source_reliability: str = "AGGREGATOR",
    freshness_policy: str = "standard_job",
    published_at: datetime | None = NOW - timedelta(days=1),
    deadline: datetime | None = None,
    status: str = "open",
    tier: str = "HIGH",
    eligible: bool = True,
    career_match: float | None = 90.0,
    income_viability: float | None = 90.0,
) -> RadarAssessment:
    opportunity = Opportunity(
        id=item_id,
        source="manual",
        source_id=item_id,
        source_url=source_url or f"https://jobs.example/{item_id}",
        company=f"Company {item_id}",
        title=title,
        description=description,
        discovered_at=NOW - timedelta(hours=1),
        published_at=published_at,
        status=status,
    )
    enrichment = OpportunityEnrichment(
        opportunity_id=item_id,
        source_category=(
            _derived(source_category)
            if source_category is not None
            else None
        ),
        canonical_url=_derived(
            source_url or f"https://jobs.example/{item_id}",
            field="source_url",
        ),
        source_reliability=source_reliability,
        source_freshness_quality="DIRECT_TIMESTAMP",
        freshness_policy=freshness_policy,
        channel_tags=channel_tags or [],
        application_deadline=(
            _derived(deadline, field="description")
            if deadline is not None
            else None
        ),
        extractor_version="rules-v4+source-catalog-v2",
        created_at=NOW,
    )
    intent_tiers = {"CAREER": tier} if career_match is not None else {}
    if income_viability is not None:
        intent_tiers["INCOME_NOW"] = tier

    return RadarAssessment(
        opportunity=opportunity,
        enrichment=enrichment,
        eligibility=EligibilityResult(
            eligible=eligible,
            hard_fail_reasons=[] if eligible else ["profile_specific_fixture"],
        ),
        career_match=career_match,
        income_viability=income_viability,
        confidence_score=80.0,
        confidence_breakdown=_confidence(),
        tier=tier,
        intent_tiers=intent_tiers,
        priority_score=90.0,
        selected_intent="CAREER" if career_match is not None else "INCOME_NOW",
        scoring_version="test",
        extractor_version="rules-v4+source-catalog-v2",
        alias_registry_version="1",
    )


def test_digest_is_independent_from_personal_fit_and_eligibility() -> None:
    strong_personal = _assessment(
        "same-opportunity",
        tier="HIGH",
        eligible=True,
        career_match=95.0,
        income_viability=92.0,
    )
    weak_personal = _assessment(
        "same-opportunity",
        tier="DISCARD",
        eligible=False,
        career_match=10.0,
        income_viability=10.0,
    )

    strong = build_community_digest([strong_personal], now=NOW)
    weak = build_community_digest([weak_personal], now=NOW)

    assert strong.items[0].model_dump() == weak.items[0].model_dump()


def test_discovery_only_sources_are_not_publishable_digest_items() -> None:
    reddit = _assessment(
        "reddit",
        source_url="https://reddit.com/r/gis/comments/example",
        source_category="COMMUNITY_SIGNAL",
    )
    hiring_index = _assessment(
        "index",
        source_url="https://hiring.cafe/example",
        source_category="DISCOVERY_INDEX",
    )

    digest = build_community_digest([reddit, hiring_index], now=NOW)

    assert digest.count == 0


def test_closed_or_deadline_expired_items_are_excluded() -> None:
    closed = _assessment("closed", status="closed")
    expired = _assessment(
        "expired",
        deadline=NOW - timedelta(days=1),
        freshness_policy="deadline_sensitive",
    )

    digest = build_community_digest([closed, expired], now=NOW)

    assert digest.count == 0


def test_freelance_project_gets_freelance_primary_bucket() -> None:
    freelance = _assessment(
        "freelance",
        title="GIS forest mapping project",
        source_url="https://workana.com/job/forest-map",
        source_category="FREELANCE_MARKETPLACE",
        channel_tags=["freelance", "project"],
        freshness_policy="fast_market_project",
    )

    digest = build_community_digest([freelance], now=NOW)

    assert digest.items[0].bucket == "FREELANCE"
    assert "GEO_CORE" in digest.items[0].bucket_tags


def test_entry_level_geology_is_tagged_without_losing_primary_entry_bucket() -> None:
    item = _assessment(
        "entry-geology",
        title="Junior Geologist",
        description="Early career exploration geology role",
    )

    digest = build_community_digest([item], now=NOW)

    assert digest.items[0].bucket == "ENTRY_LEVEL"
    assert "GEOSCIENCE_MINING" in digest.items[0].bucket_tags


def test_fast_market_stale_project_is_not_published_but_not_mutated_closed() -> None:
    stale = _assessment(
        "stale-freelance",
        source_url="https://freelancer.com/projects/gis/stale",
        source_category="FREELANCE_MARKETPLACE",
        channel_tags=["freelance", "project"],
        freshness_policy="fast_market_project",
        published_at=NOW - timedelta(days=20),
        status="open",
    )

    digest = build_community_digest([stale], now=NOW)

    assert digest.count == 0
    assert stale.opportunity.status == "open"


def test_per_source_cap_preserves_cross_platform_diversity_without_quota() -> None:
    items = [
        _assessment(
            f"workana-{index}",
            source_url=f"https://workana.com/job/{index}",
            source_category="FREELANCE_MARKETPLACE",
            channel_tags=["freelance"],
            freshness_policy="fast_market_project",
        )
        for index in range(4)
    ]
    items.extend(
        [
            _assessment(
                "geo-careers",
                source_url="https://geo-careers.com/jobs/1",
                title="Remote Sensing Analyst",
            ),
            _assessment(
                "earthworks",
                source_url="https://earthworks-jobs.com/job/1",
                title="Hydrogeologist",
            ),
        ]
    )

    digest = build_community_digest(
        items,
        now=NOW,
        policy=CommunityDigestPolicy(max_items=10, max_per_source=2),
    )

    hosts = [item.source_url.split("/")[2] for item in digest.items]
    assert hosts.count("workana.com") == 2
    assert digest.count == 4


def test_bucket_cap_never_pulls_stale_items_to_fill_capacity() -> None:
    fresh_geo = _assessment("fresh-geo", title="GIS Analyst")
    stale_other = _assessment(
        "stale-other",
        title="General Operations",
        published_at=NOW - timedelta(days=120),
    )

    digest = build_community_digest(
        [fresh_geo, stale_other],
        now=NOW,
        policy=CommunityDigestPolicy(
            max_items=10,
            max_per_bucket=1,
            min_freshness_score=20.0,
        ),
    )

    assert [item.opportunity_id for item in digest.items] == ["fresh-geo"]


def test_canonical_url_is_used_for_public_digest() -> None:
    item = _assessment(
        "clean-url",
        source_url="https://workana.com/job/example",
        source_category="FREELANCE_MARKETPLACE",
        channel_tags=["freelance"],
    )

    digest = build_community_digest([item], now=NOW)

    assert digest.items[0].source_url == "https://workana.com/job/example"


def test_digest_order_and_id_are_deterministic() -> None:
    first = _assessment("a", title="GIS Analyst")
    second = _assessment("b", title="GIS Analyst")

    left = build_community_digest([second, first], now=NOW)
    right = build_community_digest([first, second], now=NOW)

    assert [item.opportunity_id for item in left.items] == ["a", "b"]
    assert left.digest_id == right.digest_id


def _availability(
    opportunity_id: str,
    *,
    state: str,
    verified_at: datetime | None = None,
    verification_source: str | None = None,
) -> OpportunityAvailability:
    return OpportunityAvailability(
        opportunity_id=opportunity_id,
        first_seen_at=NOW - timedelta(days=2),
        last_seen_at=NOW - timedelta(hours=1),
        last_verified_at=verified_at,
        verification_source=verification_source,
        availability_state=state,
        observation_count=2,
        latest_observation_at=NOW - timedelta(hours=1),
    )


def test_verified_closed_availability_excludes_open_opportunity() -> None:
    assessment = _assessment("verified-closed", status="open")
    candidate = CommunityDigestCandidate(
        opportunity=assessment.opportunity,
        enrichment=assessment.enrichment,
        availability=_availability(
            assessment.opportunity.id,
            state="VERIFIED_CLOSED",
            verified_at=NOW - timedelta(hours=2),
            verification_source="official_company_page",
        ),
    )

    digest = build_community_digest([candidate], now=NOW)

    assert digest.count == 0
    assert assessment.opportunity.status == "open"


def test_verified_open_availability_is_exposed_without_changing_selection_score() -> None:
    assessment = _assessment("verified-open")
    candidate = CommunityDigestCandidate(
        opportunity=assessment.opportunity,
        enrichment=assessment.enrichment,
        availability=_availability(
            assessment.opportunity.id,
            state="VERIFIED_OPEN",
            verified_at=NOW - timedelta(hours=2),
            verification_source="official_company_page",
        ),
    )

    unverified = build_community_digest([assessment], now=NOW)
    verified = build_community_digest([candidate], now=NOW)

    assert verified.count == 1
    assert verified.items[0].availability_state == "VERIFIED_OPEN"
    assert verified.items[0].verification_source == "official_company_page"
    assert verified.items[0].last_verified_at == NOW - timedelta(hours=2)
    assert verified.items[0].selection_score == unverified.items[0].selection_score


def test_availability_state_changes_digest_id_when_public_output_changes() -> None:
    assessment = _assessment("digest-id")
    verified_candidate = CommunityDigestCandidate(
        opportunity=assessment.opportunity,
        enrichment=assessment.enrichment,
        availability=_availability(
            assessment.opportunity.id,
            state="VERIFIED_OPEN",
            verified_at=NOW,
            verification_source="official_company_page",
        ),
    )

    unverified = build_community_digest([assessment], now=NOW)
    verified = build_community_digest([verified_candidate], now=NOW)

    assert unverified.digest_id != verified.digest_id
