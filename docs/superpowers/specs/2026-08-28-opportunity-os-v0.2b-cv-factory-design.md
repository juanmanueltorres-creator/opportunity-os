# Opportunity OS — V0.2B CV Factory Design

Date: 2026-08-28  
Status: review  
Base: `main` at V0.2A1 multi-intent radar  
Parent roadmap: private Opportunity OS V0.2 plan in the knowledge vault

## 1. Purpose

V0.2B turns a selected, assessed opportunity into a truthful, reproducible application-preparation artifact.

It answers:

> Given this opportunity and this candidate track, which verified facts and evidence should appear in the CV, how should they be ordered and worded, and can every consequential claim be traced back to approved source data?

The output is an `ApplicationPacket` containing a structured CV model, a private rendered PDF reference, the exact fact/evidence IDs used, unresolved gaps, version metadata, and a content hash.

V0.2B does **not** send email, discover recruiters, submit forms, accept terms, answer legal/sensitive declarations, or auto-apply. Those belong to V0.2C.

---

## 2. Design principles

1. **Truth before optimization.** A requirement match never authorizes a claim by itself.
2. **Stable provenance.** Every CV claim must reference one or more approved `fact_id` / `evidence_id` values.
3. **Track isolation.** The winning radar track controls the evidence pool. Tech evidence does not become gastronomy experience and vice versa.
4. **Structured before rendered.** The composer produces `CVDocumentModel`; rendering is a downstream pure transformation.
5. **Private personal data.** Real master facts, contact details, CV PDFs, DOCX files, and application artifacts remain local/gitignored.
6. **Deterministic core.** Selection, validation, ordering, and rendering contracts do not require an LLM or network access.
7. **LLM optional, never authoritative.** A later wording adapter may rewrite an already-approved claim while preserving meaning and provenance, but cannot create facts, numbers, tools, dates, titles, or outcomes.
8. **One ATS-first layout for V0.2B.** Additional visual templates are deliberately deferred.

---

## 3. Architecture

```text
DailyRadarBatch item
    ↓
Winning CandidateTrack
    ↓
Private MasterFactsStore
    ↓
EvidenceSelector
    ↓
CVComposer
    ↓
ClaimValidator
    ↓
CVDocumentModel
    ↓
ATSRenderer
    ↓
Private PDF artifact
    ↓
ApplicationPacket
```

Each component is independently testable without network access.

---

## 4. Private master facts

### 4.1 Goal

`MasterFacts` is the single private source of candidate claims allowed to enter generated application material.

Public repository fixtures use fictional people only.

Suggested private file:

```text
profile/master_facts.local.yaml
```

It must be gitignored.

### 4.2 Fact model

```text
MasterFact
- id
- kind
- value
- track_ids[]
- verified
- source_ref optional
- start_date optional
- end_date optional
- metadata{}
```

Initial `kind` values:

```text
identity
contact
summary_claim
skill
role
employment
education
project
language
location
link
achievement
metric
other
```

Rules:

- `id` is stable and unique.
- `verified=true` is required before a fact can support a CV claim.
- `track_ids` defines where the fact may be used.
- absent track membership means the fact is not eligible for arbitrary cross-track reuse.
- sensitive/legal self-identification is outside V0.2B master facts unless explicitly needed in a future reviewed workflow.

### 4.3 Evidence model

```text
EvidenceModule
- id
- track_ids[]
- label
- fact_ids[]
- claim_candidates[]
- keywords[]
- source_refs[]
- verified
```

An evidence module groups related verified facts into reusable application material, for example a software project, an operations role, a geoscience project, or a customer-service responsibility.

`claim_candidates` are approved meanings, not unconstrained generated prose.

---

## 5. Track selection

V0.2A already records:

```text
best_career_track
best_income_track
selected_intent
track_assessments[]
```

V0.2B chooses one `application_track_id` deterministically:

1. Use the track associated with `selected_intent` when available.
2. If the selected lane has no winning track, use the other qualifying winning track.
3. If neither is available, preparation fails safely with `track_unavailable`.

The application track limits the fact/evidence pool.

No fallback may silently borrow another track merely to fill a CV section.

---

## 6. Evidence selection

### 6.1 Input

```text
RadarAssessment
OpportunityEnrichment
application_track_id
MasterFacts
EvidenceModules
CVPolicy
```

### 6.2 Selection goals

Select truthful material that best supports:

- explicit mandatory requirements;
- preferred requirements;
- role/domain relevance;
- verified accomplishments;
- relevant operational/context experience;
- location/language facts when useful.

### 6.3 Deterministic relevance

Initial relevance is rule-based and explainable.

Signals may include:

