from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3

from app.availability.models import (
    AvailabilityObservation,
    OpportunityAvailability,
)


_VERIFIED_TYPES = {"VERIFIED_OPEN", "VERIFIED_CLOSED"}
_SEEN_TYPES = {"SEEN", "VERIFIED_OPEN"}


class SQLiteAvailabilityRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS opportunity_availability_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    opportunity_id TEXT NOT NULL,
                    observation_type TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    evidence_source TEXT NOT NULL,
                    source_url TEXT,
                    note TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_availability_opportunity_time
                ON opportunity_availability_observations(
                    opportunity_id,
                    observed_at,
                    id
                )
                """
            )
        self._initialized = True

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    def record(self, observation: AvailabilityObservation) -> None:
        self._ensure_initialized()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO opportunity_availability_observations (
                    opportunity_id,
                    observation_type,
                    observed_at,
                    evidence_source,
                    source_url,
                    note
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.opportunity_id,
                    observation.observation_type,
                    observation.observed_at.isoformat(),
                    observation.evidence_source,
                    observation.source_url,
                    observation.note,
                ),
            )

    def record_seen(
        self,
        opportunity_id: str,
        *,
        observed_at: datetime,
        evidence_source: str,
        source_url: str | None = None,
    ) -> None:
        self.record(
            AvailabilityObservation(
                opportunity_id=opportunity_id,
                observation_type="SEEN",
                observed_at=observed_at,
                evidence_source=evidence_source,
                source_url=source_url,
            )
        )

    def record_verification(
        self,
        opportunity_id: str,
        *,
        is_open: bool,
        observed_at: datetime,
        evidence_source: str,
        source_url: str | None = None,
        note: str | None = None,
    ) -> None:
        self.record(
            AvailabilityObservation(
                opportunity_id=opportunity_id,
                observation_type=(
                    "VERIFIED_OPEN" if is_open else "VERIFIED_CLOSED"
                ),
                observed_at=observed_at,
                evidence_source=evidence_source,
                source_url=source_url,
                note=note,
            )
        )

    def list_observations(
        self,
        opportunity_id: str,
    ) -> list[AvailabilityObservation]:
        self._ensure_initialized()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    opportunity_id,
                    observation_type,
                    observed_at,
                    evidence_source,
                    source_url,
                    note
                FROM opportunity_availability_observations
                WHERE opportunity_id = ?
                ORDER BY observed_at ASC, id ASC
                """,
                (opportunity_id,),
            ).fetchall()
        return [AvailabilityObservation.model_validate(dict(row)) for row in rows]

    def get(self, opportunity_id: str) -> OpportunityAvailability | None:
        observations = self.list_observations(opportunity_id)
        if not observations:
            return None
        return _project(opportunity_id, observations)


def _project(
    opportunity_id: str,
    observations: list[AvailabilityObservation],
) -> OpportunityAvailability:
    first_seen_at = min(item.observed_at for item in observations)
    latest_observation_at = max(item.observed_at for item in observations)

    seen = [item for item in observations if item.observation_type in _SEEN_TYPES]
    last_seen_at = max((item.observed_at for item in seen), default=None)

    verified = [
        item for item in observations
        if item.observation_type in _VERIFIED_TYPES
    ]
    if verified:
        latest_verified = max(
            enumerate(verified),
            key=lambda pair: (pair[1].observed_at, pair[0]),
        )[1]
        last_verified_at = latest_verified.observed_at
        verification_source = latest_verified.evidence_source
        availability_state = latest_verified.observation_type
    else:
        last_verified_at = None
        verification_source = None
        availability_state = "UNVERIFIED"

    return OpportunityAvailability(
        opportunity_id=opportunity_id,
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        last_verified_at=last_verified_at,
        verification_source=verification_source,
        availability_state=availability_state,
        observation_count=len(observations),
        latest_observation_at=latest_observation_at,
    )
