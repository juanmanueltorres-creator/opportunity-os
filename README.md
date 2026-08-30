# Opportunity OS

**Buscar trabajo no debería ser abrir veinte pestañas, mandar el mismo CV a todo y esperar.**

Opportunity OS organiza la búsqueda laboral como un sistema: encuentra oportunidades, separa lo que sirve para carrera de lo que sirve para ingreso inmediato, detecta empresas interesantes aunque hoy no tengan una vacante exacta, arma CVs sólo con evidencia verificable y recuerda qué relaciones ya están abiertas para no empezar de cero cada vez.

Open source, auditable y deliberadamente humano en los pasos que cambian algo afuera del sistema.

> **Estado actual:** el package sigue en la línea prerelease V0.2C (`0.2.0c1`). Ya están implementados Intelligent Radar, Target Accounts V0.2A2, CV Factory V0.2B, ATS Polished Renderer + Layout QA V0.2B1, Email Outreach Core V0.2C, Relationship Memory / Context Bridge V0.2D, Operator Observation Bridge V0.2E y Gmail Read Adapter V0.2E1.

## En 30 segundos

```text
fuentes públicas / importación manual
        ↓
normalizar + deduplicar
        ↓
¿hay una vacante real?
   ↙               ↘
 SÍ                 NO
 ↓                   ↓
job match       target-account affinity
        ↘           ↙
¿qué sabemos de esta empresa y de la relación previa?
        ↓
WATCH / FOLLOW_UP / RESEARCH_CONTACT / PREPARE_SPECULATIVE
        ↓
usar sólo evidencia real
        ↓
preparar CV / investigar contacto / revisar contexto
        ↓
decisión humana
        ↓
acción explícita + historial auditable
```

No intenta decidir la carrera de una persona con un score mágico. La idea es sacar trabajo repetitivo del medio y dejar visibles las decisiones importantes.

## El problema

Una búsqueda laboral real es bastante más complicada que una lista de avisos:

- la misma oferta aparece varias veces;
- una buena empresa puede no tener una vacante exacta hoy;
- un trabajo puede servir para ingreso inmediato sin ser el destino profesional final;
- un CV genérico dice poco;
- una IA puede rellenar huecos con experiencia que nunca existió;
- encontrar un recruiter no significa que haya que escribirle;
- aprobar un borrador no significa autorizar un envío;
- si el sistema olvida a quién ya contactaste, vuelve a mandar mensajes, contradice procesos abiertos y quema relaciones útiles;
- una observación externa no debería poder modificar estado sin mostrar antes exactamente qué produciría.

Opportunity OS trata esos problemas por separado y los conecta con contratos explícitos.

## Qué hace hoy

| Slice | Estado | Para qué sirve |
| --- | --- | --- |
| **V0.2A — Intelligent Radar** | ✅ | descubre, normaliza, puntúa y prioriza vacantes reales |
| **V0.2A2 — Target Accounts** | ✅ | detecta organizaciones de alta afinidad aunque no exista una vacante activa |
| **V0.2B — CV Factory** | ✅ | genera CVs ATS usando sólo hechos y evidencia verificados |
| **V0.2B1 — ATS Polished Renderer + Layout QA** | ✅ | mejora jerarquía visual, controla layout y conserva el contrato ATS/provenance |
| **V0.2C — Email Outreach Core** | ✅ | separa contacto, draft, aprobación y envío en estados auditables |
| **V0.2D — Relationship Memory / Context Bridge** | ✅ | recuerda contactos, procesos, cooldowns y contexto sin exponer el CRM privado |
| **V0.2E — Operator Observation Bridge** | ✅ | permite previsualizar, confirmar e importar hechos externos normalizados al estado local |
| **V0.2E1 — Gmail Read Adapter** | ✅ | traduce evidencia seleccionada de Gmail a `OperatorObservation` sin importarla automáticamente |

Ver [`ROADMAP.md`](ROADMAP.md).

## Vacante, empresa y relación no son lo mismo

```text
ACTIVE_POSTING
= existe una requisición publicada de verdad

TARGET_ACCOUNT
= una organización que vale la pena seguir o investigar

RELATIONSHIP_CONTEXT
= qué pasó antes con esa empresa, sin convertir el CRM en datos públicos

SPECULATIVE_OUTREACH
= una recomendación para preparar un contacto espontáneo honesto
```

