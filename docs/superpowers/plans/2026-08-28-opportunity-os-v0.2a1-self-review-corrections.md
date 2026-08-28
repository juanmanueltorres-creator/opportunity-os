# Opportunity OS V0.2A1 Plan — Self-Review Corrections

Date: 2026-08-28
Status: normative plan addendum
Applies to: `docs/superpowers/plans/2026-08-28-opportunity-os-v0.2a1-multi-intent-radar-core.md`

This file closes two concrete spec-coverage gaps found during the mandatory writing-plan self-review. Read it with the A1 implementation plan. If it conflicts with that plan, this correction wins.

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

`OpportunityEnrichment` must include:

```text
application_mode
```

Default is `UNKNOWN`. V0.2A1 only classifies a mode when source evidence is explicit; it never assumes applicant-side ATS credentials exist.

### Task 2 test additions

Add failing tests before implementation:

```python
def test_explicit_application_email_is_direct_email() -> None:
    ...
    assert enrichment.application_mode == "DIRECT_EMAIL"


def test_known_hosted_ats_without_applicant_api_is_hosted_manual() -> None:
    ...
    assert enrichment.application_mode == "HOSTED_MANUAL"


def test_unknown_application_channel_remains_unknown() -> None:
    ...
    assert enrichment.application_mode == "UNKNOWN"
```

Classification rules for V0.2A1:

```text
explicit published application email -> DIRECT_EMAIL
known Greenhouse/Lever/Ashby hosted posting without an authorized applicant-side credential -> HOSTED_MANUAL
manual/restricted platform explicitly marked restricted by source config -> RESTRICTED_MANUAL
explicit supported form-assist flag supplied by source metadata -> FORM_ASSIST
AUTHORIZED_API -> only when an integration is explicitly configured as authorized; never infer from ATS brand
otherwise -> UNKNOWN
```

V0.2A1 does not submit through any of these modes. The field exists to prepare V0.2B/V0.2C.

## Correction 2 — Source reliability and freshness provenance are explicit

### Task 1 contract addition

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

`OpportunityEnrichment` must include:

```text
source_reliability
source_freshness_quality
```

### Task 2/9 behavior additions

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

Remotive must be representable as delayed/aggregated even when it has a date, so explanations do not present its freshness provenance as equivalent to a direct ATS timestamp.

### Task 6 confidence test additions

Add tests proving:

```python
def test_direct_ats_timestamp_has_higher_source_completeness_than_discovered_only(): ...
def test_delayed_aggregator_quality_does_not_change_match_score(): ...
def test_source_quality_changes_confidence_explanation_not_candidate_truth(): ...
```

Source quality can change confidence and ranking penalties where explicitly configured. It must not manufacture or erase candidate skills, legal facts or requirements.

## Updated self-review result

After these corrections, the A1 plan covers:

- enrichment/provenance;
- application mode classification without submission;
- explicit source/freshness quality;
- ES/EN requirements;
- aliases/taxonomy fallback;
- factual eligibility;
- V0.1-compatible career score;
- INCOME_NOW score;
- independent confidence;
- ranking/tiers;
- full lookback candidate universe;
- max-20 selection;
- source isolation;
- generic manual import;
- API/error/privacy boundaries.

No implementation is performed by this addendum.
