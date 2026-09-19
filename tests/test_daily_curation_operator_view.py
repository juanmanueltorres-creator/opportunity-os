from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.availability.daily_curation import DailyCurationService
from app.availability.daily_curation_operator_view import (
    DailyCurationOperatorViewOptions,
    DailyCurationOperatorViewService,
)
from app.availability.repository import SQLiteAvailabilityRepository
from app.availability.verification_queue import VerificationQueueService
from app.availability.verification_review_session import (
    VerificationReviewSessionService,
)
from app.models.domain import Opportunity
from app.radar.community_digest_preview import CommunityDigestPreviewService
from app.radar.community_digest_renderer import CommunityDigestRenderOptions
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.source_catalog import load_source_catalog
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime(2026, 9, 18, 23, 0, tzinfo=timezone.utc)


def _service(tmp_path):
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()
    catalog = load_source_catalog(Path("config/source_catalog.yaml"))
    extractor = RuleBasedRequirementExtractor(source_catalog=catalog)
    queue = VerificationQueueService(
        opportunity_repository=opportunities,
        availability_repository=availability,
        extractor=extractor,
        source_catalog=catalog,
    )
    review = VerificationReviewSessionService(queue_service=queue)
    digest = CommunityDigestPreviewService(
        opportunity_repository=opportunities,
        extractor=extractor,
        availability_repository=availability,
    )
    daily = DailyCurationService(
        queue_service=queue,
        review_session_service=review,
        digest_preview_service=digest,
    )
    return (
        DailyCurationOperatorViewService(
            daily_curation_service=daily,
        ),
        opportunities,
        availability,
    )


def _opportunity(
    item_id: str,
    *,
    source: str,
    source_url: str,
    title: str | None = None,
) -> Opportunity:
    return Opportunity(
        id=item_id,
        source=source,
        source_id=item_id,
        source_url=source_url,
        company=f"Company {item_id}",
        title=title or f"GIS Analyst {item_id}",
        description="QGIS geospatial work",
        discovered_at=NOW - timedelta(hours=1),
        published_at=NOW - timedelta(hours=2),
        status="open",
        location="Remote",
        remote_policy="remote",
    )


def test_operator_view_summarizes_review_publishable_and_held(tmp_path) -> None:
    service, repository, availability = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "reddit",
            source="reddit",
            source_url="https://reddit.com/r/gis/comments/example",
        )
    )
    repository.upsert(
        _opportunity(
            "greenhouse",
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/1",
        )
    )
    verified, _ = repository.upsert(
        _opportunity(
            "linkedin-verified",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/verified",
        )
    )
    availability.record_verification(
        verified.id,
        is_open=True,
        observed_at=NOW - timedelta(hours=2),
        evidence_source="official_company_page",
    )

    view = service.build(now=NOW)

    assert view.review_count == 1
    assert view.publishable_count == 2
    assert view.held_count == 1
    assert view.review_items[0].opportunity_id == "reddit"
    assert view.review_items[0].next_action == "Buscar fuente oficial"
    assert view.publishable.count == 2
    assert view.held.total_count == 1
    assert view.external_actions == []


def test_operator_view_preserves_exact_review_card_for_next_draft_step(
    tmp_path,
) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )

    view = service.build(now=NOW)
    item = view.review_items[0]

    assert item.card.opportunity_id == item.opportunity_id
    assert item.card.card_sha256 == item.card_sha256
    assert item.next_endpoint == "/api/v1/availability/verification/draft"
    assert item.card.external_actions == []


def test_markdown_operator_view_is_human_readable(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )

    view = service.build(
        now=NOW,
        view_options=DailyCurationOperatorViewOptions(
            title="Ronda diaria",
            format="markdown",
        ),
    )

    assert view.format == "markdown"
    assert view.rendered_view.startswith("# Ronda diaria")
    assert "## 🔎 Review ahora" in view.rendered_view
    assert "## ✅ Publishable" in view.rendered_view
    assert "## ⏸ Held" in view.rendered_view
    assert "- [ ] Confirmar" in view.rendered_view
    assert "Vista read-only" in view.rendered_view


def test_plain_operator_view_works_without_checklists(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )

    view = service.build(
        now=NOW,
        view_options=DailyCurationOperatorViewOptions(
            title="Ronda diaria",
            format="plain",
            include_checklists=False,
        ),
    )

    assert view.format == "plain"
    assert view.review_items[0].checklist == []
    assert "REVIEW AHORA" in view.rendered_view
    assert "[ ]" not in view.rendered_view


def test_operator_view_embeds_publishable_digest_text(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "greenhouse",
            source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/1",
            title="GIS Developer",
        )
    )

    view = service.build(
        now=NOW,
        digest_render_options=CommunityDigestRenderOptions(
            title="Digest listo",
            format="markdown",
            include_intro=False,
            include_footer=False,
        ),
    )

    assert view.publishable.count == 1
    assert "GIS Developer" in view.publishable.rendered_digest
    assert "GIS Developer" in view.rendered_view


def test_held_reason_labels_are_human_readable(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "reddit",
            source="reddit",
            source_url="https://reddit.com/r/gis/comments/example",
        )
    )

    view = service.build(now=NOW)

    assert view.held.reason_counts == {"buscar fuente oficial": 1}
    assert "buscar fuente oficial: 1" in view.rendered_view


def test_operator_view_is_read_only(tmp_path) -> None:
    service, repository, availability = _service(tmp_path)
    stored, _ = repository.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )
    before = availability.list_observations(stored.id)

    view = service.build(now=NOW)

    after = availability.list_observations(stored.id)
    assert view.review_count == 1
    assert before == after == []


def test_operator_view_is_deterministic_for_same_daily_snapshot(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    repository.upsert(
        _opportunity(
            "linkedin",
            source="linkedin",
            source_url="https://linkedin.com/jobs/view/1",
        )
    )

    left = service.build(now=NOW)
    right = service.build(now=NOW)

    assert left.model_dump() == right.model_dump()


def test_empty_operator_view_is_explicit(tmp_path) -> None:
    service, _, _ = _service(tmp_path)

    view = service.build(now=NOW)

    assert view.review_count == 0
    assert view.publishable_count == 0
    assert view.held_count == 0
    assert "No hay items pendientes de revisión inmediata." in view.rendered_view
    assert "Items listos para publicar: **0**" in view.rendered_view


def test_blank_operator_title_fails_closed() -> None:
    try:
        DailyCurationOperatorViewOptions(title="   ")
    except ValueError as exc:
        assert str(exc) == "title must not be blank"
    else:
        raise AssertionError("expected ValueError")