```text
exact verified skill / approved alias
requirement keyword overlap
module keyword overlap
role/domain affinity
verified evidence already used by radar
recency when dates exist
```

A taxonomy-related skill may increase selection relevance but cannot create an exact-product claim.

### 6.4 Output

```text
EvidenceSelection
- application_track_id
- selected_fact_ids[]
- selected_evidence_ids[]
- requirement_support{}
- unsupported_requirements[]
- selection_explanations[]
```

The selector does not write CV prose.

---

## 7. CV composition

### 7.1 Structured document first

```text
CVDocumentModel
- document_version
- language
- candidate_header
- headline
- summary[]
- skills[]
- experience[]
- projects[]
- education[]
- languages[]
- links[]
- provenance_map{}
```

Each visible claim has a stable `claim_id`.

`provenance_map` maps:

```text
claim_id
→ fact_ids[]
→ evidence_ids[]
```

### 7.2 Section behavior

The composer may:

- omit irrelevant modules;
- reorder sections;
- reorder bullets;
- select a role-appropriate headline from approved facts/templates;
- choose concise approved wording variants;
- use job terminology when an approved alias/equivalence exists;
- choose ES or EN output from verified source facts and approved translations.

The composer may not:

- invent years of experience;
- infer possession of a tool from a related technology;
- change a job title into a more senior or different title;
- create metrics or numerical impact;
- claim employment at a company not present in master facts;
- claim degrees/certifications not verified;
- convert a project into paid employment;
- hide an explicit factual incompatibility.

### 7.3 Summary policy

The summary is composed from approved `summary_claim` and evidence-backed facts. It may combine them into a concise role-specific narrative, but every sentence must remain provenance-backed.

No generic unsupported adjectives such as “expert”, “senior”, or “10+ years” unless those are independently verified facts.

---

## 8. Claim validation

`ClaimValidator` is a hard gate between composition and rendering.

```text
ValidationResult
- valid
- errors[]
- warnings[]
- validated_claim_ids[]
```

Hard errors include:

- claim has no provenance;
- referenced fact/evidence does not exist;
- referenced fact/evidence is unverified;
- referenced fact belongs to an incompatible track;
- metric/number has no matching verified fact;
- tool/product claim is stronger than its evidence permits;
- title/organization/date differs from verified source facts;
- renderer-visible content is not represented by a validated claim.

Warnings include:

- important opportunity requirement unsupported;
- unusually sparse section;
- stale but still valid evidence;
- unknown language/location detail relevant to the posting.

A packet cannot reach render-ready state with hard validation errors.

---

## 9. ATS renderer

### 9.1 Scope

V0.2B ships one conservative ATS-first renderer.

Requirements:

- one-column layout;
- normal text flow;
- selectable text;
- no text baked into images;
- no decorative charts, ratings, skill bars, icons used as semantic labels, or multi-column reading ambiguity;
- standard section headings;
- deterministic section/order rendering from `CVDocumentModel`;
- output intended for PDF;
- public tests may render fictional fixtures only.

### 9.2 Renderer authority

The renderer is not allowed to create or rewrite claims.

```text
CVDocumentModel → layout only → PDF
```

If visible content is not in the validated model, rendering must fail.

### 9.3 Private artifacts

Suggested local path:

```text
artifacts/applications/<application_id>/cv.pdf
```

The whole `artifacts/applications/` tree is gitignored.

DOCX is deferred until a concrete submission channel requires it.

---

## 10. ApplicationPacket

V0.2B packet:

```text
ApplicationPacket
- application_id
- opportunity_id
- opportunity_snapshot_hash
- radar_batch_id optional
- selected_intent
- application_track_id
- match_score optional
- income_viability optional
- confidence_score
- scoring_version
- extractor_version
- alias_registry_version
- taxonomy_versions{}
- master_facts_version
- evidence_catalog_version
- cv_document_version
- selected_fact_ids[]
- selected_evidence_ids[]
- unresolved_gaps[]
- cv_pdf_path
- cv_sha256
- packet_sha256
- status
- created_at
```

Initial statuses:

```text
PREPARED
BLOCKED_VALIDATION
BLOCKED_MISSING_FACTS
```

This is a preparation artifact, not approval or submission authorization.

Any later mutation to opportunity snapshot, selected facts, evidence, CV document, or rendered PDF requires a new packet/hash.

---

## 11. Versioning and fingerprints

Results must be reproducible enough to explain why a particular CV was produced.

Version/fingerprint inputs include:

- radar scoring/extractor/alias/taxonomy versions;
- master facts canonical hash/version;
- evidence catalog canonical hash/version;
- composer version;
- CV document version;
- renderer version;
- CV policy/section ordering.

Canonical JSON serialization is used for packet hashing where applicable.

