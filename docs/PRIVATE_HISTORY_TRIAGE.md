# Cruce privado con historial — Opportunity OS

El radar se cruza con las aplicaciones SOLO en Supabase privado.

- `opportunity_os.private_radar_history`: coincidencia por ID, URL exacta o empresa normalizada + título exacto.
- `opportunity_os.private_daily_shortlist`: excluye postulaciones previas del mismo cargo y títulos no afines.
- `opportunity_os.private_daily_top_five`: hasta 5 vacantes, máximo 2 de la misma empresa.
- Contactar a una empresa no equivale a haberse postulado a todos sus cargos.

### Comprobado al 28/10/2026

- 295 oportunidades acumuladas, 49 postulaciones y 152 registros de outreach conservados.
- 1 coincidencia exacta contra aplicaciones existentes; 48 siguen sin vínculo seguro con ofertas del radar.
- 9 ofertas candidatas en la vista privada; 4 en el top cinco. Nunca se rellena el cupo.
- Vistas en esquema privado, SECURITY INVOKER y sin privilegios para PUBLIC, anon o authenticated.

### Limitación crítica

**La UI pública no usa aún el historial privado**. Este cruce solo funciona en consultas SQL autorizadas; para mostrarlo en la web hace falta un backend autenticado individual, no exportar postulaciones a JSON ni poner credenciales en el navegador. Los estados de la tabla privada nunca se distribuyen en radar-public.

Consulta privada autorizada:

```sql
select company,title,source_url,history_state,fit_score
from opportunity_os.private_daily_top_five;
```

El estado LISTED_ON_PUBLIC_ATS no confirma que el aviso esté abierto, ni asegura idioma de trabajo o seniority.