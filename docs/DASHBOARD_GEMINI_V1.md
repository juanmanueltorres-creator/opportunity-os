# Opportunity OS — Radar UI + Gemini (incremental MVP)

## Qué agrega

El proyecto ya disponía de una API PostgreSQL con vacantes, historial, filtros y un conector Remotive. Esta implementación agrega una **interfaz privada** sobre ese backend, sin sustituir ni modificar las APIs existentes.

- `GET /dashboard`: interfaz responsive de búsqueda y seguimiento visual.
- Filtros en servidor: texto, modalidad, idioma, elegibilidad Argentina, verificación, fecha y exclusión de aplicaciones registradas.
- Filtros **orientativos locales**: área de interés (por palabras del título) y ubicación Córdoba/San Juan (por texto en la ubicación). Solo afectan a los resultados cargados. No son elegibilidad confirmada.
- Paginación de 60 ofertas por llamada, botón "Cargar más".
- Tarjeta de detalle con enlace HTTPS a la fuente real; estados `PENDING` y `UNKNOWN` visibles.
- `POST /api/v1/dashboard/ai-review`: analiza **una vacante guardada** con Gemini y, opcionalmente, el contexto profesional proporcionado conscientemente.
- `POST /api/v1/source/refresh` (ya existente) desde la UI: sincroniza Remotive solo si el backend tiene credenciales de escritura. Las nuevas vacantes son PENDING; no son consideradas verificadas.
- Token privado en memoria de la pestaña, no en localStorage ni cookies. No hay credenciales Gemini ni Supabase en el código cliente.

## Arranque

Python >= 3.12. Ejecutar desde la raíz del checkout:

```bash
python -m pip install -e .
python -m pip install 'psycopg[binary]>=3.2,<4'
export OPPORTUNITY_POSTGRES_DSN='postgresql://...'
export OPPORTUNITY_API_TOKEN='un-token-aleatorio-con-mas-de-32-caracteres'
# Opcional para IA:
export GEMINI_API_KEY='clave-configurada-solo-en-servidor'
export GEMINI_FREE_TIER_CONFIRMED='true' # Solo luego de verificar Free Tier sin facturación
# Opcional para permitir importación de Remotive:
export OPPORTUNITY_POSTGRES_WRITE_DSN='postgresql://...'
uvicorn app.dashboard_api:app --host 127.0.0.1 --port 8100
```

Abrir **http://127.0.0.1:8100/dashboard** y pegar el `OPPORTUNITY_API_TOKEN` en el campo privado. El token se pierde al recargar la pestaña, intencionalmente.

El backend necesita que el schema `opportunity_os` y sus tablas estén creadas. Revisar `docs/POSTGRES_SEARCH_RUNTIME.md` y `docs/POSTGRES_WORKFLOW_API.md`. Si no hay vacantes, la interfaz indica una base vacía; **no hay resultados de prueba simulados ni búsqueda web de Gemini**.

## Configuración opcional de Gemini

Crear la clave en [Google AI Studio](https://aistudio.google.com/apikey) dentro de un proyecto que figure como **Free Tier** y **NO tenga una cuenta de facturación vinculada**. No activar "Set up billing". Guardar `GEMINI_API_KEY` solo como variable secreta del servicio backend.

**Modo exclusivamente gratuito:** la app utiliza solo `gemini-2.5-flash-lite`, modelo oficialmente compatible con la capa gratuita ([precios](https://ai.google.dev/gemini-api/docs/pricing)). La variable `GEMINI_MODEL` se ignora intencionalmente, para impedir un cambio accidental a un modelo de pago. Las llamadas están bloqueadas hasta establecer `GEMINI_FREE_TIER_CONFIRMED=true`, tras verificar manualmente en AI Studio que la clave corresponde a un proyecto Free Tier sin facturación. **El software no puede averiguar el nivel de facturación solamente a partir de una clave**: esa confirmación es una obligación del operador. Si se habilita un proyecto con facturación de todos modos, Google podría cobrar solicitudes incluso a modelos con capa gratis. No hay llamadas automáticas, reintentos ni cambio a modelos pagos.

Si se agota la cuota gratuita, la API devuelve HTTP 429 y la UI muestra un error. Se espera el reinicio de la cuota; nunca se amplía a un plan pago. Los límites reales dependen del proyecto y se consultan en [AI Studio](https://aistudio.google.com/).

Se puede definir `OPPORTUNITY_CANDIDATE_CONTEXT` del lado del servidor como descripción breve y no sensible del perfil. Si el usuario ingresa contexto en el panel, ese texto tiene prioridad para esa llamada; no se persiste en base de datos. Al hacer clic en "Analizar", se comparte con Google **la descripción del aviso y el contexto elegido**. La IA no verifica que la vacante exista hoy, no envía CV, no dispara postulaciones ni cambia registros.

El frontend informa si la clave está configurada **y el operador confirmó Free Tier**, sin revelar secretos. Si la API no responde o devuelve JSON no válido, el servicio falla explícitamente sin recomendar una postulación ficticia.

## Limitaciones y seguridad

1. La UI no prueba una conexión de base al cargar HTML; solo al autenticar y consultar. No hay fallback silencioso a SQLite.
2. El estado de apertura no es una garantía: solo `VERIFIED` muestra "Verificada" si un operador registró evidencia mediante el flujo existente. Un aviso importado es `PENDING`.
3. Solo Remotive tiene botón de sincronización en esta versión. Las demás fuentes requieren sus conectores y despliegue independiente; Gemini no rastrea Internet en este flujo.
4. **En producción**, servir exclusivamente bajo HTTPS y autenticación perimetral (además del Bearer). Mantener claves y DSN del lado del servidor. No usar tokens de Supabase en el navegador.
5. Si se instala como paquete/wheel independiente del checkout, incluir el recurso `app/dashboard.html` en la distribución, o iniciar el servicio desde el directorio del repositorio.
6. El proyecto de Google AI Studio debe mantenerse en el nivel gratuito sin facturación; el código no puede garantizar por sí solo la ausencia de cargos si una clave corresponde a una cuenta pagada. Google puede utilizar los datos enviados en el nivel gratuito para mejorar sus productos; evitá introducir CV completos, correos personales u otros datos sensibles.

## Pruebas

```bash
pytest -q tests/test_dashboard_api.py tests/test_postgres_read_api.py tests/test_postgres_workflow_api.py
```

Las pruebas del dashboard sustituyen Gemini y PostgreSQL por dobles; ninguna realiza solicitudes externas ni requiere credenciales reales. Una prueba end-to-end contra Supabase y Gemini deberá realizarse en el servicio configurado.
