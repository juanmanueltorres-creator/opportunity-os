-- Opportunity OS v3: record positive published ATS presence evidence.
-- Opportunity OS v2: retain source-derived provenance during private sync.
-- Opportunity OS: pull the already-public, sanitized GitHub snapshot into the
-- private opportunity_os schema. No GitHub/Supabase API key is transmitted.
-- The source URL is a fixed literal; callers cannot supply arbitrary hosts.
-- Never alters applications, contacts, outreach or manually reviewed statuses.

create extension if not exists http with schema extensions;

create or replace function opportunity_os.refresh_public_radar()
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, opportunity_os, extensions
as $function$
declare
  response extensions.http_response;
  payload jsonb;
  snapshot_time timestamptz;
  batch_count integer;
  changed_count integer;
  created_count integer;
begin
  -- One bounded HTTP request to the exact source emitted by our scheduled
  -- GitHub Actions workflow. This is not an arbitrary URL proxy.
  select * into response
  from extensions.http_get(
    'https://raw.githubusercontent.com/juanmanueltorres-creator/opportunity-os/radar-public/jobs.json'
  );

  if response.status is distinct from 200 then
    raise exception 'Opportunity OS snapshot HTTP status %', response.status;
  end if;
  if response.content is null or octet_length(response.content) > 3000000 then
    raise exception 'Opportunity OS snapshot missing or too large';
  end if;
  payload := response.content::jsonb;
  if jsonb_typeof(payload) <> 'object'
     or jsonb_typeof(payload->'atlas') <> 'array'
     or payload->>'schema_version' <> '1' then
    raise exception 'Opportunity OS snapshot schema not recognized';
  end if;
  batch_count := jsonb_array_length(payload->'atlas');
  if batch_count < 1 or batch_count > 500 then
    raise exception 'Opportunity OS snapshot unexpected count: %', batch_count;
  end if;
  snapshot_time := (payload->>'generated_at')::timestamptz;
  -- An old snapshot must never be reported as a fresh import.
  if snapshot_time is null
     or snapshot_time < now() - interval '2 days'
     or snapshot_time > now() + interval '10 minutes' then
    raise exception 'Opportunity OS snapshot timestamp is outside freshness limits';
  end if;

  with source_rows as (
    select value as j
    from jsonb_array_elements(payload->'atlas')
  ), valid_rows as (
    select
      j->>'id' as id,
      j->>'source' as source,
      substring(j->>'id' from length(j->>'source') + 2) as source_id,
      j->>'source_url' as source_url,
      j->>'company' as company,
      j->>'title' as title,
      nullif(j->>'location','') as location,
      case when j->>'remote_mode' in ('REMOTE','HYBRID','ONSITE','UNKNOWN')
           then j->>'remote_mode' else 'UNKNOWN' end as remote_mode,
      case
        when j->>'argentina_eligible' = 'YES'
         and coalesce(j->>'eligibility_evidence','') ~
           '^(Ubicación declarada: |Cobertura geográfica declarada en el título: )'
        then 'YES'
        when j->>'argentina_eligible' = 'NO' then 'NO'
        else 'UNKNOWN'
      end as argentina_eligible,
      case
        when j->>'argentina_eligible' in ('YES','NO')
         and coalesce(j->>'eligibility_evidence','') ~
           '^(Ubicación declarada: |Cobertura geográfica declarada en el título: |Restricción geográfica explícita: )'
        then left(j->>'eligibility_evidence',350)
        else null
      end as eligibility_evidence,
      case
        when j->>'work_language' = 'ES'
         and j->>'language_evidence' = 'Requisito explícito en la descripción'
        then 'ES'
        when j->>'work_language' in ('EN','BILINGUAL')
        then j->>'work_language'
        else 'UNKNOWN'
      end as work_language,
      case
        when j->>'language_evidence' in (
          'Requisito explícito en la descripción',
          'Inglés avanzado exigido explícitamente'
        ) then j->>'language_evidence'
        else null
      end as language_evidence,
      -- These are still heuristic signals, not manually VERIFIED postings.
      case when j->>'listing_language' in ('ES','EN')
           then j->>'listing_language'
           when j->>'listing_language' = 'MIXED' then 'OTHER'
           else 'UNKNOWN' end as posting_language,
      nullif(j->>'published_at','')::timestamptz as published_at
    from source_rows
    where jsonb_typeof(j) = 'object'
      and j->>'source' in ('getonboard','lever','ashby','greenhouse',
                          'remoteok','jobicy','remotive','himalayas','arbeitnow')
      and j->>'id' like (j->>'source') || ':%'
      and length(j->>'id') between 5 and 255
      and length(j->>'title') between 3 and 300
      and length(j->>'company') between 1 and 200
      and length(j->>'source_url') between 15 and 2048
      and j->>'source_url' ~ '^https://[a-zA-Z0-9][a-zA-Z0-9.-]+(/|$)'
  ), inserted_rows as (
    insert into opportunity_os.opportunities (
      id,source,source_id,source_url,company,title,location,
      remote_policy,remote_mode,argentina_eligible,eligibility_evidence,
      work_language,language_evidence,
      posting_language,discovered_at,published_at,last_seen_at,
      verification_status,status
    )
    select
      id,source,source_id,source_url,company,title,location,
      lower(remote_mode),remote_mode,argentina_eligible,eligibility_evidence,
      work_language,language_evidence,
      posting_language,snapshot_time,published_at,now(),
      'PENDING','found'
    from valid_rows
    on conflict (source,source_id) do update
      set last_seen_at = excluded.last_seen_at,
          updated_at = now(),
          -- Backfill only UNKNOWN fields, never replace manual observations,
          -- and only if the source evidence satisfies strict DB constraints.
          argentina_eligible = case
            when opportunity_os.opportunities.verification_status = 'PENDING'
             and opportunity_os.opportunities.argentina_eligible = 'UNKNOWN'
             and excluded.argentina_eligible = 'YES'
             and nullif(btrim(excluded.eligibility_evidence),'') is not null
            then 'YES'
            else opportunity_os.opportunities.argentina_eligible
          end,
          eligibility_evidence = case
            when opportunity_os.opportunities.verification_status = 'PENDING'
             and opportunity_os.opportunities.argentina_eligible = 'UNKNOWN'
             and excluded.argentina_eligible = 'YES'
             and nullif(btrim(excluded.eligibility_evidence),'') is not null
            then excluded.eligibility_evidence
            else opportunity_os.opportunities.eligibility_evidence
          end,
          work_language = case
            when opportunity_os.opportunities.verification_status = 'PENDING'
             and opportunity_os.opportunities.work_language = 'UNKNOWN'
             and excluded.work_language = 'ES'
             and excluded.language_evidence = 'Requisito explícito en la descripción'
            then 'ES'
            else opportunity_os.opportunities.work_language
          end,
          language_evidence = case
            when opportunity_os.opportunities.verification_status = 'PENDING'
             and opportunity_os.opportunities.work_language = 'UNKNOWN'
             and excluded.work_language = 'ES'
             and excluded.language_evidence = 'Requisito explícito en la descripción'
            then excluded.language_evidence
            else opportunity_os.opportunities.language_evidence
          end
    returning (xmax = 0) as was_inserted
  )
  select count(*)::integer,
         (count(*) filter (where was_inserted))::integer
  into changed_count,created_count
  from inserted_rows;

  if changed_count < 1 then
    raise exception 'Opportunity OS snapshot contains no valid records';
  end if;

  -- Evidence of *presence in the company's public ATS listing* only.
  -- This is intentionally SEEN, not VERIFIED_OPEN: the upstream API listing
  -- does not guarantee an employer will still accept an application.
  -- Same captured job is recorded at most once even when cron retries.
  insert into opportunity_os.availability_observations (
    opportunity_id, observation_type, observed_at, evidence_source,
    source_url, note, evidence_kind
  )
  select
    j->>'id',
    'SEEN',
    (j->>'source_checked_at')::timestamptz,
    'OFFICIAL_ATS_PUBLIC_BOARD',
    j->>'source_url',
    'Publicada en el listado oficial del ATS al momento de la captura; no confirma recepción de postulaciones.',
    'PUBLIC_ATS_LIST'
  from jsonb_array_elements(payload->'atlas') as j
  where j->>'source_check' = 'LISTED_ON_PUBLIC_ATS'
    and j->>'source' in ('ashby','greenhouse','lever')
    and nullif(j->>'source_checked_at','') is not null
    and (j->>'source_checked_at')::timestamptz between snapshot_time
                                                     and snapshot_time + interval '15 minutes'
    and (
      (j->>'source' = 'ashby'
        and j->>'source_url' ~ '^https://jobs\\.ashbyhq\\.com/[^/]+/[^/?#]+')
      or (j->>'source' = 'lever'
        and j->>'source_url' ~ '^https://jobs\\.lever\\.co/[^/]+/[^/?#]+')
      or (j->>'source' = 'greenhouse'
        and j->>'source_url' ~ '^https://(boards|job-boards)\\.greenhouse\\.io/[^/]+/jobs/[^/?#]+')
    )
    and exists (
      select 1 from opportunity_os.opportunities o
      where o.id = j->>'id'
        and o.source = j->>'source'
        and o.source_url = j->>'source_url'
    )
    and not exists (
      select 1 from opportunity_os.availability_observations a
      where a.opportunity_id = j->>'id'
        and a.observation_type = 'SEEN'
        and a.evidence_source = 'OFFICIAL_ATS_PUBLIC_BOARD'
        and a.observed_at = (j->>'source_checked_at')::timestamptz
    );

  insert into opportunity_os.source_refresh_runs (
    run_key,source_key,started_at,finished_at,status,
    fetched_count,created_count
  )
  values (
    'github-public:' || (payload->>'generated_at'),
    'github_public_radar',
    now(),now(),'OK',changed_count,created_count
  )
  on conflict (run_key) do update
    set finished_at=now(),
        status='OK',
        fetched_count=excluded.fetched_count,
        created_count=excluded.created_count;

  return jsonb_build_object(
    'status','OK',
    'snapshot_at',snapshot_time,
    'fetched',batch_count,
    'persisted',changed_count,
    'created',created_count,
    'existing',changed_count - created_count
  );
end;
$function$;

-- Private operator-only. Do not give EXECUTE to anon, authenticated, or
-- service_role: a user JWT must not be able to trigger network/database writes.
revoke all on function opportunity_os.refresh_public_radar()
from public, anon, authenticated, service_role;
grant execute on function opportunity_os.refresh_public_radar()
to postgres;
