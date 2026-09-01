# Opportunity OS — Roadmap

Opportunity OS no apunta a ser un autopilot que “consigue trabajo”. Apunta a que una persona vea mejor el mercado, repita menos tareas y pueda auditar cada decisión importante.

La regla para agregar features es simple:

> automatizar lo repetitivo, conservar evidencia y dejar la decisión humana donde una acción cambia algo afuera del sistema.

## Estado actual

### ✅ V0.2A — Intelligent Radar

- ingesta desde fuentes públicas y manual import;
- normalización y deduplicación;
- candidate tracks;
- scoring separado de `CAREER`, `INCOME_NOW` y `CONFIDENCE`;
- selector diario determinista;
- provenance y manejo explícito de información faltante.

### ✅ V0.2A2 — Target Accounts

- `TargetAccount` separado de `Opportunity`;
- registry YAML público/privado con validación estricta;
- score independiente de capability/sector, proximity, scale/stability, innovation, contactability y hiring;
- selección del mejor candidate track sin mezclar evidencia;
- confidence sensible a freshness;
- ejemplos públicos ficticios y `targets.local.yaml` privado/gitignored;
- endpoint de recomendación `POST /api/v1/targets/radar/run` sin efectos externos.

La semántica permanece separada:

```text
ACTIVE_POSTING
= existe una requisición publicada

TARGET_ACCOUNT
= la organización tiene afinidad suficiente para seguirla o investigarla

SPECULATIVE_OUTREACH
= el sistema recomienda preparar un contacto espontáneo verdadero
```

Target Accounts no agrega `SEND`, no crea CVs, no consume créditos de Apollo y no manda emails.

### ✅ V0.2B — CV Factory

- facts y evidence privados/verificados;
- selección de evidencia por track;
- `ClaimValidator` fail-closed;
- CV ATS reproducible;
- `ApplicationPacket` con hashes y gaps visibles;
- guardas para que proyectos, empleos, métricas y tecnologías no se mezclen ni inventen.

### ✅ V0.2B1 — ATS Polished Renderer + Layout QA

V0.2B1 mejora la presentación del CV sin ampliar la autoridad semántica de CV Factory.

- renderer determinista `ats-pdf-v2`;
- A4, one-column y texto seleccionable;
- Helvetica / Helvetica-Bold únicamente;
- jerarquía tipográfica más fuerte y un único color de acento no semántico;
- sin fotos, logos, tablas, sidebars, charts, skill bars ni fuentes externas;
- `Layout QA` posterior al render y anterior al `ApplicationPacket`;
- errores duros de layout siguen mapeando a `BLOCKED_RENDER` y eliminan el PDF parcial;
- low/high page utilization producen warnings deterministas, no claims ni decisiones nuevas;
- filename recruiter-facing profesional, determinista y path-safe;
- requisitos objetivo no soportados siguen siendo gaps: layout y keyword matching no inventan experiencia.

La frontera sigue siendo:

```text
verified facts/evidence
→ CVComposer
→ ClaimValidator
→ ats-pdf-v2
→ Layout QA
→ ApplicationPacket
```

### ✅ V0.2B2 — One-page Recruiter Pipeline

V0.2B2 convierte la salida recruiter en un artefacto canónico de exactamente una página sin ampliar la autoridad sobre claims.

```text
RadarAssessment
-> EvidenceSelector
-> CVComposer
-> ClaimValidator
-> RecruiterDocumentComposer
-> RecruiterDocumentValidator
-> RenderCV/Typst one-page renderer
-> RecruiterQualityQA
-> ApplicationPacket
```

Implementado:

- `RecruiterDocumentModel` sólo referencia claims del `CVDocumentModel` semántico;
- grupos de skills y presupuestos de contenido definidos por `recruiter-policy-v1`;
- reducción determinista y acotada cuando el primer render no entra;
- exactamente una página A4 como condición de `PREPARED`;
- body font mínimo de 9 pt y texto extraíble;
- `RenderCV/Typst` con renderer versionado `rendercv-typst-v1`;
- `RecruiterQualityQA` con hard fail para dos páginas, clipping/overflow defendible, fuente insuficiente o texto no extraíble;
- verificación ATS con PyPDF y PyMuPDF;
- golden fixtures públicas ficticias para software/geoespacial y tech+operations;
- `ApplicationPacket` conserva documento semántico, documento recruiter, versiones y hashes reproducibles;
- `packet_sha256` cambia si cambia el agrupamiento/orden recruiter relevante;
- CLI canónico `python -m app.application.prepare` que exige un `RadarAssessment` serializado y nunca inventa track/score/intent;
- runbook fresh-context en `docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md`;
- datos privados y PDFs reales permanecen fuera del repo.

