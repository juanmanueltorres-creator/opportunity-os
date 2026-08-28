from dataclasses import dataclass

from app.connectors.base import JobConnector
from app.repositories.opportunities import SQLiteOpportunityRepository


@dataclass(frozen=True, slots=True)
class IngestionResult:
    created: int
    existing: int


async def ingest(
    connector: JobConnector,
    repository: SQLiteOpportunityRepository,
) -> IngestionResult:
    opportunities = await connector.fetch()
    created = 0
    existing = 0

    for opportunity in opportunities:
        _, was_created = repository.upsert(opportunity)
        if was_created:
            created += 1
        else:
            existing += 1

    return IngestionResult(created=created, existing=existing)