`application_id` must not be treated as approval authorization.

---

## 12. Privacy and repository boundary

Public repository MAY contain:

- schemas/models;
- deterministic selector/composer/validator;
- ATS renderer code;
- fictional fixtures;
- public templates with no personal details;
- tests.

Public repository MUST NOT contain:

- real personal master facts;
- personal phone/address/email in fixtures;
- real CV PDFs/DOCX;
- generated application packets containing personal data;
- private recruiter/contact data;
- legal/sensitive form answers;
- Gmail data/tokens;
- portal credentials.

CI must enforce private/generated artifact guards.

---

## 13. Error handling

Typed preparation errors:

```text
master_facts_unavailable
invalid_master_facts
track_unavailable
insufficient_verified_evidence
claim_validation_failed
render_failed
artifact_write_failed
version_mismatch
```

Rules:

- errors never dump private master-facts contents;
- rendering failure never changes source facts;
- packet is not marked PREPARED unless validation and artifact hashing both succeed;
- missing evidence is surfaced as a gap, never converted into an invented claim.

---

## 14. API / service boundary

Primary service:

```python
class CVPreparationService:
    def prepare(
        self,
        assessment: RadarAssessment,
        master_facts: MasterFacts,
        evidence_catalog: EvidenceCatalog,
        policy: CVPolicy,
        now: datetime,
    ) -> ApplicationPacket: ...
```

V0.2B does not require a public HTTP endpoint to be useful.

Preferred first interface is service/CLI/local invocation so personal data does not have to cross an HTTP boundary unnecessarily.

An API endpoint may be added later only if there is a concrete operator need.

---

## 15. Language policy

Initial output languages:

```text
es

en
```

Source facts stay canonical. Approved translations or deterministic labels can provide language-specific display values.

A translation may alter wording, not meaning.

If no approved translation exists for a consequential free-text claim, keep the canonical language or block that translation rather than fabricate one.

---

## 16. Testing strategy

CI remains offline and uses fictional data.

### Contracts

- strict master fact/evidence schemas;
- aware timestamps;
- stable IDs;
- canonical fingerprints/hashes;
- real personal file patterns remain forbidden.

### Track isolation

- tech application cannot consume gastronomy-only fact;
- gastronomy application cannot consume tech-only role claim;
- shared fact requires explicit membership in both tracks.

### Evidence selection

- exact requirement support outranks merely related evidence;
- unsupported mandatory requirement remains a gap;
- selected IDs are deterministic;
- selection never upgrades taxonomy-related evidence to exact-product proof.

### Composition

- same inputs/version produce identical `CVDocumentModel`;
- irrelevant evidence can be omitted;
- ordering changes by role while facts remain unchanged;
- no section may contain unreferenced claim text.

### Validation

- unverified fact hard-fails;
- nonexistent provenance hard-fails;
- unsupported metric hard-fails;
- modified employer/title/date hard-fails;
- unsupported requirement is warning/gap, not invented content.

### Renderer

- renderer consumes validated structured model only;
- PDF is generated from fictional fixture;
- deterministic text/section ordering;
- rendering cannot insert additional claims;
- failure leaves no PREPARED packet.

### Packet

- packet hash changes when CV/facts/evidence change;
- identical canonical inputs produce identical content hashes;
- packet records radar + CV versions;
- packet never authorizes submission.

### Regression / safety

- all V0.2A1 radar tests remain green;
- public repo contains no real CV/master facts/generated private artifacts;
- V0.1/V0.2A APIs remain unchanged unless separately specified.

---

## 17. Deliberate exclusions

Not V0.2B:

- recruiter/contact discovery;
- Apollo enrichment;
- Gmail draft creation;
- mail copy generation;
- mail sending;
- browser/form automation;
- ATS submission;
- approval UI/workflow;
- application ledger/outcome learning;
- DOCX unless a real channel requires it;
- multiple visual CV designs;
- LLM as source of truth;
- autonomous semantic fact creation.

These exclusions keep V0.2B focused on one hard problem: produce a tailored CV that is both useful and provably truthful.

---

## 18. Success criteria

V0.2B is complete when, for a fictional selected radar opportunity, the system can:

1. choose the correct candidate track;
2. load only verified facts/evidence allowed for that track;
3. select relevant evidence deterministically;
4. produce an opportunity-specific `CVDocumentModel`;
5. prove every consequential visible claim against fact/evidence IDs;
6. surface unsupported job requirements as gaps rather than inventions;
7. render one ATS-friendly private PDF artifact;
8. hash the CV and packet reproducibly;
9. produce an `ApplicationPacket` ready to become V0.2C email/submission input;
10. keep all V0.2A1 regressions and privacy guards green.
