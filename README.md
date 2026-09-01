# Opportunity OS

**A local-first system for turning job search into an auditable workflow instead of a pile of tabs, generic CVs and forgotten follow-ups.**

Opportunity OS helps discover opportunities, separate real vacancies from interesting target companies, prepare recruiter-ready CVs using only verified evidence, preserve relationship context and keep external actions behind explicit human approval.

> **Automate repetition. Preserve evidence. Keep authority with the operator.**

Current package line: `0.2.0c1` · Python 3.12+ · open source · local/private state stays outside the repository.

---

## What it does

```text
public job sources / manual import
            ↓
 normalize + deduplicate
            ↓
   opportunity radar
      ↙           ↘
real posting     target company
      ↘           ↙
   relationship context
            ↓
 select verified evidence
            ↓
 recruiter-ready CV
            ↓
 outreach brief / draft state
            ↓
      human decision
            ↓
 explicit external action
```

The system does **not** treat every company as a vacancy and does **not** treat every useful contact as permission to send a message.

### Today it can

| Capability | What it is for |
| --- | --- |
| **Opportunity Radar** | ingest, normalize, deduplicate and rank real job postings |
| **Target Accounts** | identify companies worth following even when no matching vacancy is open |
| **Evidence-backed CVs** | build recruiter CVs from verified facts instead of invented tailoring |
| **Relationship Memory** | remember prior contact, replies, open processes, cooldowns and follow-up context |
| **Operator Observation Bridge** | preview and explicitly confirm external facts before importing them into local state |
| **Selective Gmail read** | turn an explicitly selected Gmail message/thread into a constrained observation without mailbox sync |
| **Process Email** | classify one selected inbound Gmail message into bounded ES/EN hiring-process evidence before any local import |
| **Outreach Core** | separate contact resolution, draft identity, approval, send request and send authorization |
| **Search Health** | project local discovery, qualification, outreach and outcome evidence into coverage-aware counts and conversion cohorts |

See [`ROADMAP.md`](ROADMAP.md) for the detailed version history and future work.

---

## Vacancy, company and relationship are different things

```text
ACTIVE_POSTING
= a real published requisition exists

TARGET_ACCOUNT
= the organization is worth following or researching

RELATIONSHIP_CONTEXT
= what already happened with that organization

SPECULATIVE_OUTREACH
= a reason to prepare truthful outreach, not permission to send it
```

That distinction prevents a common failure mode in job-search automation: turning weak signals into fake certainty.

A target company never becomes a vacancy just because it scores well. A past conversation never becomes permission for another message just because enough time passed.

---

## Recruiter CV pipeline

Opportunity OS treats CV generation as a provenance problem before it treats it as a formatting problem.

```text
RadarAssessment
      ↓
EvidenceSelector
      ↓
CVComposer
      ↓
ClaimValidator
      ↓
RecruiterDocumentComposer
      ↓
RecruiterDocumentValidator
      ↓
RenderCV/Typst
      ↓
RecruiterQualityQA
      ↓
ApplicationPacket
```

The canonical recruiter artifact is:

- exactly **one A4 page**;
- text-extractable and ATS-readable;
- rendered with versioned `rendercv-typst-v1`;
- generated only from validated semantic claims;
- deterministic for the same canonical inputs;
- checked for layout failures before it becomes `PREPARED`;
- emitted with real clickable email/web annotations when those claims are verified.

`PREPARED` does **not** mean approved and does **not** mean sent.

### Language is explicit

The application pipeline carries an auditable `LanguageDecision` (`es` / `en`) instead of letting different stages silently choose their own language.

The decision propagates through the application packet, CV and outreach state. Confident language mismatches fail closed rather than producing a mixed-language application by accident.

### The attachment is part of the contract

Outreach is bound to the exact canonical `ApplicationPacket` / `OutreachBrief` that produced it.

Legacy CV renderer artifacts are rejected before outreach. The operator contract deliberately avoids selecting attachments by filename similarity, “latest PDF” or fuzzy matching.

See [`docs/CV_ATTACHMENT_SELECTION.md`](docs/CV_ATTACHMENT_SELECTION.md).

---

## Relationship Memory

Opportunity OS keeps relationship state private and local so every run does not start from zero.

```text
current state
+
append-only events
```

It can distinguish, among other states:

