# Opportunity OS — V0.2B CV Factory Design

Date: 2026-08-28
Status: approved
Base: `main` at V0.2A1 multi-intent radar
Parent roadmap: private Opportunity OS V0.2 plan in the knowledge vault

## Purpose

V0.2B turns a selected `RadarAssessment` into a truthful, reproducible application-preparation artifact. It must answer which verified facts and evidence belong in the CV for the selected candidate track, how to order them for the opportunity, and whether every consequential visible claim can be traced to approved source data.

Output: an `ApplicationPacket` with the structured CV, rendered private PDF reference, exact fact/evidence IDs, unresolved gaps, version metadata, and content hashes.

V0.2B does not send email, discover recruiters, submit forms, accept terms, answer legal/sensitive declarations, or auto-apply. Those belong to V0.2C.

## Principles

1. Truth before optimization.
2. Every candidate-specific claim has stable provenance.
3. Winning radar track is a hard evidence boundary.
4. Structured document before rendering.
5. Real personal data and generated CV artifacts stay private/gitignored.
6. Selection, validation, hashing, and rendering are deterministic and offline.
7. LLM wording may be added later only as a non-authoritative adapter over approved claims.
8. V0.2B ships one ATS-first one-column PDF layout.

## Architecture

```text
DailyRadarBatch item
→ winning CandidateTrack
→ private MasterFactsSnapshot + EvidenceCatalogSnapshot
→ EvidenceSelector
→ CVComposer
→ ClaimValidator
→ CVDocumentModel
→ ATSRenderer
→ private PDF
→ ApplicationPacket
```

Each unit is independently testable without network access.

## Private facts and evidence

`MasterFact` contains a stable `id`, `kind`, canonical `value`, optional language display values, `track_ids`, verification metadata, optional source reference, and structured metadata.

Initial kinds: identity, contact, summary_claim, skill, role, employment, education, project, language, location, link, achievement, metric, other.

Only verified facts can support CV claims. Verification semantics are normative in the companion self-review clarification.

`EvidenceModule` groups verified facts into reusable material for one or more explicit tracks. It contains stable ID, track IDs, label, fact IDs, approved claim candidates, keywords, source references, and verified state.

Public fixtures use fictional identities, employers, schools, domains, and URLs only.

## Track resolution

V0.2A already records `selected_intent`, `best_career_track`, and `best_income_track`.

Resolution order:

1. Use the winning track for `selected_intent` when available.
2. If that lane has no winner, use the other qualifying winning track.
3. If neither exists, block with `track_unavailable`.

No fallback may borrow another track just to fill a CV section.

## Evidence selection

Inputs: `RadarAssessment`, `OpportunityEnrichment`, application track, master facts, evidence catalog, and `CVPolicy`.

Selection is rule-based and explainable. Signals include exact verified skill support, approved aliases, requirement/keyword overlap, role/domain affinity, verified radar evidence, and recency where dates exist.

Support precedence:

```text
exact verified
> approved alias
> taxonomy related
> unsupported
```

Taxonomy-related evidence can increase relevance but cannot become exact-product proof.

Output `EvidenceSelection` records selected fact IDs, evidence IDs, requirement support, unsupported requirements, and explanations.

Unsupported posting requirements remain gaps unless policy explicitly declares one a preparation prerequisite.

## Structured composition

`CVDocumentModel` contains language, header, optional headline, summary claims, skills, experience entries, projects, education, languages, links, and a provenance map.

Every candidate-specific visible claim has a stable `claim_id`. `provenance_map` maps each claim to fact IDs, evidence IDs, and optionally an approved claim ID.

Composer may omit irrelevant modules, reorder sections/bullets, select approved role-appropriate wording, and use approved translations/aliases. It may not invent years, tools, titles, employers, degrees, certifications, metrics, outcomes, or paid-employment status.

Projects remain projects. Employment remains employment. Related technologies do not become direct experience.

## Claim validation

