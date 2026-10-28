# Opportunity OS — observación de fuentes ATS públicas

**Dos conceptos que no deben confundirse:**
- `LISTED_ON_PUBLIC_ATS`: la vacante figuró en el listado público del ATS
  del empleador durante la captura (Ashby, Lever o Greenhouse).
- `VERIFIED_OPEN`: comprobación independiente de que puede enviarse una
  solicitud en ese momento. **No se infiere ni se emite automáticamente**.

Se usa exclusivamente la respuesta de los conectores oficiales de la misma
ejecución de GitHub Actions; no se hacen sondeos HTTP masivos ni se intenta
descifrar si una empresa ya no acepta solicitudes.

La respuesta debe contener el identificador exacto del anuncio y un enlace
HTTPS del dominio oficial apropiado. Ashby omite explícitamente `isListed=false`.
Greenhouse expone publicaciones del Job Board y Lever su lista pública de
puestos publicados.

El sitio permite filtrar por «Vistas en ATS oficial» y muestra la fecha
exacta de observación, no un sello de vacante «activa». Para agregadores
(Get on Board, Indeed, etc.) se mantiene «Sin comprobación directa».

En Supabase, `opportunity_os.availability_observations` guarda
`observation_type='SEEN'`, `evidence_kind='PUBLIC_ATS_LIST'` y la marca de
tiempo de captura, sin alterar `verification_status` (permanece PENDING)
ni estados de `applications`, `outreach_ledger` o notas privadas.
La importación es idempotente por vacante, fecha y fuente. La función
`refresh_public_radar()` conserva los mismos permisos privados de
invocación de las versiones anteriores.

**Limitaciones:** un anuncio pudo cerrarse inmediatamente después de la
captura, o mantenerse publicado aun cuando no reciba solicitudes; ver el ATS
no confirma residencia admitida, salario ni adecuación del postulante.
La desaparición de un anuncio NO desencadena un cierre automático.
Tampoco se distribuyen claves privadas o credenciales de Gemini.

Referencias oficiales:
- https://developers.ashbyhq.com/docs/public-job-posting-api
- https://docs.greenhouse.io/job-board
- https://github.com/lever/postings-api
