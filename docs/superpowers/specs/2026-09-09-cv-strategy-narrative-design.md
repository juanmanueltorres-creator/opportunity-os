# CV Strategy, Narrative Composition, Layout, and Quality Architecture

**Date:** 2026-09-09  
**Status:** Proposed for implementation after review  
**Scope:** Opportunity-OS CV preparation pipeline  

## 1. Problem statement

Opportunity-OS already has a strong evidence-first CV pipeline. It can select verified evidence, compose claims with provenance, validate those claims, render a recruiter-facing PDF, and reject outputs that violate physical constraints such as page count, text extraction, minimum font size, or page overflow.

That is necessary but not sufficient.

The current pipeline can produce a PDF that is factually defensible and mechanically valid while still being a poor recruiting document. The missing capabilities are:

- an explicit strategy for what the recruiter should understand about the candidate;
- narrative ranking and omission rules;
- control of competing professional identities;
- visual hierarchy and scanability checks;
- separation between narrative policy and rendering policy;
- renderer-independent resume data export;
- ATS round-trip validation after rendering.

The conceptual bug is:

> `render succeeded` and `ATS-readable` do not imply `CV succeeded`.

A document must not reach `PREPARED` merely because it fits on a page and its text can be extracted.

## 2. Design goals

The new subsystem MUST:

1. preserve the existing evidence and provenance guarantees;
2. introduce an explicit per-opportunity CV strategy before recruiter-document composition;
3. make the document communicate no more than a small number of coherent core messages;
4. rank visible claims by strategy relevance, evidence strength, specificity, and impact rather than source order alone;
5. penalize redundancy, generic language, unsupported identity noise, and verbosity;
6. reject unsupported seniority/title inflation rather than merely scoring it lower;
7. keep user-specific career tracks outside the public core;
8. keep rendering interchangeable and downstream of content decisions;
9. validate semantic quality, narrative quality, visual quality, and ATS recoverability independently;
10. retain RenderCV/Typst as a safe existing renderer while allowing additional renderers;
11. remain reproducible through versioned policies, strategies, layout profiles, renderer versions, and QA results;
12. evolve the existing pipeline incrementally rather than replacing it wholesale.

## 3. Non-goals

The first version will NOT:

- build a full graphical resume editor;
- fork or embed the complete Reactive Resume application;
- replace Opportunity-OS provenance with JSON Resume;
- generate arbitrary decorative templates;
- use photos, charts, skill bars, or other ATS-hostile visual elements in the default layouts;
- allow an LLM to invent unsupported claims or seniority;
- claim to reproduce the behavior of a specific commercial ATS vendor;
- optimize directly for a single ATS vendor;
- make user-specific career identities part of the public repository.

## 4. Existing architecture to preserve

The current conceptual chain is valuable and remains the source of truth:

```text
MasterFactsSnapshot
        +
EvidenceCatalogSnapshot
        ↓
EvidenceSelector
        ↓
CVDocumentModel
        ↓
claim validation + provenance
        ↓
RecruiterDocumentModel
        ↓
renderer
        ↓
PDF QA
        ↓
ApplicationPacket
```

`CVDocumentModel` remains authoritative for visible claims and provenance. JSON Resume, renderer payloads, and PDFs are projections of that model, not replacements for it.

The existing orchestration boundary in `CVPreparationService` also remains. The service will gain stages rather than being replaced.

## 5. Target architecture

```text
RadarAssessment / Opportunity
            ↓
Requirement extraction / enrichment
            ↓
EvidenceSelector
            ↓
CVDocumentModel
            ↓
Semantic validation
            ↓
CVStrategyBuilder
            ↓
CVStrategy
            ↓
NarrativeComposer
            ↓
RecruiterDocumentModel
            ↓
Narrative QA
            ↓
LayoutSelector
            ↓
LayoutProfile
            ↓
Renderer
            ↓
Rendered artifact
            ↓
┌──────────────────────────────┐
│ Render / structural QA       │
│ Visual QA                    │
│ ATS round-trip QA            │
└──────────────┬───────────────┘
               ↓
        ApplicationPacket
```

