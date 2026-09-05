# Cross-Repo Handoff V0.1

Opportunity OS accepts versioned research handoff artifacts as **read-only snapshots**. The handoff layer does not create hiring targets, relationship state, outreach state, contribution state, or external actions.

## Authority boundary

```text
handoff preview != import
IMPORT_PUBLIC_CONTRIBUTION != automatic import
PUBLIC_CONTRIBUTION_CANDIDATE != JOB_OPENING
```

Additional invariants remain authoritative:

```text
PR_OPENED != EMPLOYMENT_INTEREST
PR_MERGED != EMPLOYMENT_INTEREST
GOOD_PROBLEM != AVAILABLE_PROBLEM
```

`source_freshness = AS_OF_EXPORT` means the artifact describes what the source system knew at export time. Opportunity OS does not call Question Radar or Andes Context OS to claim that the source decision is still current.

## Territorial actor-need path

An `ACTOR_NEED_HYPOTHESIS` is reviewable research context only. Territorial actors are not coerced into `TargetAccount`, Relationship, buyer, customer, or contact-permission state.

Legal preview dispositions are:

```text
RESEARCH_ACTOR   # only when actor_refs is non-empty
WATCH
DISCARD
```

Evidence refs, assumptions, missing context, and research status remain separate and are preserved verbatim.

## Public GitHub contribution path

Public GitHub acquisition remains in the existing Contribution Observation Bridge against one explicit public resource:

```text
explicit GitHub issue / PR
        ↓
existing app.contributions.intake_cli preview
        ↓
exact ContributionPreview
        ↓
Contract 2 PUBLIC_CONTRIBUTION_CANDIDATE
        ↓
read-only handoff preview
```

The adapter accepts only an existing `ContributionPreview` that is `IMPORTABLE`, has a non-null `proposed_entry`, and has no candidate event. It performs no GitHub network call itself.

When explicit local `entry_id` and aware `discovered_at` metadata are supplied, the handoff preview may show `IMPORT_PUBLIC_CONTRIBUTION` as an **eligibility disposition**. That means only that the candidate is compatible with the existing contribution domain model.

It does not write SQLite and it does not import the candidate.

Actual persistence remains exclusively:

```text
original existing ContributionPreview
        ↓
explicit human confirmation
        ↓
existing ContributionObservationBridge import path
```

The ephemeral contribution entry constructed by the handoff preview is compatibility evidence only and is never an import payload.

## No mutation authority

The V0.1 handoff package has no FastAPI route and no import subcommand. It does not create or update:

- `TargetAccount` state;
- Relationship state;
- outreach or draft state;
- application state;
- contribution SQLite state;
- GitHub issue or pull-request state.

A valid zero-result outcome is allowed. If evidence cannot support an actionable candidate, the correct result is to preserve uncertainty and stop rather than manufacture an opportunity.
