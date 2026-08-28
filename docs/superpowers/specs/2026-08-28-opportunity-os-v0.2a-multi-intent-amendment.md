# Opportunity OS — V0.2A Multi-Intent Work Radar Amendment

Date: 2026-08-28
Status: review
Applies to: `2026-08-28-opportunity-os-v0.2a-intelligent-radar-design.md`

## 1. Why this amendment exists

The first V0.2A design was too narrowly optimized for a target tech/geospatial career path. Opportunity OS also needs to help when the immediate goal is simply to find viable paid work.

The radar must therefore distinguish:

- **career direction** — work that advances a preferred professional path;
- **income-now viability** — work the candidate can realistically obtain and perform now;
- **channel/type** — full-time, part-time, freelance/gig, public-sector competition, local hourly work, remote contract, etc.;
- **discovery** — viable opportunities outside predeclared target-role families.

A role being outside the preferred career family is no longer, by itself, an eligibility hard fail.

This amendment is normative. Where it conflicts with the base V0.2A spec, this file wins for V0.2A planning and implementation.

## 2. Core model: intent is not job type

Do not model `career`, `freelance`, `public`, and `random` as four mutually exclusive role families. They describe different dimensions.

Opportunity OS V0.2A uses:

```text
Search intent
- CAREER
- INCOME_NOW

Opportunity channel/type tags
- salaried
- part_time
- temporary
- freelance
- contractor
- public_sector
- local_service
- internship
- other

Discovery policy
- targeted
- adjacent
- wildcard
```

Examples:

```text
GIS Developer at a company
intent fit: CAREER + INCOME_NOW
channel: salaried

short PostGIS freelance project
intent fit: CAREER + INCOME_NOW
channel: freelance

pizzero / cocina role
intent fit: INCOME_NOW
channel: salaried or part_time

public-sector geospatial competition
intent fit: CAREER + INCOME_NOW
channel: public_sector

unexpected operations/support role with strong transferable fit
intent fit: INCOME_NOW
channel: salaried
policy origin: wildcard
```

## 3. Candidate tracks

The single flat V0.1 candidate profile is insufficient for broad discovery because unrelated verified experience should not contaminate every role score.

V0.2A adds optional `CandidateTrack` records while preserving the existing root fields for backward compatibility.

Conceptual contract:

```text
CandidateTrack
- id
- label
- intents[]
- roles[]
- skills[]
- domains[]
- evidence[]
- accepted_work_modes[]
- no_go_constraints[]
```

Existing V0.1 root `roles`, `skills`, `domains`, and `evidence` are treated as an implicit `default` track when no explicit tracks exist.

A local personal profile may therefore represent separate verified capability groups, for example:

```text
track: tech_geospatial
  intents: [CAREER, INCOME_NOW]

track: gastronomy_operations
  intents: [INCOME_NOW]

track: general_operations
  intents: [INCOME_NOW]
```

The public repository still contains only fictional examples.

## 4. Two independent fit questions

Every radar candidate may be evaluated against multiple candidate tracks.

### 4.1 Career match

The existing V0.1 score remains the authoritative career-oriented match score:

```text
mandatory/core skill fit   40
role/domain fit            20
verified evidence fit      20
location/remote fit        10
freshness                  10
```

This score is preserved for regression compatibility and is calculated against the best CAREER-capable candidate track.

### 4.2 Income-now viability

A second deterministic score answers a different question:

> Can the candidate realistically obtain and perform this work soon enough for it to be useful as income?

Initial product weights:

```text
verified capability / requirement fit   35
logistics / location feasibility         25
schedule / work-mode compatibility       15
entry friction / formal barrier fit      15
freshness / deadline                     10
--------------------------------------------
total                                   100
```

Rules:

- capability uses only verified skills/experience from an INCOME_NOW track;
- logistics includes explicit remote/local/relocation/commute constraints when configured;
- schedule fit uses explicit schedule/work-mode information only;
- entry friction reflects observable barriers such as mandatory licenses, formal education, long multi-stage concours, portfolio requirements, or unknown mandatory declarations;
- freshness uses publication age or an explicit application deadline;
- missing salary does not reduce fit by itself; it reduces confidence if compensation is decision-critical;
- low career relevance never reduces income-now viability.