- untouched company;
- contacted company;
- reply received;
- open selection process;
- closed process;
- active cooldown;
- usable vs deliberately held contact;
- a defensible reason to prepare a follow-up.

`FOLLOW_UP` means **there is enough context to consider preparing one**. It never means `SEND`.

The default relationship store is local SQLite:

```text
state/relationships.local.sqlite3
```

Public API projections are redacted and do not expose private contact names, email bodies, provider payloads or personal notes.

---

## External observations: observe first, import second

Provider-specific information does not get authority over the local domain model.

```text
selected external evidence
        ↓
OperatorObservation
        ↓
normalize
        ↓
preview
        ↓
exact preview hash
        ↓
human confirmation
        ↓
RelationshipEvent
        ↓
Relationship Memory
```

The preview is read-only. If relevant state changes before the first import, the old preview becomes stale and fails closed. Exact retries are idempotent.

The current Gmail adapter is intentionally narrow: it reads only an explicitly selected message or thread, keeps allowlisted metadata, discards bodies/raw MIME/attachments and stops at `OperatorObservation`. Import into Relationship Memory remains a separate confirmed action.

> **An imported observation is evidence about what happened; it is not authority to make something happen.**

---

## Process Email

Process Email adds a separate semantic preview for one **selected inbound message**. It does not change the metadata-only Gmail Read contract and it does not create a second write path.

```text
explicit inbound Gmail message
        ↓
transient FULL content
        ↓
deterministic ES/EN signals + evidence preview
        ↓
zero/one candidate OperatorObservation
        ↓
existing Operator Bridge preview
        ↓
explicit human confirm/import
```

The evidence boundary is deliberate:

```text
body access != body persistence
classification != authority
ACK != process open
```

`APPLICATION_ACKNOWLEDGED` means there is explicit evidence that the application was received. It does not open a hiring process. Low-confidence, ambiguous or conflicting evidence produces no candidate mutation, and a rejection cannot fabricate a process close when no open process exists.

Subject, current-message body and evidence spans remain transient. Persisted semantic provenance is limited to bounded classifier/ruleset/classification/reason identifiers. The FULL-content reader is limited to the explicitly selected message, rejects unsupported or oversized content fail-closed, excludes attachments and strips recognized quoted history before classification.

There is no Process Email import route. The preview service has no write method: persistence still goes through the existing Operator Bridge and requires **human confirmation** of the exact preview. The classifier uses deterministic local ES/EN rules, not an external LLM, and does not send, apply or follow up.

The API surface is independently feature-flagged and disabled by default:

```text
OPPORTUNITY_PROCESS_EMAIL_ENABLED=false
```

Process Email does not classify Gmail threads, scan a mailbox, or treat content access as permission to retain source text.

---

## Search Health

Search Health is a **read-only, provenance-aware projection** over the evidence Opportunity OS already has. It reports what can be defended about discovery, qualification, preparation, outreach and outcomes without turning incomplete history into fake precision.

```text
Opportunity Store / Radar evidence
              +
     Outreach / Relationship state
              +
  explicitly imported history
              ↓
      exact reconciliation
              ↓
        Metrics Projection
              ↓
       CLI + aggregate JSON
```

The boundary is explicit:

```text
native history != reconstructed history
missing evidence is not zero
```

Historical observations live in a separate private SQLite store. They never fabricate retrospective `OutreachEvent`, `SendReceipt` or `RelationshipEvent` rows. When native and reconstructed evidence refer to the same exact event, native evidence wins; reconciliation never uses fuzzy company names, subject similarity or nearest timestamps.

Every metric carries a coverage class:

- `COMPLETE` — the declared evidence population for that metric/cohort is complete;
- `PARTIAL` — useful observed evidence exists, but it does not cover the whole population;
- `UNKNOWN` — there is no defensible metric population.

A partial count may be a defensible lower bound. A conversion ratio remains `null` when its denominator or observation cohort cannot be defended. Search Health does not silently render missing evidence as `0` or `0%`.

Generate a report with a fixed as-of boundary:

```bash
python -m app.metrics.report \
  --from 2026-08-01 \
  --as-of 2026-09-01T00:00:00+00:00
```

Optional historical evidence is imported explicitly from an allowlisted private manifest:

```bash
python -m app.metrics.import_history \
  --manifest state/history-import-2026-08.local.json \
  --history-db state/history.local.sqlite3
```

