"""Optional persistence of public job matches to the private Supabase schema.

Requires a least-privilege Postgres writer credential provided via GitHub Actions
secret. Never publishes private CRM or credentials to GitHub artifacts.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any

from app.radar.daily_search import JobMatch


def persist(matches: list[JobMatch]) -> dict[str, Any]:
    dsn = os.getenv("OPPORTUNITY_POSTGRES_WRITE_DSN", "")
    if not dsn:
        return {"status": "NOT_CONFIGURED", "created": 0, "existing": 0,
                "history_checked": False}
    import psycopg
    from psycopg.rows import dict_row

    created = 0
    existing = 0
    skipped_applied = 0
    excluded_applied_ids: list[str] = []
    with psycopg.connect(dsn, connect_timeout=10, sslmode="require",
                         row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            for item in matches:
                job = item.job
                cursor.execute(
                    """
                    select exists (
                      select 1 from opportunity_os.applications a
                      where lower(btrim(a.company))=lower(btrim(%s))
                        and lower(btrim(coalesce(a.role_title,'')))=lower(btrim(%s))
                        and a.status=any(%s)
                    ) as applied
                    """,
                    (job.company, job.title, ["SENT", "APPLIED", "REPLIED",
                                              "INTERVIEW", "REJECTED"]),
                )
                if cursor.fetchone()["applied"]:
                    skipped_applied += 1
                    excluded_applied_ids.append(job.id)
                    continue
                cursor.execute(
                    """
                    insert into opportunity_os.opportunities (
                      id,source,source_id,source_url,company,title,description,
                      location,remote_policy,remote_mode,argentina_eligible,
                      eligibility_evidence,work_language,language_evidence,
                      discovered_at,published_at,last_seen_at,verification_status,
                      status,required_skills,preferred_skills,compensation
                    ) values(
                      %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                      %s,%s,%s,'PENDING','found',%s,%s,%s
                    )
                    on conflict (source,source_id) do update
                       set last_seen_at=excluded.last_seen_at,
                           updated_at=now()
                    returning (xmax=0) as created
                    """,
                    (
                        job.id, job.source, job.source_id, job.source_url,
                        job.company, job.title, job.description[:20000],
                        job.location, job.remote_policy, item.remote_mode,
                        item.argentina_eligible, item.eligibility_evidence,
                        item.work_language, item.language_evidence,
                        job.discovered_at, job.published_at,
                        datetime.now(timezone.utc), job.required_skills,
                        job.preferred_skills, job.compensation
                    ),
                )
                result = cursor.fetchone()
                if result and result["created"]:
                    created += 1
                else:
                    existing += 1
        conn.commit()
    return {"status": "OK", "created": created, "existing": existing,
            "skipped_applied": skipped_applied, "history_checked": True,
            "_excluded_ids": excluded_applied_ids}
