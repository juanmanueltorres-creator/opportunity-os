from dataclasses import dataclass
from datetime import datetime

from app.availability.repository import SQLiteAvailabilityRepository
from app.connectors.base import JobConnector
from app.repositories.opportunities import SQLiteOpportunityRepository


@dataclass(frozen=True, slots=True)
class IngestionResult:
    created: int
    existing: int


async def ingest(
    connector: JobConnector,
    repository: SQLiteOpportunityRepository,
    *,
    availability_repository: SQLiteAvailabilityRepository | None = None,
    observed_at: datetime | None = None,
) -> IngestionResult:
    if availability_repository is not None:
        if observed_at is None:
            raise ValueError(
                "observed_at is required when availability memory is enabled"
            )
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")

    opportunities = await connector.fetch()
    created = 0
    existing = 0

    for opportunity in opportunities:
        stored, was_created = repository.upsert(opportunity)
        if availability_repository is not None and observed_at is not None:
            availability_repository.record_seen(
                stored.id,
                observed_at=observed_at,
                evidence_source=opportunity.source,
                source_url=opportunity.source_url,
            )
        if was_created:
            created += 1
        else:
            existing += 1

    return IngestionResult(created=created, existing=existing)
