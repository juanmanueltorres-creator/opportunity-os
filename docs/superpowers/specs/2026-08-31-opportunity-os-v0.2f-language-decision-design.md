# Opportunity OS V0.2F — Auditable Language Decision Design

## Status

Approved design for implementation on `feat/v0.2f-language-decision`.

## Problem

The current canonical application CLI hardcodes `CVPolicy(language="en")`, while outreach drafts can be registered with arbitrary subject/body text. `OutreachBrief.language` inherits the CV document language, but the draft registration path does not verify that the actual outreach copy uses the same language.

This creates two failure modes:

1. the CV language can be wrong for the opportunity because the CLI always selects English;
2. the email body can disagree with the CV/outreach language, as happened in the Canals test run where an English CV was paired with a Spanish draft.

The fix must be deterministic, auditable, fail closed on clear inconsistencies, and must not depend on an LLM or an external language-detection package.

## Goals

1. Resolve one explicit output language, `es` or `en`, for each application.
2. Use the same decision for the CV, recruiter document, `ApplicationPacket`, `OutreachBrief`, and registered Gmail draft snapshot.
3. Make the decision auditable by recording both the selected language and the basis used to select it.
4. Allow an explicit CLI override for ambiguous or exceptional cases.
5. Detect and block a confidently mismatched draft body/subject.
6. Preserve the current evidence, claim-validation, recruiter QA, offline runtime, approval, and send-gate contracts.

## Non-goals

- No automatic machine translation.
- No LLM-based language classification.
- No new runtime dependency.
- No change to job scoring, eligibility, contact resolution, approval semantics, Gmail send semantics, or recruiter PDF layout policy.
- No rule of the form `foreign company => English`.
- No use of a job requirement such as `English required` as sufficient evidence that recruiter outreach itself must be English.

## Domain model

Add the following types to the Radar domain because the decision is derived from opportunity context before document composition:

```python
OutputLanguage = Literal["es", "en"]
LanguageDecisionBasis = Literal[
    "explicit_override",
    "posting_language",
    "market_location",
    "international_remote_fallback",
]

class LanguageDecision(StrictRadarModel):
    language: OutputLanguage
    basis: LanguageDecisionBasis
    confidence: float = Field(ge=0, le=1)
    source_field: str = Field(min_length=1)
    source_text: str | None = None
```

`source_text` is short evidence for auditability, not the entire job description.

## Resolver

Create `app/radar/language.py` with a deterministic resolver:

```python
def resolve_output_language(
    assessment: RadarAssessment,
    *,
    override: Literal["es", "en"] | None = None,
) -> LanguageDecision:
    ...
```

### Precedence

The resolver uses this exact precedence:

1. explicit override;
2. dominant language of the posting text;
3. Spanish-speaking market/location fallback;
4. international/remote fallback to English.

The nationality of the company is never a signal by itself.

### 1. Explicit override

When `override` is `es` or `en`:

- select it directly;
- `basis = "explicit_override"`;
- `confidence = 1.0`;
- `source_field = "cli.language"`.

### 2. Posting-language signal

The posting signal is computed from `Opportunity.title + Opportunity.description`.

Use a deterministic lexical detector with two small frozen vocabularies containing common non-technical Spanish and English recruiting words. Technical tokens such as `Python`, `SQL`, `React`, `FastAPI`, `API`, `backend`, and company/product names do not count as language evidence.

A posting is confidently classified only when:

- one language has at least 3 marker hits; and
- its marker-hit count exceeds the other language by at least 2.

When classified from posting text:

- `basis = "posting_language"`;
- `confidence = 0.95`;
- `source_field = "opportunity.title+description"`;
- `source_text` contains a compact normalized excerpt of the posting evidence.

If the threshold is not met, the posting is considered ambiguous and resolution continues.

### 3. Market/location fallback

If the posting text is ambiguous, inspect, in order:

1. `assessment.enrichment.country.value` when present;
2. `assessment.enrichment.region.value` when present;
3. `assessment.opportunity.location`.

A normalized match against a frozen Spanish-speaking market set selects Spanish. The set includes Argentina, Bolivia, Chile, Colombia, Costa Rica, Cuba, Ecuador, El Salvador, Spain/España, Guatemala, Honduras, Mexico/México, Nicaragua, Panama/Panamá, Paraguay, Peru/Perú, Dominican Republic/República Dominicana, Uruguay, and Venezuela.

When selected from market/location:

- `basis = "market_location"`;
- `confidence = 0.80`;
- `source_field` identifies the field that matched;
- `source_text` stores the matched market/location value.

Generic `LATAM`, `Latin America`, or `Remote` alone does not force Spanish because such roles may operate in English.

### 4. International/remote fallback

When neither posting text nor market/location resolves the language:

- select English;
- `basis = "international_remote_fallback"`;
- `confidence = 0.60`;
- `source_field = "fallback"`.

This is intentionally conservative and deterministic.

## Text-language detector for draft safety

The same lexical primitives are exposed through:

```python
def detect_text_language(text: str) -> OutputLanguage | None:
    ...
```

It returns `None` when evidence is ambiguous.

This detector is used only as a safety check. It does not translate or rewrite copy.

## Canonical CLI contract

Change `python -m app.application.prepare` to accept:

```text
--language auto|es|en
```

Default: `auto`.

Behavior:

- `auto` => `resolve_output_language(assessment)`;
- `es|en` => `resolve_output_language(assessment, override=<value>)`.

Remove the current hardcoded `CVPolicy(language="en")` behavior. The CV policy still owns structural requirements, but the output language comes from the resolved `LanguageDecision`.

The CLI JSON response for `PREPARED` adds:

```json
{
  "language": "en",
  "language_basis": "posting_language"
}
```

