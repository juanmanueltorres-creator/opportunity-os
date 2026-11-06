# Opportunity OS · Orientación pública y chat Gemini (2026-11-04)

## Propósito

Orientar a visitantes sobre **sectores, empresas, vacantes y caminos de ingresos**, sin cuenta, sin Excel y sin publicar datos privados. El Excel personal sigue siendo útil exclusivamente en la pestaña **Seguimiento**.

## Contrato de evidencia

| Fuente | Ruta de la web / API | Actualización | Qué demuestra | Qué NO demuestra |
|---|---|---|---|---|
| Radar público | `radar-public/jobs.json` de GitHub | GitHub Actions del radar | Avisos capturados y campos de su fuente | Vigencia al minuto, aceptación desde Argentina si es UNKNOWN, resultado de postulación |
| CESSI | `site/discovery-companies-2026.json` | Selección editorial de 2026-11-04 | Domicilio y actividad informada por CESSI | Que esas empresas estén contratando |
| Directorio de carreras | `site/public-company-guides-2026.json` | Revisión humana de 2026-11-04 | Portal público de empleador y foco profesional | Vacante activa, puesto remoto o salario |
| Comparación de sectores | `site/market-context-2026.json` | Revisión humana, por indicador | Magnitudes y fuentes fechadas | Probabilidad personal de conseguir empleo |
| CEP XXI | `site/cep-provincial-2022.json` | Estadística histórica 2022 | Puestos y establecimientos por provincia/actividad, según muestra publicada | Empresas únicas o vacantes 2026 |
| Objetivos remotos | `site/remote-targets-2026.json` | Selección editorial fechada | Vías y cautelas por empleador | Elegibilidad universal de la empresa |

La comparación entre 4.203.016 asalariados en Comercio **y Servicios** (promedio 2025) y 39.698 empleos **mineros directos** (enero 2026) es ilustrativa, no una comparación de categorías idénticas. El empleo minero indirecto puede encontrarse en tecnología, mantenimiento, ingeniería, logística, consultoría y comercio. Si se comparan probabilidades individuales se necesitan **aperturas por rol, requisitos, vacantes verificadas, candidatura, competencia y tasas de respuesta**, no solo tamaño de población.

## Arquitectura

```text
Landing pública · Brújula / Datos / Empresas / Buscar
          |
          +-- Rutas de búsqueda y datos públicos (sin login)
          +-- Mapa Leaflet (solo tras consentimiento de carga)
          +-- Chat incorporado /api/chat (POST)
                    |
                    +-- Valida tamaño, método, origen y ritmo de solicitudes
                    +-- Lee SOLO capturas públicas y catálogos editoriales
                    +-- Recupera vacantes, perfiles, datos CEP y fuentes relevantes
                    +-- Construye contexto acotado con advertencias de evidencia
                    +-- Gemini generateContent con clave privada en servidor
                    +-- Devuelve texto y enlaces HTTPS de fuente comprobables
```

El chat no sube archivos ni accede a Supabase privado, Gmail, seguimiento local o Excel. La conversación vive en memoria del navegador y solo los turnos recientes se incluyen en cada pregunta. Google procesa la consulta enviada mediante Gemini; por eso la web advierte que no se incluyan datos personales.

Las respuestas del modelo se muestran como **texto**, sin renderizar HTML remoto. Los links se construyen únicamente desde el listado de evidencias del servidor. La clave Gemini no aparece en HTML, JavaScript público ni URLs.

## Recuperación estructurada del radar (2026-11-05)

El servicio lee `radar-public/jobs.json` generado por GitHub Actions, **no consulta el historial de ejecuciones**. Un módulo determinista `site/api/radar-query.js` interpreta filtros explícitos de la pregunta y calcula sobre el snapshot completo antes de enviar contexto a Gemini:

- Temas/rol: coincidencia con título, tópicos declarados y sector (sin equiparar cualquier software con Python).
- Modalidad remota: únicamente `remote_mode=REMOTE`.
- Elegibilidad desde Argentina cuando el usuario pide confirmación: únicamente `argentina_eligible=YES`. `UNKNOWN` queda fuera del conteo confirmado.
- Requisitos de idioma laboral en español: únicamente `work_language=ES`. Un anuncio escrito en español no prueba el idioma exigido.
- Últimas 24 horas / 7 días: solo `published_at` válido dentro de una ventana respecto de `generated_at` del snapshot. Se informa cuántos candidatos no tienen fecha.
- Resumen de empresas y cantidad de avisos en la **muestra filtrada**. No equivale a firmas contratando actualmente.

