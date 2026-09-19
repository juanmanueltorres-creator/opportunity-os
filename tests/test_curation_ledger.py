from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
import sqlite3

import pytest

from app.availability.daily_curation import DailyCurationService
from app.availability.daily_curation_operator_view import (
    DailyCurationOperatorViewService,
)
from app.availability.refresh_curation_operator import (
    RefreshCurationOperatorService,
)
from app.availability.repository import SQLiteAvailabilityRepository
from app.availability.verification_queue import VerificationQueueService
from app.availability.verification_review_session import (
    VerificationReviewSessionService,
)
from app.curation.models import (
    PublicationCheckpointConfirmRequest,
    PublicationCheckpointEvidence,
)
from app.curation.repository import SQLiteCurationLedgerRepository
from app.curation.service import CurationLedgerService
from app.models.domain import Opportunity
from app.radar.community_digest_preview import CommunityDigestPreviewService
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.source_catalog import load_source_catalog
from app.radar.source_refresh import SourceRefreshService
from app.radar.sources import ConfiguredConnector
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime(2026, 9, 19, 2, 0, tzinfo=timezone.utc)


class StaticConnector:
    def __init__(self, opportunities: list[Opportunity]) -> None:
        self.opportunities = opportunities

    async def fetch(self) -> list[Opportunity]:
        return list(self.opportunities)


def _opportunity(
    item_id: str,
    *,
    source_url: str,
) -> Opportunity:
    source_id = item_id.split(":", 1)[-1]
    return Opportunity(
        id=item_id,
        source="greenhouse",
        source_id=source_id,
        source_url=source_url,
        company=f"Company {source_id}",
        title=f"GIS Analyst {source_id}",
        description="QGIS geospatial work",
        discovered_at=NOW - timedelta(hours=1),
        published_at=NOW - timedelta(hours=2),
        status="open",
        location="Remote",
        remote_policy="remote",
    )


def _services(tmp_path, items: list[Opportunity]):
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    ledger_repository = SQLiteCurationLedgerRepository(path)
    opportunities.initialize()
    availability.initialize()
    ledger_repository.initialize()

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
        curation_ledger_repository=ledger_repository,
    )
    operator = DailyCurationOperatorViewService(
        daily_curation_service=daily,
    )
    refresh = SourceRefreshService(
        opportunity_repository=opportunities,
        availability_repository=availability,
        connectors=[
            ConfiguredConnector(
                name="greenhouse:acme",
                connector=StaticConnector(items),
            )
        ],
    )
    combined = RefreshCurationOperatorService(
        source_refresh_service=refresh,
        operator_view_service=operator,
    )
    ledger = CurationLedgerService(repository=ledger_repository)
    return combined, ledger, daily, ledger_repository


@pytest.mark.asyncio
async def test_record_run_is_idempotent_for_exact_snapshot(tmp_path) -> None:
    combined, ledger, _, _ = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ],
    )
    run = await combined.run(now=NOW)

    first = ledger.record_run(run, recorded_at=NOW + timedelta(minutes=1))
    second = ledger.record_run(run, recorded_at=NOW + timedelta(minutes=2))

    assert first.status == "NEW"
    assert second.status == "IDENTICAL"
    assert first.record is not None
    assert second.record is not None
    assert first.record.run_id == run.run_id
    assert first.record.publishable_opportunity_ids == ["greenhouse:1"]
    assert second.record.recorded_at == first.record.recorded_at


@pytest.mark.asyncio
async def test_derived_run_field_tampering_is_blocked(tmp_path) -> None:
    combined, ledger, _, _ = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ],
    )
    run = await combined.run(now=NOW)
    assert ledger.record_run(run, recorded_at=NOW).status == "NEW"

    mutated = run.model_copy(
        update={"partial_source_failure": True}
    )
    result = ledger.record_run(
        mutated,
        recorded_at=NOW + timedelta(minutes=1),
    )

    assert result.status == "BLOCKED"
    assert result.errors == ["run_partial_failure_snapshot_mismatch"]