No existe fallback automático a dos páginas. Un hard fail recruiter termina en `BLOCKED_RENDER` y elimina el PDF parcial. `PREPARED` sigue sin significar `APPROVE` ni `SEND`.

### ✅ V0.2C — Email Outreach Core

- resolución de contacto permitido;
- `OutreachBrief`;
- identidad exacta del draft;
- aprobación ligada al contenido exacto;
- `SendRequest` separado de approval;
- `SendGate`;
- receipts idempotentes;
- ledger append-only;
- privacy guards.

El flujo del operador ya fue probado en uso real, pero el core no presupone integración automática con proveedores externos.

### ✅ V0.2D — Relationship Memory / Context Bridge

Relationship Memory evita que cada corrida empiece de cero.

- storage privado SQLite: `state/relationships.local.sqlite3`;
- estado actual de cuenta/contactos separado de eventos append-only;
- eventos idempotentes por `event_id` y conflictos fail-closed;
- estados persistidos `UNTOUCHED`, `CONTACTED`, `REPLIED`, `PROCESS_OPEN`, `PROCESS_CLOSED`;
- `DORMANT` derivado por lectura, nunca persistido por el Context Bridge;
- contactos `AVAILABLE`, `HELD` e `INACTIVE`;
- un contacto `HELD` puede conservarse sin recomendar usarlo mientras existe otro canal activo;
- `PROCESS_OPEN` no se degrada por un contacto o reply posterior;
- cooldown explícito por relación;
- `FOLLOW_UP` requiere historia, timing mínimo y una razón nueva concreta;
- Context Bridge redactado: no expone nombres, emails, bodies, provider IDs ni notas privadas;
- Target Accounts consume `RelationshipContext` antes de recomendar acción;
- endpoints locales read-only:
  - `GET /api/v1/relationships/context`
  - `GET /api/v1/relationships/{account_id}/context`;
- si la DB no existe, el sistema usa memoria vacía y no crea el archivo por una lectura.

Acciones posibles tras combinar afinidad + memoria:

```text
WATCH
FOLLOW_UP
RESEARCH_CONTACT
PREPARE_SPECULATIVE
```

Ninguna equivale a `SEND`.

Relationship Memory no importa automáticamente Gmail, Apollo, el vault ni un CRM existente. Esos datos reales permanecen privados.

### ✅ V0.2E — Operator Observation Bridge

V0.2E implementa el bridge provider-neutral para traer hechos externos autorizados al estado local sin darles autoridad de acción.

Flujo:

```text
operator / provider adapter
        ↓
OperatorObservation
        ↓
normalización determinista
        ↓
ObservationPreview
        ↓
hash exacto del preview + estado relevante
        ↓
confirmación humana
        ↓
RelationshipEvent
        ↓
Relationship Memory
```

Implementado:

- contratos Pydantic estrictos y provider-neutral;
- observaciones soportadas:
  - `CONTACT_VERIFIED`
  - `MESSAGE_SENT`
  - `REPLY_RECEIVED`
  - `PROCESS_OPENED`
  - `PROCESS_UPDATED`
  - `PROCESS_CLOSED`;
- `reason` corto y acotado; no hay `body`, raw payload ni metadata libre;
- `RelationshipService.preview()` y `record()` comparten la misma lógica de transición;
- validación cronológica read-only compartida con el ledger;
- event IDs deterministas por identidad de la observación;
- semantic hash separado del event ID;
- preview sin escrituras;
- hash del preview sensible a la observación y al estado relevante;
- import sólo con confirmación del hash exacto;
- retry idéntico devuelve `ALREADY_IMPORTED` sin segundo evento;
- misma identidad con semántica distinta falla cerrado;
- cambio de estado antes del primer import invalida el preview anterior;
- `MESSAGE_SENT` sólo actualiza Relationship Memory como `CONTACTED`;
- no crea `SendReceipt` ni entra al send path del Outreach Core;
- operator routes ausentes por defecto;
- flag explícito `OPPORTUNITY_OPERATOR_IMPORT_ENABLED=false`;
- bridge habilitado sin DB de relaciones existente devuelve `503` sin crearla;
- `app/operator_bridge` no contiene Gmail/Apollo SDK, HTTP/network I/O ni dependencias del send path.

La frontera queda explícita:

> An imported observation is evidence about what happened; it is not authority to make something happen.

Los provider-specific adapters permanecen separados de V0.2E: el bridge sigue provider-neutral y continúa siendo la única frontera de preview/confirm/import.

