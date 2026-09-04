from __future__ import annotations

from pathlib import Path
import sqlite3

from app.contributions.models import ContributionEvent, PublicContributionEntry
from app.contributions.observations import ContributionImportReceipt
from app.contributions.projector import ContributionProjector


class SQLiteContributionRepository:
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
                CREATE TABLE IF NOT EXISTS contribution_entries (
                    entry_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    discovered_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS contribution_events (
                    event_id TEXT PRIMARY KEY,
                    entry_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_contribution_events_entry
                ON contribution_events(entry_id, observed_at, event_id)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS contribution_import_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    observation_id TEXT NOT NULL UNIQUE,
                    entry_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                )
                """
            )

    def _require_initialized(self) -> None:
        if not self.path.exists():
            raise RuntimeError("contribution repository is not initialized")

    @staticmethod
    def _entry_from_row(row: sqlite3.Row | None) -> PublicContributionEntry | None:
        if row is None:
            return None
        return PublicContributionEntry.model_validate_json(row["payload_json"])

    @staticmethod
    def _event_from_row(row: sqlite3.Row | None) -> ContributionEvent | None:
        if row is None:
            return None
        return ContributionEvent.model_validate_json(row["payload_json"])

    @staticmethod
    def _receipt_from_row(row: sqlite3.Row | None) -> ContributionImportReceipt | None:
        if row is None:
            return None
        return ContributionImportReceipt.model_validate_json(row["payload_json"])

    def _get_entry_conn(
        self,
        conn: sqlite3.Connection,
        entry_id: str,
    ) -> PublicContributionEntry | None:
        row = conn.execute(
            "SELECT payload_json FROM contribution_entries WHERE entry_id = ? LIMIT 1",
            (entry_id,),
        ).fetchone()
        return self._entry_from_row(row)

    def get_entry(self, entry_id: str) -> PublicContributionEntry | None:
        if not self.path.exists():
            return None
        with self._connect() as conn:
            return self._get_entry_conn(conn, entry_id)

    def _get_event_conn(
        self,
        conn: sqlite3.Connection,
        event_id: str,
    ) -> ContributionEvent | None:
        row = conn.execute(
            "SELECT payload_json FROM contribution_events WHERE event_id = ? LIMIT 1",
            (event_id,),
        ).fetchone()
        return self._event_from_row(row)

    def get_event(self, event_id: str) -> ContributionEvent | None:
        if not self.path.exists():
            return None
        with self._connect() as conn:
            return self._get_event_conn(conn, event_id)

    def _list_events_conn(
        self,
        conn: sqlite3.Connection,
        entry_id: str,
    ) -> list[ContributionEvent]:
        rows = conn.execute(
            """
            SELECT payload_json
            FROM contribution_events
            WHERE entry_id = ?
            ORDER BY observed_at ASC, event_id ASC
            """,
            (entry_id,),
        ).fetchall()
        return [ContributionEvent.model_validate_json(row["payload_json"]) for row in rows]

    def list_events(self, entry_id: str) -> list[ContributionEvent]:
        if not self.path.exists():
            return []
        with self._connect() as conn:
            return self._list_events_conn(conn, entry_id)

    def _get_receipt_for_observation_conn(
        self,
        conn: sqlite3.Connection,
        observation_id: str,
    ) -> ContributionImportReceipt | None:
        row = conn.execute(
            """
            SELECT payload_json
            FROM contribution_import_receipts
            WHERE observation_id = ?
            LIMIT 1
            """,
            (observation_id,),
        ).fetchone()
        return self._receipt_from_row(row)

    def get_receipt_for_observation(
        self,
        observation_id: str,
    ) -> ContributionImportReceipt | None:
        if not self.path.exists():
            return None
        with self._connect() as conn:
            return self._get_receipt_for_observation_conn(conn, observation_id)

    def _validate_receipt_conn(
        self,
        conn: sqlite3.Connection,
        receipt: ContributionImportReceipt,
    ) -> ContributionImportReceipt | None:
        existing_by_observation = self._get_receipt_for_observation_conn(
            conn,
            receipt.observation_id,
        )
        if existing_by_observation is not None:
            if existing_by_observation != receipt:
                raise ValueError("contribution receipt observation conflict")
            return existing_by_observation

        row = conn.execute(
            "SELECT payload_json FROM contribution_import_receipts WHERE receipt_id = ? LIMIT 1",
            (receipt.receipt_id,),
        ).fetchone()
        existing_by_id = self._receipt_from_row(row)
        if existing_by_id is not None:
            if existing_by_id != receipt:
                raise ValueError("contribution receipt_id conflict")
            return existing_by_id
        return None

    @staticmethod
    def _insert_receipt_conn(
        conn: sqlite3.Connection,
        receipt: ContributionImportReceipt,
    ) -> None:
        conn.execute(
            """
            INSERT INTO contribution_import_receipts (
                receipt_id, observation_id, entry_id, payload_json, processed_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                receipt.receipt_id,
                receipt.observation_id,
                receipt.entry_id,
                receipt.model_dump_json(),
                receipt.processed_at.isoformat(),
            ),
        )

    def insert_entry_with_receipt(
        self,
        entry: PublicContributionEntry,
        receipt: ContributionImportReceipt,
    ) -> tuple[PublicContributionEntry, ContributionImportReceipt, bool]:
        self._require_initialized()
        if receipt.entry_id != entry.entry_id or receipt.contribution_event_id is not None:
            raise ValueError("entry receipt does not match contribution entry")

        with self._connect() as conn:
            existing_entry = self._get_entry_conn(conn, entry.entry_id)
            existing_receipt = self._validate_receipt_conn(conn, receipt)

            if existing_entry is not None:
                if existing_entry != entry:
                    raise ValueError("contribution entry_id conflict")
                if existing_receipt is None:
                    self._insert_receipt_conn(conn, receipt)
                    existing_receipt = receipt
                return existing_entry, existing_receipt, False

            conn.execute(
                """
                INSERT INTO contribution_entries (entry_id, payload_json, discovered_at)
                VALUES (?, ?, ?)
                """,
                (entry.entry_id, entry.model_dump_json(), entry.discovered_at.isoformat()),
            )
            if existing_receipt is None:
                self._insert_receipt_conn(conn, receipt)
                existing_receipt = receipt
            return entry, existing_receipt, True

    def append_event_with_receipt(
        self,
        event: ContributionEvent,
        receipt: ContributionImportReceipt,
        projector: ContributionProjector,
    ) -> tuple[ContributionEvent, ContributionImportReceipt, bool]:
        self._require_initialized()
        if (
            receipt.entry_id != event.entry_id
            or receipt.contribution_event_id != event.event_id
        ):
            raise ValueError("event receipt does not match contribution event")

        with self._connect() as conn:
            entry = self._get_entry_conn(conn, event.entry_id)
            if entry is None:
                raise ValueError("unknown contribution entry")

            existing_event = self._get_event_conn(conn, event.event_id)
            existing_receipt = self._validate_receipt_conn(conn, receipt)

            if existing_event is not None:
                if existing_event != event:
                    raise ValueError("contribution event_id conflict")
                if existing_receipt is None:
                    self._insert_receipt_conn(conn, receipt)
                    existing_receipt = receipt
                return existing_event, existing_receipt, False

            events = self._list_events_conn(conn, event.entry_id)
            if events:
                latest = events[-1]
                if (event.observed_at, event.event_id) <= (
                    latest.observed_at,
                    latest.event_id,
                ):
                    raise ValueError("out-of-order contribution event")

            projector.project(entry=entry, events=events + [event])

            conn.execute(
                """
                INSERT INTO contribution_events (
                    event_id, entry_id, kind, payload_json, observed_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.entry_id,
                    event.kind,
                    event.model_dump_json(),
                    event.observed_at.isoformat(),
                ),
            )
            if existing_receipt is None:
                self._insert_receipt_conn(conn, receipt)
                existing_receipt = receipt
            return event, existing_receipt, True
