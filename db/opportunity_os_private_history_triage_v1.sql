-- Opportunity OS: privately reconcile captured listings with application history.
-- SAFE: views only; no inserts, updates or deletes of application/contact data.
-- SECURITY: invoker views in private opportunity_os schema, no anonymous grants.
--
-- High-confidence: same opportunity ID or exact source/canonical URL.
-- Conservative legacy: normalized company AND exact role title.
-- Company-only contacts are informational: never suppress a different role.

create or replace view opportunity_os.private_radar_history
with (security_invoker = true)
as
select
  o.id as opportunity_id,
  o.company,
  o.title,
  o.source_url,
  o.source,
  o.location,
  o.remote_mode,
  o.argentina_eligible,
  o.eligibility_evidence,
  o.work_language,
  o.published_at,
  o.last_seen_at,
  o.verification_status,
  a_match.status as previous_application_status,
  a_match.event_at as previous_application_at,
  a_match.match_method as application_match_method,
  case
    when a_match.match_method is not null
      and a_match.status in ('SENT','APPLIED','REPLIED','INTERVIEW','REJECTED','WITHDRAWN')
      then 'PRIOR_APPLICATION'
    when a_match.match_method is not null and a_match.status = 'DRAFT'
      then 'DRAFT_EXISTS'
    when a_match.match_method is not null then 'CHECK_HISTORY'
    when exists (
      select 1 from opportunity_os.email_observations e
      where length(regexp_replace(lower(coalesce(e.company,'')), '[^[:alnum:]]', '', 'g')) >= 3
        and regexp_replace(lower(coalesce(e.company,'')), '[^[:alnum:]]', '', 'g')
          = regexp_replace(lower(coalesce(o.company,'')), '[^[:alnum:]]', '', 'g')
        and length(regexp_replace(lower(coalesce(e.role_title,'')), '[^[:alnum:]]', '', 'g')) >= 5
        and regexp_replace(lower(coalesce(e.role_title,'')), '[^[:alnum:]]', '', 'g')
          = regexp_replace(lower(coalesce(o.title,'')), '[^[:alnum:]]', '', 'g')
    ) then 'EMAIL_ROLE_SIGNAL_REVIEW'
    else 'NO_ROLE_MATCH'
  end as history_state,
  exists (
    select 1 from opportunity_os.outreach_ledger l
    where length(regexp_replace(lower(coalesce(l.company_or_project,'')), '[^[:alnum:]]', '', 'g')) >= 4
      and regexp_replace(lower(coalesce(l.company_or_project,'')), '[^[:alnum:]]', '', 'g')
        = regexp_replace(lower(coalesce(o.company,'')), '[^[:alnum:]]', '', 'g')
  ) as company_has_outreach_history,
  exists (
    select 1 from opportunity_os.outreach_ledger l
    where l.secondary_do_not_contact is true
      and length(regexp_replace(lower(coalesce(l.company_or_project,'')), '[^[:alnum:]]', '', 'g')) >= 4
      and regexp_replace(lower(coalesce(l.company_or_project,'')), '[^[:alnum:]]', '', 'g')
        = regexp_replace(lower(coalesce(o.company,'')), '[^[:alnum:]]', '', 'g')
  ) as company_has_do_not_contact_flag
from opportunity_os.opportunities o
left join lateral (
  select a.status, a.event_at,
    case
      when a.opportunity_id = o.id then 'OPPORTUNITY_ID'
      when a.source_reference like 'https://%'
        and a.source_reference in (o.source_url, o.canonical_url) then 'EXACT_SOURCE_URL'
      else 'EXACT_COMPANY_AND_TITLE'
    end as match_method
  from opportunity_os.applications a
  where a.opportunity_id = o.id
    or (a.source_reference like 'https://%' and a.source_reference in (o.source_url, o.canonical_url))
    or (
      length(regexp_replace(lower(coalesce(a.company,'')), '[^[:alnum:]]', '', 'g')) >= 4
      and regexp_replace(lower(coalesce(a.company,'')), '[^[:alnum:]]', '', 'g')
        = regexp_replace(lower(coalesce(o.company,'')), '[^[:alnum:]]', '', 'g')
      and length(regexp_replace(lower(coalesce(a.role_title,'')), '[^[:alnum:]]', '', 'g')) >= 5
      and regexp_replace(lower(coalesce(a.role_title,'')), '[^[:alnum:]]', '', 'g')
        = regexp_replace(lower(coalesce(o.title,'')), '[^[:alnum:]]', '', 'g')
    )
  order by
    case when a.opportunity_id = o.id then 1
      when a.source_reference like 'https://%'
         and a.source_reference in (o.source_url, o.canonical_url) then 2
      else 3 end,
    a.event_at desc nulls last, a.application_key
  limit 1
) a_match on true;

comment on view opportunity_os.private_radar_history is
  'PRIVATE owner-only read model. Role-level application signals, not proof of listing freshness or a public status API.';

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
  'PRIVATE daily candidate pool excluding matched applications. Query ORDER BY fit_score DESC LIMIT N. Not a public endpoint or guarantee of an active vacancy.';

revoke all on opportunity_os.private_radar_history from public, anon, authenticated;
revoke all on opportunity_os.private_daily_shortlist from public, anon, authenticated;
