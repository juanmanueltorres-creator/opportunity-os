# Opportunity OS — Integración de fuentes: Argentina primero por especialidad

Revisado el 28 de octubre de 2026. Distinguimos tres estados:
**AUTOMÁTICA** (GitHub Actions efectivamente ejecuta el conector);
**MANUAL** (enlace a la fuente, sin copiar automáticamente sus datos);
**POR AUTORIZAR / ESTUDIAR** (no marcar como conectado).

| Fuente | URL fuente real | Estado | Próximo paso |
|---|---|---|---|
| YPF · Búsquedas activas | https://oportunidades.ypf.com/search/ | MANUAL | Validar una vía de integración autorizada del portal SAP SuccessFactors |
| YPF · Negocios | https://oportunidades.ypf.com/go/Negocios/9521900/ | MANUAL | Contemplar pozos, operaciones, geología, perforación, logística, tecnología |
| YPF · Áreas corporativas | https://oportunidades.ypf.com/go/%C3%81reas-corporativas/9522000/ | MANUAL | Tecnología, compras, analistas, gestión, ambiente |
| Trabajo Minería Salta | https://trabajomineria.salta.gob.ar/trabajos/ | MANUAL | Solicitar autorización o feed oficial, sin reproducción automatizada por defecto |
| Computrabajo Argentina | https://ar.computrabajo.com/trabajo-de-geologia | MANUAL / CONECTOR CHATGPT | Consulta nacional por palabras clave; estudiar API/condiciones de distribución antes de automatizar la web pública |
| Indeed Argentina | https://ar.indeed.com/jobs?l=Argentina&q=GIS | MANUAL / CONECTOR CHATGPT | La API pública documentada Job Sync es para **publicar**, no para descargar búsquedas |
| LinkedIn Jobs Argentina | https://ar.linkedin.com/jobs/gis-empleos | MANUAL | No hacer scraping automático: requiere autorización expresa según sus términos |
| Lever/Ashby/Greenhouse | Fuentes de las empresas ya registradas | AUTOMÁTICA | Ampliar tableros verificados, auditar vigencia, permisos de publicación y país |
| Get on Board, Remotive, Jobicy y similares | Referencias en `app/radar/daily_search.py` | AUTOMÁTICA | Mejorar fechas y cobertura argentina sin alterar la información de origen |

**Importante:** contar una fuente en el catálogo de Supabase NO significa que tenga un
recolector funcionando. La lista de fuentes efectivamente ejecutadas es
`sources` en el snapshot `radar-public/jobs.json` y se muestra al pie de la web.

## YPF: diferencia de frescura

YPF indica en su página de postulaciones que las vacantes se publican por
**10 días corridos**; el plazo se verifica contra la fecha oficial de cada
vacante. No inferir que un anuncio de YPF viejo está abierto solo porque
un buscador externo aún lo indexa.

- Portal: https://oportunidades.ypf.com/search/
- Información de proceso: https://oportunidades.ypf.com/content/Como-sumar-tu-energia/?locale=es_ES

YPF usa tecnología SAP SuccessFactors. SAP publica documentación de feeds XML
para distribución de vacantes, pero son configurados por el titular/administrador
del ATS. **No** asumir una API pública de consulta por el hecho de existir el
portal ni transformar HTML indexado por buscadores en una API no autorizada.

- SAP (distribución XML): https://learning.sap.com/courses/sap-successfactors-recruiting-candidate-experience-administration/posting-jobs
- SAP (RSS XML obsoleto desde 2025, retirada prevista 2027):
  https://learning.sap.com/courses/sap-successfactors-recruiting-candidate-experience/describing-the-new-features-and-enhancements-in-the-2h-2023-release_f278480f-f3fe-4bf0-9c57-ad63fdda3f5b

## Integración de fuentes de búsqueda

El usuario busca una especialidad **sin seleccionar una provincia de entrada**.
Etiquetas sugeridas: GIS/SIG/geoespacial, geología/hidrogeología,
minería/mining tech, agro/AgTech, ambiente, Urban Tech, desarrollo técnico-comercial,
Python/software, logística, soporte y gastronomía. Ubicación, traslado e idioma
se evalúan después.

No se deben hacer pasar fuentes manuales por conectores del radar ni generar
registros simulados. Si se obtiene acceso legítimo a un feed, el adaptador debe:
validar URL de origen, ID propio, fecha publicada, fecha observada, ubicación
declarada; deduplicar por empresa + puesto + ubicación y manejar desapariciones
sin borrar el historial de postulaciones. Respetar restricciones del proveedor.

## Antes de conectar Gemini

Separamos el radar público (equipo) del seguimiento privado (dueño de la cuenta).
Gemini debe ejecutarse **bajo demanda** y detrás de autorización/rate limiting,
nunca exponer su clave en el HTML ni enviar automáticamente CV o contactos al
proveedor.
