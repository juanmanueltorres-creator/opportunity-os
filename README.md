# Opportunity OS

**Buscar trabajo no debería ser abrir veinte pestañas, mandar el mismo CV a todo y esperar.**

Opportunity OS organiza ese problema como un sistema: encuentra oportunidades, separa lo que sirve para carrera de lo que sirve para ingresos, arma CVs sólo con evidencia verificable y prepara contactos sin inventar vacantes ni mandar mensajes por accidente.

Open source, auditable y deliberadamente humano en los pasos que importan.

> **Estado actual:** prerelease V0.2C (`0.2.0c1`). El radar, la CV Factory y el core de outreach ya existen. Target Accounts y memoria de relaciones están en el roadmap, no en `main` todavía.

## En 30 segundos

```text
fuentes públicas / importación manual
        ↓
normalizar + deduplicar
        ↓
¿sirve para carrera, para ingreso ahora, o para ambas?
        ↓
usar sólo evidencia real del candidato
        ↓
preparar CV verificable
        ↓
resolver un canal de contacto válido
        ↓
crear draft
        ↓
revisión humana
        ↓
orden explícita de envío
        ↓
receipt + historial auditable
```

No intenta decidir la carrera de una persona con un score mágico. El objetivo es sacar trabajo repetitivo del medio y dejar visibles las decisiones importantes.

## El problema que intenta resolver

Una búsqueda laboral real tiene bastante más ruido que un listado de vacantes:

- la misma oferta aparece varias veces;
- hay roles interesantes que no sirven para el momento económico actual;
- hay trabajos útiles para generar ingresos que no son el destino profesional final;
- un CV genérico termina diciendo poco;
- una herramienta de IA puede completar huecos con experiencia que nunca existió;
- encontrar un recruiter no significa que haya que escribirle;
- aprobar un borrador no significa autorizar un envío;
- una empresa puede ser muy interesante aunque hoy no tenga una vacante publicada;
- si no se guarda historial, cada nueva sesión vuelve a empezar de cero.

Opportunity OS trata esas cosas como problemas distintos en vez de mezclarlos en una sola automatización.

## Qué hace hoy

| Slice | Estado | Para qué sirve |
| --- | --- | --- |
| **V0.2A — Intelligent Radar** | ✅ implementado | descubre, normaliza, puntúa y prioriza oportunidades |
| **V0.2B — CV Factory** | ✅ implementado | genera CVs ATS usando sólo hechos y evidencia verificados |
| **V0.2C — Email Outreach Core** | ✅ implementado | controla contacto, draft, aprobación y envío como estados separados |
| **Target Accounts** | 🧭 diseñado / roadmap | detectar empresas valiosas aunque no exista una vacante activa |
| **Relationship memory / Context Bridge** | 🧭 roadmap | recordar contactos, cooldowns, procesos y razones para volver a hablar |

El roadmap público está en [`ROADMAP.md`](ROADMAP.md).

## Tres preguntas, no un solo score

El radar separa tres cosas que suelen confundirse:

- **CAREER** — cuánto empuja una oportunidad hacia la dirección profesional elegida.
- **INCOME_NOW** — qué tan realista es conseguirla y hacerla útil como ingreso en el corto plazo.
- **CONFIDENCE** — qué tan buenos son los datos usados para llegar a esa conclusión.

Ejemplo:

```text
CAREER       31 / 100
INCOME_NOW   84 / 100
CONFIDENCE   90 / 100

Interpretación:
no es un gran destino de carrera,
pero puede ser una buena oportunidad de ingreso ahora.
```

La confianza no es fit. La falta de información baja confianza; no se transforma silenciosamente en un dato negativo sobre la persona.

## La evidencia manda

Opportunity OS no debería poder escribir en un CV algo que el candidato no pueda defender después.

La **CV Factory** parte de hechos privados verificados y módulos de evidencia aprobados. Puede seleccionar, ordenar u omitir información, pero no inventar años de experiencia, empleadores, títulos, métricas, herramientas o proyectos.

```text
Radar-selected opportunity
-> verified private facts
-> evidence selection
-> provenance-backed CV model
-> ClaimValidator
-> ATS PDF
-> reproducible ApplicationPacket
```

Los requisitos se distinguen entre experiencia exacta, alias aprobados, habilidades relacionadas y desconocidos. Una tecnología “parecida” puede aportar contexto; no demuestra experiencia directa con otra herramienta.

## Contactar no es spamear

El core de outreach usa una prioridad simple:

```text
email publicado en la vacante
-> canal oficial de Careers / HR
-> recruiter verificado
-> formulario o ruta manual
```

No adivina direcciones tipo `jobs@empresa.com`.

