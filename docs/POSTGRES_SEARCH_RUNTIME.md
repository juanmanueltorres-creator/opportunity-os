# Opportunity OS PostgreSQL-only search runtime

**Status:** A separate, read-only FastAPI application is implemented in `app/postgres_read_api.py`. It reads directly from the private `opportunity_os` schema already created in the user's GeoPlatform Supabase project. **It does not run SQLite at all.** It is an incremental search runtime, **not a feature-complete replacement** for the main `app/main.py` API.

## Why a separate entrypoint?

The existing `app/main.py` still shares a SQLite file among availability memory, radar enrichments, curation, relationship history, and opportunity storage. Switching a single repository would silently split the data and break consistency. This runtime exposes only already-migrated, inspectable PostgreSQL data without pretending that the older endpoints are ported.

## Setup (server only)

1. Ensure migrations already applied in Supabase: `opportunity_os_private_core_v1`, `opportunity_os_private_history_v1`, `opportunity_os_email_evidence_v1`.
2. Apply `db/opportunity_os_reader.sql` to grant a **NOLOGIN, read-only** group the minimum read permissions and corresponding private-schema RLS policies. Provision a distinct login role and strong password in a private admin context, then grant that group role to it. Do **not** use a browser-exposed key or commit a database password.
3. Install: `pip install '.[postgres]'`.
4. Configure environment secrets `OPPORTUNITY_POSTGRES_DSN` and `OPPORTUNITY_API_TOKEN` (32+ characters). Never put these in `.env` tracked by Git or in a frontend `VITE_` environment variable.
5. Run: `uvicorn app.postgres_read_api:app --host 127.0.0.1 --port 8100`.

For managed hosting, put both secrets in the provider's secret store, add TLS/authentication at ingress, and keep this as a **private service**. The API rejects requests when its token is missing and never silently falls back to SQLite.

Use the appropriate connection mode (direct for a persistent IPv6 backend; session pooler for IPv4) as advised in the official [Supabase connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres). TLS is mandatory in application code. A strong SSL certificate verification setup (`verify-full` and trusted root CA) is preferable for production; the minimal code enforces encryption via `require`.

## Minimal endpoints (Bearer auth required except health)

- `GET /healthz` — **liveness only**; does not prove DB connectivity.
- `GET /api/v1/summary` — counts of source catalog, vacancies, applications, outreach, email evidence.
- `GET /api/v1/sources` — all sources and connector statuses; `NOT_CONFIGURED` means the source has not been scraped.
- `GET /api/v1/opportunities` — filters `keyword`, `source`, `remote_mode`, `argentina_eligible`, `work_language`, `verification_status`, `since`, `exclude_applied`, `limit`, `offset`.
- `GET /api/v1/history/applications` — verified application/send statuses and Gmail evidence links.
- `GET /api/v1/history/outreach` — historical contacted companies, without personal contact email addresses.

Example local request (avoid pasting an actual secret into public logs):

```bash
curl -H "Authorization: Bearer $OPPORTUNITY_API_TOKEN" \
  "http://127.0.0.1:8100/api/v1/opportunities?remote_mode=REMOTE&argentina_eligible=YES&work_language=ES&exclude_applied=true"
```

## Known limitations

- No vacancy collectors have been implemented. The `opportunities` table had **0 rows** at creation. Empty search results must never be described as "no jobs exist."
- The current historical data includes 39 application/send records and 59 Gmail observations at last checked; the new runtime does not poll Gmail or Drive.
- `exclude_applied` does conservative employer+title matching, not full cross-ATS fuzzy matching.
- No web UI and no deploy secrets have been provisioned by this change. The existing SQLite runtime remains unchanged. This must not be advertised as the full SQLite cutover.
- **Do not deploy in place of `app.main:app` while anyone depends on curation, radar, relationships, Gmail adapters, or other unavailable routes.** Implement and test their PostgreSQL repositories before a complete cutover.

## Development checks

CI includes isolated FastAPI tests covering missing token, invalid auth, missing DSN, parameterized query construction, safe output and input limits. The tests mock database reads; live deployment validation requires a private backend identity and real PostgreSQL test connection.

## Next implementation slices

- Export/import any remaining local SQLite records with idempotency and reconciliation (the private `opportunities.db` is not accessible from this session).
- Port availability, enrichments, curation and relationships to PostgreSQL; then cut over all existing endpoints together.
- Implement source collectors and scheduled refreshes.