Blocked/error payloads use `null` for these fields when no decision is available.

## CV preparation contract

`CVPreparationService.prepare(...)` receives a required `language_decision: LanguageDecision`.

`compose_cv(...)` is called with:

```python
language=language_decision.language
```

The resulting invariant is:

```python
packet.cv_document.language == packet.language_decision.language
```

The recruiter document continues to derive from that validated CV document, so no independent recruiter-language switch is introduced.

## ApplicationPacket contract

Add:

```python
language_decision: LanguageDecision
```

to `ApplicationPacket`.

Include the complete serialized decision in `_packet_content_payload(...)` so changing the language or its provenance changes `packet_sha256`.

The packet therefore becomes the canonical source of language truth after `PREPARED`.

## Outreach contract

`OutreachPreparationService` continues to build `OutreachBrief.language`, but it now copies from:

```python
application_packet.language_decision.language
```

and validates that:

```python
application_packet.cv_document.language
    == application_packet.language_decision.language
```

A mismatch returns `BLOCKED_INVALID_PACKET` with `packet_language_mismatch`.

## Draft contract

Add required `language: Literal["es", "en"]` to `DraftSnapshot`.

Change `OutreachService.register_draft(...)` to require:

```python
language: Literal["es", "en"]
```

Before persisting the draft:

1. if declared `language != brief.language`, raise `ValueError("draft_language_mismatch")`;
2. run `detect_text_language(subject + "\n" + body)`;
3. if detection is confident and detected language differs from `brief.language`, raise `ValueError("draft_text_language_mismatch")`;
4. if detection returns `None`, allow registration based on the explicit declared language.

This catches a Spanish Canals-style draft even if a caller incorrectly labels it `en`, while avoiding false failures on very short or highly technical copy.

Include `language` in `draft_semantic_payload(...)`. A language change must change `draft_sha256` and therefore invalidate any prior approval, preserving the existing safety semantics.

## Backward compatibility

- Existing `RadarAssessment` JSON does not need a new required field; language is resolved at application preparation time.
- Existing CV composer callers can continue using `policy.language` when they do not pass an explicit `language`; canonical application preparation always passes the decision explicitly.
- `ApplicationPacket` and `DraftSnapshot` are intentionally strengthened contracts. Tests and fixtures that construct these models must provide the new field.
- Stored old snapshots are not mutated. New runtime output uses the strengthened schema.

## Failure behavior

The feature must fail closed for contradictions, not for weak evidence.

Hard failures:

- packet language decision differs from CV document language;
- declared draft language differs from outreach brief language;
- confidently detected draft text language differs from outreach brief language.

Non-failure ambiguity:

- posting text language cannot be determined => continue to market/fallback;
- draft text language cannot be determined => trust the explicit declared language already checked against the brief.

## Tests

### Resolver tests

Add deterministic cases for:

1. English US/international posting similar to Canals => `en`, `posting_language`;
2. Spanish Córdoba/Argentina posting => `es`, `posting_language` or `market_location` depending on text;
3. ambiguous technical posting located in Argentina => `es`, `market_location`;
4. ambiguous remote international posting => `en`, `international_remote_fallback`;
5. explicit `--language es` overrides English posting;
6. explicit `--language en` overrides Spanish posting;
7. `English required` inside an otherwise Spanish posting does not by itself switch the communication language to English.

### CV/service tests

- prepared Spanish decision => `packet.cv_document.language == "es"`;
- prepared English decision => `packet.cv_document.language == "en"`;
- packet hash changes when language decision changes;
- recruiter pipeline remains `PREPARED` and one page under both supported languages when the fixture contains both language variants.

### Outreach tests

- brief inherits packet language decision;
- packet/CV language mismatch blocks outreach;
- declared draft-language mismatch blocks registration;
- Spanish body with `language="en"` and English brief blocks with `draft_text_language_mismatch`;
- English body with English brief registers successfully;
- ambiguous technical body can register when declared language matches the brief;
- draft hash changes with language.

### CLI tests

- default `--language auto` selects expected language;
- `--language es` and `--language en` override auto;
- CLI JSON exposes `language` and `language_basis`;
- invalid language value is rejected by argparse.

### Offline runtime acceptance

Extend the canonical offline runtime verifier so the fictional preparation exercise checks:

- `PREPARED`;
- `packet.language_decision.language == packet.cv_document.language`;
- CLI language metadata is present;
- existing A4/one-page/text/link checks remain green.

No network package index may be required.

## Files expected to change

Create:

- `app/radar/language.py`
- `tests/test_radar_language.py`

Modify:

- `app/radar/models.py`
- `app/application/prepare.py`
- `app/cv/models.py`
- `app/cv/service.py`
- `app/outreach/models.py`
- `app/outreach/hashing.py`
- `app/outreach/preparation.py`
- `app/outreach/draft.py`
- `app/outreach/service.py`
- focused existing tests/fixtures for packet and draft construction
- `scripts/verify_offline_runtime.py`
- `docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md`

No renderer, scoring, connector, contact-resolution, approval, or send-gate implementation should change unless a failing compatibility test proves a direct dependency.

## Acceptance criteria

The change is complete only when all of the following are true:

1. canonical preparation no longer hardcodes English;
2. language is resolved by the documented precedence and recorded in `ApplicationPacket`;
3. CV and outreach language are guaranteed to match the packet decision;
4. confidently mismatched draft text is rejected before registration;
5. explicit CLI override works and is auditable;
6. Canals-like international English case resolves to English;
7. Argentina Spanish case resolves to Spanish;
8. full pytest suite passes;
9. offline runtime build/verify passes for supported Python minors;
10. PR CI is green before merge;
11. post-merge `main` runtime artifact is verified against the exact merge SHA before using it for future production application runs.
