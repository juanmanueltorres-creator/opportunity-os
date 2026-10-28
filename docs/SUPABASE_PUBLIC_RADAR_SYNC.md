# Opportunity OS — persistencia diaria del radar público

Estado verificado el 28-10-2026: 241 oportunidades insertadas en
`opportunity_os.opportunities`, sin modificaciones a las 49 postulaciones
ni a los 152 registros de outreach.

## Arquitectura activa

- 09:23 ART (12:23 UTC): GitHub Actions obtiene anuncios y publica JSON
  estrictamente público en rama `radar-public`.
- 09:40 ART (12:40 UTC): Supabase `pg_cron` ejecuta
  `opportunity_os.refresh_public_radar()` como rol propietario PostgreSQL.
- La función usa una única llamada HTTPS de `extensions.http_get` a la URL
  **fija** del snapshot; no recibe URLs ni credenciales de clientes.
- Valida forma, tamaño (máximo 3 MB), conteo (1–500), versión de esquema y
  antigüedad (menos de 48 h). Si falla, la transacción aborta.
- Hace `INSERT ... ON CONFLICT(source,source_id) DO UPDATE` únicamente
  para `last_seen_at` y `updated_at`. Nunca modifica estados privados,
  `verification_status`, aplicaciones, contactos o notas.
- Para el feed actual, `argentina_eligible=YES` y `work_language=ES` pasan a
  `UNKNOWN` porque la exportación pública no conserva las pruebas textuales
  que requieren las restricciones de la base. No se eluden esas restricciones.
- `source_refresh_runs` registra cada snapshot importado. `cron.job_run_details`
  permite observar fallos programados.

## Permisos y limitaciones

- Función `SECURITY INVOKER`, sin permisos de ejecución a `anon`,
  `authenticated` ni `service_role`.
- No se envían tokens de Supabase a GitHub ni se publica historial privado.
- La función es interna: no es una API web pública y no usa Gemini.
- El campo `last_seen_at` prueba presencia en la captura pública, **no**
  verificación manual de que el puesto sigue aceptando aplicaciones.
- El snapshot usa la fecha de publicación disponible y acepta `NULL` si no
  hay evidencia. No inventar fechas ni geocodificar sin respaldo.
- Los anuncios descartados por los filtros del radar antes del exportador no
  se almacenan; esta versión guarda solo las vacantes del atlas público.
- `http` hace petición síncrona y `pg_cron` requiere un job de base de datos.
  No incrementar frecuencia ni exposición de red sin monitorear latencia.

## Operación

Estado:
```sql
select jobid,jobname,schedule,active from cron.job
where jobname='opportunity-os-import-public-radar';
select count(*) from opportunity_os.opportunities;
select run_key,status,fetched_count,created_count,finished_at
from opportunity_os.source_refresh_runs
where source_key='github_public_radar' order by finished_at desc limit 5;
```

Reimportación manual idempotente:
```sql
select opportunity_os.refresh_public_radar();
```

Desactivar automáticamente sin borrar vacantes:
```sql
select cron.unschedule('opportunity-os-import-public-radar');
```

## Qué no se habilitó

- Escritura GitHub Actions→Supabase por contraseña: innecesaria.
  `OPPORTUNITY_POSTGRES_WRITE_DSN` puede seguir sin configurarse.
- Autenticación comunitaria, Gemini ni RLS de usuario final: trabajo posterior.
- Las marcas `Guardé`, `Postulé`, `Descarté` de Vercel permanecen en
  almacenamiento local del navegador; no se sincronizan automáticamente.

## Fuentes técnicas consultadas

- Supabase, *Scheduling Edge Functions*:
  https://supabase.com/docs/guides/functions/schedule-functions
- Supabase, cron:
  https://supabase.com/docs/guides/cron
- Supabase, HTTP Postgres extension:
  https://supabase.com/docs/guides/database/extensions/http
