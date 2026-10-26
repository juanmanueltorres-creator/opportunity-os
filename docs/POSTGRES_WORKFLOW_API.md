# PostgreSQL workflow API — second slice

The new runtime `app.postgres_workflow_api:app` extends `app.postgres_read_api:app` and never imports or opens SQLite. The old `app.main:app` stays available until all other modules are ported; **do not replace it in production yet**.

## What is ready in code

- Existing read-only endpoints: summary, sources, opportunities with Argentina/remote/Spanish filters, application and outreach history.
- `POST /api/v1/opportunities/manual`: register sourced vacancy. Repeating a source+source_id does not duplicate. Remote is not automatically equivalent to Argentina eligibility. Verification defaults to `PENDING`.
- `POST /api/v1/history/applications`: add a single confirmed outbound/application status; deterministic idempotency by source evidence reference + employer + title, no sending emails.
- `POST /api/v1/opportunities/{opportunity_id}/verify`: explicit human evidence required; verified open/closed observation and status change in one SQL statement/transaction.
- `GET /api/v1/opportunities/{opportunity_id}/observations`: audit trail of verifications.
- `POST /api/v1/source/refresh`: supports only `{"source":"remotive"}`. Fetches via existing official Remotive API connector. Writes up to 250 entries per call, marks all as pending/unverified; never claims an active/open vacancy based on a successful fetch.

## Server-only deployment

1. Install `pip install 'psycopg[binary]>=3.2,<4'`.
2. Configure secrets in the **server**: `OPPORTUNITY_POSTGRES_DSN` (read-only DB user), `OPPORTUNITY_POSTGRES_WRITE_DSN` (separate writer DB user), and a random `OPPORTUNITY_API_TOKEN` (32+ characters). No secrets in frontend, repository, logs, or ChatGPT.
3. Provision DB roles `opportunity_os_reader`, `opportunity_os_writer` (NOLOGIN groups) through the migration applied in Supabase. In a secure SQL/admin context, create two separate LOGIN roles and grant the appropriate groups. Do not grant to `anon` or `authenticated`; do not use `service_role` as general-purpose application identity.
4. Run `uvicorn app.postgres_workflow_api:app --host 127.0.0.1 --port 8100`. Apply TLS and authentication at ingress. Treat this as an internal API.
5. Smoke-test production-read credentials, writer credentials, and queries with a disposable fictional job, then confirm its removal by authorized DB admin. The code tests alone do **not** prove the deployed service works.

### Critical limitations

- There is no scheduled worker yet. Remotive refresh is manual, and live source HTTP availability has not been verified.
- The endpoint writes first 250 fetched Remotive jobs per call; call-count and rate limits must be managed by the deployment; no built-in concurrency lock.
- Canonical cross-platform company/title/location fuzzy deduplication and historical SQLite merge are not yet complete.
- SQLite repositories for availability projections, radar scoring, curation and relationship memory are still in the old application. **No full backend cutover yet.**
- A new schema migration adds availability evidence observations and RLS policies. It was applied to the user's private Supabase project before code was written; the repository does not include a plaintext copy of private user records.
- No background job or email sending occurs.

## Security characteristics

Server-side Bearer token validation is enforced for all data endpoints. PostgreSQL queries are parameterized; failed DB connectivity returns 503 and never falls back to local SQLite. Writer role is restricted to private `opportunity_os` tables and non-destructive inserts/updates; the historical outreach and email evidence tables remain read-only. Database SSL is enforced; for production additionally set up verification of the CA identity.

## Next step

Complete the remaining backend modules (availability projection, enrichment, curation, relationship memory) and run a reconciled import of any local SQLite file before switching the legacy API. For a useful job search immediately, configure and execute the first Remotive refresh once, then grow the collector catalog selectively.
