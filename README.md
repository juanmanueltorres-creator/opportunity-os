# Opportunity OS

**Buscar trabajo no debería ser abrir veinte pestañas, mandar el mismo CV a todo y esperar.**

Opportunity OS organiza ese problema como un sistema: encuentra oportunidades, separa lo que sirve para carrera de lo que sirve para ingresos, detecta empresas que vale la pena tener en radar aunque hoy no publiquen una vacante, arma CVs sólo con evidencia verificable y mantiene los contactos bajo reglas explícitas.

Open source, auditable y deliberadamente humano en los pasos que importan.

> **Estado actual:** prerelease V0.2C (`0.2.0c1`) + Target Accounts V0.2A2. El radar de vacantes, el radar de empresas, la CV Factory y el core de outreach existen. Relationship Memory / Context Bridge es el próximo bloque del roadmap.

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
¿sirve para carrera, ingreso ahora o seguimiento?
        ↓
usar sólo evidencia real
        ↓
preparar CV / investigar contacto
        ↓
revisión humana
        ↓
acción explícita + historial auditable
```

No intenta decidir la carrera de una persona con un score mágico. La idea es sacar trabajo repetitivo del medio y dejar visibles las decisiones importantes.

## El problema

Una búsqueda laboral real es más complicada que una lista de avisos:

- la misma oferta aparece varias veces;
- una buena empresa puede no tener una vacante exacta hoy;
- un trabajo puede servir para ingreso inmediato sin ser el destino profesional final;
- un CV genérico dice poco;
- una IA puede rellenar huecos con experiencia que nunca existió;
- encontrar un recruiter no significa que haya que escribirle;
- aprobar un borrador no significa autorizar un envío;
- si el sistema olvida contactos anteriores, termina repitiendo mensajes y quemando relaciones.

Opportunity OS trata esas cosas como problemas distintos.

## Qué hace hoy

| Slice | Estado | Para qué sirve |
| --- | --- | --- |
| **V0.2A — Intelligent Radar** | ✅ | descubre, normaliza, puntúa y prioriza vacantes reales |
| **V0.2A2 — Target Accounts** | ✅ | detecta organizaciones de alta afinidad aunque no exista una vacante activa |
| **V0.2B — CV Factory** | ✅ | genera CVs ATS usando sólo hechos y evidencia verificados |
| **V0.2C — Email Outreach Core** | ✅ | separa contacto, draft, aprobación y envío en estados auditables |
| **Relationship Memory / Context Bridge** | 🧭 NEXT | recordar procesos, contactos, cooldowns y razones para retomar una relación |

Ver [`ROADMAP.md`](ROADMAP.md).

## Vacante, empresa y contacto no son lo mismo

```text
ACTIVE_POSTING
= existe una requisición publicada de verdad

TARGET_ACCOUNT
= una organización que vale la pena seguir o investigar

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

El selector puede recomendar únicamente:

```text
PREPARE_SPECULATIVE
RESEARCH_CONTACT
WATCH
```

Nunca devuelve `SEND`.

### Cooldown y anti-spam

- cooldown por organización: 30 días por defecto;
- un contacto reciente fuerza `WATCH`;
- sin canal usable, prioriza `RESEARCH_CONTACT`;
- afinidad/confianza insuficientes terminan en `WATCH`;
- no adivina emails;
- no diseña ráfagas a varios recruiters;
- una recomendación no autoriza una acción externa.

Los targets reales viven en `targets.local.yaml`, que está gitignored. El repo público trae sólo `targets/example_targets.yaml` con fixtures ficticios.

## Tres preguntas, no un solo score

El radar de vacantes mantiene separadas:

- **CAREER** — cuánto empuja una oportunidad hacia una dirección profesional;
- **INCOME_NOW** — qué tan viable es como ingreso cercano;
- **CONFIDENCE** — qué tan confiables son los datos usados.

```text
CAREER       31 / 100
INCOME_NOW   84 / 100
CONFIDENCE   90 / 100

Interpretación:
no es un gran destino de carrera,
pero puede ser una buena oportunidad de ingreso ahora.
```

Confidence no es fit. La falta de información baja confianza; no se transforma silenciosamente en un dato negativo sobre la persona.

## La evidencia manda

La **CV Factory** no debería poder escribir algo que el candidato no pueda defender después.

```text
Radar-selected opportunity
-> verified private facts
-> evidence selection
-> provenance-backed CV model
-> ClaimValidator
-> ATS PDF
-> reproducible ApplicationPacket
```

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
WATCH / RESEARCH_CONTACT / PREPARE_SPECULATIVE
```

La memoria de relaciones será el puente entre ambos recorridos: recordar qué empresa/persona ya fue contactada, cuándo, por qué y con qué resultado.

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
```

## HTTP API

```text
GET  /health
GET  /api/v1/opportunities
GET  /api/v1/opportunities/{id}
POST /api/v1/opportunities/manual
POST /api/v1/ingest/remotive
POST /api/v1/assessments/{opportunity_id}
POST /api/v1/radar/run
POST /api/v1/targets/radar/run
```

V0.2B y V0.2C no agregan endpoints públicos para CV/outreach: esas boundaries siguen locales. V0.2A2 sí expone un endpoint **read-only de recomendación** para Target Accounts; no crea CV, draft, contacto ni envío.

## Privacy by default

- no committed credentials;
- no perfil personal público;
- no CV real tracked por defecto;
- facts/evidence privados gitignored;
- targets reales gitignored;
- datos reales de recruiters/contactos fuera del core público;
- outreach state local;
- errores externos sanitizados;
- unknown facts permanecen unknown;
- claims numéricos/títulos/fechas requieren soporte verificable.

## Diseño y planes

```text
docs/superpowers/specs/2026-08-28-opportunity-os-v0.1-design.md
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2a-intelligent-radar-design.md
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2a-multi-intent-amendment.md
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2-target-accounts-speculative-outreach-amendment.md
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2b-cv-factory-design.md
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2c-email-outreach-design.md

docs/superpowers/plans/2026-08-28-opportunity-os-v0.2a2-target-accounts.md
```

## License

MIT