Una captura aislada no demuestra qué avisos cambiaron desde la anterior. Para preguntas sobre cambios, la implementación actual consulta **dos capturas públicas consecutivas** cuando ambas están disponibles y valida identificadores y fechas: ver «Comparación entre capturas públicas consecutivas» más abajo. «Nuevo en la captura» no significa primera publicación y «ya no observado» no significa vacante cerrada; sin un par válido se informa indisponibilidad. Si un filtro produce cero resultados, el servicio devuelve cero, no rellena el listado. Gemini explica los conteos calculados, pero no debe inventar su propia aritmética. Se enlazan primero las vacantes seleccionadas; la selección sigue limitada a ocho ejemplos y las referencias a catorce HTTPS.

El chat continúa sin acceso a perfil privado, Supabase, correo ni almacenamiento de conversaciones. Los filtros del RAG se basan en la **pregunta explícita**, no convierten preferencias agregadas automáticamente por la brújula en restricciones obligatorias.

## Variables de entorno

Configurar **solo del lado de Vercel**, nunca prefijadas con `NEXT_PUBLIC_` o expuestas en el frontend:

- `GEMINI_API_KEY`: valor privado del proyecto.
- `OPPORTUNITY_GEMINI_ENABLED=true`: habilitación explícita.
- `GEMINI_FREE_TIER_CONFIRMED=true`: confirmación explícita del uso de la cuota gratuita por su responsable.
- `OPPORTUNITY_GEMINI_MODEL` (opcional): modelo en catálogo oficial; por defecto `gemini-3.5-flash-lite`.

Sin cualquiera de las tres primeras condiciones, `GET /api/chat` informa `enabled:false` y `POST` devuelve 503 con un mensaje comprensible. Esto protege las previews sin secretos. **No copiar secretos a previews solo para probar**.

El código aplica una cuota de mejor esfuerzo por instancia (6 solicitudes/5 minutos/IP), límites de entrada, modelo con tope de salida, timeout y validación de origen. En Vercel serverless **esto no constituye una protección global ni una garantía de gasto cero**. Antes de abrir un chat de alto tráfico, se debe complementar con límites en Vercel Firewall / rate limiting distribuido y presupuestos/alertas en Google AI Studio. Un aumento de tráfico no debe disparar un upgrade de plan sin revisar costos.

## Cómo verificar

1. CI: `site-smoke` y `tests`, incluyendo `node --test tests/test_public_market_chat.mjs`.
2. Vercel Preview: comprobar `GET /api/chat`, brújula, búsqueda, comparador, directorio, botón de mapa y estado claro si Gemini no está habilitado. Algunas previews pueden requerir inicio de sesión.
3. En producción, confirmar `GET /api/chat.enabled === true` sin exponer la clave y probar una pregunta de baja sensibilidad; cotejar respuesta contra sus fuentes.
4. Comprobar móvil y escritorio, teclado y políticas CSP. El mapa requiere consentimiento de carga y attribution OpenStreetMap.
5. Confirmar que la pestaña **Empresas** abre por defecto la parte pública, y que los registros locales siguen siendo optativos y privados.
6. Revisar periódicamente enlaces, fecha de capturas y categorías. Si una fuente falla, mostrar error, nunca datos simulados.

## Límites y próximos datos a incorporar cuando estén verificados

- No existe todavía un censo de **vacantes por sector** que permita estimar tasas reales de éxito.
- Empresas internacionales en el directorio son **rutas para investigar**, no ofertas laborales.
- Para más cobertura sumar fuentes permitidas por API o directorios oficiales con fecha y procedencia; no copiar listados privados ni hacer scraping indiscriminado.
- Si el chat no puede acceder al radar público, debe decirlo y apoyarse solo en estadísticas y empresas verificadas.

La prueba de éxito es una decisión mejor respaldada: qué empresas investigar, qué puestos descartar y cuál es el siguiente paso, no el número de componentes en la página.

## Comparación entre capturas públicas consecutivas

El workflow del radar lee el `jobs.json` anterior **antes** de publicar el siguiente. Genera `radar-public/changes.json` con `scripts/compare_public_snapshots.py`, usando únicamente identificadores y atributos de avisos ya exportados públicamente.

- `newly_observed_count`: aparece en la captura nueva pero no en la anterior. Puede ser una reaparición, no necesariamente una publicación reciente.
- `no_longer_observed_count`: figuraba antes y no figura ahora. **No prueba cierre**: puede cambiar por cobertura de fuentes, límites de ranking o fallas temporales.
- `continuing_count`: se observa en las dos capturas consecutivas.
- `available=false`: no existe una captura anterior válida o la comparación no coincide con la fecha exacta del feed actual. El chat debe decirlo expresamente.

El endpoint `/api/chat` sólo recupera el archivo de diferencias para preguntas comparativas. Valida fechas, conteos e identificadores y luego aplica filtros por rol, modalidad y elegibilidad. Gemini recibe el resumen computado y evidencia con enlaces, pero no calcula diferencias por su cuenta.

El alcance es **un par de capturas consecutivas**, no una serie histórica de 7 o 30 días. Ninguna diferencia prueba vigencia, elegibilidad ni cierre definitivo. No se agregan servicios pagos, infraestructura nueva ni acceso a datos privados.
