# Opportunity OS — Company Atlas + Gemini privado V1

Estado: rama de implementación; no considerar probado en producción hasta CI, preview y smoke tests.

## Alcance
- Interfaz /empresas (sección del sitio): agrupa por nombre normalizado los empleadores observados en el **feed público** `radar-public/jobs.json`, nunca inventa compañías, sedes ni coordenadas.
- Filtros `Con avisos en español` y `Todas`; un aviso redactado en español **no prueba** que el trabajo sea en español.
- Las fichas muestran total de avisos y elegibilidad provisional. Al hacer clic en «Ver vacantes» se filtra el Atlas existente.
- No modifica ni borra SQL, contactos, postulaciones, CV, SQLite ni cron; la selección privada de Supabase sigue separada.
- No hay mapa geográfico de puntos hasta contar con coordenadas verificadas. Los nombres de provincias, cuando existan, representan **ubicaciones en vacantes**, no oficinas.

## Gemini API (una vacante, propietario)
- `site/api/review.py`: endpoint POST server-only con token secreto y clave Gemini de Vercel.
- Llama `gemini-3.1-flash-lite`; recibe solo un `opportunity_id` existente en snapshot público y texto opcional proporcionado intencionalmente por el usuario.
- `GEMINI_API_KEY`, `OPPORTUNITY_REVIEW_TOKEN`, `OPPORTUNITY_GEMINI_ENABLED=true`, `GEMINI_FREE_TIER_CONFIRMED=true` son necesarias en **Production**. El frontend no conoce la clave de Google. La app guarda el token del operador solo en memoria de la pestaña, nunca en storage.
- Requiere introducir el token privado de operador (NO la clave de Gemini) la primera vez en la sesión. No existe autenticación multiusuario en esta fase; nunca compartir el token con usuarios públicos.
- Si el idioma de trabajo es desconocido, exige revisión antes de postular. Una marca de «visto en ATS» no valida apertura.
- Datos al nivel gratuito de Google podrían usarse para mejorar sus productos: **no pegar CV completo, DNI, emails ni datos sensibles**. Cualquier solicitud a Gemini debe iniciarse con clic explícito.

## Limitaciones
- La base actual no almacena descripciones completas de vacantes: sin pegar requisitos originales Gemini solo puede hacer una evaluación orientativa.
- No hay rate limit persistente entre invocaciones serverless: se evita exposición mediante secreto fuerte y el proveedor gestiona cuotas. Para acceso comunitario, agregar Auth individual y rate limiting persistente antes de habilitar.
- Las marcas del Atlas quedan en localStorage y NO escriben en `opportunity_os.applications`.
- Un resultado de Gemini no genera CV ni envía candidaturas. El pipeline de CV existente sigue intacto.

## Pruebas de aceptación
1. `python -m pytest tests/test_gemini_shortlist_ux.py tests/test_private_gemini_review.py`
2. Preview Vercel READY, filtros de empresas con fichas y enlaces verificables.
3. `POST /api/review` sin configuración => 503; con token falso => 401.
4. Una llamada real autenticada a un aviso existente, desde la interfaz: respuesta estructurada en español, sin almacenar datos privados.
5. Confirmar que producción recibió el SHA aprobado. No interpretar READY preview como producción.

### Trabajos futuros distintos
- Catálogo canónico privado de empresas + relaciones con historial Supabase Auth.
- Mapa con georreferenciación validada y distinción sede/oferta.
- Integración del pipeline RenderCV/Typst tras verificar los requisitos.