@pytest.mark.asyncio
async def test_publication_preview_requires_recorded_run(tmp_path) -> None:
    _, ledger, _, _ = _services(tmp_path, [])

    preview = ledger.preview_publication(
        PublicationCheckpointEvidence(
            run_id="missing",
            digest_id="missing",
            opportunity_ids=["greenhouse:1"],
            channel="WHATSAPP",
        )
    )

    assert preview.status == "BLOCKED"
    assert preview.errors == ["curation_run_not_recorded"]


@pytest.mark.asyncio
async def test_publication_preview_only_accepts_publishable_ids(tmp_path) -> None:
    combined, ledger, _, _ = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ],
    )
    run = await combined.run(now=NOW)
    ledger.record_run(run, recorded_at=NOW)

    preview = ledger.preview_publication(
        PublicationCheckpointEvidence(
            run_id=run.run_id,
            digest_id=run.operator_view.publishable.digest_id,
            opportunity_ids=["not-in-digest"],
            channel="WHATSAPP",
        )
    )

    assert preview.status == "BLOCKED"
    assert preview.errors == [
        "opportunity_not_in_recorded_publishable_digest"
    ]


@pytest.mark.asyncio
async def test_confirm_publication_records_checkpoint_without_sending(tmp_path) -> None:
    combined, ledger, _, repository = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ],
    )
    run = await combined.run(now=NOW)
    ledger.record_run(run, recorded_at=NOW)
    evidence = PublicationCheckpointEvidence(
        run_id=run.run_id,
        digest_id=run.operator_view.publishable.digest_id,
        opportunity_ids=["greenhouse:1"],
        channel="WHATSAPP",
    )
    preview = ledger.preview_publication(evidence)

    result = ledger.confirm_publication(
        PublicationCheckpointConfirmRequest(
            preview=preview,
            confirmed_by="operator",
            confirmed_at=NOW + timedelta(minutes=5),
            note="Posted manually to Equipo Geoespacial",
        ),
        processed_at=NOW + timedelta(minutes=6),
    )

    assert preview.status == "READY"
    assert result.status == "RECORDED"
    assert result.checkpoint is not None
    assert result.checkpoint.opportunity_ids == ["greenhouse:1"]
    assert repository.publication_count() == 1
    assert repository.list_published_opportunity_ids(
        ["greenhouse:1"]
    ) == {"greenhouse:1"}


@pytest.mark.asyncio
async def test_repeated_publication_is_blocked(tmp_path) -> None:
    combined, ledger, _, _ = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ],
    )
    run = await combined.run(now=NOW)
    ledger.record_run(run, recorded_at=NOW)
    evidence = PublicationCheckpointEvidence(
        run_id=run.run_id,
        digest_id=run.operator_view.publishable.digest_id,
        opportunity_ids=["greenhouse:1"],
        channel="WHATSAPP",
    )
    first_preview = ledger.preview_publication(evidence)
    first = ledger.confirm_publication(
        PublicationCheckpointConfirmRequest(
            preview=first_preview,
            confirmed_by="operator",
            confirmed_at=NOW + timedelta(minutes=5),
        ),
        processed_at=NOW + timedelta(minutes=6),
    )
    second_preview = ledger.preview_publication(evidence)

    assert first.status == "RECORDED"
    assert second_preview.status == "BLOCKED"
    assert second_preview.already_published_opportunity_ids == [
        "greenhouse:1"
    ]
    assert second_preview.errors == ["opportunity_already_published"]