The weights are versioned product defaults and require calibration from outcomes.

## 5. Confidence remains separate

The existing V0.2A `confidence_score` remains independent of both fit scores.

Example:

```text
career_match = 31
income_viability = 84
confidence = 90

Interpretation:
not a strategic career target, but a strong near-term income opportunity.
```

Another example:

```text
career_match = 88
income_viability = 52
confidence = 82

Interpretation:
excellent career fit, but current logistics/schedule/friction make it less immediately viable.
```

The system must expose both dimensions instead of collapsing them into one opaque percentage.

## 6. Eligibility change

Remove the base-spec rule:

```text
role family explicitly outside non-empty configured target families -> hard fail
```

Replace it with:

```text
role outside preferred target families -> not a hard fail
```

It may:

- receive low `career_match`;
- qualify through `income_viability`;
- enter the wildcard discovery pool;
- remain blocked by real hard constraints such as legal incompatibility, verified missing mandatory license, location impossibility, or configured no-go schedule.

Hard gates remain factual, not aspirational.

## 7. Opportunity enrichment additions

Add derived fields when available:

```text
channel_tags[]
sector                 # private / public / nonprofit / unknown
application_deadline
work_schedule
contract_duration
application_friction
source_category
```

Every derived value keeps provenance under the existing `DerivedValue` contract.

`application_deadline` is especially important for public competitions and short freelance bids where freshness based only on publication age is misleading.

## 8. Discovery policy

The radar candidate universe has three discovery origins:

### Targeted

Queries/sources aligned with configured candidate tracks.

### Adjacent

Roles related by approved aliases/taxonomy or transferable verified skills.

### Wildcard

Broad-source opportunities that are not in preferred families but have enough structured information to compute income viability.

Wildcard does **not** mean random spam. A wildcard item enters the selectable pool only if:

- it passes hard eligibility;
- `income_viability` meets the configured MEDIUM/HIGH threshold;
- confidence meets threshold;
- it is not a duplicate/applied requisition;
- it satisfies normal company/source/cooldown policies.

## 9. Source strategy must broaden beyond ATS tech feeds

V0.1 sources remain useful but are biased toward software/remote/company ATS postings.

V0.2A source architecture must support additional source classes without coupling them to scoring:

```text
ATS/API feed
aggregated/public employment feed
official public-sector notices
local employment portal
freelance marketplace reference
email alert
manual URL/import
```

### 9.1 Verified current source examples

Research performed on 2026-08-28 identified:

- Argentina `Portal Empleo` as a public/free employment platform;
- Argentina `CONCURSAR` / Cartelera de Empleo Público for National Public Administration competitions;
- current 2026 national competition notices that use `concursar.miportal.gob.ar` for electronic registration;
- Municipalidad de Córdoba employment portal with general/local job offers across gastronomy, factories, cleaning, sales and other categories;
- Municipalidad de Córdoba `Conecta Oficios` for local service work;
- Workana public job browsing for freelance projects.

References:

- https://www.argentina.gob.ar/trabajo/empleo
- https://www.argentina.gob.ar/desregulacion/transformacion-del-estado-y-funcion-publica/desarrollo-y-modernizacion-del-empleo-26
- https://empleo.cordoba.gob.ar/
- https://empleo.cordoba.gob.ar/category/ofertas-laborales/
- https://empleo.cordoba.gob.ar/conecta-oficios/
- https://www.workana.com/es/jobs

### 9.2 Integration policy

A source being publicly browsable does not automatically authorize automated scraping or application.

For V0.2A:

- use official/public APIs when available and permitted;
- use explicit RSS/feed endpoints when available;
- permit manual URL/import and email-alert ingestion as universal fallbacks;
- treat authenticated/restricted marketplaces as manual/reference sources unless an authorized integration is verified;
- never bypass login, CAPTCHA, anti-bot, or platform restrictions.