### ✅ V0.2E1 — Gmail Read Adapter

V0.2E1 conecta Gmail en **lectura autorizada, selectiva y fail-closed** sin cambiar el contrato central.

```text
selected Gmail message/thread
        ↓
Gmail read-only adapter
        ↓
OperatorObservation
        ↓
STOP
        ↓
V0.2E preview
        ↓
human confirm
        ↓
local import
```

Implementado:

- exactamente un `message_id` o `thread_id` por selección;
- `account_id` provisto por el caller; Gmail no adivina la identidad de la empresa;
- cliente REST con `httpx` y `format=metadata`;
- allowlist de headers `From`, `To`, `Cc`, `Subject`, `In-Reply-To`, `References`;
- normalización inmediata que descarta body, snippet, raw MIME, attachments y payloads no permitidos;
- direcciones de email normalizadas para determinar dirección del mensaje;
- `MESSAGE_SENT` sólo con evidencia `SENT` + sender propio + destinatario externo;
- `REPLY_RECEIVED` sólo con outbound previo e inbound estrictamente posterior en el mismo thread;
- IDs y provenance deterministas de Gmail;
- errores 401/403/404/429/timeout/payload inválido convertidos en códigos acotados;
- `external_actions=[]` como invariante;
- ruta `POST /api/v1/adapters/gmail/observe` ausente por defecto;
- flag `OPPORTUNITY_GMAIL_READ_ENABLED=false`;
- sin creación automática de cliente OAuth/credenciales desde `main`;
- provider failure no altera Relationship Memory;
- no llama `OperatorBridgeService.import_observation()`;
- no crea drafts, no envía, no responde y no muta labels/archive/delete;
- V0.2E permanece como única puerta para importar una observación a memoria.

V0.2E1 tampoco clasifica automáticamente mails de proceso como `PROCESS_OPENED`, `PROCESS_UPDATED` o `PROCESS_CLOSED`: esa semántica requiere otra política de evidencia.

### ✅ Search Health — provenance-aware pipeline reporting

Search Health convierte el estado ya existente en un reporte local **read-only** en vez de crear un segundo sistema de tracking.

```text
Opportunity Store / Radar evidence
              +
Outreach ledger / Relationship Memory
              +
historical observations (private, separate)
              ↓
       exact reconciliation
              ↓
        Metrics Projection
              ↓
       CLI + aggregate JSON
```

Implementado:

- modelos estrictos para counts, ratios, coverage y ventana temporal;
- cobertura explícita `COMPLETE`, `PARTIAL` y `UNKNOWN`;
- `native history != reconstructed history`: el backfill histórico vive en un SQLite privado separado y nunca fabrica eventos nativos retrospectivos;
- precedencia de evidencia `NATIVE > IMPORTED_PROVIDER > MANUAL` sólo cuando existe un anchor exacto compatible;
- sin fuzzy matching por empresa, subject o proximidad temporal;
- `event_confidence` separado de `link_confidence`;
- observaciones con link incierto pueden permanecer como evidencia/counts, pero no entran silenciosamente en ratios de conversión;
- `missing evidence is not zero`: una población o denominador no defendible produce `UNKNOWN`/`null`, no `0` o `0%`;
- lectura de SQLite operacional en modo read-only; una fuente faltante no se crea como efecto colateral del reporting;
- counts de discovery, qualification, packets, drafts, sends, replies y process state con coverage explícita;
- conversiones sólo sobre cohortes defendibles;
- CLI determinista `python -m app.metrics.report` + JSON agregado;
- import histórico explícito e idempotente con `python -m app.metrics.import_history`;
- manifests, SQLite histórico y reportes reales permanecen privados/gitignored;
- output agregado sin provider IDs, contactos, emails, subjects, bodies ni notas privadas;
- CI cubre contratos de history, sources, reconciliation, projection, determinismo y privacy.

El backfill inicial fue ejercitado de forma privada contra una selección explícita de evidencia laboral real, declarada como `SELECTED_THREADS`: no se publica el historial personal ni se presenta esa selección como cobertura total del mailbox.

**Metrics do not grant SEND, APPLY or FOLLOW-UP authority.** Search Health describe evidencia observada; no es un productivity score, success predictor ni causal optimizer.

---

## NEXT — V0.2E2 — Conversation-provider adapter design

El próximo problema validado es ampliar la memoria de relaciones con conversaciones que hoy viven fuera de Gmail.

**WhatsApp es un provider candidate prioritario**, especialmente para detectar conversaciones profesionales pendientes de respuesta, pero todavía no está implementado.

