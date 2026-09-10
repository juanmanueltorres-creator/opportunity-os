# Opportunity OS — Semantic CAREER Matching Amendment

**Status:** Approved by dogfood
**Date:** 2026-09-10
**Scope:** CAREER scoring only

## Problem

A real Product Engineer posting remained `DISCARD` after the experience-duration fix even though eligibility passed and the candidate had relevant verified projects. The remaining false negative came from three modeling errors:

1. CAREER domain fit divided matched candidate domains by all candidate domains, so a multidisciplinary profile was penalized for having extra domains.
2. Role-shaped requirements such as `Product Engineering` were treated only as literal skills, ignoring verified candidate roles such as `Product Engineer`.
3. Evidence coverage required literal skill coverage even when a role match was backed by verified project/experience evidence in the same opportunity domain.

## Design

Keep the public CAREER score shape unchanged:

`40% mandatory + 20% domain + 20% evidence + 10% location + 10% freshness`

Do not lower thresholds and do not change eligibility.

### Domain compatibility

For CAREER, candidate domains are alternatives/specializations, not a checklist the opportunity must consume.

- any explicit track-domain match in the opportunity corpus => `domain_fit=100`
- no track domains configured => neutral `50`
- no explicit domain match => neutral `50`

Having additional unrelated candidate domains MUST NOT lower a positive domain match.

### Role-shaped capability matching

When a conceptual skill requirement cannot be resolved by the approved skill taxonomy, CAREER may compare it against `CandidateTrack.roles` using deterministic role-family normalization.

Examples:

- `Product Engineering` ↔ `Product Engineer` => match
- `Full Stack Development` ↔ `Full Stack Developer` => match
- `Product Engineer` ↔ `Account Executive` => no match

The matcher may normalize grammatical variants such as `engineering/engineer`, `development/developer`, and `management/manager`, and may ignore seniority/noise tokens. It MUST require at least two meaningful overlapping role tokens and an occupational head token. Exact-product requirements MUST NOT use role fallback.

### Transferable evidence

A role-shaped requirement is not fully evidenced merely because the candidate lists a role.

It receives evidence coverage only when verified `project` or `experience` evidence belongs to an opportunity-matched candidate domain. Literal/alias skill evidence continues to work as before.

### Preferred strengths

If mandatory requirements exist, positively matched preferred skill/role requirements may be surfaced as strengths, but preferred misses MUST NOT become mandatory gaps.

## Boundaries

- Do not modify the frozen v0.1 scorer contract.
- Do not modify INCOME_NOW semantics.
- Do not change ranking thresholds or CAREER weights.
- Do not special-case any company, posting, or candidate.
- Do not infer unverified roles, years, skills, or outcomes.
- Keep true eligibility hard-fails unchanged.

## Acceptance benchmark

A Product Engineer posting with:

- remote-compatible location;
- mandatory 3 years software-development duration with relevant verified capability but unknown exact duration;
- preferred Product Engineering;
- candidate role `Product Engineer`;
- verified software-domain projects;

must remain eligible, preserve the years gap/risk, achieve at least MEDIUM CAREER under default policy, and become selectable for downstream CV preparation.