This means broad discovery can expand before every marketplace has a custom connector.

## 10. Generic manual/URL ingestion becomes important

To support random/local/public opportunities without waiting for one connector per website, V0.2A planning should include a source-neutral ingestion contract:

```text
ManualOpportunityInput
- source
- source_url
- title
- company_or_organization
- description
- location optional
- published_at optional
- application_deadline optional
- channel_tags[] optional
```

This contract can be populated later by:

- a user pasting a URL/text;
- Gmail alerts;
- authorized ChatGPT/app connectors;
- source-specific parsers;
- scheduled monitors.

The normalization, extraction, eligibility, scoring, confidence and ranking pipeline after ingestion remains identical.

## 11. Multi-intent tiering

Keep career tier thresholds from the base spec.

Add income-now defaults:

```text
INCOME_HIGH
  eligible = true
  income_viability >= 75
  confidence >= 75

INCOME_MEDIUM
  eligible = true
  income_viability >= 62
  confidence >= 65

INCOME_LOW
  otherwise
```

Thresholds are configuration and versioned.

An opportunity qualifies for the daily selectable pool if it is HIGH/MEDIUM under at least one enabled intent.

## 12. Daily batch policy

`max_items = 20` remains a total cap, not 20 per intent.

The batch must not be dominated accidentally by one search intent when the user has enabled more than one.

Add configurable selection mode:

```text
career_first
income_first
balanced
```

Recommended default for the current product direction: `income_first`.

`income_first` means:

1. rank all eligible income HIGH/MEDIUM by income viability + confidence;
2. retain strong career opportunities even if their immediate-income score is lower;
3. use dedupe/company/cooldown rules;
4. permit a small wildcard representation only when wildcard opportunities themselves meet quality thresholds;
5. stop at 20; never lower thresholds to fill capacity.

Implementation planning must define deterministic tie-breaking and avoid counting the same opportunity twice when it qualifies under multiple intents.

## 13. Output contract amendment

`RadarAssessment` adds:

```text
track_assessments[]
best_career_track optional
career_match optional
best_income_track optional
income_viability optional
intent_tiers[]
channel_tags[]
discovery_origin
```

Each selected item explains plainly:

```text
why it helps career
why it may provide income now
which verified track/evidence supports it
what prevents/complicates application
what is unknown
```

Examples of valid explanations:

```text
Career: LOW
Income now: HIGH
Reason: strong verified gastronomy/operations experience, local compatible schedule, low formal barrier.
```

```text
Career: HIGH
Income now: HIGH
Reason: target geospatial role, verified stack coverage, remote-compatible, fresh posting.
```

## 14. Tests added by this amendment

- a non-target role is not hard-failed solely for role family;
- a candidate with multiple tracks is scored independently per track;
- gastronomy skills cannot inflate a tech career score;
- tech skills cannot be claimed as gastronomy experience;
- best track selection is deterministic;
- a low-career/high-income item can enter an `income_first` batch;
- a strong career opportunity remains visible under `income_first`;
- wildcard items require real income/confidence thresholds;
- one opportunity qualifying in two intents appears once;
- public-sector application deadline participates in freshness/deadline logic;
- missing salary alone does not create a negative match;
- manual/imported opportunities flow through the same enrichment/scoring pipeline;
- existing V0.1 single-profile fixtures remain backward compatible.

## 15. Scope control

This amendment broadens **discovery and ranking**, not submission.

V0.2A still does not:

- generate CVs;
- send applications;
- automate Workana/LinkedIn/Indeed submissions;
- authenticate into government portals;
- accept legal terms;
- infer sensitive/legal answers;
- bypass CAPTCHA or anti-bot controls.

V0.2B/C will use the selected item's winning candidate track to choose the correct CV/evidence/application strategy.

## 16. Revised V0.2A success statement

V0.2A is successful when Opportunity OS can answer both:

> What are the best opportunities for the career I want to build?

and

> What viable paid work can I realistically pursue now, even if it is outside that career path?

without mixing unrelated experience, hiding trade-offs, or turning broad discovery into spam.