Una empresa puede ser un target fuerte por sector, ubicación, estabilidad, adopción tecnológica, canal de CV o afinidad con las capacidades del candidato.

Pero `TARGET_ACCOUNT` nunca cuenta como vacante.

## Target Accounts V0.2A2

Cada empresa se evalúa con un score distinto al job match:

| Componente | Peso |
| --- | ---: |
| Capability / sector affinity | 30% |
| Proximity / logistics | 20% |
| Scale / stability | 15% |
| Innovation / AI / digital | 15% |
| Contactability | 10% |
| Current hiring signal | 10% |

Las señales numéricas requieren **provenance y fecha de observación**. La falta de una vacante activa baja sólo la señal de contratación; no elimina automáticamente una empresa útil.

Con V0.2D, el selector puede devolver:

```text
FOLLOW_UP
PREPARE_SPECULATIVE
RESEARCH_CONTACT
WATCH
```

Nunca devuelve `SEND`.

## Relationship Memory V0.2D

La memoria responde una pregunta muy simple que cambia mucho el comportamiento:

> **¿qué sabemos ya de nuestra relación con esta empresa antes de recomendar otro contacto?**

El runtime privado usa SQLite con dos ideas juntas:

```text
estado actual
+
eventos append-only
```

El estado actual permite responder rápido. Los eventos permiten reconstruir qué pasó sin reescribir la historia.

El sistema distingue, entre otras cosas:

- empresa nunca contactada;
- contacto reciente con cooldown activo;
- respuesta recibida;
- proceso de selección abierto;
- proceso cerrado;
- contacto verificado y disponible;
- contacto conocido pero `HELD`, es decir, guardado deliberadamente para no usarlo ahora;
- relación histórica que hoy aparece como `DORMANT`;
- razón nueva que justifica considerar un `FOLLOW_UP`.

### `DORMANT` no es una escritura escondida

`DORMANT` es un estado **derivado por el Context Bridge**. No se guarda mágicamente en SQLite porque pasaron algunos días y una lectura nunca modifica el CRM.

Eso importa porque consultar el estado no debería cambiarlo.

### `FOLLOW_UP` no significa “mandar otro mail”

Para recomendar `FOLLOW_UP` hacen falta tres cosas:

1. historial previo real;
2. timing mínimo cumplido;
3. una razón nueva y explícita.

Que haya pasado tiempo, por sí solo, no alcanza.

### Context Bridge: útil sin volcar el CRM

El Context Bridge expone una proyección chica y redactada:

```text
account_id
relationship_state
last_contacted_at
last_reply_at
cooldown_until
cooldown_active
open_process
usable_contact_count
held_contact_count
preferred_contact_type
last_reason
recommended_relationship_action
reason
```

Por defecto no expone nombres de contactos, emails, cuerpos de mensajes, IDs de proveedor, notas privadas ni payloads crudos.

La base real queda fuera del repo:

```text
state/relationships.local.sqlite3
```

Y esta slice **no importa automáticamente Gmail, Apollo ni el CRM**. Tampoco busca contactos, consume créditos o sincroniza proveedores.

## Operator Observation Bridge V0.2E

V0.2E agrega una frontera provider-neutral para traer un hecho autorizado al estado local sin darle autoridad al proveedor sobre el dominio.

```text
Observe → preview → confirm → import local fact
```

El flujo concreto es:

```text
OperatorObservation
        ↓
normalización determinista
        ↓
ObservationPreview
        ↓
preview_sha256 exacto
        ↓
confirmación humana de ese hash
        ↓
RelationshipEvent
        ↓
Relationship Memory
```

El preview es un **dry-run** contra el estado actual y usa las mismas reglas de transición y cronología que el import real. No escribe cuentas, contactos ni eventos.

La confirmación queda ligada al hash exacto de la observación normalizada y del estado relevante. Si el estado cambia antes del primer import, el preview viejo queda inválido. Un reintento exactamente idéntico después de un import exitoso devuelve `ALREADY_IMPORTED` sin duplicar el evento. Reutilizar la misma identidad con otra semántica falla cerrado como conflicto.

Los hechos soportados en esta slice son:

```text
CONTACT_VERIFIED
MESSAGE_SENT
REPLY_RECEIVED
PROCESS_OPENED
PROCESS_UPDATED
PROCESS_CLOSED
```

