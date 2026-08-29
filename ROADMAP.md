# Opportunity OS — Roadmap

Opportunity OS no apunta a ser un autopilot que “consigue trabajo”. Apunta a que una persona vea mejor el mercado, repita menos tareas y pueda auditar cada decisión importante.

La regla para agregar features es simple:

> automatizar lo repetitivo, conservar evidencia, y dejar la decisión humana donde una acción cambia algo afuera del sistema.

## Estado actual

### ✅ V0.2A — Intelligent Radar

Ya implementado.

- ingesta desde fuentes públicas y manual import;
- normalización y deduplicación;
- candidate tracks;
- scoring separado de `CAREER`, `INCOME_NOW` y `CONFIDENCE`;
- selector diario determinista;
- provenance y manejo explícito de información faltante.

### ✅ V0.2A2 — Target Accounts

Implementado en esta slice.

- `TargetAccount` separado de `Opportunity`;
- registry YAML público/privado con validación estricta;
- señales de afinidad con provenance y fecha de observación;
- score independiente de capability/sector, proximity, scale/stability, innovation, contactability y hiring;
- selección del mejor candidate track sin mezclar evidencia entre tracks;
- confidence sensible a freshness;
- cooldown por organización;
- recomendaciones `WATCH`, `RESEARCH_CONTACT` y `PREPARE_SPECULATIVE`;
- endpoint read-only `POST /api/v1/targets/radar/run`;
- ejemplos públicos ficticios y `targets.local.yaml` privado/gitignored.

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

Ya implementado.

- facts y evidence privados/verificados;
- selección de evidencia por track;
- `ClaimValidator` fail-closed;
- CV ATS reproducible;
- `ApplicationPacket` con hashes y gaps visibles;
- guardas para que proyectos, empleos, métricas y tecnologías no se mezclen ni inventen.

### ✅ V0.2C — Email Outreach Core

Ya implementado.

- resolución de contacto permitido;
- `OutreachBrief`;
- identidad exacta del draft;
- aprobación ligada al contenido exacto;
- `SendRequest` separado de approval;
- `SendGate`;
- receipts idempotentes;
- ledger append-only;
- privacy guards.

El flujo del operador ya fue probado en uso real, pero la integración end-to-end entre el core determinista y las herramientas externas todavía puede hacerse más directa.

---

## NEXT — Relationship memory / Context Bridge

Este bloque surge de una limitación práctica: descubrir un buen contacto sirve poco si el sistema olvida al día siguiente que ya se habló con esa persona o empresa.

La memoria real debe ser **privada** y responder preguntas operativas simples:

- ¿ya contactamos a esta empresa?;
- ¿por qué canal?;
- ¿qué rol o intención motivó el contacto?;
- ¿hubo respuesta?;
- ¿hay un proceso abierto?;
- ¿hasta cuándo corre el cooldown?;
- ¿hay otro contacto técnico valioso que conviene guardar pero no usar todavía?;
- ¿apareció una razón nueva y concreta para retomar la conversación?

Contrato privado de referencia:

```text
CareerContact
- company
- person
- role
- contact_type
- verification_status
- verification_source
- observed_at
- affinity_reason
- last_contacted_at
- cooldown_until
- relationship_state
- notes
```

Los emails reales, nombres de contactos, mailbox exports, procesos y notas privadas **no pertenecen al repositorio público**.

El core público puede definir contratos y fixtures ficticios. La instancia real debe vivir en storage local/privado.

### Integración con Target Accounts

El selector V0.2A2 ya acepta una abstracción `OutreachHistory.last_contacted_at(account_id)` y aplica cooldown. El próximo slice debe reemplazar esa memoria mínima por un contexto más rico sin darle autoridad para enviar nada.

```text
empresa detectada
        ↓
¿hay proceso/contacto previo?
        ↓
SÍ -> leer estado + cooldown + última razón
NO -> resolver canal de contacto
        ↓
recomendar WATCH / FOLLOW_UP / RESEARCH_CONTACT / PREPARE
```

La memoria no autoriza acciones externas. Sólo evita repetición, contradicciones y spam.

---

## AFTER — Operator integration

El core ya representa `ApplicationPacket`, drafts, approvals, send gates y receipts. Falta cerrar mejor el puente con herramientas reales sin romper esa separación.

Objetivo:

```text
core determinista
↕
operator / connected tools
↕
Gmail, contact discovery, public research
```

El operador puede ejecutar una acción externa sólo después de una intención humana inequívoca.

No se planea meter credenciales de Gmail/Apollo dentro del core ni convertir proveedores externos en dependencias obligatorias.

---

## LATER — Monitoring y follow-up

Con Target Accounts implementado y relationship memory como próximo bloque, el sistema podrá producir recordatorios útiles en vez de más volumen:

- apareció una vacante nueva en una empresa de alta afinidad;
- terminó un cooldown;
- un proceso abierto lleva demasiado tiempo sin cambio;
- una fuente cambió o desapareció;
- una empresa target empezó a contratar una familia de roles relevante.

El principio sigue siendo el mismo: **notificar cuando cambió algo útil**, no generar actividad por generar actividad.

---

## Fuera de scope por diseño

Opportunity OS no tiene como objetivo:

- aplicar automáticamente a todo lo que encuentre;
- completar declaraciones legales sensibles sin intervención humana;
- resolver CAPTCHAs o evadir controles de sitios;
- inventar experiencia o “optimizar” claims falsos;
- comprar/enriquecer contactos sin control de costo;
- mandar campañas masivas de cold email;
- publicar el perfil privado, CRM o historial de una persona.

## Cómo leer este roadmap

`NEXT` significa: próximo problema validado y candidato inmediato a diseño/implementación.

`AFTER` significa: dirección clara, pero debe hacerse después del bloque NEXT.

`LATER` significa: dirección útil, todavía no una promesa de release.

El roadmap puede cambiar con evidencia de uso real. Los límites de privacidad, provenance y aprobación humana no deberían hacerlo.
