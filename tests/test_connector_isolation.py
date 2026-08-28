from datetime import datetime, timezone

import pytest

from app.connectors.base import ConnectorError
from app.models.domain import Opportunity
from app.repositories.opportunities import SQLiteOpportunityRepository
from app.services.ingestion import ingest

NOW = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)


def _greenhouse_job() -> Opportunity:
    return Opportunity(
        id="greenhouse:1",
        source="greenhouse",
        source_id="1",
        source_url="https://boards.greenhouse.io/example/jobs/1",
        company="Example Co",
        title="GIS Developer",
        description="Build GIS software",
        discovered_at=NOW,
    )


@pytest.mark.asyncio
async def test_failure_of_one_source_does_not_invalidate_another_source(tmp_path) -> None:
    repository = SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()

    class SuccessfulConnector:
        async def fetch(self) -> list[Opportunity]:
            return [_greenhouse_job()]

    class FailingConnector:
        async def fetch(self) -> list[Opportunity]:
            raise ConnectorError("another source failed")

    result = await ingest(SuccessfulConnector(), repository)
    assert result.created == 1

    with pytest.raises(ConnectorError):
        await ingest(FailingConnector(), repository)

    stored = repository.list()
    assert len(stored) == 1
    assert stored[0].source == "greenhouse"
