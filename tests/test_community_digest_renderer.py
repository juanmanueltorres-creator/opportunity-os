from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.radar.community_digest import CommunityDigest, CommunityDigestItem
from app.radar.community_digest_renderer import (
    CommunityDigestRenderOptions,
    render_community_digest,
)


NOW = datetime(2026, 9, 18, 16, 0, tzinfo=timezone.utc)


def _item(
    item_id: str,
    *,
    bucket: str = "GEO_CORE",
    title: str = "GIS Analyst",
    company: str = "Example Co",
    source_url: str = "https://geo-careers.com/jobs/example",
    location: str | None = "Argentina",
    remote_policy: str | None = "Remote",
    deadline: datetime | None = None,
    availability_state: str = "UNVERIFIED",
    last_verified_at: datetime | None = None,
    verification_source: str | None = None,
) -> CommunityDigestItem:
    return CommunityDigestItem(
        opportunity_id=item_id,
        bucket=bucket,
        bucket_tags=[bucket],
        title=title,
        company=company,
        source_url=source_url,
        source_category="NICHE_JOB_BOARD",
        source_reliability="AGGREGATOR",
        source_freshness_quality="DIRECT_TIMESTAMP",
        channel_tags=["job"],
        location=location,
        remote_policy=remote_policy,
        published_at=NOW,
        application_deadline=deadline,
        availability_state=availability_state,
        last_verified_at=last_verified_at,
        verification_source=verification_source,
        freshness_score=100.0,
        selection_score=90.0,
    )


def _digest(items: list[CommunityDigestItem]) -> CommunityDigest:
    return CommunityDigest(
        digest_id="community-digest-test",
        generated_at=NOW,
        policy={"max_items": 10},
        items=items,
        count=len(items),
        bucket_counts={},
    )


def test_whatsapp_renderer_outputs_compact_publishable_text() -> None:
    digest = _digest(
        [
            _item(
                "freelance",
                bucket="FREELANCE",
                title="GIS Forest Mapping",
                company="Client project",
                source_url="https://workana.com/job/forest-map",
                deadline=datetime(2026, 9, 21, tzinfo=timezone.utc),
            )
        ]
    )

    text = render_community_digest(
        digest,
        options=CommunityDigestRenderOptions(
            timezone_name="America/Argentina/Cordoba",
        ),
    )

    assert "🚀 *Oportunidades y proyectos — Equipo Geoespacial | 18/09*" in text
    assert "*1️⃣ 📑 Freelance — GIS Forest Mapping*" in text
    assert "🏢 Client project" in text
    assert "🌎 Remote · Argentina" in text
    assert "📍 Workana" in text
    assert "📅 Cierre: 21/09/2026" in text
    assert "https://workana.com/job/forest-map" in text


def test_renderer_never_exposes_internal_scores_or_personal_fit_fields() -> None:
    item = _item("geo")
    text = render_community_digest(_digest([item]))

    assert "selection_score" not in text
    assert "freshness_score" not in text
    assert "career_match" not in text
    assert "income_viability" not in text
    assert "confidence" not in text


def test_renderer_uses_item_url_verbatim_without_adding_tracking() -> None:
    clean = "https://cadcrowd.com/job/example?project=42"
    text = render_community_digest(
        _digest([_item("cad", source_url=clean)])
    )

    assert clean in text
    assert "utm_" not in text
    assert "chatgpt" not in text.casefold()


def test_markdown_renderer_uses_markdown_headings_without_changing_content() -> None:
    text = render_community_digest(
        _digest([_item("geo")]),
        options=CommunityDigestRenderOptions(
            format="markdown",
            include_intro=False,
            include_footer=False,
        ),
    )

    assert text.startswith("# 🚀 Oportunidades y proyectos — Equipo Geoespacial | 18/09")
    assert "## 1️⃣ 🗺️ GIS / Geoespacial — GIS Analyst" in text
    assert "*1️⃣" not in text


def test_empty_digest_is_explicit_instead_of_fabricating_content() -> None:
    text = render_community_digest(
        _digest([]),
        options=CommunityDigestRenderOptions(
            include_intro=False,
            include_footer=False,
        ),
    )

    assert "No hay oportunidades suficientemente verificadas" in text


def test_renderer_supports_more_than_ten_items_without_invalid_number_emoji() -> None:
    items = [_item(f"item-{index}") for index in range(1, 12)]

    text = render_community_digest(_digest(items))

    assert "*🔟 🗺️ GIS / Geoespacial — GIS Analyst*" in text
    assert "*11. 🗺️ GIS / Geoespacial — GIS Analyst*" in text


def test_unknown_source_uses_clean_host_as_label() -> None:
    text = render_community_digest(
        _digest(
            [
                _item(
                    "unknown",
                    source_url="https://jobs.example.org/opening/1",
                )
            ]
        )
    )

    assert "📍 jobs.example.org" in text


def test_invalid_timezone_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown timezone_name"):
        CommunityDigestRenderOptions(timezone_name="Mars/Olympus_Mons")


def test_title_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="title must not be blank"):
        CommunityDigestRenderOptions(title="   ")


def test_renderer_is_deterministic_for_same_digest_and_options() -> None:
    digest = _digest([_item("a"), _item("b")])
    options = CommunityDigestRenderOptions(
        timezone_name="America/Argentina/Cordoba",
    )

    assert render_community_digest(digest, options=options) == render_community_digest(
        digest,
        options=options,
    )


def test_renderer_shows_explicit_verified_open_evidence() -> None:
    text = render_community_digest(
        _digest(
            [
                _item(
                    "verified",
                    availability_state="VERIFIED_OPEN",
                    last_verified_at=datetime(
                        2026,
                        9,
                        18,
                        15,
                        0,
                        tzinfo=timezone.utc,
                    ),
                    verification_source="official_company_page",
                )
            ]
        ),
        options=CommunityDigestRenderOptions(
            timezone_name="America/Argentina/Cordoba",
        ),
    )

    assert (
        "✅ Verificada abierta: official_company_page · 18/09/2026"
        in text
    )


def test_renderer_does_not_claim_verification_for_unverified_item() -> None:
    text = render_community_digest(_digest([_item("unverified")]))

    assert "Verificada abierta" not in text


def test_renderer_neutralizes_untrusted_inline_formatting_and_newlines() -> None:
    text = render_community_digest(
        _digest(
            [
                _item(
                    "unsafe",
                    title="GIS\n*Admin* [click](https://evil.example)",
                    company="Acme\n_Inc_",
                    location="Argentina\n~hidden~",
                )
            ]
        )
    )

    assert "GIS\n*Admin*" not in text
    assert "*Admin*" not in text
    assert "[click]" not in text
    assert "Acme\n_Inc_" not in text
    assert "GIS ∗Admin∗ ［click］(https://evil.example)" in text
    assert "🏢 Acme ＿Inc＿" in text
    assert "Argentina ∼hidden∼" in text
