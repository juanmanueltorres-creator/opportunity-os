from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.availability.repository import SQLiteAvailabilityRepository
from app.models.domain import Opportunity
from app.radar.community_digest import CommunityDigestPolicy
from app.radar.community_digest_preview import CommunityDigestPreviewService
from app.radar.community_digest_renderer import CommunityDigestRenderOptions
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.source_catalog import load_source_catalog
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime(2026, 9, 18, 17, 0, tzinfo=timezone.utc)


def _repository(tmp_path) -> SQLiteOpportunityRepository:
    repository = SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()
    return repository


def _service(tmp_path) -> tuple[
    CommunityDigestPreviewService,
    SQLiteOpportunityRepository,
    SQLiteAvailabilityRepository,
]:
    repository = _repository(tmp_path)
    availability = SQLiteAvailabilityRepository(repository.path)
    availability.initialize()
    extractor = RuleBasedRequirementExtractor(
        source_catalog=load_source_catalog(Path("config/source_catalog.yaml")),
    )
    return (
        CommunityDigestPreviewService(
            opportunity_repository=repository,
            extractor=extractor,
            availability_repository=availability,
        ),
        repository,
        availability,
    )


def _opportunity(
    item_id: str,
    *,
    source: str = "workana",
    source_url: str | None = None,
    title: str = "GIS Forest Mapping",
    description: str = "QGIS remote sensing project",
    published_at: datetime | None = NOW - timedelta(hours=4),
    status: str = "open",
) -> Opportunity:
    return Opportunity(
        id=item_id,
        source=source,
        source_id=item_id,
        source_url=source_url or f"https://workana.com/job/{item_id}",
        company="Example Client",
        title=title,
        description=description,
        discovered_at=NOW - timedelta(hours=1),
        published_at=published_at,
        status=status,
        location="Remote",
        remote_policy="remote",
    )


def test_preview_reads_repository_and_returns_structured_digest_plus_text(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(_opportunity("forest-map"))

    preview = service.preview(
        now=NOW,
        policy=CommunityDigestPolicy(max_items=5),
        render_options=CommunityDigestRenderOptions(
            timezone_name="America/Argentina/Cordoba",
            format="whatsapp",
        ),
    )

    assert preview.candidate_count == 1
    assert preview.digest.count == 1
    assert preview.digest.items[0].bucket == "FREELANCE"
    assert preview.format == "whatsapp"
    assert "GIS Forest Mapping" in preview.rendered_text
    assert "https://workana.com/job/forest-map" in preview.rendered_text


def test_preview_does_not_require_or_construct_candidate_profile(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(_opportunity("profile-free"))

    preview = service.preview(now=NOW)

    assert preview.digest.count == 1
    assert not hasattr(preview.digest.items[0], "career_match")
    assert "career_match" not in preview.rendered_text
    assert "income_viability" not in preview.rendered_text


def test_preview_is_read_only_with_respect_to_opportunity_repository(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    stored, created = repository.upsert(_opportunity("read-only"))
    assert created is True

    before = repository.list(limit=100)
    preview = service.preview(now=NOW)
    after = repository.list(limit=100)

    assert preview.digest.count == 1
    assert before == after
    assert repository.get(stored.id) == stored


def test_preview_excludes_discovery_only_source_without_external_verification(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "reddit-signal",
            source="reddit",
            source_url="https://reddit.com/r/gis/comments/example",
        )
    )

    preview = service.preview(now=NOW)

    assert preview.candidate_count == 1
    assert preview.digest.count == 0


def test_preview_respects_public_policy_and_render_options(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    for index in range(3):
        repository.upsert(
            _opportunity(
                f"workana-{index}",
                source_url=f"https://workana.com/job/{index}",
            )
        )

    preview = service.preview(
        now=NOW,
        policy=CommunityDigestPolicy(
            max_items=10,
            max_per_source=1,
        ),
        render_options=CommunityDigestRenderOptions(
            title="Radar de prueba",
            format="markdown",
            include_intro=False,
            include_footer=False,
        ),
    )

    assert preview.digest.count == 1
    assert preview.format == "markdown"
    assert preview.rendered_text.startswith("# 🚀 Radar de prueba")


def test_preview_uses_ninety_day_read_window_but_digest_freshness_still_filters(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "old-standard",
            source="manual",
            source_url="https://example.org/job/old",
            published_at=NOW - timedelta(days=60),
            title="GIS Analyst",
        )
    )
    repository.upsert(
        _opportunity(
            "too-old",
            source="manual",
            source_url="https://example.org/job/too-old",
            published_at=NOW - timedelta(days=91),
            title="GIS Analyst",
        )
    )

    preview = service.preview(now=NOW)

    assert preview.candidate_count == 1
    assert preview.digest.count == 1
    assert preview.digest.items[0].opportunity_id == "old-standard"


def test_preview_rejects_naive_now(tmp_path) -> None:
    service, _, _ = _service(tmp_path)

    try:
        service.preview(now=datetime(2026, 9, 18, 17, 0))
    except ValueError as exc:
        assert str(exc) == "now must be timezone-aware"
    else:
        raise AssertionError("expected ValueError")


def test_preview_excludes_verified_closed_and_surfaces_verified_open(tmp_path) -> None:
    service, repository, availability = _service(tmp_path)
    closed, _ = repository.upsert(_opportunity("closed-by-verification"))
    opened, _ = repository.upsert(_opportunity("verified-open"))

    availability.record_verification(
        closed.id,
        is_open=False,
        observed_at=NOW - timedelta(hours=2),
        evidence_source="official_company_page",
    )
    availability.record_verification(
        opened.id,
        is_open=True,
        observed_at=NOW - timedelta(hours=1),
        evidence_source="official_company_page",
    )

    preview = service.preview(
        now=NOW,
        render_options=CommunityDigestRenderOptions(
            timezone_name="America/Argentina/Cordoba",
        ),
    )

    ids = [item.opportunity_id for item in preview.digest.items]
    assert closed.id not in ids
    assert opened.id in ids
    open_item = next(
        item
        for item in preview.digest.items
        if item.opportunity_id == opened.id
    )
    assert open_item.availability_state == "VERIFIED_OPEN"
    assert open_item.verification_source == "official_company_page"
    assert "✅ Verificada abierta" in preview.rendered_text


def test_preview_remains_backward_compatible_without_availability_repository(tmp_path) -> None:
    repository = _repository(tmp_path)
    repository.upsert(_opportunity("no-memory"))
    extractor = RuleBasedRequirementExtractor(
        source_catalog=load_source_catalog(Path("config/source_catalog.yaml")),
    )
    service = CommunityDigestPreviewService(
        opportunity_repository=repository,
        extractor=extractor,
        availability_repository=None,
    )

    preview = service.preview(now=NOW)

    assert preview.digest.count == 1
    assert preview.digest.items[0].availability_state == "UNVERIFIED"