`MESSAGE_SENT` sólo puede convertirse en historial de relación `CONTACTED`. No fabrica un receipt del Outreach Core ni saltea la cadena draft → approval → SendRequest → SendGate → provider success.

**An imported observation is evidence about what happened; it is not authority to make something happen.**

V0.2E no lee proveedores por sí mismo, no llama Apollo, no hace HTTP desde `app/operator_bridge`, no crea drafts y no manda mensajes. Los adapters permanecen separados del bridge.

## Gmail Read Adapter V0.2E1

V0.2E1 agrega una primera integración real de proveedor sin darle autoridad de escritura.

```text
selected Gmail message/thread
        ↓
Gmail Read Adapter
        ↓
OperatorObservation
        ↓
STOP
```

Después, si el operador quiere incorporar ese hecho a la memoria, usa el flujo V0.2E por separado:

```text
preview → human confirm → import local fact
```

El adapter sólo consulta un `message_id` o `thread_id` explícitamente seleccionado y conserva metadata mínima: IDs de Gmail, fecha, labels y headers allowlisted. No persiste bodies, raw MIME, attachments ni payloads crudos.

En esta primera versión sólo produce observaciones cuando la evidencia de transporte es fuerte:

- `MESSAGE_SENT`: mensaje confirmado en `SENT`, enviado desde una dirección propia a un destinatario externo;
- `REPLY_RECEIVED`: thread con un mensaje saliente previo y una respuesta entrante estrictamente posterior.

Los casos ambiguos fallan cerrados. Un asunto `Re:` no alcanza para inventar una respuesta ni un estado de proceso.

**Gmail Read Adapter does not create drafts.**
**Gmail Read Adapter does not send.**
**Gmail Read Adapter does not import Relationship Memory.**

La ruta local `POST /api/v1/adapters/gmail/observe` está ausente por defecto y sólo aparece con `OPPORTUNITY_GMAIL_READ_ENABLED=true`. Habilitarla no configura OAuth ni crea un cliente real por arte de magia: el runtime debe inyectar explícitamente un servicio autorizado.

## La evidencia manda

El radar de vacantes mantiene separadas:

- **CAREER** — cuánto empuja una oportunidad hacia una dirección profesional;
- **INCOME_NOW** — qué tan viable es como ingreso cercano;
- **CONFIDENCE** — qué tan confiables son los datos usados.

Confidence no es fit. La falta de información baja confianza; no se transforma silenciosamente en un dato negativo sobre la persona.

La **CV Factory** tampoco debería poder escribir algo que el candidato no pueda defender después.

```text
Radar-selected opportunity
-> verified private facts
-> evidence selection
-> provenance-backed CV model
-> ClaimValidator
-> ATS Polished Renderer (ats-pdf-v2)
-> Layout QA
-> reproducible ApplicationPacket
```

V0.2B1 mantiene el PDF **A4, one-column, selectable-text y con fuentes Helvetica estándar**, pero agrega una jerarquía visual más clara y una sola tonalidad de acento no semántica. `Layout QA` mide page count, utilización aproximada, tamaño mínimo de cuerpo, wrapping del headline y presencia de texto extraíble antes de permitir el `ApplicationPacket`.

La presentación no gana autoridad sobre la evidencia: **unsupported target skills remain gaps**. Un requisito de una vacante no aparece como experiencia sólo porque mejoraría el match visual o lexical.

Puede seleccionar, ordenar u omitir información. No inventa años, empleadores, títulos, métricas, herramientas o proyectos.

Los datos privados permanecen locales:

```text
profile/master_facts.local.yaml
profile/evidence_catalog.local.yaml
artifacts/applications/<application_id>/cv.pdf
```

## Contactar no es spamear

Prioridad del core de outreach:

```text
email publicado en la vacante
-> canal oficial Careers / HR
-> recruiter verificado
-> formulario / ruta manual
```

Después:

```text
ApplicationPacket
-> verified contact
-> OutreachBrief
-> DraftSnapshot
-> ApprovalRecord
-> explicit SendRequest
-> SendGate
-> provider SendReceipt
-> append-only ledger
```

Draft, aprobación y envío son cosas distintas.

### Hard release boundaries

Estas garantías forman parte del release contract testeado:

