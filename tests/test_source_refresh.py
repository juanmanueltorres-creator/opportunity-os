from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.availability.repository import SQLiteAvailabilityRepository
from app.connectors.base import ConnectorError
from app.models.domain import Opportunity
from app.radar.source_refresh import SourceRefreshService
from app.radar.sources import ConfiguredConnector
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime(2026, 9, 19, 1, 0, tzinfo=timezone.utc)


def _opportunity(
    item_id: str,
    *,
    source: str,
    company: str | None = None,
    title: str = "GIS Analyst",
) -> Opportunity:
    source_id = item_id.split(":", 1)[-1]
    return Opportunity(
        id=item_id,
        source=source,
        source_id=source_id,
        source_url=f"https://example.com/{source}/{source_id}",
        company=company or f"Company {source_id}",
        title=title,
        description="QGIS geospatial work",
        discovered_at=NOW - timedelta(hours=1),
        published_at=NOW - timedelta(days=1),
        status="open",
        location="Remote",
        remote_policy="remote",
    )


class StaticConnector:
    def __init__(self, opportunities: list[Opportunity]) -> None:
        self.opportunities = opportunities
        self.calls = 0

    async def fetch(self) -> list[Opportunity]:
        self.calls += 1
        return list(self.opportunities)


class FailingConnector:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self) -> list[Opportunity]:
        self.calls += 1
        raise ConnectorError("DO_NOT_ECHO_UPSTREAM_SECRET")


def _service(tmp_path, connectors: list[ConfiguredConnector]):
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()
    return (
        SourceRefreshService(
            opportunity_repository=opportunities,
            availability_repository=availability,
            connectors=connectors,
        ),
        opportunities,
        availability,
    )


@pytest.mark.asyncio
async def test_refresh_ingests_sources_and_records_seen(tmp_path) -> None:
    greenhouse = StaticConnector(
        [_opportunity("greenhouse:1", source="greenhouse")]
    )
    service, opportunities, availability = _service(
        tmp_path,
        [
            ConfiguredConnector(
                name="greenhouse:example",
                connector=greenhouse,
            )
        ],
    )

    run = await service.run(now=NOW)

    assert run.source_count == 1
    assert run.ok_count == 1
    assert run.error_count == 0
    assert run.fetched_count == 1
    assert run.created_count == 1
    assert run.existing_count == 0
    assert run.seen_recorded_count == 1
    assert run.closure_inference is False
    assert run.external_reads == ["greenhouse:example"]
    assert run.external_actions == []
    assert opportunities.get("greenhouse:1") is not None
    state = availability.get("greenhouse:1")
    assert state is not None
    assert state.first_seen_at == NOW
    assert state.last_seen_at == NOW
    assert state.availability_state == "UNVERIFIED"


@pytest.mark.asyncio
async def test_second_refresh_records_new_sighting_without_duplicate_row(tmp_path) -> None:
    connector = StaticConnector(
        [_opportunity("greenhouse:1", source="greenhouse")]
    )
    service, opportunities, availability = _service(
        tmp_path,
        [
            ConfiguredConnector(
                name="greenhouse:example",
                connector=connector,
            )
        ],
    )

    first = await service.run(now=NOW)
    second = await service.run(now=NOW + timedelta(hours=2))

    assert first.created_count == 1
    assert second.created_count == 0
    assert second.existing_count == 1
    assert len(opportunities.list()) == 1
    state = availability.get("greenhouse:1")
    assert state is not None
    assert state.first_seen_at == NOW
    assert state.last_seen_at == NOW + timedelta(hours=2)
    assert state.observation_count == 2


@pytest.mark.asyncio
async def test_duplicate_payload_records_only_one_seen_for_stored_identity(tmp_path) -> None:
    opportunity = _opportunity("remotive:1", source="remotive")
    connector = StaticConnector([opportunity, opportunity])
    service, _, availability = _service(
        tmp_path,
        [ConfiguredConnector(name="remotive", connector=connector)],
    )

    run = await service.run(now=NOW)

    assert run.fetched_count == 2
    assert run.created_count == 1
    assert run.existing_count == 1
    assert run.seen_recorded_count == 1
    observations = availability.list_observations("remotive:1")
    assert len(observations) == 1
    assert observations[0].observation_type == "SEEN"


