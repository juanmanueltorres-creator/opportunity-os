from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import sqlite3
from typing import Literal

from app.curation.models import CurationRunRecord, PublicationCheckpoint


class SQLiteCurationLedgerRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS curation_runs (
                    run_id TEXT PRIMARY KEY,
                    generated_at TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    digest_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_curation_runs_recorded
                ON curation_runs(recorded_at, run_id)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS publication_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    digest_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    confirmed_by TEXT NOT NULL,
                    confirmed_at TEXT NOT NULL,
                    preview_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_publication_checkpoints_time
                ON publication_checkpoints(confirmed_at, checkpoint_id)
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_publication_preview_unique
                ON publication_checkpoints(preview_sha256)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS publication_checkpoint_items (
                    checkpoint_id TEXT NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    confirmed_at TEXT NOT NULL,
                    PRIMARY KEY(checkpoint_id, opportunity_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_publication_items_opportunity_time
                ON publication_checkpoint_items(opportunity_id, confirmed_at)
                """
            )
        self._initialized = True

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    def record_run(
        self,
        record: CurationRunRecord,
        *,
        payload_json: str,
    ) -> Literal["NEW", "IDENTICAL", "CONFLICT"]:
        self._ensure_initialized()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT payload_sha256
                FROM curation_runs
                WHERE run_id = ?
                """,
                (record.run_id,),
            ).fetchone()
            if row is not None:
                if row["payload_sha256"] == record.payload_sha256:
                    return "IDENTICAL"
                return "CONFLICT"
            conn.execute(
                """
                INSERT INTO curation_runs (
                    run_id,
                    generated_at,
                    recorded_at,
                    payload_sha256,
                    digest_id,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.generated_at.isoformat(),
                    record.recorded_at.isoformat(),
                    record.payload_sha256,
                    record.digest_id,
                    payload_json,
                ),
            )
        return "NEW"

    def get_run_record(self, run_id: str) -> CurationRunRecord | None:
        self._ensure_initialized()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM curation_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        return CurationRunRecord.model_validate(payload["record"])

    def get_run_payload_json(self, run_id: str) -> str | None:
        self._ensure_initialized()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM curation_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        return None if row is None else str(row["payload_json"])

    def list_run_payload_json(self, *, limit: int) -> list[str]:
        self._ensure_initialized()
        if not 1 <= limit <= 100:
            raise ValueError("limit must be within 1..100")
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM curation_runs
                ORDER BY generated_at DESC, run_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [str(row["payload_json"]) for row in rows]

    def list_publication_checkpoints_for_run(
        self,
        run_id: str,
    ) -> list[PublicationCheckpoint]:
        self._ensure_initialized()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM publication_checkpoints
                WHERE run_id = ?
                ORDER BY confirmed_at ASC, checkpoint_id ASC
                """,
                (run_id,),
            ).fetchall()
        return [
            PublicationCheckpoint.model_validate_json(row["payload_json"])
            for row in rows
        ]

    def publication_count(self) -> int:
        self._ensure_initialized()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM publication_checkpoints"
            ).fetchone()
        return int(row["count"])

    def record_publication_if_count_unchanged(
        self,
        checkpoint: PublicationCheckpoint,
        *,
        expected_publication_count: int,
    ) -> bool:
        self._ensure_initialized()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM publication_checkpoints"
            ).fetchone()
            if int(row["count"]) != expected_publication_count:
                return False
            conn.execute(
                """
                INSERT INTO publication_checkpoints (
                    checkpoint_id,
                    run_id,
                    digest_id,
                    channel,
                    confirmed_by,
                    confirmed_at,
                    preview_sha256,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.checkpoint_id,
                    checkpoint.run_id,
                    checkpoint.digest_id,
                    checkpoint.channel,
                    checkpoint.confirmed_by,
                    checkpoint.confirmed_at.isoformat(),
                    checkpoint.preview_sha256,
                    checkpoint.model_dump_json(),
                ),
            )
            conn.executemany(
                """
                INSERT INTO publication_checkpoint_items (
                    checkpoint_id,
                    opportunity_id,
                    confirmed_at
                ) VALUES (?, ?, ?)
                """,
                [
                    (
                        checkpoint.checkpoint_id,
                        opportunity_id,
                        checkpoint.confirmed_at.isoformat(),
                    )
                    for opportunity_id in checkpoint.opportunity_ids
                ],
            )
        return True

    def list_recently_published_opportunity_ids(
        self,
        *,
        since: datetime,
        until: datetime,
    ) -> set[str]:
        self._ensure_initialized()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT opportunity_id
                FROM publication_checkpoint_items
                WHERE confirmed_at >= ?
                  AND confirmed_at <= ?
                ORDER BY opportunity_id ASC
                """,
                (since.isoformat(), until.isoformat()),
            ).fetchall()
        return {str(row["opportunity_id"]) for row in rows}

    def get_publication_by_preview_sha256(
        self,
        preview_sha256: str,
    ) -> PublicationCheckpoint | None:
        self._ensure_initialized()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM publication_checkpoints
                WHERE preview_sha256 = ?
                ORDER BY confirmed_at ASC, checkpoint_id ASC
                LIMIT 1
                """,
                (preview_sha256,),
            ).fetchone()
        if row is None:
            return None
        return PublicationCheckpoint.model_validate_json(row["payload_json"])

    def list_published_opportunity_ids_for_run(
        self,
        *,
        run_id: str,
        opportunity_ids: list[str],
    ) -> set[str]:
        self._ensure_initialized()
        if not opportunity_ids:
            return set()
        placeholders = ",".join("?" for _ in opportunity_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT items.opportunity_id
                FROM publication_checkpoint_items AS items
                JOIN publication_checkpoints AS checkpoints
                  ON checkpoints.checkpoint_id = items.checkpoint_id
                WHERE checkpoints.run_id = ?
                  AND items.opportunity_id IN ({placeholders})
                """,
                (run_id, *opportunity_ids),
            ).fetchall()
        return {str(row["opportunity_id"]) for row in rows}

    def list_published_opportunity_ids(
        self,
        opportunity_ids: list[str],
    ) -> set[str]:
        self._ensure_initialized()
        if not opportunity_ids:
            return set()
        placeholders = ",".join("?" for _ in opportunity_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT opportunity_id
                FROM publication_checkpoint_items
                WHERE opportunity_id IN ({placeholders})
                """,
                tuple(opportunity_ids),
            ).fetchall()
        return {str(row["opportunity_id"]) for row in rows}