- **CV Factory does not send email and does not submit applications.**
- **Opportunity OS does not create Gmail drafts automatically.**
- **Approval is not a send command.**

Relationship Memory tampoco agrega una excepción: recordar que existe un contacto o recomendar `FOLLOW_UP` no autoriza un draft ni un envío.

Operator Observation Bridge tampoco agrega una excepción: confirmar un import local no es una aprobación de outreach ni un permiso de envío.

Gmail Read Adapter tampoco agrega una excepción: leer un mensaje o producir un `OperatorObservation` no autoriza una mutación ni un envío.

Un proveedor debe confirmar éxito antes de registrar `SENT`.

## Probado con uso real, sin vender humo

El flujo del operador ya se usó como smoke test en una candidatura real:

```text
oportunidad
→ evidencia
→ CV
→ contacto publicado
→ draft Gmail
→ revisión humana
→ instrucción explícita
→ envío confirmado
```

Eso no significa que todo el recorrido esté automatizado end-to-end. El core determinista y las herramientas del operador siguen siendo capas separadas.

V0.2D permite recordar contexto. V0.2E agrega un contrato seguro para importar observaciones normalizadas. V0.2E1 puede leer evidencia seleccionada de Gmail, pero **no sincroniza todo el mailbox, no importa automáticamente y no agrega autoridad de envío**.

## Arquitectura

```text
PUBLIC JOB SOURCES / MANUAL IMPORT
                ↓
          OPPORTUNITY RADAR
                ↓
CAREER / INCOME_NOW / CONFIDENCE
                ↓
           CV FACTORY
                ↓
        ApplicationPacket
                ↓
          OUTREACH CORE

PRIVATE / SOURCED TARGET REGISTRY
                ↓
        TARGET ACCOUNT RADAR
                ↓
account affinity + confidence
                ↓
       RELATIONSHIP CONTEXT
                ↓
WATCH / FOLLOW_UP / RESEARCH_CONTACT / PREPARE_SPECULATIVE

PRIVATE RELATIONSHIP SQLITE
current state + append-only events
                ↑
         RELATIONSHIP SERVICE
                ↑
       OPERATOR OBSERVATION BRIDGE
   preview → exact confirm → local import
                ↑
        OperatorObservation
                ↑
   selected Gmail read-only evidence
```

## Fuentes de vacantes soportadas

- **Remotive**;
- **Greenhouse Job Board API**;
- **Lever Postings API**;
- **Ashby Public Job Posting API**;
- **manual import**.

Una fuente caída no invalida las demás.

## Quick start

Requires **Python 3.12+**.

```bash
python -m venv .venv
# activate the environment for your shell
python -m pip install -e ".[dev]"
cp profiles/example_profile.yaml profile.local.yaml
cp sources/example_sources.yaml sources.local.yaml
cp targets/example_targets.yaml targets.local.yaml
uvicorn app.main:app --reload
```

Run verification:

```bash
python -m pytest -v
python -m compileall app
```

## Local configuration

```text
OPPORTUNITY_DB_PATH=opportunities.db
OPPORTUNITY_PROFILE_PATH=profile.local.yaml
HTTP_TIMEOUT_SECONDS=10
OPPORTUNITY_TAXONOMY_PATH=
OPPORTUNITY_ALIAS_REGISTRY_PATH=data/skill_aliases.yaml
OPPORTUNITY_SOURCES_PATH=sources.local.yaml
OPPORTUNITY_TARGETS_PATH=targets.local.yaml
OPPORTUNITY_RELATIONSHIPS_PATH=state/relationships.local.sqlite3
OPPORTUNITY_OPERATOR_IMPORT_ENABLED=false
OPPORTUNITY_GMAIL_READ_ENABLED=false
```

Si el archivo de Relationship Memory no existe, Opportunity OS usa una memoria vacía y **no crea la base sólo por arrancar o consultar el API**.

Las rutas de Operator Observation Bridge están ausentes por defecto. Activar `OPPORTUNITY_OPERATOR_IMPORT_ENABLED=true` sólo registra el bridge local. No habilita Gmail, Apollo, web research ni ningún proveedor. Si se habilita el bridge pero la base de Relationship Memory no existe, los endpoints operator devuelven `503 relationship_storage_unavailable` sin crearla silenciosamente.