`ClaimValidator` is a hard gate before rendering.

Hard errors include missing provenance, missing referenced fact/evidence, unverified provenance, incompatible track provenance, unsupported metric/number, stronger tool/product claim than evidence allows, changed employer/title/date, and candidate-specific renderer content absent from the validated model.

Warnings include important unsupported posting requirements, sparse but truthful sections, stale evidence, and relevant unknowns.

A document with hard validation errors cannot render into a prepared packet.

## ATS renderer

One-column, selectable-text PDF with standard text flow and headings. No images containing text, skill bars, semantic icons, decorative charts, or multi-column reading ambiguity.

Renderer authority is layout only:

```text
validated CVDocumentModel → layout → PDF
```

Fixed language-specific headings such as `Experience` or `Experiencia` are allowed without provenance. Candidate name, contact details, headline, summary, employer, title, dates, bullets, project claims, education, skills, languages, and links require validated structured claims.

The renderer must control unstable PDF metadata so identical validated input + renderer version + policy produces stable bytes in CI fixtures.

## ApplicationPacket

A packet exists only after validation and successful PDF hashing. It records opportunity identity/hash, radar versions/scores, selected intent/track, fact/evidence snapshot fingerprints, composer/document/renderer versions, selected IDs, unresolved gaps, structured CV, PDF path, PDF SHA-256, semantic packet SHA-256, and creation time.

`application_id` is an opaque identifier, never an approval token.

Any semantic change to opportunity snapshot, facts, evidence, CV content, renderer version, or rendered bytes requires a new content hash.

## Privacy boundary

Public repo may contain schemas, deterministic selection/composition/validation/rendering code, fictional fixtures, public templates, tests, and documentation.

Public repo must not contain real master facts, real contact details, real CV PDF/DOCX files, real application packets, recruiter data, Gmail data/tokens, legal/sensitive answers, or portal credentials.

Suggested private paths:

```text
profile/master_facts.local.yaml
profile/evidence_catalog.local.yaml
artifacts/applications/<application_id>/cv.pdf
```

## Service boundary

Primary local service:

```text
CVPreparationService.prepare(
  assessment,
  master_facts,
  evidence_catalog,
  policy,
  artifact_root,
  now
) -> PreparationResult
```

Preferred interface is local service/CLI invocation; V0.2B does not require a new HTTP endpoint.

## Error model

Typed preparation errors include: master_facts_unavailable, invalid_master_facts, track_unavailable, insufficient_verified_evidence, claim_validation_failed, render_failed, artifact_write_failed, version_mismatch.

Errors never dump private source contents. Missing evidence becomes a gap, never an invented claim.

## Language policy

Initial output languages: `es`, `en`.

Canonical facts stay canonical. Approved display values/claims provide language-specific wording. A translation may change wording but not meaning; consequential free text without an approved translation stays canonical or blocks that translation.

## Testing

CI remains offline and fictional. Tests cover strict contracts, aware timestamps, canonical snapshot fingerprints, track isolation, exact/alias/related support, deterministic selected IDs, deterministic composition, provenance integrity, unsupported metrics/titles/employers/dates, selectable PDF text, stable fixture PDF SHA, packet hashing, blocked-result semantics, V0.2A regression, and tracked-private-file guards.

## Deliberate exclusions

Not V0.2B: recruiter/contact discovery, Apollo enrichment, Gmail draft creation, mail copy, sending, browser/form automation, ATS submission, approval UI/workflow, outcome ledger, DOCX, multiple visual templates, LLM authority, autonomous fact creation.

## Success criteria

V0.2B is complete when a fictional selected opportunity can deterministically resolve the correct track, load only verified allowed facts/evidence, select relevant support, produce a tailored provenance-backed `CVDocumentModel`, surface unsupported requirements as gaps, validate every candidate-specific claim, render one ATS-friendly private PDF with stable fixture hash, and return a reproducible `ApplicationPacket` while all existing radar tests and privacy guards remain green.
