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

V0.2E implementa el primer bridge provider-neutral para traer hechos externos autorizados al estado local sin darles autoridad de acción.

Flujo:

```text
operator / future adapter
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

Los provider adapters remain future work: V0.2E implementa el enchufe seguro, no Gmail/Apollo sync.

---

## NEXT — V0.2E1 — Gmail read adapter

El siguiente slice debe conectar Gmail en **lectura autorizada y selectiva** sin cambiar el contrato central.

Objetivo:

```text
selected Gmail message/thread
        ↓
read-only adapter
        ↓
normalized OperatorObservation
        ↓
V0.2E preview
        ↓
human confirm
        ↓
local import
```

Requisitos:

- leer sólo mensajes/threads explícitamente seleccionados o consultados;
- no importar automáticamente;
- no crear drafts;
- no enviar;
- no transformar una respuesta ambigua en estado definitivo sin evidencia suficiente;
- conservar message/thread provenance sin copiar cuerpos completos al core;
- provider failure no debe alterar Relationship Memory;
- mantener V0.2E como única frontera de import.

El adapter debe poder producir hechos como:

- `MESSAGE_SENT` cuando existe evidencia autorizada suficiente;
- `REPLY_RECEIVED` cuando se observa una respuesta concreta;
- eventualmente una observación de proceso sólo cuando la clasificación pueda defenderse y siga pasando por preview/confirm.

---

## AFTER — Contact/public research adapters

Después del Gmail read adapter pueden evaluarse adapters de:

- fuentes públicas;
- páginas oficiales de careers;
- contact discovery autorizado;
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
- una empresa target empezó a contratar una familia de roles relevante.

El principio sigue siendo el mismo: **notificar cuando cambió algo útil**, no generar actividad por generar actividad.

`FOLLOW_UP` seguirá significando “hay una razón defendible para preparar una continuación”, nunca “mandar automáticamente otro mensaje”.

---

## LATER — Mejoras de producto

Después de cerrar el bridge con operadores reales, pueden evaluarse:

- vistas/resúmenes diarios que combinen vacantes, targets y relationships;
- motivos estructurados para follow-up;
- adapters adicionales de fuentes públicas;
- reporting de pipeline sin exponer PII;
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