@pytest.mark.asyncio
async def test_stale_publication_preview_fails_closed(tmp_path) -> None:
    combined, ledger, _, _ = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            ),
            _opportunity(
                "greenhouse:2",
                source_url="https://boards.greenhouse.io/acme/jobs/2",
            ),
        ],
    )
    run = await combined.run(now=NOW)
    ledger.record_run(run, recorded_at=NOW)
    one = ledger.preview_publication(
        PublicationCheckpointEvidence(
            run_id=run.run_id,
            digest_id=run.operator_view.publishable.digest_id,
            opportunity_ids=["greenhouse:1"],
            channel="WHATSAPP",
        )
    )
    two = ledger.preview_publication(
        PublicationCheckpointEvidence(
            run_id=run.run_id,
            digest_id=run.operator_view.publishable.digest_id,
            opportunity_ids=["greenhouse:2"],
            channel="WHATSAPP",
        )
    )
    assert one.publication_count_before == two.publication_count_before == 0

    first = ledger.confirm_publication(
        PublicationCheckpointConfirmRequest(
            preview=one,
            confirmed_by="operator",
            confirmed_at=NOW + timedelta(minutes=5),
        ),
        processed_at=NOW + timedelta(minutes=6),
    )
    stale = ledger.confirm_publication(
        PublicationCheckpointConfirmRequest(
            preview=two,
            confirmed_by="operator",
            confirmed_at=NOW + timedelta(minutes=6),
        ),
        processed_at=NOW + timedelta(minutes=7),
    )

    assert first.status == "RECORDED"
    assert stale.status == "BLOCKED"
    assert stale.errors == ["publication_ledger_changed"]


@pytest.mark.asyncio
async def test_confirmation_before_run_is_blocked(tmp_path) -> None:
    combined, ledger, _, _ = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ],
    )
    run = await combined.run(now=NOW)
    ledger.record_run(run, recorded_at=NOW)
    preview = ledger.preview_publication(
        PublicationCheckpointEvidence(
            run_id=run.run_id,
            digest_id=run.operator_view.publishable.digest_id,
            opportunity_ids=["greenhouse:1"],
            channel="WHATSAPP",
        )
    )

    result = ledger.confirm_publication(
        PublicationCheckpointConfirmRequest(
            preview=preview,
            confirmed_by="operator",
            confirmed_at=NOW - timedelta(seconds=1),
        ),
        processed_at=NOW + timedelta(minutes=1),
    )

    assert result.status == "BLOCKED"
    assert result.errors == ["confirmation_before_curation_run"]


@pytest.mark.asyncio
async def test_recent_publication_is_excluded_from_next_daily_digest(tmp_path) -> None:
    combined, ledger, daily, _ = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ],
    )
    run = await combined.run(now=NOW)
    ledger.record_run(run, recorded_at=NOW)
    preview = ledger.preview_publication(
        PublicationCheckpointEvidence(
            run_id=run.run_id,
            digest_id=run.operator_view.publishable.digest_id,
            opportunity_ids=["greenhouse:1"],
            channel="WHATSAPP",
        )
    )
    ledger.confirm_publication(
        PublicationCheckpointConfirmRequest(
            preview=preview,
            confirmed_by="operator",
            confirmed_at=NOW + timedelta(minutes=5),
        ),
        processed_at=NOW + timedelta(minutes=6),
    )

    next_run = daily.run(now=NOW + timedelta(days=1))

    assert next_run.publishable.digest.count == 0
    assert next_run.publication_memory.exclusion_ids == ["greenhouse:1"]
    assert next_run.publication_memory.exclusion_count == 1
    assert next_run.counts["recently_published"] == 1


@pytest.mark.asyncio
async def test_publication_cooldown_expires_and_item_can_return(tmp_path) -> None:
    combined, ledger, daily, _ = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ],
    )
    run = await combined.run(now=NOW)
    ledger.record_run(run, recorded_at=NOW)
    preview = ledger.preview_publication(
        PublicationCheckpointEvidence(
            run_id=run.run_id,
            digest_id=run.operator_view.publishable.digest_id,
            opportunity_ids=["greenhouse:1"],
            channel="WHATSAPP",
        )
    )
    ledger.confirm_publication(
        PublicationCheckpointConfirmRequest(
            preview=preview,
            confirmed_by="operator",
            confirmed_at=NOW + timedelta(minutes=5),
        ),
        processed_at=NOW + timedelta(minutes=6),
    )

    later = daily.run(now=NOW + timedelta(days=31))

    assert later.publication_memory.exclusion_ids == []
    assert later.publishable.digest.count == 1
    assert later.publishable.digest.items[0].opportunity_id == "greenhouse:1"