Una vez preparado el mensaje, **draft, aprobación y envío son eventos diferentes**. Un draft aprobado no puede enviarse sólo por existir: hace falta una instrucción explícita posterior y evidencia de éxito del proveedor antes de registrar `SENT`.

Eso permite mantener idempotencia, trazabilidad y una regla básica: una automatización nunca debería convertir una intención ambigua en una acción externa irreversible.

## Lo que se niega a hacer

- inventar experiencia para mejorar un match;
- presentar una empresa interesante como si tuviera una vacante que no existe;
- mezclar evidencia de perfiles profesionales distintos;
- mandar el mismo mensaje a varios recruiters para “subir probabilidades”;
- considerar un draft aprobado como una orden de envío;
- exponer CVs reales, contactos o historial privado en el repositorio público;
- ocultar gaps o incertidumbre detrás de un score prolijo;
- convertir un máximo diario en una cuota de spam.

## Probado con uso real, sin vender humo

El flujo operativo ya se usó como smoke test en una candidatura real:

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

Eso **no** significa que todo el recorrido esté automatizado end-to-end. El core determinista y las herramientas del operador siguen siendo capas separadas; conectar ambos de forma más directa está en el roadmap.

Ese límite es intencional: primero tiene que ser verificable y seguro; después, cómodo.

## Lo próximo: ver empresas, no sólo avisos

El siguiente bloque diseñado es **Target Accounts**.

La idea es separar claramente:

```text
ACTIVE_POSTING
= una vacante publicada de verdad

TARGET_ACCOUNT
= una organización que vale la pena seguir o investigar

SPECULATIVE_OUTREACH
= una recomendación para preparar un contacto espontáneo honesto
```

Una empresa puede ser un target fuerte por sector, ubicación, estabilidad, adopción tecnológica o afinidad con las capacidades del candidato aunque hoy no tenga un puesto abierto.

Pero `TARGET_ACCOUNT` nunca debe contarse como una vacante.

El diseño completo está en:

```text
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2-target-accounts-speculative-outreach-amendment.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.2a2-target-accounts.md
```

## Technical reference

### V0.2A — Intelligent Radar

El scoring de carrera conserva los pesos originales:

| Component | Weight |
| --- | ---: |
| Core / mandatory skill fit | 40% |
| Role / domain fit | 20% |
| Verified evidence fit | 20% |
| Location / remote fit | 10% |
| Freshness | 10% |

Default CAREER tiers:

```text
HIGH    match >= 78 and confidence >= 75
MEDIUM  match >= 65 and confidence >= 65
STRETCH match >= 55 but below MEDIUM
DISCARD match < 55 or factual hard fail
```

INCOME_NOW usa otra función:

| Component | Weight |
| --- | ---: |
| Verified capability / requirement fit | 35% |
| Logistics / location feasibility | 25% |
| Schedule / work-mode compatibility | 15% |
| Entry friction / formal barrier fit | 15% |
| Freshness / deadline | 10% |

```text
HIGH    viability >= 75 and confidence >= 75
MEDIUM  viability >= 62 and confidence >= 65
LOW     otherwise
```

Los pesos y thresholds son configuración de producto versionada, no una verdad científica.

### Candidate tracks

Los tracks evitan mezclar evidencia incompatible:

```text
tech_geospatial       -> CAREER + INCOME_NOW
gastronomy_operations -> INCOME_NOW
general_operations    -> INCOME_NOW
```

Un CV técnico no puede tomar experiencia de otro track sólo para llenar espacio.

### CV Factory

`CVDocumentModel` mantiene claims visibles y provenance. Antes de renderizar, `ClaimValidator` verifica entre otras cosas:

- que cada claim tenga origen;
- que facts/evidence existan y estén verificados;
- que pertenezcan al track seleccionado;
- que títulos, fechas y métricas coincidan con su fuente;
- que los gaps sigan siendo gaps.

La salida actual es un PDF ATS deliberadamente simple: A4, una columna, texto seleccionable, sin imágenes, iconos, tablas ni skill bars.

Un `ApplicationPacket` exitoso guarda el track, metadata del radar, hashes de fuentes, evidencia seleccionada, gaps, modelo validado, versión del renderer y hashes reproducibles.

### Email outreach core

```text
ApplicationPacket
-> verified contact
-> OutreachBrief
-> DraftSnapshot
-> ApprovalRecord
-> explicit SendRequest
-> SendGate
-> provider receipt
-> append-only ledger
```

`DraftSnapshot` usa identidad semántica: destinatario, asunto, cuerpo, reply target, attachment y hashes relevantes. IDs de Gmail y timestamps no definen el contenido del draft.

Una modificación material invalida la aprobación anterior.

