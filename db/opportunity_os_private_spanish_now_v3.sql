-- Español ahora: NO inventar idioma laboral. Nunca usar avisos en inglés
-- ni ofertas explícitamente bilingües/inglés en el top privado actual.
-- Aviso en español con work_language UNKNOWN es SOLO candidato a confirmar.
-- Los otros puestos siguen disponibles en el atlas y tablas privadas.
-- No cambia datos de postulaciones ni expone el esquema privado.
create or replace view opportunity_os.private_daily_top_five
with (security_invoker = true)
as
with ranked as (
  select d.*,
      row_number() over (partition by lower(regexp_replace(d.company,'[^[:alnum:]]','','g'))
        order by d.fit_score desc, d.last_seen_at desc, d.opportunity_id) as company_rank
  from opportunity_os.private_daily_shortlist d
  join opportunity_os.opportunities o on o.id=d.opportunity_id
  where o.work_language='ES'
     or (o.work_language='UNKNOWN' and o.posting_language='ES')
)
select opportunity_id,company,title,source_url,location,remote_mode,
       argentina_eligible,published_at,last_seen_at,fit_score,
       history_state,company_has_outreach_history,company_has_do_not_contact_flag
from ranked
where company_rank <= 2
order by fit_score desc, last_seen_at desc, opportunity_id
limit 5;


comment on view opportunity_os.private_daily_top_five is
 'ESPAÑOL AHORA: work_language=ES OR anuncio ES con trabajo UNKNOWN. NO significa trabajo confirmado en español. Top hasta 5, máximo 2 por empresa y sin aplicaciones previas del mismo cargo.';
revoke all on opportunity_os.private_daily_top_five from public, anon, authenticated;