@pytest.mark.asyncio
async def test_partial_source_failure_is_isolated_and_public_safe(tmp_path) -> None:
    good = StaticConnector([_opportunity("remotive:1", source="remotive")])
    bad = FailingConnector()
    service, opportunities, _ = _service(
        tmp_path,
        [
            ConfiguredConnector(name="remotive", connector=good),
            ConfiguredConnector(name="lever:broken", connector=bad),
        ],
    )

    run = await service.run(now=NOW)

    assert run.ok_count == 1
    assert run.error_count == 1
    assert opportunities.get("remotive:1") is not None
    failed = next(
        item for item in run.diagnostics
        if item.source == "lever:broken"
    )
    assert failed.status == "error"
    assert failed.code == "source_unavailable"
    assert failed.message == "Source unavailable"
    assert "DO_NOT_ECHO_UPSTREAM_SECRET" not in run.model_dump_json()


@pytest.mark.asyncio
async def test_absence_from_later_refresh_never_infers_closure(tmp_path) -> None:
    connector = StaticConnector(
        [_opportunity("greenhouse:1", source="greenhouse")]
    )
    service, opportunities, availability = _service(
        tmp_path,
        [
            ConfiguredConnector(
                name="greenhouse:example",
                connector=connector,
            )
        ],
    )

    await service.run(now=NOW)
    availability.record_verification(
        "greenhouse:1",
        is_open=True,
        observed_at=NOW + timedelta(minutes=5),
        evidence_source="official_company_page",
    )
    before = availability.get("greenhouse:1")
    connector.opportunities = []

    run = await service.run(now=NOW + timedelta(days=1))
    after = availability.get("greenhouse:1")

    assert run.fetched_count == 0
    assert run.seen_recorded_count == 0
    assert run.closure_inference is False
    assert opportunities.get("greenhouse:1").status == "open"
    assert before is not None
    assert after is not None
    assert after.availability_state == "VERIFIED_OPEN"
    assert after.last_verified_at == before.last_verified_at
    assert after.last_seen_at == before.last_seen_at


@pytest.mark.asyncio
async def test_exact_source_subset_runs_only_requested_connectors(tmp_path) -> None:
    remotive = StaticConnector(
        [_opportunity("remotive:1", source="remotive")]
    )
    greenhouse = StaticConnector(
        [_opportunity("greenhouse:1", source="greenhouse")]
    )
    service, opportunities, _ = _service(
        tmp_path,
        [
            ConfiguredConnector(name="remotive", connector=remotive),
            ConfiguredConnector(
                name="greenhouse:example",
                connector=greenhouse,
            ),
        ],
    )

    run = await service.run(
        now=NOW,
        source_names=["greenhouse:example"],
    )

    assert run.requested_sources == ["greenhouse:example"]
    assert [item.source for item in run.diagnostics] == [
        "greenhouse:example"
    ]
    assert remotive.calls == 0
    assert greenhouse.calls == 1
    assert opportunities.get("remotive:1") is None
    assert opportunities.get("greenhouse:1") is not None


@pytest.mark.asyncio
async def test_unknown_source_subset_fails_before_any_fetch_or_write(tmp_path) -> None:
    connector = StaticConnector(
        [_opportunity("remotive:1", source="remotive")]
    )
    service, opportunities, _ = _service(
        tmp_path,
        [ConfiguredConnector(name="remotive", connector=connector)],
    )

    with pytest.raises(
        ValueError,
        match="requested source is not configured",
    ):
        await service.run(
            now=NOW,
            source_names=["mystery"],
        )

    assert connector.calls == 0
    assert opportunities.list() == []


@pytest.mark.asyncio
async def test_duplicate_or_blank_source_subset_fails_closed(tmp_path) -> None:
    service, _, _ = _service(tmp_path, [])

    with pytest.raises(ValueError, match="source names must not be empty"):
        await service.run(
            now=NOW,
            source_names=[],
        )

    with pytest.raises(ValueError, match="source names must be unique"):
        await service.run(
            now=NOW,
            source_names=["remotive", "remotive"],
        )

    with pytest.raises(ValueError, match="source names must not be blank"):
        await service.run(
            now=NOW,
            source_names=["  "],
        )

    with pytest.raises(
        ValueError,
        match="source names must not contain surrounding whitespace",
    ):
        await service.run(
            now=NOW,
            source_names=[" remotive "],
        )


@pytest.mark.asyncio
async def test_empty_registry_returns_explicit_empty_refresh(tmp_path) -> None:
    service, _, _ = _service(tmp_path, [])

    run = await service.run(now=NOW)

    assert run.configured_sources == []
    assert run.requested_sources == []
    assert run.diagnostics == []
    assert run.source_count == 0
    assert run.ok_count == 0
    assert run.error_count == 0
    assert run.fetched_count == 0


@pytest.mark.asyncio
async def test_refresh_requires_timezone_aware_now(tmp_path) -> None:
    service, _, _ = _service(tmp_path, [])

    with pytest.raises(ValueError, match="now must be timezone-aware"):
        await service.run(now=datetime(2026, 9, 19, 1, 0))