@pytest.mark.asyncio
async def test_future_publication_confirmation_is_blocked(tmp_path) -> None:
    combined, ledger, _, _ = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ],
    )
    run = await combined.run(now=NOW)
    ledger.record_run(run, recorded_at=NOW)
    preview = ledger.preview_publication(
        PublicationCheckpointEvidence(
            run_id=run.run_id,
            digest_id=run.operator_view.publishable.digest_id,
            opportunity_ids=["greenhouse:1"],
            channel="WHATSAPP",
        )
    )

    result = ledger.confirm_publication(
        PublicationCheckpointConfirmRequest(
            preview=preview,
            confirmed_by="operator",
            confirmed_at=NOW + timedelta(minutes=10),
        ),
        processed_at=NOW + timedelta(minutes=5),
    )

    assert result.status == "BLOCKED"
    assert result.errors == ["confirmation_in_future"]


@pytest.mark.asyncio
async def test_exact_publication_confirm_retry_is_idempotent(tmp_path) -> None:
    combined, ledger, _, repository = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ],
    )
    run = await combined.run(now=NOW)
    ledger.record_run(run, recorded_at=NOW)
    preview = ledger.preview_publication(
        PublicationCheckpointEvidence(
            run_id=run.run_id,
            digest_id=run.operator_view.publishable.digest_id,
            opportunity_ids=["greenhouse:1"],
            channel="WHATSAPP",
        )
    )
    request = PublicationCheckpointConfirmRequest(
        preview=preview,
        confirmed_by="operator",
        confirmed_at=NOW + timedelta(minutes=5),
        note="Posted manually",
    )

    first = ledger.confirm_publication(
        request,
        processed_at=NOW + timedelta(minutes=6),
    )
    second = ledger.confirm_publication(
        request,
        processed_at=NOW + timedelta(minutes=7),
    )

    assert first.status == "RECORDED"
    assert second.status == "ALREADY_RECORDED"
    assert first.checkpoint is not None
    assert second.checkpoint is not None
    assert first.checkpoint.checkpoint_id == second.checkpoint.checkpoint_id
    assert repository.publication_count() == 1


@pytest.mark.asyncio
async def test_same_opportunity_can_be_published_again_in_new_run_after_cooldown(
    tmp_path,
) -> None:
    combined, ledger, _, repository = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ],
    )
    first_run = await combined.run(now=NOW)
    ledger.record_run(first_run, recorded_at=NOW)
    first_preview = ledger.preview_publication(
        PublicationCheckpointEvidence(
            run_id=first_run.run_id,
            digest_id=first_run.operator_view.publishable.digest_id,
            opportunity_ids=["greenhouse:1"],
            channel="WHATSAPP",
        )
    )
    first = ledger.confirm_publication(
        PublicationCheckpointConfirmRequest(
            preview=first_preview,
            confirmed_by="operator",
            confirmed_at=NOW + timedelta(minutes=5),
        ),
        processed_at=NOW + timedelta(minutes=6),
    )
    assert first.status == "RECORDED"

    later_at = NOW + timedelta(days=31)
    second_run = await combined.run(now=later_at)
    assert second_run.operator_view.publishable.opportunity_ids == [
        "greenhouse:1"
    ]
    ledger.record_run(
        second_run,
        recorded_at=later_at + timedelta(minutes=1),
    )
    second_preview = ledger.preview_publication(
        PublicationCheckpointEvidence(
            run_id=second_run.run_id,
            digest_id=second_run.operator_view.publishable.digest_id,
            opportunity_ids=["greenhouse:1"],
            channel="WHATSAPP",
        )
    )
    assert second_preview.status == "READY"

    second = ledger.confirm_publication(
        PublicationCheckpointConfirmRequest(
            preview=second_preview,
            confirmed_by="operator",
            confirmed_at=later_at + timedelta(minutes=5),
        ),
        processed_at=later_at + timedelta(minutes=6),
    )

    assert second.status == "RECORDED"
    assert repository.publication_count() == 2