The core separation is:

- **EvidenceSelector:** what can be supported.
- **CVStrategyBuilder:** what should be communicated for this opportunity.
- **NarrativeComposer:** which supported claims should be visible and in what order.
- **Validator:** whether claims remain evidence-safe.
- **LayoutSelector:** how the narrative should be presented.
- **Renderer:** how that layout becomes an artifact.
- **QA layers:** whether the resulting artifact remains semantically, narratively, visually, and ATS-recoverable.

## 6. CV strategy model

`CVStrategy` is an editorial plan, not final resume copy.

Proposed model:

```python
class CoreMessage(StrictCVModel):
    id: str
    message: str
    fact_ids: list[str]
    evidence_ids: list[str]
    importance: float
    reason: str


class CVStrategy(StrictCVModel):
    strategy_version: str
    application_track_id: str
    target_role: str
    target_company: str | None
    positioning: str
    recruiter_question: str
    core_messages: list[CoreMessage]
    must_show_fact_ids: list[str]
    supporting_fact_ids: list[str]
    optional_fact_ids: list[str]
    explicit_gaps: list[str]
    preferred_section_order: list[str]
    preferred_layout_profile_id: str | None
```

### Strategy invariants

- A strategy MUST contain at least one and at most three core messages.
- Every core message MUST resolve to verified or otherwise permitted facts/evidence under the existing evidence contract.
- A strategy MUST record explicit material gaps rather than silently papering over them.
- `positioning` is a recruiter-facing framing, not permission to create a new unsupported title.
- Unsupported seniority/title upgrades MUST be rejected by strategy validation.
- A strategy MUST be deterministic for identical versioned inputs and policies unless a non-deterministic strategy provider is explicitly introduced later.

## 7. Strategy construction

The initial `CVStrategyBuilder` should be rules-first and deterministic.

Inputs:

- selected opportunity and enrichment;
- application track;
- `EvidenceSelection`;
- `CVDocumentModel`;
- versioned `NarrativePolicy`;
- optional user-private track configuration.

The builder should derive:

- the primary recruiting question;
- a role-safe positioning statement;
- up to three core messages;
- must-show and optional evidence;
- explicit gaps;
- preferred section order;
- preferred layout family.

An LLM may later propose strategy candidates, but a deterministic validator must constrain the result to supported facts, allowed aliases, and policy.

## 8. User-private track configuration

The public core MUST remain candidate-agnostic.

User-specific configuration belongs in an external/private runtime location that is not committed to the public repository. An illustrative local layout is:

```text
<private-state-root>/
  profiles/
    <user>/
      tracks/
        software_data.yaml
        geospatial_domain.yaml
        operations_support.yaml
```

If a developer chooses a path under the local checkout, that path MUST be gitignored and treated as private state. Public examples MUST use synthetic data only.

A private track may express:

```yaml
id: software_data
preferred_layout: technical_clean
priorities:
  - software systems
  - data infrastructure
  - automation
  - decision support
deemphasize:
  - unrelated identity signals
allow_as_context:
  - domain expertise
  - operations experience
```

The public repository provides schemas, validation, examples with synthetic data, and default policies only.

## 9. Narrative composition

The existing recruiter compositor benefits from verified and supported claim ordering, but the new composer must explicitly rank claims against the strategy.

Proposed score family:

```text
narrative_score =
    requirement_relevance
  + core_message_support
  + evidence_strength
  + specificity
  + measurable_impact
  + recency_weight
  - redundancy_penalty
  - generic_language_penalty
  - competing_identity_penalty
  - verbosity_penalty
```

Unsupported seniority/title inflation is not a score term. It is a validation failure.

The exact numeric weights are policy, not model semantics. They MUST be versioned.

### Composition rules

The V1 composer MUST:

- select and reorder only claims already present in the validated semantic document;
- NOT mint new recruiter-facing claim text inside the narrative stage;
- prioritize claims that support the strategy's core messages;
- prevent one weak keyword match from displacing stronger direct evidence;
- suppress generic claims when more specific evidence exists;
- avoid repeating the same concept across summary, skills, projects, and experience unless repetition is policy-justified;
- avoid exposing unrelated identities that compete with the selected positioning;
- preserve enough context that a recruiter can understand chronology and role history without reading an exhaustive biography.

