from dataclasses import dataclass
from datetime import datetime

from app.availability.repository import SQLiteAvailabilityRepository
from app.connectors.base import JobConnector
from app.repositories.opportunities import SQLiteOpportunityRepository


@dataclass(frozen=True, slots=True)
class IngestionResult:
    created: int
    existing: int
    fetched: int
    unique_stored: int
    seen_recorded: int


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
    seen_ids: set[str] = set()
    stored_ids: set[str] = set()

    for opportunity in opportunities:
        snapshot_opportunity = opportunity
        if (
            availability_repository is not None
            and observed_at is not None
            and opportunity.discovered_at > observed_at
        ):
            snapshot_opportunity = opportunity.model_copy(
                update={"discovered_at": observed_at}
            )

        stored, was_created = repository.upsert(snapshot_opportunity)
        stored_ids.add(stored.id)
        if (
            availability_repository is not None
            and observed_at is not None
            and stored.id not in seen_ids
        ):
            availability_repository.record_seen(
                stored.id,
                observed_at=observed_at,
                evidence_source=snapshot_opportunity.source,
                source_url=snapshot_opportunity.source_url,
            )
            seen_ids.add(stored.id)
        if was_created:
            created += 1
        else:
            existing += 1

    return IngestionResult(
        created=created,
        existing=existing,
        fetched=len(opportunities),
        unique_stored=len(stored_ids),
        seen_recorded=len(seen_ids),
    )
