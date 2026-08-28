from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

from app.models.domain import Opportunity


class SQLiteOpportunityRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS opportunities (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    discovered_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    location TEXT,
                    remote_policy TEXT,
                    published_at TEXT,
                    required_skills TEXT NOT NULL,
                    preferred_skills TEXT NOT NULL,
                    compensation TEXT,
                    dedupe_key TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                idx_opportunities_source_identity
                ON opportunities(source, source_id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_opportunities_dedupe_key
                ON opportunities(dedupe_key)
                """
            )

    @staticmethod
    def _dedupe_key(opportunity: Opportunity) -> str:
        def normalize(value: str | None) -> str:
            return " ".join((value or "").casefold().split())

        return "|".join(
            [
                normalize(opportunity.company),
                normalize(opportunity.title),
                normalize(opportunity.location),
            ]
        )

    @staticmethod
    def _serialize(opportunity: Opportunity) -> dict[str, object]:
        return {
            "id": opportunity.id,
            "source": opportunity.source,
            "source_id": opportunity.source_id,
            "source_url": opportunity.source_url,
            "company": opportunity.company,
            "title": opportunity.title,
            "description": opportunity.description,
            "discovered_at": opportunity.discovered_at.isoformat(),
            "status": opportunity.status,
            "location": opportunity.location,
            "remote_policy": opportunity.remote_policy,
            "published_at": opportunity.published_at.isoformat() if opportunity.published_at is not None else None,
            "required_skills": json.dumps(opportunity.required_skills),
            "preferred_skills": json.dumps(opportunity.preferred_skills),
            "compensation": opportunity.compensation,
            "dedupe_key": SQLiteOpportunityRepository._dedupe_key(opportunity),
        }

    @staticmethod
    def _row_to_opportunity(row: sqlite3.Row) -> Opportunity:
        payload = dict(row)
        payload.pop("dedupe_key", None)
        payload["required_skills"] = json.loads(payload["required_skills"])
        payload["preferred_skills"] = json.loads(payload["preferred_skills"])
        return Opportunity.model_validate(payload)

    def upsert(self, opportunity: Opportunity) -> tuple[Opportunity, bool]:
        serialized = self._serialize(opportunity)
        dedupe_key = str(serialized["dedupe_key"])

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM opportunities WHERE source = ? AND source_id = ? LIMIT 1",
                (opportunity.source, opportunity.source_id),
            ).fetchone()
            if existing is None:
                existing = conn.execute(
                    "SELECT * FROM opportunities WHERE dedupe_key = ? ORDER BY discovered_at ASC LIMIT 1",
                    (dedupe_key,),
                ).fetchone()
            if existing is not None:
                return self._row_to_opportunity(existing), False

            conn.execute(
                """
                INSERT INTO opportunities (
                    id, source, source_id, source_url, company, title,
                    description, discovered_at, status, location,
                    remote_policy, published_at, required_skills,
                    preferred_skills, compensation, dedupe_key
                ) VALUES (
                    :id, :source, :source_id, :source_url, :company, :title,
                    :description, :discovered_at, :status, :location,
                    :remote_policy, :published_at, :required_skills,
                    :preferred_skills, :compensation, :dedupe_key
                )
                """,
                serialized,
            )
            inserted = conn.execute(
                "SELECT * FROM opportunities WHERE id = ?", (opportunity.id,)
            ).fetchone()

        if inserted is None:
            raise RuntimeError("Inserted opportunity could not be reloaded")
        return self._row_to_opportunity(inserted), True

    def get(self, opportunity_id: str) -> Opportunity | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_opportunity(row)

    def list(self, limit: int = 100) -> list[Opportunity]:
        if limit < 1:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM opportunities ORDER BY discovered_at DESC, id ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_opportunity(row) for row in rows]

    def list_radar_candidates(
        self,
        *,
        now: datetime,
        lookback_days: int,
    ) -> list[Opportunity]:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if lookback_days < 0:
            raise ValueError("lookback_days must be non-negative")

        now_utc = now.astimezone(timezone.utc)
        cutoff = now_utc - timedelta(days=lookback_days)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM opportunities
                WHERE COALESCE(published_at, discovered_at) >= ?
                  AND COALESCE(published_at, discovered_at) <= ?
                ORDER BY COALESCE(published_at, discovered_at) DESC, id ASC
                """,
                (cutoff.isoformat(), now_utc.isoformat()),
            ).fetchall()
        return [self._row_to_opportunity(row) for row in rows]
