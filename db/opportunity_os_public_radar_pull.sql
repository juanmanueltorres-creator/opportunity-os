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
      case when j->>'argentina_eligible' in ('YES','NO','UNKNOWN')
           then j->>'argentina_eligible' else 'UNKNOWN' end as argentina_eligible,
      case when j->>'work_language' in ('ES','EN','BILINGUAL','UNKNOWN')
           then j->>'work_language' else 'UNKNOWN' end as work_language,
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
      remote_policy,remote_mode,argentina_eligible,work_language,
      posting_language,discovered_at,published_at,last_seen_at,
      verification_status,status
    )
    select
      id,source,source_id,source_url,company,title,location,
      lower(remote_mode),remote_mode,argentina_eligible,work_language,
      posting_language,snapshot_time,published_at,now(),
      'PENDING','found'
    from valid_rows
    on conflict (source,source_id) do update
      set last_seen_at = excluded.last_seen_at,
          updated_at = now()
    returning (xmax = 0) as was_inserted
  )
  select count(*)::integer,
         (count(*) filter (where was_inserted))::integer
  into changed_count,created_count
  from inserted_rows;

  if changed_count < 1 then
    raise exception 'Opportunity OS snapshot contains no valid records';
  end if;

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
