# Opportunity OS — V0.2B CV Factory Self-Review Clarifications

Date: 2026-08-28
Status: approved-normative
Applies to: `2026-08-28-opportunity-os-v0.2b-cv-factory-design.md`

This clarification is normative for V0.2B planning and implementation. Where wording in the base design is ambiguous, this file wins.

## 1. Verified means reviewed provenance, not a boolean alone

`MasterFact` must record `verification_method`, timezone-aware `verified_at`, and optional `source_ref`.

Initial methods:

```text
manual_confirmation
repository_evidence
document_evidence
employment_record
education_record
public_profile
other_reviewed_source
```

Rules:

- `verified=true` requires non-empty method and aware timestamp.
- Evidence-backed methods require `source_ref`.
- `manual_confirmation` is valid for self-attested identity/contact/location and explicitly reviewed wording.
- `manual_confirmation` must not establish employment, education, certifications, metrics, tools, dates, or external outcomes.

## 2. Blocked preparation is not an ApplicationPacket

Use `PreparationResult` with status, optional packet, errors, and warnings.

```text
PREPARED
→ packet present
→ PDF path/hash present
→ packet hash present

BLOCKED_VALIDATION
BLOCKED_MISSING_FACTS
BLOCKED_TRACK_UNAVAILABLE
BLOCKED_RENDER
→ packet absent
→ structured errors/warnings only
```

No null-filled fake packet is persisted.

## 3. Packet hashing is semantic

`packet_sha256` excludes execution noise:

```text
application_id
created_at
cv_pdf_path
filesystem-specific values
load timestamps
```

It includes semantic inputs/outputs:

```text
opportunity snapshot hash
selected intent and track
radar/scoring/extractor/alias/taxonomy versions
master-facts fingerprint
evidence-catalog fingerprint
composer/document/renderer versions
selected fact/evidence IDs
unresolved gaps
canonical CVDocumentModel content
cv_sha256
```

Semantically unordered lists are canonicalized. Visible CV ordering remains significant.

## 4. Deterministic PDF bytes are a tested contract

The renderer must not inject current timestamps, random document IDs, machine-specific paths, or unstable metadata. Identical validated document + renderer version + policy should produce stable PDF bytes and `cv_sha256` in CI fixtures.

If a future renderer cannot guarantee stable bytes, the contract must be explicitly revised before implementation; it cannot silently claim determinism.

## 5. Fixed template labels versus candidate claims

Unprovenanced fixed section labels are allowed:

```text
Experience / Experiencia
Projects / Proyectos
Education / Educación
Skills / Habilidades
Languages / Idiomas
```

Candidate-specific visible content always requires provenance: name, contact, location, headline, summary, employer, title, dates, bullets, project names/descriptions, education, skills, languages/levels, and links.

## 6. Snapshot version identity is a content fingerprint

`master_facts_version` and `evidence_catalog_version` are canonical content SHA-256 fingerprints, not manually maintained labels alone.

Recommended wrappers:

```text
MasterFactsSnapshot
- schema_version
- content_sha256
- facts[]

EvidenceCatalogSnapshot
- schema_version
- content_sha256
- modules[]
```

Hash excludes filesystem path and load time. Stable-ID ordering is canonical unless visible order is explicitly semantic.

## 7. Minimum truthful-evidence rule

A strong radar match can still be impossible to prepare truthfully.

Block with `insufficient_verified_evidence` when required CV identity/structure cannot be built, for example:

- policy-required verified identity/contact facts are missing;
- selected track has no verified experience/project/evidence module at all;
- a policy-required section has no truthful content.

A missing posting requirement alone is not a preparation hard fail. It remains an unresolved gap unless policy explicitly declares it a preparation prerequisite.

## 8. Track isolation is absolute

Facts/modules are eligible only when the selected application track is explicitly in their `track_ids`. Shared facts must explicitly list every allowed track. No cross-track fallback is permitted to make a CV look fuller.

## 9. Renderer cannot rewrite semantics

Renderer may wrap, paginate, style, and add fixed headings. It cannot paraphrase, translate, shorten, expand, or otherwise change claim meaning. Wording adaptation belongs in composition and must remain approved/provenance-backed.

## 10. V0.2C boundary

`ApplicationPacket` is preparation output only. It is not approval. It does not authorize Gmail drafts, email sending, ATS submission, browser automation, or recruiter contact. Those remain separate reviewed actions in V0.2C.