@pytest.mark.asyncio
async def test_run_record_before_generation_is_blocked(tmp_path) -> None:
    combined, ledger, _, _ = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ],
    )
    run = await combined.run(now=NOW)

    result = ledger.record_run(
        run,
        recorded_at=NOW - timedelta(seconds=1),
    )

    assert result.status == "BLOCKED"
    assert result.errors == ["recorded_at_before_run"]


@pytest.mark.asyncio
async def test_concurrent_run_record_retries_are_idempotent(tmp_path) -> None:
    combined, ledger, _, repository = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ],
    )
    run = await combined.run(now=NOW)
    workers = 8
    barrier = Barrier(workers)

    def record_once(_: int) -> str:
        barrier.wait()
        result = ledger.record_run(
            run,
            recorded_at=NOW + timedelta(minutes=1),
        )
        return result.status

    with ThreadPoolExecutor(max_workers=workers) as executor:
        statuses = list(executor.map(record_once, range(workers)))

    assert statuses.count("NEW") == 1
    assert statuses.count("IDENTICAL") == workers - 1
    assert repository.get_run_record(run.run_id) is not None


@pytest.mark.asyncio
async def test_history_uses_recorded_snapshot_and_publication_checkpoints(
    tmp_path,
) -> None:
    combined, ledger, _, _ = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ],
    )
    run = await combined.run(now=NOW)
    recorded = ledger.record_run(
        run,
        recorded_at=NOW + timedelta(minutes=1),
    )
    assert recorded.status == "NEW"

    preview = ledger.preview_publication(
        PublicationCheckpointEvidence(
            run_id=run.run_id,
            digest_id=run.operator_view.publishable.digest_id,
            opportunity_ids=["greenhouse:1"],
            channel="WHATSAPP",
        )
    )
    confirmation = ledger.confirm_publication(
        PublicationCheckpointConfirmRequest(
            preview=preview,
            confirmed_by="operator",
            confirmed_at=NOW + timedelta(minutes=2),
        ),
        processed_at=NOW + timedelta(minutes=3),
    )
    assert confirmation.status == "RECORDED"

    history = ledger.history(limit=10)

    assert history.count == 1
    item = history.items[0]
    assert item.run_id == run.run_id
    assert item.recorded_at == NOW + timedelta(minutes=1)
    assert item.new_opportunity_count == run.source_refresh.created_count
    assert item.source_error_count == 0
    assert item.failed_sources == []
    assert item.review_count == run.operator_view.review_count
    assert item.publishable_count == run.operator_view.publishable_count
    assert item.held_count == run.operator_view.held_count
    assert item.publishable_opportunity_ids == ["greenhouse:1"]
    assert item.publication_checkpoint_count == 1
    assert item.published_opportunity_ids == ["greenhouse:1"]
    assert item.publication_channels == ["WHATSAPP"]
    assert item.latest_published_at == NOW + timedelta(minutes=2)
    assert history.external_actions == []


@pytest.mark.asyncio
async def test_history_is_newest_first_and_respects_limit(tmp_path) -> None:
    combined, ledger, _, _ = _services(
        tmp_path,
        [
            _opportunity(
                "greenhouse:1",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ],
    )
    first = await combined.run(now=NOW)
    ledger.record_run(first, recorded_at=NOW + timedelta(minutes=1))

    second_time = NOW + timedelta(days=1)
    second = await combined.run(now=second_time)
    ledger.record_run(
        second,
        recorded_at=second_time + timedelta(minutes=1),
    )

    history = ledger.history(limit=1)

    assert history.count == 1
    assert history.items[0].run_id == second.run_id
    assert history.items[0].generated_at == second_time


def test_history_checkpoint_lookup_index_is_initialized(tmp_path) -> None:
    path = tmp_path / "curation-index.db"
    repository = SQLiteCurationLedgerRepository(path)
    repository.initialize()

    with sqlite3.connect(path) as conn:
        indexes = {
            row[1]
            for row in conn.execute(
                "PRAGMA index_list(publication_checkpoints)"
            ).fetchall()
        }

    assert "idx_publication_checkpoints_run_time" in indexes
