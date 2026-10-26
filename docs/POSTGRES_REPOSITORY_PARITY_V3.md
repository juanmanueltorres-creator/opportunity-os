# PostgreSQL Repository Parity V3

Implements `PostgresOpportunityRepository`, `PostgresAvailabilityRepository`, and `PostgresEnrichmentRepository` in `app/repositories/postgres.py` using `OPPORTUNITY_POSTGRES_WRITE_DSN` and psycopg 3. They do **not** use SQLite.

Database: private `opportunity_os` schema in GeoPlatform Supabase; migration `opportunity_os_repository_parity_v1` has been applied, extending availability observation metadata and storing versioned enrichments.

### Important: do not switch main runtime yet
This slice covers **three** repository contracts only. The legacy app `app.main:app` still depends on SQLite for curation, relationships, process emails, operator bridge and other subsystems. None of these has been migrated in this slice; do not treat `app.repositories.postgres` as feature-complete.

Opportunity insert preserves source identity and normalized company/title/location deduplication, with an advisory transaction lock to prevent simultaneous duplicates. Availability retains verified-status provenance; `record_verification()` intentionally fails closed because the legacy signature lacks `confirmed_by` and cannot satisfy the new SQL evidence contract. Use `record()` with explicit human evidence instead. Existing API verification route already supports this evidence model.

### Next
1. Port curation + relationship repositories and integrate backend selection.
2. Reconcile remaining local SQLite data before cutover.
3. Provision server-only write DSN, deploy, run database integration tests and a real source refresh (not run here).
4. Enable only after the complete suite and data comparison pass.
