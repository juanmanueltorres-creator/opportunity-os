from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.metrics.models import StrictMetricsModel

HistoricalKind = Literal[
    "DRAFT_OBSERVED",
    "SEND_OBSERVED",
    "REPLY_OBSERVED",
    "PROCESS_OPENED_OBSERVED",
    "PROCESS_CLOSED_OBSERVED",
]
HistoricalProvenance = Literal["IMPORTED_GMAIL", "MANUAL_ASSERTION"]
SelectionScope = Literal["SELECTED_THREADS", "ALL_DECLARED_OUTREACH_THREADS"]


def _require_aware(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class HistoricalObservation(StrictMetricsModel):
    observation_id: str = Field(min_length=1)
    kind: HistoricalKind
    opportunity_id: str | None = None
    account_id: str | None = None
    company: str | None = None
    role: str | None = None
    occurred_at: datetime
    observed_at: datetime
    provenance: HistoricalProvenance
    source_ref: str | None = None
    provider_message_id: str | None = None
    provider_thread_id: str | None = None
    event_confidence: float = Field(ge=0, le=1)
    link_confidence: float = Field(ge=0, le=1)
    reconstruction_note: str | None = Field(default=None, max_length=500)

    @field_validator("occurred_at", "observed_at")
    @classmethod
    def timestamps_must_be_aware(cls, value: datetime) -> datetime:
        return _require_aware(value, field_name="historical observation timestamp")


class HistoricalImportBatch(StrictMetricsModel):
    batch_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    window_start: datetime
    window_end: datetime
    selection_scope: SelectionScope
    selected_message_count: int = Field(ge=0)
    selected_thread_count: int = Field(ge=0)
    completed_at: datetime
    complete_for_declared_scope: bool

    @field_validator("window_start", "window_end", "completed_at")
    @classmethod
    def timestamps_must_be_aware(cls, value: datetime) -> datetime:
        return _require_aware(value, field_name="historical import timestamp")

    @model_validator(mode="after")
    def window_must_be_ordered(self) -> "HistoricalImportBatch":
        if self.window_end < self.window_start:
            raise ValueError("historical import window end must not precede start")
        return self


class HistoricalImportManifest(StrictMetricsModel):
    batch: HistoricalImportBatch
    observations: list[HistoricalObservation] = Field(default_factory=list)


class SQLiteHistoricalRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS historical_observations (
                    observation_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_historical_observations_time
                ON historical_observations(occurred_at, observation_id)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS historical_import_batches (
                    batch_id TEXT PRIMARY KEY,
                    window_start TEXT NOT NULL,
                    window_end TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def get_observation(self, observation_id: str) -> HistoricalObservation | None:
        if not self.path.exists():
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM historical_observations WHERE observation_id = ? LIMIT 1",
                (observation_id,),
            ).fetchone()
        if row is None:
            return None
        return HistoricalObservation.model_validate_json(row["payload_json"])

    def save_observation(
        self, observation: HistoricalObservation
    ) -> tuple[HistoricalObservation, bool]:
        existing = self.get_observation(observation.observation_id)
        if existing is not None:
            if existing != observation:
                raise ValueError("historical observation_id conflict")
            return existing, False

        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO historical_observations (
                        observation_id, kind, occurred_at, payload_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        observation.observation_id,
                        observation.kind,
                        observation.occurred_at.isoformat(),
                        observation.model_dump_json(),
                    ),
                )
            except sqlite3.IntegrityError:
                existing = self.get_observation(observation.observation_id)
                if existing is not None and existing == observation:
                    return existing, False
                raise ValueError("historical observation_id conflict")
        return observation, True

    def list_observations(self) -> list[HistoricalObservation]:
        if not self.path.exists():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM historical_observations
                ORDER BY occurred_at ASC, observation_id ASC
                """
            ).fetchall()
        return [
            HistoricalObservation.model_validate_json(row["payload_json"])
            for row in rows
        ]

    def get_batch(self, batch_id: str) -> HistoricalImportBatch | None:
        if not self.path.exists():
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM historical_import_batches WHERE batch_id = ? LIMIT 1",
                (batch_id,),
            ).fetchone()
        if row is None:
            return None
        return HistoricalImportBatch.model_validate_json(row["payload_json"])

    def save_batch(
        self, batch: HistoricalImportBatch
    ) -> tuple[HistoricalImportBatch, bool]:
        existing = self.get_batch(batch.batch_id)
        if existing is not None:
            if existing != batch:
                raise ValueError("historical batch_id conflict")
            return existing, False

        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO historical_import_batches (
                        batch_id, window_start, window_end, completed_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        batch.batch_id,
                        batch.window_start.isoformat(),
                        batch.window_end.isoformat(),
                        batch.completed_at.isoformat(),
                        batch.model_dump_json(),
                    ),
                )
            except sqlite3.IntegrityError:
                existing = self.get_batch(batch.batch_id)
                if existing is not None and existing == batch:
                    return existing, False
                raise ValueError("historical batch_id conflict")
        return batch, True

    def list_batches(self) -> list[HistoricalImportBatch]:
        if not self.path.exists():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM historical_import_batches
                ORDER BY completed_at ASC, batch_id ASC
                """
            ).fetchall()
        return [
            HistoricalImportBatch.model_validate_json(row["payload_json"])
            for row in rows
        ]
