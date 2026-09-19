from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.availability.repository import SQLiteAvailabilityRepository
from app.models.domain import Opportunity
from app.repositories.opportunities import SQLiteOpportunityRepository
from app.services.ingestion import ingest


NOW = datetime(2026, 9, 18, 18, 30, tzinfo=timezone.utc)


def _opportunity(
    item_id: str,
    *,
    source: str = "workana",
    source_id: str | None = None,
    company: str = "Example Co",
    title: str = "GIS Developer",
    location: str = "Argentina",
) -> Opportunity:
    return Opportunity(
        id=item_id,
        source=source,
        source_id=source_id or item_id,
        source_url=f"https://{source}.example/jobs/{item_id}",
        company=company,
        title=title,
        description="Build geospatial tools",
        discovered_at=NOW - timedelta(days=1),
        location=location,
    )


@pytest.mark.asyncio
async def test_ingestion_records_seen_for_created_and_existing_rows(tmp_path) -> None:
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()

    class Connector:
        async def fetch(self) -> list[Opportunity]:
            return [_opportunity("opp-1")]

    first_at = NOW - timedelta(hours=2)
    second_at = NOW

    first = await ingest(
        Connector(),
        opportunities,
        availability_repository=availability,
        observed_at=first_at,
    )
    second = await ingest(
        Connector(),
        opportunities,
        availability_repository=availability,
        observed_at=second_at,
    )

    assert first.created == 1
    assert second.existing == 1
    state = availability.get("opp-1")
    assert state is not None
    assert state.first_seen_at == first_at
    assert state.last_seen_at == second_at
    assert state.observation_count == 2
    assert state.availability_state == "UNVERIFIED"


@pytest.mark.asyncio
async def test_cross_source_dedupe_records_sighting_on_canonical_opportunity(tmp_path) -> None:
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()

    canonical, _ = opportunities.upsert(
        _opportunity(
            "canonical",
            source="source-a",
            source_id="a-1",
        )
    )

    class Connector:
        async def fetch(self) -> list[Opportunity]:
            return [
                _opportunity(
                    "duplicate",
                    source="source-b",
                    source_id="b-1",
                )
            ]

    result = await ingest(
        Connector(),
        opportunities,
        availability_repository=availability,
        observed_at=NOW,
    )

    assert result.existing == 1
    assert availability.get("duplicate") is None
    state = availability.get(canonical.id)
    assert state is not None
    observations = availability.list_observations(canonical.id)
    assert len(observations) == 1
    assert observations[0].evidence_source == "source-b"
    assert observations[0].source_url == "https://source-b.example/jobs/duplicate"


@pytest.mark.asyncio
async def test_availability_memory_requires_explicit_observation_time(tmp_path) -> None:
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()

    class Connector:
        async def fetch(self) -> list[Opportunity]:
            return [_opportunity("opp-1")]

    with pytest.raises(
        ValueError,
        match="observed_at is required when availability memory is enabled",
    ):
        await ingest(
            Connector(),
            opportunities,
            availability_repository=availability,
        )


@pytest.mark.asyncio
async def test_connector_returning_nothing_does_not_create_closed_observation(tmp_path) -> None:
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()

    stored, _ = opportunities.upsert(_opportunity("opp-1"))
    availability.record_seen(
        stored.id,
        observed_at=NOW - timedelta(days=1),
        evidence_source="source-a",
    )

    class EmptyConnector:
        async def fetch(self) -> list[Opportunity]:
            return []

    result = await ingest(
        EmptyConnector(),
        opportunities,
        availability_repository=availability,
        observed_at=NOW,
    )

    assert result.created == 0
    assert result.existing == 0
    state = availability.get(stored.id)
    assert state is not None
    assert state.observation_count == 1
    assert state.availability_state == "UNVERIFIED"
