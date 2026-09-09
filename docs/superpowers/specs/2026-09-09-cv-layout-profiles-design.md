# CV Layout Profiles Design

## Goal

Introduce a deterministic, ATS-safe presentation layer between `CVStrategy` and `RenderCVTypstRenderer` so Opportunity-OS can choose among a small set of role-appropriate visual layouts without changing claim selection, claim order, provenance, or render safety.

## Why this exists

The current CV pipeline can now decide what can be said, what should be said, whether the narrative is coherent, and whether the result passes a ten-second semantic scan. The remaining presentation problem is that the renderer still uses one fixed RenderCV design for every role. Layout choice must become explicit, testable, and separate from narrative policy.

## Scope

PR #47 introduces:

1. A versioned `LayoutProfile` contract.
2. Three public ATS-safe profiles:
   - `technical_clean`
   - `operations_clean`
   - `compact_ats`
3. A deterministic `LayoutSelector`.
4. Service wiring that resolves one profile per prepared CV.
5. Renderer wiring that uses the selected profile's design configuration.
6. Tests proving layout selection cannot alter recruiter-facing claims or bypass existing semantic/narrative/render gates.

PR #47 does **not** introduce Visual QA, a second renderer, JSON Resume, ATS round-trip QA, ApplicationPacket schema changes, Gmail/outreach behavior, or private candidate track configuration.

## Architectural position

```text
EvidenceSelection
    ↓
CVStrategy
    ↓
Narrative Composer
    ↓
Narrative QA
    ↓
LayoutSelector
    ↓
LayoutProfile
    ↓
RenderCVTypstRenderer
    ↓
RecruiterQualityQA
```

The layout layer is presentation-only. It cannot become a second narrative engine.

## Core boundaries

### Narrative owns content

`CVStrategy`, the narrative composer, and narrative QA remain authoritative for:

- which facts are selected;
- which claims are visible;
- recruiter-facing ordering of claims and sections;
- core-message coverage;
- positioning;
- must-show/supporting/optional evidence;
- explicit gaps.

### Layout owns presentation

`LayoutProfile` may control only physical/visual presentation parameters such as:

- RenderCV design file;
- spacing/density class;
- emphasis level;
- typography scale intent;
- section-separator style;
- conservative ATS presentation mode.

A layout profile must not:

- add, remove, rewrite, or reorder claim IDs;
- change `RecruiterDocumentModel` content;
- change evidence/provenance;
- change `CVStrategy`;
- override `RenderPolicy` page-size, page-count, or minimum-font constraints;
- mint recruiter-facing text.

### RenderPolicy remains physically authoritative

`RenderPolicy` remains the only authority for:

- `page_size`;
- `preferred_pages`;
- `max_pages`;
- `min_body_font_pt`;
- `preferred_body_font_pt`.

`LayoutProfile` cannot weaken these constraints.

## Versioned model

Create `app/cv/layout/models.py` with:

```python
LAYOUT_PROFILE_VERSION = "layout-profile-v1"

class LayoutProfile(StrictCVModel):
    version: str
    id: Literal["technical_clean", "operations_clean", "compact_ats"]
    design_path: str
    density: Literal["comfortable", "balanced", "compact"]
    emphasis: Literal["technical", "experience", "neutral"]
    ats_mode: Literal["strict"] = "strict"
```

Validation requirements:

- `version` must equal `layout-profile-v1`;
- `design_path` must be non-empty and repository-relative;
- `ats_mode` must remain `strict` in V1;
- no unknown fields;
- profile IDs are closed to the three V1 values.

The model intentionally does not contain section order, claim IDs, narrative weights, page count, or font minimums.

## Public profile registry

Create `config/layout_profiles.yaml` as the single public registry for V1.

Required IDs and intended behavior:

### `technical_clean`

Purpose: software, data, geospatial, engineering, and technical-product roles.

Visual intent:

- clear hierarchy;
- comfortable but efficient spacing;
- stronger visual grouping for technology and selected projects;
- one-column ATS-safe structure;
- no sidebars, charts, icons as semantic carriers, progress bars, skill meters, or multi-column reading order.

### `operations_clean`

Purpose: operations, support, field-support, production, and process-oriented roles.

Visual intent:

- traditional chronological reading;
- stronger emphasis on experience entries;
- balanced spacing;
- conservative one-column ATS-safe structure;
- fewer visual cues that privilege projects over work history.

### `compact_ats`

Purpose: universal fallback and highly conservative ATS contexts.

Visual intent:

- compact density;
- neutral emphasis;
- maximum simplicity;
- one-column layout;
- no decorative layout features that could reduce parser recoverability.

Each profile points to a separate RenderCV design file under `config/layouts/`.

## Layout selection contract

Create `app/cv/layout/selector.py` with:

```python
def select_layout_profile(
    *,
    strategy: CVStrategy,
    profiles: Mapping[str, LayoutProfile],
) -> LayoutProfile:
```

Selection order is deterministic:

1. If `strategy.preferred_layout_profile_id` is present:
   - it must exist in the profile registry;
   - return it;
   - otherwise fail closed with `ValueError("layout_profile_unavailable")`.
2. Otherwise use the public track mapping:
   - `software-data-decision` → `technical_clean`
   - `geospatial-mining-tech` → `technical_clean`
   - `operations-support` → `operations_clean`
3. Any other track → `compact_ats`.

The selector must never infer from free-form job-title keywords. V1 selection is based only on explicit strategy preference or the stable application-track ID.

Private candidate configuration remains outside the public repository. Public mapping may reference the generic public track IDs already used by the CV system, but must not commit Juan-specific evidence, personal claims, or private track metadata.

## Loader contract

Create `app/cv/layout/policy.py` or an equivalently focused loader module with:

```python
def load_layout_profiles(path: str | Path) -> dict[str, LayoutProfile]:
```

Requirements:

- YAML root must be a mapping;
- every key must equal the contained profile `id`;
- duplicate IDs are impossible by construction;
- all three V1 profiles must be present;
- unexpected profile IDs fail validation;
- returned mapping is deterministic by profile ID.

## Renderer integration

`RenderCVTypstRenderer` currently accepts a renderer-level design path at construction time. PR #47 changes the render contract so the selected layout profile is explicit for each render.

Preferred interface:

```python
def render(
    self,
    recruiter_document: RecruiterDocumentModel,
    source_document: CVDocumentModel,
    output_path: str | Path,
    policy: RecruiterPolicy,
    layout_profile: LayoutProfile,
) -> RecruiterRenderResult:
```

The renderer resolves `layout_profile.design_path` against the repository root and renders using that design.

Fail-closed requirements:

- missing design file → `ValueError("RenderCV/Typst render failed")`;
- path escaping the repository root → fail;
- invalid profile → rejected before renderer invocation by model/loader;
- no fallback from a missing explicit profile to another profile inside the renderer.

The renderer must not inspect `CVStrategy` directly. Selection is upstream.

## Service integration

`CVPreparationService` gains injected layout-profile registry support:

```python
layout_profiles: Mapping[str, LayoutProfile] | None = None
```

Default registry loads from `config/layout_profiles.yaml`.

After strategy creation and before render, service resolves exactly one layout profile:

```text
strategy
  ↓
select_layout_profile(...)
  ↓
selected LayoutProfile
  ↓
renderer.render(..., layout_profile=selected_profile)
```

If layout selection fails, preparation returns a deterministic blocked result rather than silently falling back from an invalid explicit preference.

Recommended code/message:

- status: `BLOCKED_RENDER`
- issue code: `layout_profile_unavailable`
- message: `Selected CV layout profile is unavailable`

An unknown track without an explicit profile is not an error; it deterministically selects `compact_ats`.

## Reduction-loop behavior

The same selected layout profile must be used for every render attempt in one preparation run, including reduction retries.

A reduction may remove optional recruiter-document content according to existing policy, but it must not trigger a new layout selection. This prevents physical overflow from silently changing the visual identity of the CV.

## Existing QA compatibility

PR #47 must preserve all existing gates:

- semantic validation;
- recruiter-document validation;
- Narrative QA;
- ten-second scan;
- RenderPolicy constraints;
- recruiter PDF QA;
- reduction-loop narrative revalidation;
- offline runtime checks.

No gate may be weakened to make a layout profile pass.

## RenderCV design constraints

All three V1 design files must remain:

- single-column;
- text-first;
- ATS-safe;
- no rasterized text;
- no semantic information conveyed only by color/iconography;
- no rating bars or visual skill meters;
- no charts;
- no decorative sidebars;
- no absolute-positioned content that changes reading order;
- compatible with the current offline RenderCV/Typst runtime.

Differences between profiles should be restrained to typography, spacing, section separators, heading emphasis, and density. PR #47 is not a redesign contest; Visual QA in the next PR will measure whether these differences actually improve the output.

## Determinism requirements

For the same:

- `CVStrategy`;
- layout profile registry;
- `RecruiterDocumentModel`;
- source document;
- policies;

layout selection and renderer design choice must be identical regardless of input mapping insertion order.

No current date, randomness, LLM call, environment-specific preference, or job-title keyword inference may influence profile selection.

## Test strategy

### Model/registry tests

Prove:

- all 3 profiles load;
- unknown fields fail;
- wrong version fails;
- key/id mismatch fails;
- missing required V1 profile fails;
- no profile can contain narrative/physical-policy fields such as `section_order`, `max_pages`, `min_body_font_pt`, or claim IDs.

### Selector tests

Prove:

- explicit valid preference wins;
- explicit invalid preference fails closed;
- `software-data-decision` selects `technical_clean`;
- `geospatial-mining-tech` selects `technical_clean`;
- `operations-support` selects `operations_clean`;
- unknown track selects `compact_ats`;
- selection is deterministic under registry input-order reversal.

### Renderer tests

Prove:

- selected design path is actually used;
- missing design fails;
- repository path escape fails;
- payload claim IDs/text are unchanged across profiles;
- current ATS-safe metrics continue to be produced.

### Service tests

Prove:

- service passes one selected profile to the renderer;
- the same profile is reused after a reduction retry;
- invalid explicit profile blocks before PDF creation;
- renderer is not called when profile selection blocks;
- existing preparation behavior remains unchanged when no explicit profile exists.

### CI previews

The preview script renders at least one fictional CV with each V1 profile and still passes RecruiterQualityQA. Human preview artifacts remain supplemental; CI correctness does not depend on subjective visual approval in PR #47.

## Non-goals

PR #47 explicitly does not:

- decide whether a layout is visually beautiful;
- calculate whitespace/density quality metrics;
- introduce Visual QA issue codes;
- change claim composition or section-order logic;
- export JSON Resume;
- add React-PDF or another renderer;
- emulate a commercial ATS;
- change Gmail/outreach/application-send behavior;
- alter `ApplicationPacket` schema.

Those belong to later roadmap items.

## Success criteria

PR #47 is complete when:

1. all three V1 layout profiles exist and validate;
2. selection is deterministic and fail-closed for invalid explicit preferences;
3. `CVPreparationService` resolves exactly one profile per preparation run;
4. the renderer consumes that profile without owning selection logic;
5. the same recruiter content renders through all profiles without claim mutation;
6. existing semantic, narrative, render, privacy, preview, and offline-runtime test suites remain green;
7. no Gmail, outreach, ApplicationPacket, Visual QA, JSON Resume, or second-renderer behavior changes.
