-- Follow-up to history triage v1: remove unrelated finance positions and
-- prepare a private, diversified top-five. No modifications to application
-- or outreach records. No public schema or permissions changes.
create or replace view opportunity_os.private_daily_shortlist
with (security_invoker = true)
as
select
  h.opportunity_id, h.company, h.title, h.source_url,
  h.location, h.remote_mode, h.argentina_eligible,
  h.published_at, h.last_seen_at, h.verification_status,
  h.history_state, h.application_match_method,
  h.company_has_outreach_history, h.company_has_do_not_contact_flag,
  (
    case
      when lower(h.title) ~ '(gis|geospatial|geoespacial|geolog|geotec|mining|miner|postgis|qgis|arcgis|geomatic|geodata|cartograf|teledetec|topograf|hidrogeol|hydrogeol)' then 80
      when lower(h.title) ~ '(python|backend|back.end|data developer|technical support|soporte t[eé]cnico|support engineer|application support)' then 55
      else 25 end
    + case when lower(h.title) ~ '(^|[^a-z])(junior|jr[.]?|trainee|entry.level|intern|pasante|practicante)([^a-z]|$)' then 60 else 0 end
    + case when h.argentina_eligible = 'YES' then 48 else 0 end
    + case when h.published_at between now() - interval '14 days' and now() then 12 else 0 end
    + case when h.work_language='ES' then 10 else 0 end
    + case when h.company_has_outreach_history then 4 else 0 end
  )::integer as fit_score
from opportunity_os.private_radar_history h
where h.last_seen_at >= now() - interval '3 days'
  and h.history_state = 'NO_ROLE_MATCH'
  and h.argentina_eligible <> 'NO'
  and h.verification_status not in ('REJECTED','STALE')
  and h.source_url like 'https://%'
  and lower(h.title) !~ '(talent pool|talent community|talent network|general application|open application|evergreen)'
  and lower(h.title) !~ '(^|[^a-z])(senior|sr[.]?|semi.?senior|ssr[.]?|staff|principal|lead|head of|manager|director|architect|jefe|gerente)([^a-z]|$)'
  and lower(h.title) !~ '(liferay|snowflake|salesforce|sap abap|magento|servicenow|netsuite|cobol|mainframe)'
  -- Generic data roles in accounting/sales are not automatically GIS/Python fits.
  and lower(h.title) !~ '(billing|refunds|financial|finance|accounting|bookkeeping|payroll|invoic|sales development)'
  and (
    lower(h.title) ~ '(gis|geospatial|geoespacial|geolog|geotec|mining|miner|postgis|qgis|arcgis|geomatic|geodata|cartograf|teledetec|topograf|hidrogeol|hydrogeol|python|backend|back.end|data developer|technical support|soporte t[eé]cnico|support engineer|application support)'
    or (
      h.argentina_eligible = 'YES'
      and lower(h.title) ~ '(data engineer|data analyst|software engineer|software developer|full.stack|frontend|desarrollador|developer|programador)'
    )
  )
  and (
    h.argentina_eligible = 'YES'
    or (
      h.argentina_eligible = 'UNKNOWN'
      and h.remote_mode = 'REMOTE'
      and lower(h.title) ~ '(^|[^a-z])(junior|jr[.]?|trainee|entry.level|intern|pasante|practicante)([^a-z]|$)'
    )
  );


comment on view opportunity_os.private_daily_shortlist is
  'PRIVATE conservative candidates; excludes prior role applications and obvious finance/sales stacks.';

create or replace view opportunity_os.private_daily_top_five
with (security_invoker = true)
as
with ranked as (
  select d.*,
      row_number() over (partition by lower(regexp_replace(d.company,'[^[:alnum:]]','','g'))
        order by d.fit_score desc, d.last_seen_at desc, d.opportunity_id) as company_rank
  from opportunity_os.private_daily_shortlist d
)
select opportunity_id,company,title,source_url,location,remote_mode,
       argentina_eligible,published_at,last_seen_at,fit_score,
       history_state,company_has_outreach_history,company_has_do_not_contact_flag
from ranked
where company_rank <= 2
order by fit_score desc, last_seen_at desc, opportunity_id
limit 5;

comment on view opportunity_os.private_daily_top_five is
  'PRIVATE recommended research queue, not a live bookable/appliable vacancy guarantee. Company capped at 2; history links stay private.';

revoke all on opportunity_os.private_daily_shortlist from public, anon, authenticated;
revoke all on opportunity_os.private_daily_top_five from public, anon, authenticated;
