# Opportunity OS V0.2A1 Plan — Self-Review Corrections

Date: 2026-08-28
Status: normative plan addendum
Applies to: `docs/superpowers/plans/2026-08-28-opportunity-os-v0.2a1-multi-intent-radar-core.md`

This file closes concrete spec-coverage gaps found during plan/implementation review. Read it with the A1 implementation plan. If it conflicts with that plan, this correction wins.

## Correction 1 — Application mode is part of enrichment

### Task 1 contract addition

`app/radar/models.py` must define:

```python
ApplicationMode = Literal[
    "DIRECT_EMAIL",
    "AUTHORIZED_API",
    "FORM_ASSIST",
    "HOSTED_MANUAL",
    "RESTRICTED_MANUAL",
    "UNKNOWN",
]
```

`OpportunityEnrichment` must include `application_mode`, default `UNKNOWN`. V0.2A1 only classifies a mode when source evidence is explicit; it never assumes applicant-side ATS credentials exist.

Classification rules:

```text
explicit published application email -> DIRECT_EMAIL
known Greenhouse/Lever/Ashby hosted posting without authorized applicant-side credential -> HOSTED_MANUAL
manual/restricted platform explicitly marked restricted -> RESTRICTED_MANUAL
explicit supported form-assist flag -> FORM_ASSIST
AUTHORIZED_API -> only when explicitly configured as authorized
otherwise -> UNKNOWN
```

V0.2A1 does not submit through any of these modes.

## Correction 2 — Source reliability and freshness provenance are explicit

Define:

```python
SourceReliability = Literal[
    "DIRECT_ATS",
    "DIRECT_OFFICIAL",
    "AGGREGATOR",
    "MANUAL",
    "UNKNOWN",
]

FreshnessQuality = Literal[
    "DIRECT_TIMESTAMP",
    "DELAYED_TIMESTAMP",
    "DISCOVERED_AT_ONLY",
    "UNKNOWN",
]
```

Known defaults:

```text
Greenhouse -> DIRECT_ATS
Lever      -> DIRECT_ATS
Ashby      -> DIRECT_ATS
Remotive   -> AGGREGATOR
manual import -> MANUAL unless caller supplies a stricter known source type
```

Freshness quality:

```text
reliable source publication timestamp -> DIRECT_TIMESTAMP
known delayed aggregator timestamp/feed -> DELAYED_TIMESTAMP
no publication timestamp; only discovered_at -> DISCOVERED_AT_ONLY
insufficient metadata -> UNKNOWN
```

Source quality can change confidence and explicit ranking penalties. It must never manufacture or erase candidate skills, legal facts or requirements.

## Correction 3 — Multi-intent thresholds and daily selection mode follow the normative amendment

During Task 8 preflight, implementation review found that the A1 plan text incorrectly reused CAREER thresholds for `INCOME_NOW`. The normative multi-intent amendment explicitly overrides that assumption.

The versioned default policy is therefore:

```text
CAREER HIGH     fit >= 78 && confidence >= 75
CAREER MEDIUM   fit >= 65 && confidence >= 65

INCOME HIGH     fit >= 75 && confidence >= 75
INCOME MEDIUM   fit >= 62 && confidence >= 65

STRETCH diagnostic floor = 55
```

The daily selection mode is explicit and configurable:

```text
career_first
income_first
balanced
```

Default for V0.2A is:

```text
selection_mode = income_first
```

`income_first` affects **daily batch selection**, not candidate truth or the per-opportunity fit calculation. A strong CAREER opportunity must remain visible; the same opportunity may qualify for both intents but may appear only once in a batch.

TDD evidence for this correction:

```text
RED: 2 failures — INCOME 76/75 classified MEDIUM; selection_mode absent
GREEN: 94/94 tests
```

Implementation commit: `72ffc613037b392530f671c8e8bc11631534e2cd`.

## Updated self-review result

After these corrections, the A1 plan covers:

- enrichment/provenance;
- application mode classification without submission;
- explicit source/freshness quality;
- ES/EN requirements;
- aliases/taxonomy fallback;
- factual eligibility;
- V0.1-compatible career score;
- independent INCOME_NOW score and thresholds;
- independent confidence;
- ranking/tiers;
- default `income_first` batch policy;
- full lookback candidate universe;
- max-20 selection;
- source isolation;
- generic manual import;
- API/error/privacy boundaries.

No submission automation is introduced by this addendum.
