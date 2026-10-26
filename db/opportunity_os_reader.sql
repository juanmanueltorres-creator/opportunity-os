-- Optional private reader role for the PostgreSQL-only read API.
-- No LOGIN is created here: provision a secret-bearing login via an approved secret manager.
-- The schema is not exposed to Supabase Data API.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'opportunity_os_reader') THEN
    CREATE ROLE opportunity_os_reader NOLOGIN;
  END IF;
END $$;

GRANT USAGE ON SCHEMA opportunity_os TO opportunity_os_reader;
GRANT SELECT ON opportunity_os.sources,
                opportunity_os.opportunities,
                opportunity_os.applications,
                opportunity_os.outreach_ledger,
                opportunity_os.email_observations
TO opportunity_os_reader;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'sources', 'opportunities', 'applications', 'outreach_ledger',
    'email_observations'
  ] LOOP
    IF NOT EXISTS (
       SELECT 1 FROM pg_policies
       WHERE schemaname='opportunity_os' AND tablename=t
         AND policyname='opportunity_os_reader_select'
    ) THEN
      EXECUTE format(
        'CREATE POLICY opportunity_os_reader_select ON opportunity_os.%I FOR SELECT TO opportunity_os_reader USING (true)',
        t
      );
    END IF;
  END LOOP;
END $$;

-- NEVER grant this role to anon or authenticated.
-- A separate LOGIN role with a strong credential must be created in private admin
-- provisioning, then GRANT opportunity_os_reader TO <private_login_role>.