La ruta Gmail Read también está ausente por defecto. `OPPORTUNITY_GMAIL_READ_ENABLED=true` registra únicamente la frontera local read-only; sin un `GmailReadService` autorizado e inyectado responde `503 gmail_read_unavailable`.

## HTTP API

Siempre disponible según las demás dependencias locales:

```text
GET  /health
GET  /api/v1/opportunities
GET  /api/v1/opportunities/{id}
POST /api/v1/opportunities/manual
POST /api/v1/ingest/remotive
POST /api/v1/assessments/{opportunity_id}
POST /api/v1/radar/run
POST /api/v1/targets/radar/run
GET  /api/v1/relationships/context
GET  /api/v1/relationships/{account_id}/context
```

Con `OPPORTUNITY_OPERATOR_IMPORT_ENABLED=true`:

```text
POST /api/v1/operator/observations/preview
POST /api/v1/operator/observations/import
```

Con `OPPORTUNITY_GMAIL_READ_ENABLED=true`:

```text
POST /api/v1/adapters/gmail/observe
```

Las rutas de Relationship Memory siguen siendo **read-only y redactadas**. V0.2E no agrega `POST`, `PUT`, `PATCH` ni `DELETE` bajo `/api/v1/relationships/...`.

V0.2B y V0.2C tampoco agregan endpoints públicos para CV/outreach: esas boundaries siguen locales.

## Privacy by default

- no committed credentials;
- no perfil personal público;
- no CV real tracked por defecto;
- facts/evidence privados gitignored;
- targets reales gitignored;
- Relationship Memory real en storage local/gitignored;
- datos reales de recruiters/contactos fuera del core público;
- Context Bridge redactado por defecto;
- `OperatorObservation` no admite body, raw payload ni metadata libre;
- Gmail Read conserva sólo metadata allowlisted y no persiste bodies/raw MIME/tokens;
- el bridge no persiste mailbox dumps;
- outreach state local;
- errores externos sanitizados;
- unknown facts permanecen unknown;
- claims numéricos/títulos/fechas requieren soporte verificable.

Los ejemplos y tests públicos usan identidades ficticias. El repo publica contratos y comportamiento; no el CRM real de una persona.

## Diseño y planes

```text
docs/superpowers/specs/2026-08-28-opportunity-os-v0.1-design.md
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2a-intelligent-radar-design.md
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2a-multi-intent-amendment.md
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2-target-accounts-speculative-outreach-amendment.md
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2b-cv-factory-design.md
docs/superpowers/specs/2026-08-29-opportunity-os-v0.2b1-ats-polished-renderer-design.md
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2c-email-outreach-design.md
docs/superpowers/specs/2026-08-29-opportunity-os-v0.2d-relationship-memory-context-bridge-design.md
docs/superpowers/specs/2026-08-29-opportunity-os-v0.2d-dormant-state-amendment.md
docs/superpowers/specs/2026-08-29-opportunity-os-v0.2e-operator-observation-bridge-design.md
docs/superpowers/specs/2026-08-29-opportunity-os-v0.2e-operator-observation-bridge-approval-amendment.md
docs/superpowers/specs/2026-08-29-opportunity-os-v0.2e1-gmail-read-adapter-design.md

docs/superpowers/plans/2026-08-28-opportunity-os-v0.2a2-target-accounts.md
docs/superpowers/plans/2026-08-29-opportunity-os-v0.2b1-ats-polished-renderer.md
docs/superpowers/plans/2026-08-29-opportunity-os-v0.2d-relationship-memory-context-bridge.md
docs/superpowers/plans/2026-08-29-opportunity-os-v0.2e-operator-observation-bridge.md
docs/superpowers/plans/2026-08-29-opportunity-os-v0.2e1-gmail-read-adapter.md
```

## Próximo bloque

La siguiente expansión validada es diseñar un **conversation-provider adapter** para CRM personal/profesional. WhatsApp es un **candidato** prioritario, pero todavía no está implementado y debe respetar la misma frontera: observar primero, importar sólo mediante V0.2E y no ganar autoridad de envío por defecto.

También queda pendiente un classifier separado para emails de proceso (`PROCESS_OPENED`, `PROCESS_UPDATED`, `PROCESS_CLOSED`) con política explícita de evidencia/confianza.

La misma regla sigue vigente: **observar y preparar puede automatizarse; una acción externa irreversible necesita intención humana inequívoca.**

## License

MIT