"""Radar application history backed by the migrated Supabase application ledger.

A company name alone is insufficient to mark an unrelated role as applied.
"""
from __future__ import annotations

from datetime import datetime

from app.models.domain import Opportunity
from app.repositories.postgres import _connect


class PostgresApplicationHistory:
    _QUALIFYING = ("SENT", "APPLIED", "REPLIED", "INTERVIEW", "REJECTED")

    def was_applied(self, opportunity: Opportunity) -> bool:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM opportunity_os.applications a
                    WHERE lower(btrim(a.company)) = lower(btrim(%s))
                      AND lower(btrim(coalesce(a.role_title, ''))) = lower(btrim(%s))
                      AND a.status = ANY(%s)
                ) AS applied
                """,
                (opportunity.company, opportunity.title, list(self._QUALIFYING)),
            )
            row = cur.fetchone()
        return bool(row and row["applied"])

    def last_company_role_contact_at(
        self,
        company: str,
        title: str,
    ) -> datetime | None:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT max(a.event_at) AS contacted_at
                FROM opportunity_os.applications a
                WHERE lower(btrim(a.company)) = lower(btrim(%s))
                  AND lower(btrim(coalesce(a.role_title, ''))) = lower(btrim(%s))
                  AND a.status = ANY(%s)
                """,
                (company, title, list(self._QUALIFYING)),
            )
            row = cur.fetchone()
        return row["contacted_at"] if row else None
