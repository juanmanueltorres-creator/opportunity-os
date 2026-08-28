from datetime import datetime, timezone
from importlib import import_module

import pytest

from app.models.domain import Opportunity
from app.repositories.opportunities import SQLiteOpportunityRepository

NOW = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)


def _ingestion_module():
    return import_module("app.services.ingestion")


def _base_module():
    return import_module("app.connectors.base")


def _opportunity(*, job_id: str, source_id: str) -> Opportunity:
    return Opportunity(
        id=job_id,
        source="remotive",
        source_id=source_id,
        source_url=f"https://remotive.com/jobs/{source_id}",
        company=f"Example Co {source_id}",
        title="Geospatial Developer",
        description="Build geospatial tools",
        discovered_at=NOW,
        location="Worldwide",
        remote_policy="remote",
    )


@pytest.mark.asyncio
async def test_ingest_counts_created_and_existing_without_deleting_rows(tmp_path) -> None:
    repository = SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()
    existing, _ = repository.upsert(_opportunity(job_id="remotive:1", source_id="1"))

    class FakeConnector:
        async def fetch(self) -> list[Opportunity]:
            return [
                _opportunity(job_id="remotive:1", source_id="1"),
                _opportunity(job_id="remotive:2", source_id="2"),
            ]

    result = await _ingestion_module().ingest(FakeConnector(), repository)

    assert result.created == 1
    assert result.existing == 1
    assert repository.get(existing.id) == existing
    assert len(repository.list()) == 2


@pytest.mark.asyncio
async def test_connector_failure_leaves_previously_stored_rows_untouched(tmp_path) -> None:
    repository = SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()
    existing, _ = repository.upsert(_opportunity(job_id="remotive:1", source_id="1"))

    class FailingConnector:
        async def fetch(self) -> list[Opportunity]:
            raise _base_module().ConnectorError("public-safe failure")

    with pytest.raises(_base_module().ConnectorError):
        await _ingestion_module().ingest(FailingConnector(), repository)

    assert repository.get(existing.id) == existing
    assert repository.list() == [existing]
