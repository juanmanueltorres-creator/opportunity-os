# Opportunity OS — V0.2B CV Factory Self-Review Clarifications

Date: 2026-08-28  
Status: normative-review  
Applies to: `2026-08-28-opportunity-os-v0.2b-cv-factory-design.md`

This clarification is normative for V0.2B planning and implementation. Where wording in the base design is ambiguous, this file wins.

## 1. What `verified` means

A boolean alone is not sufficient provenance.

`MasterFact` must record:

```text
verification_method
verified_at
source_ref optional
```

Initial `verification_method` values:

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

- `verified=true` requires a non-empty `verification_method` and timezone-aware `verified_at`.
- `source_ref` is mandatory for evidence-backed methods such as repository/document/employment/education/public-profile evidence.
- `manual_confirmation` is permitted for facts that are legitimately self-attested, such as preferred display name, phone, email, city, or an explicitly reviewed summary wording.
- `manual_confirmation` does not permit inventing employment, education, certifications, metrics, tools, dates, or external outcomes.
- Verification records are private candidate data and must not be committed with real values.

## 2. Blocked preparation versus prepared packet

A failed preparation must not pretend a PDF exists.

Use:

```text
PreparationResult
- status
- packet optional
- errors[]
- warnings[]
```

`ApplicationPacket` exists only when the CV has passed claim validation and the rendered artifact has been hashed successfully.

Therefore:

```text
PREPARED
→ packet is present
→ cv_pdf_path present
→ cv_sha256 present
→ packet_sha256 present

BLOCKED_VALIDATION / BLOCKED_MISSING_FACTS
→ packet is absent
→ structured errors/gaps are returned
→ no fake/null-filled prepared artifact is persisted
```

This supersedes any interpretation of the base design that makes `ApplicationPacket.status` carry blocked states.

## 3. Reproducible hashing

`packet_sha256` is a content hash, not an execution-instance hash.

Canonical packet-hash input MUST exclude:

```text
application_id
created_at
cv_pdf_path
filesystem-specific values
```

It MUST include the semantic preparation inputs/outputs needed to detect a meaningful change, including:

```text
opportunity_snapshot_hash
selected_intent
application_track_id
radar/scoring versions
master_facts_version
evidence_catalog_version
composer_version
cv_document_version
renderer_version
selected_fact_ids[]
selected_evidence_ids[]
unresolved_gaps[]
canonical CVDocumentModel content
cv_sha256
```

Lists whose order is semantically irrelevant must be canonicalized before hashing. Lists whose order is visible in the CV retain order.

`application_id` is an opaque execution/application identifier and is not an approval token.

## 4. Deterministic PDF bytes

If V0.2B claims reproducible `cv_sha256`, the renderer must control nondeterministic PDF metadata.

The renderer must not inject current timestamps, random document IDs, machine-specific paths, or unstable metadata into the PDF bytes.

For identical validated `CVDocumentModel` + renderer version + renderer policy, `cv_sha256` should be stable in CI fixtures.

If the chosen PDF library cannot guarantee this, the implementation plan must either configure deterministic metadata explicitly or downgrade the guarantee and separately hash canonical rendered content. It may not silently claim deterministic PDF hashing when the bytes are nondeterministic.

## 5. Renderer-visible text and provenance

The base rule “renderer-visible content must be represented by a validated claim” applies to candidate/application content, not fixed presentation labels.

Allowed unprovenanced fixed template labels include language-specific section headings such as:

```text
Experience / Experiencia
Projects / Proyectos
Education / Educación
Skills / Habilidades
```

The following still require provenance-backed structured values:

- candidate name;
- phone/email/location;
- headline;
- summary text;
- employer/organization names;
- role titles;
- dates;
- bullets;
- project names/descriptions;
- education claims;
- skills;
- languages/levels;
- links.

The renderer may format these values but cannot alter their semantic content.

## 6. MasterFacts and EvidenceCatalog version identity

`master_facts_version` and `evidence_catalog_version` are canonical content fingerprints, not manually maintained labels alone.

Recommended representation:

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

The content hash excludes filesystem path and load time. Canonical ordering is by stable ID unless visible ordering is explicitly part of the data model.

## 7. Minimum evidence rule

An opportunity can be an excellent radar match and still be impossible to prepare truthfully.

Preparation blocks with `insufficient_verified_evidence` only when required CV identity/structure cannot be built truthfully, for example:

- no verified candidate identity/contact facts required by policy;
- selected application track has no verified experience/project/evidence modules at all;
- a required section configured by policy has no truthful content.

An unsupported job requirement by itself is **not** a preparation hard fail. It remains an `unresolved_gap` unless CV policy explicitly declares that requirement a preparation prerequisite.

This prevents the CV factory from inventing facts while also avoiding needless blocking whenever the candidate simply does not satisfy every posting requirement.
