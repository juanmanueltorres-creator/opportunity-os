# PostgreSQL full-API bootstrap (integration branch)

This change consolidates the unmerged PostgreSQL repository work from PRs #86 and #87 and wires it into the original FastAPI application via an **explicit** storage backend selection. It is a staged, opt-in cutover; no change is made to the current production deployment.

## What selecting PostgreSQL does

Set `OPPORTUNITY_STORAGE_BACKEND=postgres` when running `uvicorn app.main:app`.

- The existing `create_app` routes, radar, source refresh, curation, verification queue, and relationship memory receive PostgreSQL repositories rather than SQLite.
- `PostgresOpportunityRepository`, `PostgresAvailabilityRepository`, `PostgresEnrichmentRepository`, `PostgresCurationLedgerRepository`, and `PostgresRelationshipRepository` use the private `opportunity_os` schema.
- Radar receives `PostgresApplicationHistory` to avoid suggesting identical company + role combinations already marked SENT/APPLIED/REPLIED/INTERVIEW/REJECTED.
- New authenticated storage routes from `app.postgres_workflow_api` are mounted below `/storage`; use `/storage/api/v1/history/applications`, `/storage/api/v1/opportunities`, and `/storage/api/v1/source/refresh` for the newer query and write APIs.
- Every route except `/health` requires `Authorization: Bearer <private token>` and rejects missing or too-short tokens. Supabase remains the authoritative persistence; the PostgreSQL startup has **no SQLite fallback**.

**This branch does not remove the SQLite adapter code**; the legacy `OPPORTUNITY_STORAGE_BACKEND=sqlite` option exists for historical tests and controlled rollback. The production env must explicitly select `postgres`.

## Already applied Supabase schema migrations

`opportunity_os_private_core_v1`, `opportunity_os_private_history_v1`, `opportunity_os_email_evidence_v1`, `opportunity_os_private_workflow_api_v1`, `opportunity_os_repository_parity_v1`, `opportunity_os_relationship_curation_parity_v1`.

The database now contains private availability, enrichment, relationship and curation tables alongside migrated applications and outreach. RLS is on, and no app user has been granted a public read role.

## Before deployment

1. Provision separate private PostgreSQL **LOGIN** roles for `opportunity_os_reader` and `opportunity_os_writer` groups. Both groups currently have NOLOGIN; do not grant these roles to `anon` or `authenticated`.
2. Add server-only secrets `OPPORTUNITY_POSTGRES_DSN`, `OPPORTUNITY_POSTGRES_WRITE_DSN`, `OPPORTUNITY_API_TOKEN` (random >=32 chars), and `OPPORTUNITY_STORAGE_BACKEND=postgres`. Never commit or echo credentials.
3. Install `pip install 'psycopg[binary]>=3.2,<4'` as an extra deployment dependency; existing project metadata intentionally remains untouched.
4. Run integration smoke tests with **non-personal test fixtures** under restricted login roles; confirm RLS denial from `anon`/`authenticated`, verify deduplication and rollback.
5. Select a deployment workspace and service explicitly before changing any Render/Vercel configuration.
6. Confirm every legacy operator flow (verification, curation, Gmail/process-email, relationship projection) on PostgreSQL before taking traffic.
7. The operator confirms there are no local SQLite records to import; **do not demand an `opportunities.db` export**.

## Operational caveats

- Offline CI tests validate API wiring and mock database operations, **not** a live PostgreSQL credential, scheduled jobs, or verified job feed.
- The legacy verified availability convenience method in `PostgresAvailabilityRepository` intentionally fails closed unless explicit human verification evidence is provided; this method is not feature-parity with the permissive SQLite method.
- Source registry defaults to `sources.local.yaml`; without a configured registry, the old refresh worker sees no connectors. The separately mounted storage refresh currently supports Remotive only; no continuous scheduler is installed.
- `SQLiteRelationshipMemory` is currently reused with a PostgreSQL repository through its duck-typed interface; the class name is historical, not evidence of a SQLite connection.
- All currently imported historical contacts remain in `outreach_ledger`. They are **not yet projected** into the `relationship_accounts` state machine. The application-history guard only matches normalized company **and** title; it is conservative and does not fully eliminate potential duplicate outreach to a company for a different role.
- Do not claim complete cutover until tested on a real PostgreSQL deployment with all required services and the correct secrets.