The historical manifest/database and generated `artifacts/metrics/` output are local and gitignored. The aggregate JSON contains metric values, basis, warnings and coverage, but not provider message/thread IDs, contact names, email addresses, subjects, bodies or company-specific private notes.

**Metrics do not grant SEND, APPLY or FOLLOW-UP authority.** Search Health is not a productivity score, success predictor, causal optimizer or automatic follow-up engine.

---

## Offline, reproducible recruiter runtime

Agent runs can use a SHA-bound offline runtime for the canonical recruiter pipeline on Python 3.12 and 3.13.

The runtime bundle:

- is tied to an exact Git commit;
- includes the production wheels required by the recruiter pipeline;
- installs without package indexes using the bundled wheelhouse;
- verifies the canonical `python -m app.application.prepare` path in a fresh runner;
- checks the resulting one-page PDF and `ApplicationPacket`;
- excludes private candidate data and generated real applications.

This exists to make “works in CI” closer to “the exact artifact can execute the real preparation path in a clean environment”.

For the operator workflow, see [`docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md`](docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md).

---

## Supported opportunity sources

Current public/manual ingestion supports:

- **Remotive**;
- **Greenhouse Job Board API**;
- **Lever Postings API**;
- **Ashby Public Job Posting API**;
- **manual import**.

Source failures are isolated: one unavailable source does not invalidate the others.

Contact discovery, Apollo usage and other paid/external providers are deliberately outside the core unless explicitly authorized by an operator workflow.

---

## What it refuses to do

Opportunity OS is not an auto-apply bot.

By design it does not:

- mass-apply to everything it finds;
- invent experience, metrics, dates, titles or technologies;
- guess recruiter emails and treat them as verified;
- turn a target company into a fake active vacancy;
- convert time elapsed into automatic follow-up permission;
- sync or dump an entire Gmail mailbox;
- publish private candidate profiles, CRM state or real recruiter data;
- bypass CAPTCHAs or site controls;
- buy/enrich contacts without explicit cost control;
- turn an imported observation into send authority;
- send cold-email campaigns by default.

Unknown remains unknown. Missing evidence remains visible as a gap.

---

## Architecture

```text
Remotive / Greenhouse / Lever / Ashby / manual
                    ↓
             ingestion + normalization
                    ↓
               Opportunity Store
                    ↓
              Opportunity Radar
                    ↓
             RadarAssessment
                    ↓
      EvidenceSelector → CV pipeline
                    ↓
             ApplicationPacket
                    ↓
               Outreach Core

Target Registry → Target Radar
                    ↓
           Relationship Context
                    ↓
WATCH / FOLLOW_UP / RESEARCH_CONTACT / PREPARE_SPECULATIVE

selected Gmail evidence
        ↓
OperatorObservation
        ↓
preview → confirm → local import
        ↓
Relationship Memory (SQLite)

selected inbound Gmail message
        ↓
transient FULL content → deterministic Process Email classification
        ↓
zero/one OperatorObservation → existing Operator Bridge preview

native state + reconstructed history
        ↓
read-only Search Health projection
        ↓
CLI + aggregate JSON
```

Core stack:

`Python 3.12+` · `FastAPI` · `Pydantic 2` · `SQLite` · `httpx` · `RenderCV / Typst` · `PyMuPDF` · `PyPDF` · `pytest`

---

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

Verification:

```bash
python -m pytest -v
python -m compileall app
```

Useful API routes include:

```text
GET  /health
GET  /api/v1/opportunities
POST /api/v1/opportunities/manual
POST /api/v1/radar/run
POST /api/v1/targets/radar/run
GET  /api/v1/relationships/context
```

Operator-import, Gmail-read and Process Email preview routes are disabled by default and appear only when their explicit feature flags are enabled. Search Health V1 is CLI + JSON only; it does not add a metrics API route.

---

## Privacy by default

Real operator state is intentionally kept outside the public repository.

- local profile, source and target files are gitignored;
- real CV facts/evidence are private;
- recruiter/contact data stays outside the public core;
- Relationship Memory is local SQLite;
- historical Search Health evidence and generated reports are local/gitignored;
- Gmail metadata observations retain only constrained metadata;
- Process Email source body/subject/evidence remains transient and is not persisted by the classifier path;
- provider errors are sanitized;
- examples and public tests use fictional identities;
- CI includes private/generated-file guards.

