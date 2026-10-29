# Uso desde la interfaz: preparar CV sin subir datos

La vista del radar y la lista de oportunidades revisadas incorporan **Preparar CV**.

1. Seleccionar una vacante y pulsar **Preparar CV**.
2. Completar los campos con datos profesionales reales. Los campos se dejan
   **vacíos por defecto**: no existe un perfil privado respaldado en el feed.
3. Opcional: pulsar **Guardar perfil aquí**, que usa exclusivamente
   \`localStorage\` del navegador actual. No se sincroniza con Supabase,
   GitHub, Google ni Vercel. Puede borrarse con **Borrar perfil guardado**.
4. En otro aviso, usar **Preparar CV**; los datos previamente guardados
   aparecerán para revisión. Las habilidades declaradas se ordenan,
   sin añadir ninguna, si aparecen en la descripción pública del aviso.
5. Pulsar **Guardar PDF (Imprimir)** y elegir **Guardar como PDF** en
   el diálogo del navegador; revisar el PDF, enlaces y paginación.
6. Abrir la postulación original. No hay envío ni registro automático.

## Alcance exacto

Este incremento es un editor de CV **local en navegador** con exportación
mediante impresión. No es el pipeline \`app/cv/service.py\` de RenderCV/Typst,
que requiere \`master_facts\` y \`evidence_catalog\` privados y seguirá sin
ejecutarse en el frontend público hasta disponer de una API autenticada
y controles adecuados de privacidad.

No conecta con Gemini ni toca base de datos. No publica hechos personales
en el repositorio. No asegura que el aviso esté vigente o admita argentinos.

Las pruebas cubren seguridad del HTML, correspondencia de habilidades declaradas,
enlaces HTTPS, persistencia opt-in y contrato de impresión.