Any future rewrite/transformation stage that creates new visible wording requires its own evidence-safe design and validation contract.

## 10. Narrative policy

Narrative constraints must be separated from physical PDF constraints.

Proposed configuration:

```yaml
version: narrative-policy-v1
max_core_messages: 3
max_competing_identity_signals: 3
summary:
  max_sentences: 3
  max_words: 65
experience:
  max_entries: 4
  max_bullets_per_entry: 3
projects:
  max_entries: 3
bullet:
  preferred_min_words: 12
  preferred_max_words: 24
  hard_max_words: 32
penalties:
  generic_claim: 0.8
  duplicate_concept: 0.7
  competing_identity: 0.8
```

Seniority safety is enforced as validation, not a soft policy penalty.

This policy replaces no existing validation initially. It is introduced alongside existing `RecruiterPolicy` and later participates in a controlled policy split.

## 11. Narrative QA

Narrative QA runs before rendering and evaluates the recruiter document against its strategy.

Proposed result:

```python
class NarrativeQAResult(StrictCVModel):
    valid: bool
    core_message_coverage: dict[str, float]
    off_strategy_claim_ratio: float
    competing_identity_count: int
    scanability_score: float
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]
```

Required checks:

1. **Core-message coverage:** each core message must have visible supporting evidence.
2. **Off-strategy ratio:** visible claims not supporting positioning, required chronology, or material context must stay below a policy threshold.
3. **Identity coherence:** the document must not present too many competing professional identities.
4. **Generic-language detection:** generic claims should not consume scarce visible space when specific evidence is available.
5. **Seniority safety:** visible titles/headlines must not imply unsupported seniority.
6. **Scan view:** a reduced view containing headline, section headings, entry titles, and first bullet clauses should still communicate the strategy.

A narrative failure MUST prevent `PREPARED` on the strategy-aware path.

## 12. Layout profiles

The layout system should begin with three strong profiles rather than a large template catalog.

### `technical_clean`

Use for software, data, engineering, geospatial, and similar technical roles.

Characteristics:

- one column;
- strong name/headline hierarchy;
- restrained section separators;
- projects and technical evidence easy to scan;
- generous but controlled whitespace;
- no decorative graphics.

### `operations_clean`

Use for support, operations, production, and execution-heavy roles.

Characteristics:

- traditional chronology emphasis;
- experience before projects where appropriate;
- skills/tools grouped for rapid operational scan;
- one column by default;
- conservative typography.

### `compact_ats`

Fallback when ATS uncertainty is high.

Characteristics:

- single column;
- minimal styling;
- plain headings;
- no icons or visual constructs that could alter extraction order;
- deterministic textual order.

## 13. Layout model

```python
class LayoutProfile(StrictCVModel):
    id: str
    version: str
    density: Literal["compact", "balanced", "spacious"]
    hierarchy: Literal["classic", "technical", "editorial"]
    columns: Literal[1, 2]
    page_size: Literal["A4", "LETTER"]
    typography_profile: str
    spacing_profile: str
    emphasis_profile: str
    ats_safe: bool
```

V1 defaults to one-column profiles. Two-column support may exist in the model but MUST NOT be required for V1 success.

## 14. Rendering policy split

The current one-page rule is a presentation policy and should not remain a domain invariant.

Target split:

```yaml
version: render-policy-v1
page_size: A4
preferred_pages: 1
max_pages: 2
minimum_body_font_pt: 9.5
```

`preferred_pages: 1` means the reduction loop should attempt a high-quality one-page result first. `max_pages: 2` allows the system to preserve narrative quality rather than destroying content purely to satisfy an absolute one-page constraint.

This split must be introduced with backward-compatible defaults so existing CLI behavior can remain one-page until the rollout explicitly changes it.

## 15. Renderer architecture

V1 keeps the existing RenderCV/Typst path.

