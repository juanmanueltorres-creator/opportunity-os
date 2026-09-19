from __future__ import annotations

from inspect import signature
from types import SimpleNamespace

from app.main import create_app
from app.radar.community_digest_renderer import _safe_inline, _safe_url
from app.radar.extractor import (
    RuleBasedRequirementExtractor,
    _source_category,
    _strip_tracking_query,
)
from app.radar.ranking import RadarPolicy
from app.radar.source_catalog import SourceCatalogEntry


def test_canonical_url_preserves_non_tracking_query_bytes() -> None:
    source = (
        "https://example.com/apply?"
        "sig=a%20b&flag&x=1+2&utm_source=linkedin&mc_cid=abc"
    )

    assert _strip_tracking_query(source) == (
        "https://example.com/apply?sig=a%20b&flag&x=1+2"
    )


def test_host_derived_source_category_points_to_source_url() -> None:
    entry = SourceCatalogEntry(
        key="workana",
        aliases=["workana.com"],
        category="FREELANCE_MARKETPLACE",
        authority="DIRECT_PLATFORM",
        freshness_mode="DIRECT_TIMESTAMP",
        freshness_policy="fast_market_project",
        default_channel_tags=["freelance"],
        publishable=True,
        verification_required=True,
    )
    opportunity = SimpleNamespace(
        source="manual",
        source_url="https://workana.com/job/123",
    )

    category = _source_category(opportunity, entry)

    assert category is not None
    assert category.source_field == "source_url"
    assert category.source_text == opportunity.source_url


def test_extractor_cache_version_changes_with_semantic_output() -> None:
    assert RuleBasedRequirementExtractor().extractor_version == "rules-v5"


def test_radar_policy_preserves_legacy_positional_tail() -> None:
    policy = RadarPolicy(
        78.0,
        75.0,
        65.0,
        65.0,
        55.0,
        75.0,
        75.0,
        62.0,
        65.0,
        0.80,
        0.20,
        "income_first",
        20,
        2,
        31,
        9,
    )

    assert policy.candidate_lookback_days == 31
    assert policy.company_role_cooldown_days == 9
    assert policy.max_per_source is None
    assert policy.max_per_source_category is None


def test_create_app_preserves_legacy_positional_parameters() -> None:
    expected = [
        "repository",
        "profile",
        "remotive_connector",
        "radar_service",
        "enable_default_radar",
        "target_service",
        "enable_default_targets",
        "relationship_memory",
        "enable_default_relationships",
        "operator_bridge_service",
        "enable_operator_import",
        "gmail_read_service",
        "enable_gmail_read",
        "process_email_service",
        "enable_process_email",
    ]

    params = list(signature(create_app).parameters.values())

    assert [item.name for item in params[: len(expected)]] == expected
    assert all(
        item.kind.name == "KEYWORD_ONLY"
        for item in params[len(expected) :]
    )


def test_digest_inline_rendering_flattens_and_escapes_external_text() -> None:
    value = "GIS Analyst\n\n2️⃣ *Fake* [link](x)"

    rendered = _safe_inline(value, "markdown")

    assert "\n" not in rendered
    assert "\\*Fake\\*" in rendered
    assert "\\[link\\]\\(x\\)" in rendered
    assert _safe_url("https://example.com/a\n?x=1") == (
        "https://example.com/a?x=1"
    )
