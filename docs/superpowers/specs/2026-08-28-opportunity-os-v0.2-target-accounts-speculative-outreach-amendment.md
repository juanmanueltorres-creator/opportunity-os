# Opportunity OS — V0.2 Target Accounts + Speculative Outreach Amendment

Date: 2026-08-28
Status: review
Applies to: V0.2A multi-intent radar + V0.2 email/context bridge

## 1. Decision

Opportunity OS must support a third discovery mode beyond active job postings:

```text
ACTIVE_POSTING
TARGET_ACCOUNT
SPECULATIVE_OUTREACH
```

A useful employer may enter the system even when no current vacancy is published.

The purpose is to identify organizations where the candidate has credible affinity, prepare a role-appropriate CV and short message, and optionally contact one relevant recruiter/company address without pretending a vacancy exists.

## 2. Why

Large/local employers often hire continuously, accept CVs into general talent pools, or have adjacent operational/technology needs that do not map cleanly to one advertised role.

The radar therefore answers both:

1. What active role should I apply to?
2. Which employer is worth approaching proactively because the fit, location, stability, or innovation affinity is strong?

## 3. TargetAccount model

```text
TargetAccount
- id
- company
- sector
- locations[]
- careers_url
- general_cv_url optional
- public_contact_channels[]
- recruiter_discovery_status
- innovation_signals[]
- relevant_capability_tracks[]
- proximity_band
- hiring_signal
- last_checked_at
- source_refs[]
```

`innovation_signals` must be grounded in public evidence such as AI initiatives, digital transformation, Industry 4.0, data, customer-experience technology, automation, or innovation programs.

No speculative company claim is stored without source provenance.

## 4. Account affinity score

A target company has a separate `account_affinity_score`; this is not a job match score.

Initial deterministic weights:

```text
candidate capability/sector affinity    30
location/proximity usefulness           20
employment scale/stability signal       15
innovation/AI/digital adjacency         15
contactability / CV intake path         10
current hiring activity                 10
------------------------------------------
total                                  100
```

Rules:

- no active vacancy is required;
- lack of active hiring lowers only the hiring component;
- proximity is configurable from a private candidate home/reference location;
- company size/stability is a signal, not proof of job quality;
- public evidence and local relevance must be exposed in the explanation.

## 5. Proximity

V0.2 may compute broad distance/travel bands when the private profile contains a reference location:

```text
VERY_CLOSE
CLOSE
CITY_WIDE
LONG_COMMUTE
REMOTE
UNKNOWN
```

Do not publish the private home address or coordinates in the public repository or context snapshots.

A close, viable income role may outrank a strategically better role with a difficult commute in the INCOME_NOW lane.

## 6. Speculative outreach packet

```text
SpeculativeOutreachPacket
- target_account
- intent: CAREER | INCOME_NOW | BOTH
- capability_track
- selected_evidence
- CV variant
- message_subject
- message_body
- contact
- reason_for_contact
- evidence_sources
- unresolved_questions
- packet_hash
```

The message must clearly be a spontaneous/affinity application. It must never imply that a company advertised a vacancy when it did not.

## 7. Contact strategy

Priority:

```text
1. official general CV/talent intake
2. published recruiting/careers email
3. one verified Talent Acquisition / recruiter contact
4. relevant hiring manager only when there is a concrete, defensible reason
```

Do not guess email addresses.

Apollo may identify recruiting contacts, but email enrichment is optional, credit-bearing, and user-controlled.

## 8. Anti-spam rules

- maximum one speculative outreach per company within a configurable cooldown, default 30 days;
- default one recipient per company per outreach event;
- no parallel emailing of multiple recruiters simply to increase odds;
- do not send when there is no credible capability/interest link;
- personalize with 1–2 real reasons/evidence points;
- every send remains approval-gated through the existing email-first design.

## 9. Initial Córdoba target-account families

The product should allow private configuration of target organizations such as:

### Technology / fintech / digital
- Naranja X
- large software/technology employers with Córdoba presence

### Consumer / industrial / transformation
- Coca-Cola Andina Argentina
- Grupo Arcor
- Renault Argentina / Fábrica Santa Isabel
- Stellantis Polo Industrial Córdoba

### Customer experience / support / AI-enabled operations
- Konecta
- Apex America / NexGen BPO

### Retail / income-now
- Grupo Dinosaurio / Super MaMi
- Cencosud / Makro and related formats
- Mariano Max and other local supermarket chains

This list is an initial research set, not an endorsement or hardcoded production catalog.

## 10. Research signals verified 2026-08-28

Examples supporting the target-account model:

- Coca-Cola Andina Argentina has a Córdoba careers site, accepts a general CV, currently lists Córdoba roles including technology-support related work, and publicly described a 2026 internal AI assistant built with Microsoft Copilot Studio.
- Naranja X operates an active careers portal with data/software/devops/cybersecurity roles and emphasizes high-impact challenges.
- Grupo Arcor explicitly offers a general CV intake path and has documented digital-transformation/innovation activity.
- Stellantis has documented AI, Big Data, ML and Industry 4.0 projects at its Córdoba industrial operation.
- Renault's Santa Isabel factory is in Córdoba and documents extensive robotics/Industry 4.0 capability.
- Konecta currently recruits in Córdoba for customer experience/support and publicly positions AI/GenAI as part of its operating model and training.
- Apex currently lists customer experience and technical support roles in Córdoba.
- Grupo Dinosaurio / Super MaMi exposes a `Trabajá con nosotros` path and active local retail jobs.
- Cencosud/Makro has a general careers portal with Córdoba roles.

Research URLs belong in the private curated context/vault, not necessarily as runtime dependencies.

## 11. Radar integration

The daily output may contain:

```text
ACTIVE HIGH/MEDIUM opportunities
+
TARGET ACCOUNT recommendations
```

Target accounts must be labeled clearly and never mixed into active-posting counts.

Example:

```text
ACTIVE
Coca-Cola Andina — Analista Soporte Tecnológico — match 82

SPECULATIVE
Arcor — digital/operations affinity — account affinity 79
reason: general CV path + transformation signal + local relevance
```

## 12. Context Bridge integration

Curated context should expose a compact target-account section:

```text
TARGET ACCOUNTS
- company
- account affinity
- last contact
- cooldown until
- current active roles count
- recruiter/contact status
- recommended next action
```

This lets ChatGPT decide whether to inspect the company, find a recruiter, prepare a CV, or wait without loading the full research history.

## 13. Scope boundary

V0.2A implements the data/ranking contract and may surface target accounts.
CV creation remains V0.2B.
Email drafting/sending remains V0.2C through Gmail/authorized tools.
Context summaries/operational bridge remain the Context Bridge slice.