```text
RecruiterDocumentModel
        +
LayoutProfile
        ↓
RenderCV adapter
        ↓
PDF
```

A later visual renderer may use React-PDF or another MIT-compatible implementation, but it MUST consume the same recruiter document and layout abstraction.

A second renderer is not required before strategy and narrative QA are proven.

## 16. JSON Resume interoperability

JSON Resume is an export/projection boundary:

```text
RecruiterDocumentModel
        ↓
JSONResumeAdapter
        ↓
resume.json
```

Rules:

- JSON Resume MUST NOT become the canonical evidence store.
- Provenance that cannot be represented by the standard schema remains in Opportunity-OS.
- Export must be deterministic and versioned.
- Import is explicitly out of scope for V1 unless separately designed.

## 17. Visual QA

Visual QA is separate from ATS QA and existing structural PDF QA.

Proposed result:

```python
class VisualQAResult(StrictCVModel):
    valid: bool
    hierarchy_score: float
    density_score: float
    whitespace_score: float
    scanability_score: float
    consistency_score: float
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]
```

V1 checks should include:

- readable hierarchical font relationships;
- acceptable page fill range;
- no extreme over-compression;
- no giant dead zones;
- no isolated headings;
- no wall-of-text regions beyond policy thresholds;
- consistent section spacing;
- coherent alignment and indentation;
- no overflow or clipped content.

Where possible, metrics should be derived from PDF text blocks and coordinates so tests remain deterministic.

## 18. ATS round-trip QA

ATS quality should be measured after rendering, not assumed from source structure.

Interface:

```python
class ResumeParserAdapter(Protocol):
    def parse(self, pdf_path: str | Path) -> ParsedResume: ...
```

The first implementation MAY be a local deterministic parser built on extractable PDF text and structural heuristics. External parsers can later be added as optional adapters.

Round-trip flow:

```text
RecruiterDocumentModel
        ↓
PDF
        ↓
ResumeParserAdapter
        ↓
ParsedResume
        ↓
semantic comparison
```

Required recovery categories:

- identity;
- contact information;
- experience entry titles;
- critical skills;
- education;
- links where present.

Critical identity fields must recover at 100%. Non-critical aggregate recovery thresholds are policy-controlled and versioned.

This QA is explicitly a **recoverability proxy**: it verifies that structured information survives the render/parse round trip. It MUST NOT be described as proof that every commercial ATS will parse or rank the document identically.

## 19. ApplicationPacket changes

`ApplicationPacket` will gain, incrementally as each stage becomes authoritative:

```text
strategy_version
strategy
narrative_policy_version
layout_profile_id
layout_profile_version
narrative_qa
visual_qa
ats_qa
```

These fields make a prepared CV reproducible and auditable.

Packet hashing MUST incorporate the added versioned strategy, layout, and QA data once those fields become authoritative.

A schema-versioning or backward-compatible migration must accompany these additions so existing packet fixtures do not break silently.

## 20. Failure states

V1 may continue mapping failures into existing broad preparation states, but failures must have precise issue codes.

Required issue-code families:

```text
strategy_*
narrative_*
visual_*
ats_roundtrip_*
```

Examples:

```text
strategy_core_message_unsupported
strategy_unsupported_seniority
narrative_off_strategy_ratio_exceeded
narrative_competing_identity_limit_exceeded
narrative_scanability_failed
visual_density_too_high
visual_hierarchy_invalid
ats_roundtrip_identity_missing
ats_roundtrip_skill_recovery_low
```

Later, `PreparationStatus` may be expanded with dedicated blocked states only if operational value justifies the schema cost.

## 21. Reduction behavior

The current reduction loop primarily removes content until physical constraints are satisfied. The new behavior must be strategy-aware.

Reduction priority should be:

1. redundant links;
2. low-strategy-relevance skills;
3. optional low-strategy-relevance project details;
4. optional experience details;
5. optional training/education details;
6. only then reconsider page count within render policy.

Reduction MUST NOT remove the only evidence supporting a core message.

After every reduction:

- recruiter-document validation reruns;
- narrative QA reruns;
- rendering and downstream QA rerun.

