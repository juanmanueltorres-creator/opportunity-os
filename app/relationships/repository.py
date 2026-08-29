from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import sqlite3

from app.relationships.models import CareerContact, RelationshipAccount, RelationshipEvent

ProjectionResult = tuple[RelationshipAccount, list[CareerContact]]
Projector = Callable[[RelationshipAccount | None, list[CareerContact]], ProjectionResult]


class SQLiteRelationshipRepository:
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
                CREATE TABLE IF NOT EXISTS relationship_accounts (
                    account_id TEXT PRIMARY KEY,
                    relationship_state TEXT NOT NULL,
                    last_contacted_at TEXT,
                    cooldown_until TEXT,
                    open_process INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS relationship_contacts (
                    contact_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    disposition TEXT NOT NULL,
                    verification_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_relationship_contacts_account
                ON relationship_contacts(account_id, disposition, contact_id)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS relationship_events (
                    event_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    contact_id TEXT,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_relationship_events_account
                ON relationship_events(account_id, occurred_at, event_id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_relationship_events_contact
                ON relationship_events(contact_id, occurred_at, event_id)
                """
            )

    def _get_account_conn(
        self, conn: sqlite3.Connection, account_id: str
    ) -> RelationshipAccount | None:
        row = conn.execute(
            "SELECT payload_json FROM relationship_accounts WHERE account_id = ? LIMIT 1",
            (account_id,),
        ).fetchone()
        if row is None:
            return None
        return RelationshipAccount.model_validate_json(row["payload_json"])

    def get_account(self, account_id: str) -> RelationshipAccount | None:
        with self._connect() as conn:
            return self._get_account_conn(conn, account_id)

    def list_accounts(self) -> list[RelationshipAccount]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM relationship_accounts
                ORDER BY account_id ASC
                """
            ).fetchall()
        return [
            RelationshipAccount.model_validate_json(row["payload_json"])
            for row in rows
        ]

    def _get_contact_conn(
        self, conn: sqlite3.Connection, contact_id: str
    ) -> CareerContact | None:
        row = conn.execute(
            "SELECT payload_json FROM relationship_contacts WHERE contact_id = ? LIMIT 1",
            (contact_id,),
        ).fetchone()
        if row is None:
            return None
        return CareerContact.model_validate_json(row["payload_json"])

    def get_contact(self, contact_id: str) -> CareerContact | None:
        with self._connect() as conn:
            return self._get_contact_conn(conn, contact_id)

    def _list_contacts_conn(
        self, conn: sqlite3.Connection, account_id: str
    ) -> list[CareerContact]:
        rows = conn.execute(
            """
            SELECT payload_json
            FROM relationship_contacts
            WHERE account_id = ?
            ORDER BY contact_id ASC
            """,
            (account_id,),
        ).fetchall()
        return [CareerContact.model_validate_json(row["payload_json"]) for row in rows]

    def list_contacts(self, account_id: str) -> list[CareerContact]:
        with self._connect() as conn:
            return self._list_contacts_conn(conn, account_id)

    def _validate_preferred_contact(
        self, conn: sqlite3.Connection, account: RelationshipAccount
    ) -> None:
        if account.preferred_next_contact_id is None:
            return
        contact = self._get_contact_conn(conn, account.preferred_next_contact_id)
        if (
            contact is None
            or contact.account_id != account.account_id
            or not contact.active
            or contact.disposition != "AVAILABLE"
        ):
            raise ValueError("preferred contact must belong to account and be active/available")

    def _save_account_conn(
        self, conn: sqlite3.Connection, account: RelationshipAccount
    ) -> RelationshipAccount:
        self._validate_preferred_contact(conn, account)
        conn.execute(
            """
            INSERT INTO relationship_accounts (
                account_id, relationship_state, last_contacted_at,
                cooldown_until, open_process, payload_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                relationship_state = excluded.relationship_state,
                last_contacted_at = excluded.last_contacted_at,
                cooldown_until = excluded.cooldown_until,
                open_process = excluded.open_process,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (
                account.account_id,
                account.relationship_state,
                account.last_contacted_at.isoformat() if account.last_contacted_at else None,
                account.cooldown_until.isoformat() if account.cooldown_until else None,
                int(account.open_process),
                account.model_dump_json(),
                account.updated_at.isoformat(),
            ),
        )
        return account

    def save_account(self, account: RelationshipAccount) -> RelationshipAccount:
        with self._connect() as conn:
            return self._save_account_conn(conn, account)

    def _save_contact_conn(
        self, conn: sqlite3.Connection, contact: CareerContact
    ) -> CareerContact:
        conn.execute(
            """
            INSERT INTO relationship_contacts (
                contact_id, account_id, disposition, verification_status,
                payload_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(contact_id) DO UPDATE SET
                account_id = excluded.account_id,
                disposition = excluded.disposition,
                verification_status = excluded.verification_status,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (
                contact.contact_id,
                contact.account_id,
                contact.disposition,
                contact.verification_status,
                contact.model_dump_json(),
                contact.observed_at.isoformat(),
            ),
        )
        return contact

    def save_contact(self, contact: CareerContact) -> CareerContact:
        with self._connect() as conn:
            return self._save_contact_conn(conn, contact)

    def _get_event_conn(
        self, conn: sqlite3.Connection, event_id: str
    ) -> RelationshipEvent | None:
        row = conn.execute(
            "SELECT payload_json FROM relationship_events WHERE event_id = ? LIMIT 1",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return RelationshipEvent.model_validate_json(row["payload_json"])

    def get_event(self, event_id: str) -> RelationshipEvent | None:
        with self._connect() as conn:
            return self._get_event_conn(conn, event_id)

    def list_events(self, account_id: str) -> list[RelationshipEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM relationship_events
                WHERE account_id = ?
                ORDER BY occurred_at ASC, event_id ASC
                """,
                (account_id,),
            ).fetchall()
        return [RelationshipEvent.model_validate_json(row["payload_json"]) for row in rows]

    def _latest_event_order_conn(
        self,
        conn: sqlite3.Connection,
        account_id: str,
    ) -> tuple[object, str] | None:
        row = conn.execute(
            """
            SELECT payload_json
            FROM relationship_events
            WHERE account_id = ?
            ORDER BY occurred_at DESC, event_id DESC
            LIMIT 1
            """,
            (account_id,),
        ).fetchone()
        if row is None:
            return None
        latest = RelationshipEvent.model_validate_json(row["payload_json"])
        return latest.occurred_at, latest.event_id

    def _append_event_conn(
        self, conn: sqlite3.Connection, event: RelationshipEvent
    ) -> tuple[RelationshipEvent, bool]:
        existing = self._get_event_conn(conn, event.event_id)
        if existing is not None:
            if existing != event:
                raise ValueError("relationship event_id conflict")
            return existing, False

        latest_order = self._latest_event_order_conn(conn, event.account_id)
        if latest_order is not None and (event.occurred_at, event.event_id) <= latest_order:
            raise ValueError("out-of-order relationship event")

        conn.execute(
            """
            INSERT INTO relationship_events (
                event_id, account_id, contact_id, kind, payload_json, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.account_id,
                event.contact_id,
                event.kind,
                event.model_dump_json(),
                event.occurred_at.isoformat(),
            ),
        )
        return event, True

    def append_event(self, event: RelationshipEvent) -> RelationshipEvent:
        with self._connect() as conn:
            stored, _ = self._append_event_conn(conn, event)
            return stored

    def apply_event_transaction(
        self,
        event: RelationshipEvent,
        projector: Projector,
    ) -> tuple[RelationshipEvent, RelationshipAccount]:
        with self._connect() as conn:
            stored, inserted = self._append_event_conn(conn, event)
            if not inserted:
                account = self._get_account_conn(conn, event.account_id)
                if account is None:
                    raise ValueError("idempotent event has no relationship account projection")
                return stored, account

            account = self._get_account_conn(conn, event.account_id)
            contacts = self._list_contacts_conn(conn, event.account_id)
            next_account, next_contacts = projector(account, contacts)
            if next_account.account_id != event.account_id:
                raise ValueError("projection account_id mismatch")
            for contact in next_contacts:
                if contact.account_id != event.account_id:
                    raise ValueError("projection contact account_id mismatch")
                self._save_contact_conn(conn, contact)
            self._save_account_conn(conn, next_account)
            return stored, next_account
