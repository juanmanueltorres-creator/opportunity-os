# Opportunity OS · Radar global para mañana

## Qué está listo (cero servidor, cero Gemini, cero secretos)

El workflow existente \`.github/workflows/daily-opportunity-radar.yml\` corre todos los días
a las **09:23 Argentina** (UTC-3) y permite \`workflow_dispatch\` manual.

Desde esta versión, la descarga \`daily-opportunity-radar\` incluye:

- \`radar.html\`: abrir con el navegador tras extraer el ZIP. Tiene búsqueda,
  sector, modalidad, elegibilidad, idioma, ubicación, tres modos de exploración
  y enlaces HTTPS reales.
- \`jobs.json\`: campos existentes \`matches\` y \`needs_review\` + campo
  \`atlas\` (máximo 250 vacantes del universo global con afinidad temática).
- \`jobs.md\`: informe de búsqueda conservador, compatible con el flujo anterior.

No hay postulación automática, IA, geocoding, datos personales, CV ni contacto
en el artefacto público. No hay estadísticas falsas ni mapa sin coordenadas.

## Cómo usarlo

1. Ir a **GitHub → opportunity-os → Actions → Daily Opportunity Radar**.
2. Seleccionar la última ejecución exitosa o **Run workflow** (rama \`main\`,
   después de mergear esta PR).
3. Descargar el artefacto **daily-opportunity-radar**.
4. Extraer el ZIP; abrir **radar.html**.
5. Usar **Para postular** primero, luego **A verificar** y **Explorar empresas**.
6. Abrir el aviso original y verificar que admita postulaciones desde Argentina.

El archivo es una fotografía diaria; **no navega ni verifica en vivo**. No enviar
CV sin comprobar el link oficial y la elegibilidad.

## Por qué lo hicimos así

La ejecución programada del 2026-10-27 detectó **541 avisos** de 8 rutas fuente
y **1 recomendación** tras filtros estrictos. La persistencia mostró
\`db=NOT_CONFIGURED\`. Sin el secreto \`OPPORTUNITY_POSTGRES_WRITE_DSN\`, la
búsqueda funciona pero no sincroniza con el historial privado de Supabase.

El nuevo parámetro opt-in del ranking global conserva empresas de fuera de
Argentina para exploración, sin ampliar el conjunto elegible para postularse.
La UI evita descargar más de 250 candidatos y renderiza 100 por selección.

## Escalabilidad sin reescribir

- Fuentes nuevas: conectar \`AshbyConnector\`, \`LeverConnector\`,
  \`GreenhouseConnector\` a empresas objetivo y al pipeline existente.
- Integración privada: configurar rol lector/escritor de permisos mínimos y
  \`OPPORTUNITY_POSTGRES_WRITE_DSN\`; no exponerlo en GitHub o el navegador.
- UI persistente: montar el dashboard privado del PR #93 sobre Supabase cuando
  esté desplegado el backend, y aprovechar el mismo modelo de datos.
- Atlas geoespacial: agregar \`company_location\`, \`work_location\`,
  \`hiring_countries\`, \`precision\`, \`source\`; reutilizar MapLibre y geometría
  de Pulso Público. No inferir coordenadas de puestos remotos.

La vista portátil **no sincroniza favoritos ni aplicaciones con Supabase**.
Es una herramienta inmediata de selección hasta tener autenticación privada.
