# Outreach Patterns — dogfooding snapshot 2026-09-10

## Purpose

This note captures early, manually reviewed evidence from Opportunity OS dogfooding against Juan Manuel Torres' real opportunity search. It is an observational snapshot, not a claim of causality and not production scoring logic.

Source set reviewed on 2026-09-10:

- Gmail outreach/reply threads;
- Opportunity OS Relationship Ledger;
- confirmed meeting/interview state where explicitly present in the threads.

## Outcome classes observed

The reviewed threads should remain separated by outcome type:

- `INTERVIEW_CONFIRMED`: Day10 — Product Engineer (LATAM), interview scheduled for 2026-09-17 10:30 ART with Nicolas Bonora, Head of AI Delivery LATAM.
- `MEETING_OR_COLLAB_CONFIRMED`: Raphael Malikian; Juan Morales. Urbanamente has a positive CEO response but its reschedule reply is still a draft.
- `REFERRED_OR_INTERNAL_CIRCULATION`: Cheaf; Marimaca Copper.
- `DOMAIN_SIGNAL`: SSR Mining / Dario Vera supplied concrete exploration-data pain points without this implying an employment opening.
- `FUTURE_PIPELINE`: RIL / GovTech Connect; METTATEC.
- `INBOUND_FROM_PUBLIC_TECH_FOOTPRINT`: OpenLIT contacted Juan after GitHub activity and proposed a design-partner conversation.

These classes are intentionally not collapsed into a generic `positive` state.

## Early patterns

### 1. Specificity appears stronger than generic outreach

The strongest observed conversion so far is Day10. The application did not only list technologies: it mirrored the role's product/AI-native framing, connected that framing to a live production product, and supplied concrete engineering practices such as CI, regression/contract tests, least privilege, observability and rollback-minded releases.

Early hypothesis: high-specificity messages that connect the recipient's stated problem or role language to concrete evidence are more useful than generic CV distribution.

This is a hypothesis from a small sample, not a proven causal effect.

### 2. A small bounded next action lowers coordination friction

Several positive collaboration threads used a deliberately small ask:

- review one concrete case;
- discuss one bounded contribution;
- choose one small feature with issue, code, tests and PR;
- have a short call to inspect fit.

Raphael Malikian and Juan Morales both progressed from this framing into scheduled conversations.

Product implication: Opportunity OS should distinguish a low-friction `next_action` from vague relationship states.

### 3. Concrete proof assets matter

The positive threads repeatedly expose inspectable work rather than relying only on self-description:

- production GeoPlatform / SanJuanGeo;
- GitHub repositories and contribution activity;
- targeted CVs;
- explicit stack and engineering practices.

Angel Valdés explicitly reviewed SanJuanGeo before agreeing to collaborate. Urbanamente's CEO also referenced Juan's portfolio/profile and the mining–territorial-analysis crossover.

Early hypothesis: proof assets reduce the recipient's cost of understanding the profile.

### 4. Domain crossover is a differentiator, not noise

The combination of geoscience/mining/operations with software, geospatial engineering and AI repeatedly triggered substantive responses:

- Urbanamente: interest in the mining × territorial-analysis crossover;
- Marimaca: exploration/software context and internal CV circulation;
- SSR Mining: domain-specific data quality discussion;
- Day10: ambiguous domain problems translated into engineering/product decisions.

Opportunity OS should preserve this crossover when it is relevant instead of flattening the profile into only `developer` or only `geologist`.

### 5. Problem-discovery outreach can create value without a job outcome

The SSR Mining exchange is especially important. The original outreach asked where friction exists in greenfield exploration. Dario Vera identified:

- inconsistent coordinate reference systems across project datasets;
- insufficient field verification of database content;
- errors becoming institutionalized and causing loss of trust and repeated work;
- weak root-level understanding of QA/QC.

This is useful product/domain evidence. It is **not** evidence of a vacancy, purchase intent, market demand or product validation.

Opportunity OS should retain `DOMAIN_SIGNAL` / research evidence separately from employment and commercial state.

### 6. Direct contact and formal channels are complementary

Marimaca is a clear example: a direct person-to-person contact resulted in internal circulation of the CV, while the contact also asked Juan to register through the official company form.

RIL is similar at an institutional level: a direct inquiry led to routing toward the relevant team and a permanent GovTech scouting registration form.

Heuristic proposal: when a trusted direct route and an official application/registry route both exist, record both instead of treating them as substitutes.

### 7. Public technical footprint is itself an opportunity channel

OpenLIT initiated contact after GitHub activity and invited Juan into a design-partner discussion around production AI-agent observability.

This means Opportunity OS should not model discovery only as `Juan -> target`. There is also an inbound path:

`public work / contribution / interaction -> external discovery -> inbound contact -> human review -> next action`.

Again, public interaction must not be interpreted automatically as employment interest.

## Guardrails reinforced by this dogfood run

Keep the following distinctions explicit:

```text
REPLY != INTERVIEW
INTEREST != JOB_OPENING
REFERRAL != INTERVIEW
MEETING != HIRING_COMMITMENT
COLLABORATION != EMPLOYMENT_INTEREST
DOMAIN_SIGNAL != MARKET_VALIDATION
DRAFT != SENT
PUBLIC_GITHUB_INTERACTION != EMPLOYMENT_INTEREST
```

These are consistent with the repository's existing cross-repo authority boundaries.

## Product implications to evaluate — not implemented by this note

1. Track `outcome_type` separately from reply sentiment.
2. Add explicit `next_action`, `next_action_source` and, where relevant, a due/scheduled time.
3. Classify outreach strategy, for example:
   - `targeted_application`
   - `problem_discovery`
   - `collaboration_offer`
   - `routing_request`
   - `future_pipeline`
   - `inbound`
4. Track `proof_assets_used` such as production demo, portfolio, GitHub, CV or specific repository.
5. Measure conversion as a funnel by strategy rather than raw email volume:

```text
sent -> replied -> referred -> meeting -> interview
```

Not every strategy is expected to traverse every stage.
6. Surface unresolved manual actions such as:
   - reply remains draft;
   - exact meeting time pending;
   - official form still needs manual completion.
7. Preserve human approval before any outbound send.
8. Never infer hiring intent from collaboration, contribution or public GitHub activity.

## Current working heuristic

Prefer **high-specificity + evidence-backed + low-friction** outreach over raw volume.

The useful unit is not "number of emails sent". It is a traceable chain:

```text
research -> explicit fit/hypothesis -> tailored action -> human response -> classified outcome -> next action
```

## What would strengthen or falsify these hypotheses

This snapshot is too small to optimize scoring from it. Continue collecting:

- strategy used per outreach;
- target/contact type;
- proof assets included;
- response/no-response;
- response latency;
- outcome class;
- next action completed/not completed;
- eventual meeting/interview/application result.

Only after a larger sample should these observations influence automated ranking weights.
