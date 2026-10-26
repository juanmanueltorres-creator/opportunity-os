# Opportunity OS — radar diario en GitHub Actions

## Objetivo
Buscar **cada día a las 09:23 (Argentina)** puestos relacionados con software/IA/datos, SIG/geociencias/minería, gestión/operaciones y diseño web, sin pagar otro servidor ni tocar GeoPlatform.

El flujo `.github/workflows/daily-opportunity-radar.yml` usa Python 3.12 y `scripts/daily_job_radar.py`. Tiene disparador programado y manual, y sube un artefacto por ejecución: `daily-opportunity-radar`, con `jobs.json` + `jobs.md`.

### Fuentes implementadas (no son 42 scrapers)
- Remotive: API oficial, listado remoto retrasado ~24 horas. [Documentación](https://remotive.com/remote-jobs/api). Limitar a una consulta diaria y enlazar siempre a Remotive como fuente.
- Get on Board: endpoint público JSON:API por categorías `programming`, `operations-management`, `machine-learning-ai` (hasta dos páginas por categoría). El parser exige URL HTTPS real del portal y datos mínimos, de lo contrario descarta el registro. El acceso HTTP y los atributos JSON:API deben validarse en una ejecución real. Si la fuente falla se registra en el informe y el resto sigue.

Se añadieron cuatro fuentes públicas más con conectores reales: **Jobicy** (JSON API remoto, últimos 7 días), **Himalayas** (JSON API remoto con restricciones por país y vencimiento), **Remote OK** (feed JSON con atribución y aviso legal) y **Arbeitnow** (listado JSON, principalmente Europa/remoto). El procesamiento es conservador: cada fuente puede fallar sin romper las otras y una vacante siempre conserva su URL original. Remotive y Get on Board continúan activos. Total: **6 proveedores conectados en código**, **42 fuentes catalogadas**; las otras 36 son referencias sin recolector activo. Las fuentes están sujetas a sus políticas oficiales y la ejecución debe validarse con resultados reales. No inventar empleos ni cambiar el estado de una fuente sin consulta real.


### Nuevas fuentes: endpoints y límites

| Fuente | API pública | Extracción diaria | Condiciones |
| --- | --- | --- | --- |
| Jobicy | `https://jobicy.com/api/v2/remote-jobs` | 100 registros recientes | Link al aviso original, respetar atribución y no consultar con frecuencia excesiva |
| Himalayas | `https://himalayas.app/jobs/api` | Hasta 3 páginas x 20 vacantes | Conservar literalmente `applicationLink`, acreditar a Himalayas, respetar vencimientos y límites |
| Remote OK | `https://remoteok.com/api` | Una consulta | Enlace obligatorio a la publicación en Remote OK y atribución |
| Arbeitnow | `https://www.arbeitnow.com/api/job-board-api` | Una consulta | Enlace al anuncio y a Arbeitnow; descartar roles presenciales fuera de Argentina |

Documentación original:
- https://jobicy.com/jobs-rss-feed
- https://himalayas.app/docs/remote-jobs-api
- https://remoteok.com/faq
- https://www.arbeitnow.com/terms

**Límite operativo:** sumar fuentes no significa mejorar la cantidad de vacantes elegibles. Muchos resultados remotos son EE. UU./Europa o exigen inglés. Se priorizan Argentina/LATAM y roles acordes a los perfiles; la elegibilidad no verificada permanece `UNKNOWN`.

### Ranking de puestos
- **Búsqueda por títulos:** software/datos/IA, GIS/minería, gestión/compras/operaciones, diseño interactivo, gastronomía/abastecimiento.
- Prioridad Argentina/LATAM y Córdoba/San Juan (no inferir permiso laboral de una vacante solo por ser remota).
- Inglés laboral **UNKNOWN** salvo requisito expreso; si el inglés avanzado es explícitamente excluyente se reduce la prioridad.
- Senior muy avanzado baja puntaje; junior/semisenior sube.
- Solo publicaciones de los últimos 30 días cuando existe fecha verificable; si no se conoce la fecha, queda como desconocida, nunca “publicada hoy”.
- Cada resultado trae fuente original, puntuación, evidencia de ubicación, idioma laboral y etiqueta `cv_track_sugerido`. **CV PDF no generado automáticamente.**

### Relación con CV
El repositorio ya contiene `CVPreparationService`, ATS QA, render y soporte de hechos verificados. El radar solo elige la **familia del CV**:
- `desarrollo_software_ia` — software, frontend/backend, datos e IA
- `gis_geociencias` — GIS, geología y minería
- `management_ia` — gestión, operaciones, compras, coordinación y algunos trabajos de ingresos inmediatos

Generar un PDF personalizado real requiere `master_facts`, catálogo de evidencias verificadas y la versión del CV aprobada. **No guardar archivos de CV ni datos personales en el repositorio público ni el artefacto de Actions.** La adaptación final debe ser revisada por el candidato y no enviar correos ni aplicar por sí sola.

### Primera fase: funciona sin secretos
GitHub Actions puede ejecutar las consultas y guardar un resumen **solo de ofertas públicas** en el artefacto de cada ejecución sin acceso a datos personales. Consultar los artefactos desde GitHub o mediante el conector de GitHub de ChatGPT.

El informe indica `Persistencia Supabase: NOT_CONFIGURED`, y `historial_postulaciones_cruzado=false`: los resultados todavía **no están sincronizados en PostgreSQL** y **no se puede prometer la exclusión automática de postulaciones** hasta configurar el siguiente paso.

### Segunda fase: sincronización segura con Supabase
Crear **una sola vez** un rol PostgreSQL LOGIN de permisos mínimos concedidos a `opportunity_os_writer` (rol existente NOLOGIN y RLS). Utilizar Session Pooler (IPv4) o conexión directa según soporte de red; TLS requerido.

Agregar el secreto al repositorio:
**GitHub → Settings → Secrets and variables → Actions → New repository secret → `OPPORTUNITY_POSTGRES_WRITE_DSN`.**

No publicar el valor en issues, PRs, conversaciones ni logs. No usar credenciales admin `postgres` para una rutina de scraping. El conector actual de GitHub no expone una acción para escribir secretos, por lo que el paso requiere una configuración autorizada de la cuenta.

Con el secreto, el job:
1. Cruza `opportunity_os.applications` por empresa y puesto (SENT/APPLIED/REPLIED/INTERVIEW/REJECTED).
2. Excluye coincidencias del artefacto y de las inserciones.
3. Inserta idempotentemente hasta 35 vacantes públicas preseleccionadas en `opportunity_os.opportunities`. No toca tablas geoespaciales.
4. Mantiene estado `PENDING` para verificar la apertura real antes de enviar una postulación.

**Advertencia:** la deduplicación exacta no es búsqueda semántica. Las 152 entidades del historial de outreach no equivalen todas a postulaciones; evitar bloquear empresas por el solo hecho de figurar en ese listado.

### Operación
- La programación de Actions opera en la rama por defecto: el PR debe fusionarse a `main` para que las búsquedas sean diarias.
- Los artefactos se conservan 14 días y solo contienen datos públicos.
- En repositorios públicos GitHub puede desactivar el schedule tras 60 días de inactividad; la programación puede retrasarse y requiere comprobación de cada ejecución.
- Si Get on Board cambia sus campos o limita la API, el radar lo marcará en el reporte; no asumir éxito sin jobs parseados.
- **Sin acceso a secretos** no hay sincronización automática en Supabase, pero puede consultarse el artefacto desde ChatGPT y revisar las vacantes con las tablas ya accesibles mediante Supabase.
- Ninguna parte envía postulaciones ni correos de forma automática.

### Comprobación
Ejecutar `python -m pytest tests/test_daily_job_radar.py`; correr desde GitHub Actions con `workflow_dispatch` para comprobar solicitudes reales y reportes. Usar el artefacto antes de considerar listo el sistema; las pruebas unitarias son simuladas.