La próxima fase debe diseñar primero la frontera antes de escribir integración:

- usar una vía oficial/autorizada de WhatsApp cuando exista para la cuenta objetivo;
- no depender de scraping frágil de WhatsApp Web ni automatización de sesión personal;
- distinguir mensaje inbound/outbound con provenance suficiente;
- modelar `NEEDS_REPLY` preferentemente como estado derivado de la cronología, no como permiso de acción;
- mantener bodies privados y minimizar persistencia de contenido;
- reutilizar `OperatorObservation` y V0.2E para cualquier import a Relationship Memory;
- no agregar auto-send por defecto;
- separar importación histórica explícita de cualquier integración viva futura.

El diseño debe decidir qué puede observarse de WhatsApp personal vs WhatsApp Business Platform sin inventar capacidades ni violar los límites del proveedor.

---

## AFTER — Process-email classifier

Con Gmail read ya separado del bridge, puede evaluarse una clasificación semántica específica para mensajes de proceso:

- candidatura recibida;
- entrevista propuesta;
- avance de etapa;
- rechazo/cierre;
- actualización explícita de un proceso existente.

La clasificación deberá tener una política visible de evidencia/confidence. Un subject o keyword aislado no alcanza para modificar Relationship Memory.

---

## AFTER — Contact/public research adapters

Pueden evaluarse adapters de:

- fuentes públicas;
- páginas oficiales de careers;
- contact discovery autorizado;
- Apollo con control explícito de costo/contactos acumulados;
- private workspace.

Cualquier fuente paga debe tener control explícito de costo. Ningún adapter puede inventar emails, contactos o estados.

---

## AFTER — Outreach reconciliation

La evidencia histórica de un proveedor puede servir para reconciliar lo ocurrido con el Outreach Core, pero una observación externa no equivale a un receipt fuerte.

La reconciliación futura debe respetar:

```text
DraftSnapshot
→ ApprovalRecord
→ SendRequest
→ SendGate
→ provider-confirmed success
→ SendReceipt
```

V0.2E no fabrica esa cadena retrospectivamente.

---

## AFTER — Monitoring y follow-up

Con Target Accounts, Relationship Memory y observaciones reales entrando de forma segura, el sistema puede producir recordatorios útiles en vez de más volumen:

- apareció una vacante nueva en una empresa de alta afinidad;
- terminó un cooldown;
- un proceso abierto lleva demasiado tiempo sin cambio;
- una fuente cambió o desapareció;
- una empresa target empezó a contratar una familia de roles relevante;
- existe una conversación profesional con respuesta pendiente cuando el provider lo permite de forma defendible.

El principio sigue siendo el mismo: **notificar cuando cambió algo útil**, no generar actividad por generar actividad.

`FOLLOW_UP` seguirá significando “hay una razón defendible para preparar una continuación”, nunca “mandar automáticamente otro mensaje”.

---

## LATER — Mejoras de producto

Después de cerrar el bridge con operadores reales, pueden evaluarse:

- vistas/resúmenes diarios que combinen vacantes, targets y relationships;
- motivos estructurados para follow-up y actionable-next-state;
- comparaciones descriptivas por source, language, intent o strategy con tamaños de muestra visibles;
- dashboard/UI sobre la proyección existente, sin duplicar semántica;
- métricas temporales como median time-to-reply cuando exista cobertura defendible;
- adapters adicionales de fuentes públicas;
- export/import local y portable del estado privado;
- mejor observabilidad de freshness/provenance.

No son promesas de release; deben entrar sólo si el uso real demuestra valor.

---

## Fuera de scope por diseño

Opportunity OS no tiene como objetivo:

- aplicar automáticamente a todo lo que encuentre;
- completar declaraciones legales sensibles sin intervención humana;
- resolver CAPTCHAs o evadir controles de sitios;
- inventar experiencia o “optimizar” claims falsos;
- comprar/enriquecer contactos sin control de costo;
- mandar campañas masivas de cold email;
- publicar el perfil privado, CRM o historial de una persona;
- convertir el paso del tiempo en permiso automático para contactar de nuevo;
- tratar una observación importada como permiso de envío.

## Cómo leer este roadmap

`NEXT` significa: próximo problema validado y candidato inmediato a diseño/implementación.

`AFTER` significa: dirección clara, pero debe hacerse después del bloque NEXT.

`LATER` significa: dirección útil, todavía no una promesa de release.

El roadmap puede cambiar con evidencia de uso real. Los límites de privacidad, provenance y aprobación humana no deberían hacerlo.