The repository publishes the contracts and behavior of the system, not one person's CRM.

---

## Verification and reliability

The project uses regression-heavy CI rather than treating a successful render as enough evidence.

Current verification includes:

- pytest suite;
- Python compilation;
- whitespace/diff checks;
- private/generated-file guard;
- recruiter PDF visual previews;
- one-page / extractable-text / clickable-link checks;
- offline runtime build and fresh-runner verification for Python 3.12 and 3.13.

Search Health adds regression coverage for strict historical imports, read-only source access, exact reconciliation, native evidence precedence, coverage propagation, conversion cohorts, deterministic JSON and aggregate-output privacy.

Process Email adds regressions for one-message FULL content handling, MIME/size failures, bilingual classification, false-positive guards, relationship-aware projection, stale previews, idempotent confirmed import and source-text privacy in local SQLite.

Recent production-path bugs — including a missing runtime PDF dependency, `3D` being misread as a numeric metric, language drift and legacy CV attachment selection — were turned into regression tests before their fixes were merged.

---

## Compatibility and operator contract

The product-first README keeps the historical public contract explicit so release tests and operator automation do not depend on prose that disappeared during an editorial rewrite.

- **V0.2B — CV Factory**: CV Factory does not send email and does not submit applications. It uses `profile/master_facts.local.yaml` and `profile/evidence_catalog.local.yaml`; the canonical recruiter output is `artifacts/applications/<application_id>/cv.pdf` inside an `ApplicationPacket`.
- **V0.2B1 — ATS Polished Renderer + Layout QA**: the compatibility renderer remains `ats-pdf-v2`, uses a one-column ATS-safe layout, and unsupported target skills remain gaps.
- **V0.2B2 — One-page Recruiter Pipeline**: the canonical flow includes `RadarAssessment → EvidenceSelector → CVComposer → ClaimValidator → RecruiterDocumentComposer → RecruiterDocumentValidator → RenderCV/Typst → RecruiterQualityQA → ApplicationPacket`. Canonical preparation starts with `python -m app.application.prepare`.
- **V0.2C — Email Outreach Core**: Opportunity OS does not create Gmail drafts automatically. Approval is not a send command. `OutreachBrief`, `SendRequest`, and `SendReceipt` remain separate auditable contracts.
- **V0.2D — Relationship Memory / Context Bridge**: relationship context includes `FOLLOW_UP` and derived `DORMANT` state. Configure it with `OPPORTUNITY_RELATIONSHIPS_PATH`. Read-only routes include `GET  /api/v1/relationships/context` and `GET  /api/v1/relationships/{account_id}/context`. Esta slice no importa automáticamente Gmail, Apollo ni el CRM.
- **V0.2E — Operator Observation Bridge**: `Observe → preview → confirm → import local fact`. An imported observation is evidence about what happened; it is not authority to make something happen.
- **Gmail Read Adapter V0.2E1**: it accepts a selected Gmail message/thread and produces an `OperatorObservation`; it does not create drafts, does not send, and does not import Relationship Memory.
- **Process Email V1**: one selected inbound Gmail message can be read through the separate transient FULL-content surface, classified by versioned deterministic ES/EN rules, projected to zero/one `OperatorObservation`, and handed to the existing Operator Bridge preview. Source text is transient; persistence still requires explicit human confirmation/import.
- **Search Health V1**: read-only CLI + aggregate JSON over typed native/reconstructed evidence. Coverage is explicit, historical state remains separate, and metrics do not authorize external actions.

The safety boundary remains explicit: CV Factory does not send email and does not submit applications. Opportunity OS does not create Gmail drafts automatically. Approval is not a send command.

---

## Documentation

Start here for deeper implementation detail:

- [`ROADMAP.md`](ROADMAP.md) — capability history and future direction;
- [`docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md`](docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md) — canonical operator/agent workflow;
- [`docs/CV_ATTACHMENT_SELECTION.md`](docs/CV_ATTACHMENT_SELECTION.md) — exact recruiter CV attachment contract;
- [`docs/superpowers/specs/`](docs/superpowers/specs/) — approved design specifications;
- [`docs/superpowers/plans/`](docs/superpowers/plans/) — implementation plans.

---

## Principle

**The system can automate finding, organizing, validating and preparing. The moment an action changes something outside the system, human intent must be explicit.**

## License

MIT