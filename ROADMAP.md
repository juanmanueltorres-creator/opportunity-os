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

Relationship Memory no importa automáticamente Gmail, Apollo, el vault ni un CRM existente. Esos datos reales permanecen privados y sólo pueden entrar mediante una futura integración autorizada.

---

## NEXT — Operator integration

Ahora el core ya sabe representar oportunidades, targets, evidencia, drafts, approvals, receipts y memoria de relaciones. El siguiente problema es conectar observaciones reales **sin destruir esas fronteras**.

Objetivo:

```text
Gmail / contact discovery / public research / private workspace
                       ↓
              authorized adapter
                       ↓
          normalized observation/event
                       ↓
            deterministic core state
```

El adapter debería poder traducir hechos autorizados, por ejemplo:

- “este mensaje fue enviado y el proveedor lo confirmó”;
- “este recruiter respondió”;
- “este proceso cambió de estado”;
- “este contacto fue verificado en esta fecha”;
- “apareció una nueva vacante que constituye una razón nueva”.

Pero debe conservar estas reglas:

- no copiar credenciales al core;
- no convertir Gmail/Apollo en dependencias obligatorias;
- no inventar contactos ni estados;
- no consumir créditos sin control explícito;
- no traducir una observación ambigua en una acción irreversible;
- idempotencia y provenance para cada evento importado;
- fallas de un proveedor no deben corromper la memoria local.

### Primer slice recomendado

Empezar por **importación explícita de observaciones**, no por autopilot.

```text
operator obtiene dato autorizado
        ↓
preview normalizado
        ↓
humano confirma importación
        ↓
RelationshipService / Outreach ledger
```

Eso da mucho valor sin convertir Opportunity OS en una campaña automática.

---

## AFTER — Monitoring y follow-up

Con Target Accounts y Relationship Memory ya implementados, el sistema puede producir recordatorios útiles en vez de más volumen:

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
- convertir el paso del tiempo en permiso automático para contactar de nuevo.

## Cómo leer este roadmap

`NEXT` significa: próximo problema validado y candidato inmediato a diseño/implementación.

`AFTER` significa: dirección clara, pero debe hacerse después del bloque NEXT.

`LATER` significa: dirección útil, todavía no una promesa de release.

El roadmap puede cambiar con evidencia de uso real. Los límites de privacidad, provenance y aprobación humana no deberían hacerlo.