## 22. Regression fixtures

The repository should contain synthetic regression fixtures representing known failure classes without exposing user-private CV data.

Suggested fixtures:

```text
tests/fixtures/cv_quality/
  narrative_identity_soup/
  dense_valid_but_unreadable/
  sparse_underfilled/
  unsupported_seniority/
  ats_extraction_loss/
```

A synthetic `identity_soup` fixture should deliberately include several individually valid but mutually competing identity signals. It should pass semantic validation and fail narrative QA.

A `dense_valid_but_unreadable` fixture should remain text-extractable and within page bounds while failing visual density/scanability thresholds.

These fixtures turn known failure modes into permanent regression protection.

## 23. Proposed code structure

```text
app/cv/
├── models.py
├── selector.py
├── composer.py
├── validator.py
├── service.py
│
├── strategy/
│   ├── __init__.py
│   ├── models.py
│   ├── builder.py
│   ├── policy.py
│   └── scoring.py
│
├── narrative/
│   ├── __init__.py
│   ├── composer.py
│   ├── ranking.py
│   ├── reducer.py
│   └── qa.py
│
├── layout/
│   ├── __init__.py
│   ├── models.py
│   ├── selector.py
│   └── visual_qa.py
│
├── adapters/
│   └── json_resume.py
│
├── ats/
│   ├── __init__.py
│   ├── models.py
│   ├── parser.py
│   └── roundtrip_qa.py
│
└── renderers/
    └── rendercv_typst.py

config/
├── narrative_policy.yaml
├── render_policy.yaml
└── cv_layouts/
    ├── technical_clean.yaml
    ├── operations_clean.yaml
    └── compact_ats.yaml
```

The exact file split may be adjusted during implementation if tests reveal a simpler boundary, but the conceptual modules and responsibilities must remain separated.

## 24. Incremental implementation sequence

### PR 1 — Strategy foundation

Add `CVStrategy`, `CoreMessage`, policy, builder, and tests. Compute strategy without changing rendered output.

Exit criteria:

- deterministic strategy from current pipeline inputs;
- max-three-core-message invariant;
- unsupported seniority/title invariant enforced as a validation failure;
- no production PDF change.

### PR 2 — Strategy-aware narrative composer

Add ranking and new compositor behind an explicit integration path. Keep legacy compositor available during migration.

Exit criteria:

- side-by-side comparison fixtures;
- evidence/provenance invariants preserved;
- strategy relevance affects ordering and inclusion;
- no new visible claim text is minted by the narrative composer.

### PR 3 — Narrative QA

Add coverage, identity coherence, generic-language, off-strategy, and scanability gates.

Exit criteria:

- synthetic identity-soup fixture fails;
- coherent fixture passes;
- narrative failure blocks preparation on the new path.

### PR 4 — Policy split

Separate `NarrativePolicy` and `RenderPolicy` from the legacy mixed recruiter policy while retaining compatibility.

Exit criteria:

- current CLI behavior remains reproducible;
- one-page behavior remains default until explicitly changed;
- no semantic model requires exactly one page.

### PR 5 — Layout profiles

Add layout abstraction and three V1 profiles.

Exit criteria:

- layout selection is deterministic;
- RenderCV consumes selected layout settings through a stable adapter;
- no user-private identity data is committed.

### PR 6 — Visual QA

Add deterministic PDF geometry checks for density, spacing, hierarchy, and scanability.

Exit criteria:

- dense-but-valid regression fixture fails visual QA;
- existing good fixture passes structural and visual QA.

### PR 7 — JSON Resume export

Add deterministic adapter from recruiter document to JSON Resume.

Exit criteria:

- schema-valid export for supported fields;
- provenance remains in Opportunity-OS;
- snapshot tests guarantee stable mapping.

### PR 8 — Optional second renderer

Introduce a human-first renderer only after narrative and layout contracts are stable.

Exit criteria:

- consumes existing `RecruiterDocumentModel` and `LayoutProfile`;
- no duplicate content composition path;
- rendered output passes all shared QA contracts.

### PR 9 — ATS round-trip

