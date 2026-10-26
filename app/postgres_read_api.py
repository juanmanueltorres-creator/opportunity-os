"""Private, read-only Opportunity OS API backed exclusively by Supabase PostgreSQL.

Deploy this separately from the legacy SQLite API until feature parity is proven.
Requires OPPORTUNITY_POSTGRES_DSN and OPPORTUNITY_API_TOKEN (server-only secrets).
"""
from __future__ import annotations

import hmac
import logging
import os
from datetime import date
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query

log = logging.getLogger(__name__)
app = FastAPI(title="Opportunity OS — PostgreSQL Search", version="0.1.0")


def _authorize(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    token = os.getenv("OPPORTUNITY_API_TOKEN", "")
    if len(token) < 32:
        raise HTTPException(status_code=503, detail="Private API token not configured")
    if not hmac.compare_digest(authorization or "", "Bearer " + token):
        raise HTTPException(status_code=401, detail="Unauthorized")


Auth = Depends(_authorize)


def _select(query: str, params: tuple[object, ...] = ()) -> list[dict]:
    """Execute server-side parameterized SELECT with no secret in output."""
    dsn = os.getenv("OPPORTUNITY_POSTGRES_DSN", "")
    if not dsn:
        raise HTTPException(status_code=503, detail="PostgreSQL not configured")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="PostgreSQL driver not installed") from exc

    try:
        with psycopg.connect(
            dsn, connect_timeout=8, sslmode="require", row_factory=dict_row
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute(query, params)
                return list(cursor.fetchall())
    except Exception as exc:
        log.error("PostgreSQL read error (type=%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="PostgreSQL query unavailable") from exc


@app.get("/healthz")
def healthz() -> dict:
    """Liveness only; never claims a database is connected."""
    return {"status": "ok", "storage": "postgres-only"}


@app.get("/api/v1/summary", dependencies=[Auth])
def summary() -> dict:
    rows = _select(
        """
        SELECT
          (SELECT count(*) FROM opportunity_os.sources) AS sources,
          (SELECT count(*) FROM opportunity_os.opportunities) AS opportunities,
          (SELECT count(*) FROM opportunity_os.applications) AS applications,
          (SELECT count(*) FROM opportunity_os.outreach_ledger) AS outreach_records,
          (SELECT count(*) FROM opportunity_os.email_observations) AS email_observations
        """
    )
    return rows[0] if rows else {}


@app.get("/api/v1/sources", dependencies=[Auth])
def list_sources(
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[dict]:
    return _select(
        """
        SELECT source_key, source_url, category, authority, connector_status,
               last_checked_at, last_error_code
        FROM opportunity_os.sources ORDER BY source_key LIMIT %s
        """,
        (limit,),
    )


@app.get("/api/v1/opportunities", dependencies=[Auth])
def list_opportunities(
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    keyword: Annotated[str | None, Query(max_length=140)] = None,
    source: Annotated[str | None, Query(max_length=100)] = None,
    remote_mode: Literal["REMOTE", "HYBRID", "ONSITE", "UNKNOWN"] | None = None,
    argentina_eligible: Literal["YES", "NO", "UNKNOWN"] | None = None,
    work_language: Literal["ES", "EN", "BILINGUAL", "UNKNOWN"] | None = None,
    verification_status: Literal["VERIFIED", "PENDING", "REJECTED", "STALE"] | None = None,
    since: date | None = None,
    exclude_applied: bool = True,
) -> list[dict]:
    clauses = ["TRUE"]
    params: list[object] = []
    if keyword and keyword.strip():
        clauses.append("(o.title ILIKE %s OR o.company ILIKE %s)")
        params.extend([f"%{keyword.strip()}%", f"%{keyword.strip()}%"])
    for field, value in [
        ("source", source),
        ("remote_mode", remote_mode),
        ("argentina_eligible", argentina_eligible),
        ("work_language", work_language),
        ("verification_status", verification_status),
    ]:
        if value is not None and str(value).strip():
            clauses.append(f"o.{field} = %s")
            params.append(value)
    if since is not None:
        clauses.append("o.discovered_at >= %s")
        params.append(since)
    if exclude_applied:
        # Exclude only a matching employer AND title. A past email to a company
        # must not hide every unrelated vacancy from that employer.
        clauses.append(
            """
            NOT EXISTS (
              SELECT 1 FROM opportunity_os.applications a
              WHERE lower(trim(a.company)) = lower(trim(o.company))
                AND lower(trim(coalesce(a.role_title, ''))) = lower(trim(o.title))
                AND a.status IN ('SENT', 'APPLIED', 'REPLIED', 'INTERVIEW', 'REJECTED')
            )
            """
        )
    params.extend([limit, offset])
    return _select(
        """
        SELECT o.id, o.company, o.title, o.source, o.source_url,
               o.canonical_url, o.location, o.remote_mode, o.argentina_eligible,
               o.work_language, o.verification_status, o.published_at,
               o.discovered_at, o.last_verified_at, o.compensation
        FROM opportunity_os.opportunities o
        WHERE """
        + " AND ".join(clauses)
        + " ORDER BY coalesce(o.published_at, o.discovered_at) DESC, o.id LIMIT %s OFFSET %s",
        tuple(params),
    )


@app.get("/api/v1/history/applications", dependencies=[Auth])
def list_applications(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status: Literal["DRAFT", "SENT", "APPLIED", "REPLIED", "INTERVIEW", "REJECTED", "WITHDRAWN", "UNKNOWN"] | None = None,
) -> list[dict]:
    clause = "WHERE status = %s" if status else ""
    params = (status, limit) if status else (limit,)
    return _select(
        """
        SELECT application_key, company, role_title, channel, status,
               event_at, source_reference
        FROM opportunity_os.applications
        """
        + clause
        + " ORDER BY event_at DESC, application_key LIMIT %s",
        params,
    )


@app.get("/api/v1/history/outreach", dependencies=[Auth])
def list_outreach(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict]:
    # Do not return personal contact email addresses from the private ledger.
    return _select(
        """
        SELECT company_or_project, raw_status, last_activity,
               secondary_do_not_contact
        FROM opportunity_os.outreach_ledger
        ORDER BY last_activity DESC NULLS LAST, source_row
        LIMIT %s
        """,
        (limit,),
    )