## Daily selector

El modo por defecto es `income_first`, con límites anti-spam:

- máximo 20 oportunidades totales, nunca como cuota;
- sólo HIGH o MEDIUM entran al batch;
- STRETCH no rellena capacidad sobrante;
- máximo 2 oportunidades de la misma empresa por defecto;
- requisiciones ya aplicadas se excluyen;
- duplicados aparecen una sola vez;
- cooldowns son explícitos;
- CAREER fuerte sigue visible aunque el selector priorice ingreso.

Si sólo 7 oportunidades cumplen calidad, el batch contiene 7.

## Architecture

```text
Authorized public sources / manual import
                ↓
Source adapters + isolated failures
                ↓
Normalized Opportunity
                ↓
SQLite persistence + deduplication
                ↓
Versioned enrichment + provenance
                ↓
Candidate tracks
                ↓
Factual eligibility gates
                ↓
CAREER + INCOME_NOW scoring
                ↓
Independent confidence
                ↓
Deterministic daily selector
                ↓
Verified private facts + evidence
                ↓
CV Factory + ClaimValidator
                ↓
ApplicationPacket
                ↓
Verified contact + OutreachBrief
                ↓
DraftSnapshot + ApprovalRecord
                ↓
SendRequest + SendGate
                ↓
Provider receipt + append-only ledger
```

Source-specific payloads stay inside connectors. El scoring, CV preparation y outreach policy no dependen de raw ATS JSON, un taxonomy service vivo, Gmail/Apollo SDKs ni de que un LLM “tenga razón”.

## Sources

V0.2A soporta registros locales construidos desde:

- **Remotive** — public remote-job feed;
- **Greenhouse Job Board API** — public GET job-board data;
- **Lever Postings API** — public published postings;
- **Ashby Public Job Posting API** — public job-board postings;
- **manual import** — para oportunidades provistas por el usuario u otras fuentes no cubiertas.

Una fuente caída no invalida las demás.

## Quick start

Requires **Python 3.12+**.

```bash
python -m venv .venv
# activate the environment for your shell
python -m pip install -e ".[dev]"
cp profiles/example_profile.yaml profile.local.yaml
cp sources/example_sources.yaml sources.local.yaml
uvicorn app.main:app --reload
```

Run verification:

```bash
python -m pytest -v
python -m compileall app
```

Fixtures de tests, CV y outreach no necesitan acceso live a job boards, Gmail, Apollo o taxonomy services.

## Local configuration

```text
OPPORTUNITY_DB_PATH=opportunities.db
OPPORTUNITY_PROFILE_PATH=profile.local.yaml
HTTP_TIMEOUT_SECONDS=10
OPPORTUNITY_TAXONOMY_PATH=
OPPORTUNITY_ALIAS_REGISTRY_PATH=data/skill_aliases.yaml
OPPORTUNITY_SOURCES_PATH=sources.local.yaml
```

Los datos reales permanecen locales y gitignored.

## HTTP API

```text
GET  /health
GET  /api/v1/opportunities
GET  /api/v1/opportunities/{id}
POST /api/v1/opportunities/manual
POST /api/v1/ingest/remotive
POST /api/v1/assessments/{opportunity_id}
POST /api/v1/radar/run
```

V0.2B y V0.2C no agregan endpoints públicos: CV preparation y outreach orchestration permanecen como boundaries internas/locales.

## Privacy by default

- no committed credentials;
- no public personal candidate profile;
- no real CV tracked by default;
- private facts/evidence remain gitignored;
- generated application files are guarded by CI;
- real recruiter/contact data stays outside the public core;
- real outreach state stays local;
- external errors are sanitized;
- unknown facts remain unknown;
- numeric/title/date claims require verified support;
- provider success evidence is required before `SENT`.

Los ejemplos públicos son ficticios. El repo contiene contratos y comportamiento; los datos reales pertenecen a la capa privada del operador.

## Design docs

V0.1:

```text
docs/superpowers/specs/2026-08-28-opportunity-os-v0.1-design.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.1.md
```

V0.2A:

```text
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2a-intelligent-radar-design.md
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2a-multi-intent-amendment.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.2a1-multi-intent-radar-core.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.2a1-self-review-corrections.md
```

Target Accounts / speculative outreach:

```text
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2-target-accounts-speculative-outreach-amendment.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.2a2-target-accounts.md
```

V0.2B:

```text
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2b-cv-factory-design.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.2b-cv-factory.md
```

V0.2C:

```text
docs/superpowers/specs/2026-08-28-opportunity-os-v0.2c-email-outreach-design.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.2c-email-outreach.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.2c-email-outreach-self-review.md
```

## License

MIT