Add parser interface, local parser implementation, semantic recovery comparison, and thresholds.

Exit criteria:

- critical fields recover at required thresholds;
- extraction-loss fixture fails;
- round-trip result is written into `ApplicationPacket`;
- documentation calls the check a recoverability proxy, not vendor ATS emulation.

## 25. Testing strategy

Implementation must follow test-first changes for each PR.

Required test layers:

### Unit tests

- strategy construction and invariants;
- narrative ranking;
- penalty behavior;
- layout selection;
- JSON Resume mapping;
- QA threshold calculations.

### Contract tests

- provenance remains complete;
- unsupported claims never become visible;
- strategy cannot create unsupported seniority;
- core-message evidence cannot be removed by reduction;
- renderer adapters preserve canonical order where required.

### Regression tests

Synthetic fixtures for:

- identity soup;
- generic filler;
- dense visual output;
- sparse output;
- unsupported seniority;
- ATS recovery failure.

### Integration tests

The preparation CLI should continue to support an end-to-end preparation path and expose precise errors when any new gate fails.

## 26. Backward compatibility

The migration must be staged.

Rules:

- no existing public API or CLI flag is removed in PRs 1–3;
- legacy recruiter composition remains available until strategy-aware composition passes regression coverage;
- existing packet fixtures are migrated explicitly when packet schema changes;
- RenderCV remains the default renderer throughout the initial migration;
- the default render policy initially reproduces existing one-page behavior;
- new failure gates may first run in shadow/report mode in fixtures before becoming blocking in production, but blocking behavior is required before V1 is declared complete.

## 27. External project usage and licensing

Opportunity-OS may study compatible open-source resume projects for architecture and implementation ideas.

Current design assumptions:

- Reactive Resume is suitable as an architectural/reference source for templates, structured styling, and renderer separation where its MIT-licensed code is reused with required attribution/license compliance.
- Resume Matcher is suitable as a reference for resume/job matching concepts under its Apache-2.0 license, subject to normal notice requirements if code is reused.
- OpenResume should be treated as a benchmark/reference rather than copied into the core because its AGPL license would impose different distribution obligations.
- JSON Resume is used as an interoperability schema/export target, not as the provenance source of truth.

Any actual code reuse must be reviewed at the specific file/dependency level during implementation; this design document does not itself authorize wholesale copying.

## 28. Observability and reproducibility

For every successful preparation, Opportunity-OS should eventually be able to answer:

- which facts and evidence were selected;
- which strategy version ran;
- which core messages were chosen;
- why each visible claim was selected;
- which claims were reduced and why;
- which layout profile and renderer version were used;
- what narrative, visual, and ATS QA scores were produced;
- what exact versions and hashes reproduce the artifact.

This extends the existing provenance model from `why is this claim true?` to also answer `why is this claim visible in this particular CV?`.

## 29. V1 definition of done

The subsystem is V1-complete when a caller can provide:

```text
opportunity
+ master facts
+ evidence catalog
+ application track/private track config
```

and obtain a CV pipeline result that is simultaneously:

- factually defensible;
- provenance-complete;
- coherent around no more than three core messages;
- adapted to the opportunity without unsupported title/seniority inflation;
- visually professional under a defined layout profile;
- readable in a recruiter scan view;
- ATS-recoverable under round-trip recovery thresholds;
- reproducible from versioned inputs and policies;
- free of required user-private configuration in the public repository.

Most importantly:

> A PDF that passes structural/text extraction checks but fails narrative or visual quality MUST NOT be marked `PREPARED`.

## 30. Architectural decision summary

The approved direction is an incremental extension of Opportunity-OS rather than a resume-builder replacement:

```text
Evidence
  ↓
Semantic CV
  ↓
Strategy
  ↓
Narrative
  ↓
Layout
  ↓
Renderer
  ↓
Semantic + Narrative + Visual + ATS Recoverability QA
  ↓
ApplicationPacket
```

Opportunity-OS remains the evidence and decision engine. Renderers remain replaceable projections. User-specific positioning remains private configuration. Quality is promoted from a page-fit check to a first-class, multi-layer contract.
