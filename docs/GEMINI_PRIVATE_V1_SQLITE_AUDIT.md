# Gemini privado y auditoría SQLite — Opportunity OS

## SQLite: decisión informada

**No borrar SQLite todavía.** El sitio estático de Vercel y la importación GitHub → Supabase NO lo usan. Sin embargo, el backend local sí:

- app/main.py:create_app crea SQLiteOpportunityRepository por defecto.
- La disponibilidad, la curación y las relaciones usan SQLiteAvailabilityRepository, SQLiteCurationLedgerRepository y SQLiteRelationshipRepository.
- app/main.py también admite SQLiteRelationshipMemory y SQLiteEnrichmentRepository.
- app/postgres_read_api.py es un runtime separado, solo lectura; no reemplaza todas las funciones locales. Ver docs/POSTGRES_SEARCH_RUNTIME.md.
- Los ficheros *.sqlite3 y *.db son locales, ignorados por Git y no deben borrarse sin backup/migración.

**Decisión:** no eliminar SQLite hasta migrar esas funciones, comprobar paridad y realizar pruebas de regresión. Este PR no modifica ni elimina datos SQLite.

## Gemini privado (prototipo de un propietario)

Se agregó la función Vercel site/api/review.py, usando solo la librería estándar Python, y un botón «Analizar con Gemini» en cada oportunidad. Funciona únicamente bajo demanda sobre UNA vacante pública elegida.

- Busca la vacante por ID en el feed público a través de GitHub Contents API de URL fija; jamás consulta la base privada.
- Modelo estable: gemini-3.1-flash-lite.
- Permite pegar opcionalmente experiencia profesional comprobable (hasta 1.500 caracteres) y texto del aviso original (hasta 6.000).
- Sin perfil, el resultado de compatibilidad es indeterminado. No inventa títulos, idioma, apertura, salario ni experiencia.
- No escribe en Supabase, no genera un CV, no envía correos ni postula.
- Acceso protegido por token privado de operador; la clave API Gemini permanece exclusivamente en servidor.
- **Apagado por defecto**, hasta configurar credenciales y confirmar voluntariamente un proyecto de nivel gratuito.

## Habilitación en Vercel

En opportunity-os-site → Settings → Environment Variables → Production, configurar:

1. GEMINI_API_KEY = tu clave existente en Google AI Studio (NUNCA en el chat ni el repositorio).
2. OPPORTUNITY_REVIEW_TOKEN = token aleatorio privado de al menos 32 caracteres.
3. OPPORTUNITY_GEMINI_ENABLED = true.
4. GEMINI_FREE_TIER_CONFIRMED = true solo tras verificar en Google que el proyecto es Free Tier sin facturación.

Crear un token localmente, sin compartirlo:
python -c "import secrets; print(secrets.token_urlsafe(36))"

Luego redeploy de Vercel y verificar: sin configuración debe devolver 503, con token incorrecto 401 y con clave válida debe analizar solo un aviso.

**Privacidad:** el nivel gratuito de Gemini puede utilizar el contenido para mejorar productos. No pegar DNI, CV completo, emails, números personales, credenciales ni documentos confidenciales. La bandera GEMINI_FREE_TIER_CONFIRMED no garantiza por sí sola que Google no cobre: es un control operativo.

**Comunidad:** NO compartir un solo token con Equipo Geoespacial. Para activar IA multiusuario se necesitan autenticación individual, cuotas y controles de acceso.

## Límites

- El feed público no contiene toda la descripción: hay campo optativo para pegar requisitos desde la fuente.
- Gemini no verifica vigencia actual ni elegibilidad legal; solo produce una orientación.
- El prototipo viejo del PR #93 usa una interfaz y backend PostgreSQL distintos. No se fusiona directamente.

Documentación:
https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite
https://ai.google.dev/gemini-api/docs/pricing
https://vercel.com/docs/functions/runtimes/python
