# CV Layout Profiles Design

## Goal

Introduce a deterministic, ATS-safe presentation layer between `CVStrategy` and `RenderCVTypstRenderer` so Opportunity-OS can choose among a small set of visual layouts without changing claim selection, claim order, provenance, narrative strategy, or render safety.

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

## Scope

PR #47 introduces:

1. A versioned `LayoutProfile` contract.
2. Three public ATS-safe profiles:
   - `technical_clean`
   - `operations_clean`
   - `compact_ats`
3. A deterministic `LayoutSelector`.
4. A privacy-safe injectable `track_layout_map` seam.
5. Service wiring that resolves one profile per preparation run.
6. Renderer wiring that consumes the selected profile's RenderCV design file.
7. Tests proving layout selection cannot alter recruiter-facing claims or bypass semantic, narrative, render, or privacy gates.

PR #47 does **not** introduce Visual QA, JSON Resume, a second renderer, ATS round-trip QA, `ApplicationPacket` schema changes, Gmail/outreach behavior, or private candidate configuration.

## Ownership boundaries

### Narrative owns content

`CVStrategy`, the narrative composer, and Narrative QA remain authoritative for:

- selected facts and visible claims;
- recruiter-facing claim and section order;
- positioning and core-message coverage;
- must-show/supporting/optional evidence;
- explicit gaps.

### Layout owns presentation

`LayoutProfile` may control only presentation parameters such as:

- RenderCV design file;
- spacing/density intent;
- heading emphasis;
- typography intent;
- conservative ATS presentation mode.

A layout profile must not:

- add, remove, rewrite, or reorder claim IDs;
- change `RecruiterDocumentModel`;
- change provenance or `CVStrategy`;
- override `RenderPolicy`;
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

Create `app/cv/layout/models.py`:

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

- `version == "layout-profile-v1"`;
- `design_path` is non-empty and repository-relative;
- absolute paths and `..` path traversal fail validation;
- `ats_mode` remains `strict` in V1;
- unknown fields fail;
- profile IDs are closed to the three V1 values.

The model intentionally contains no section order, claim IDs, narrative weights, page count, or font constraints.

## Public profile registry

Create `config/layout_profiles.yaml` as the public V1 registry. It must contain exactly the three V1 profile IDs and point to separate design files under `config/layouts/`.

### `technical_clean`

For technical/software/data/geospatial contexts when selected by an authorized runtime mapping or explicit strategy preference.

Visual intent:

- clear hierarchy;
- comfortable but efficient spacing;
- stronger heading emphasis;
- single-column, text-first, ATS-safe structure.

### `operations_clean`

For operations/support/process contexts when selected by an authorized runtime mapping or explicit strategy preference.

Visual intent:

- traditional, conservative hierarchy;
- balanced spacing;
- experience-friendly visual rhythm;
- single-column, text-first, ATS-safe structure.

### `compact_ats`

Universal public fallback.

Visual intent:

- compact density;
- neutral emphasis;
- maximum simplicity;
- single-column, text-first, ATS-safe structure.

## Privacy-safe layout selection contract

Private candidate track IDs must **not** be committed to the public repository. The public core therefore does not contain a hardcoded mapping from Juan-specific/private track names to layouts.

Create:

```python
def select_layout_profile(
    *,
    strategy: CVStrategy,
    profiles: Mapping[str, LayoutProfile],
    track_layout_map: Mapping[str, str] | None = None,
) -> LayoutProfile:
```

Selection order is deterministic:

1. If `strategy.preferred_layout_profile_id` is present:
   - it must exist in `profiles`;
   - return it;
   - otherwise raise `ValueError("layout_profile_unavailable")`.
2. Otherwise, if `track_layout_map` contains `strategy.application_track_id`:
   - resolve the mapped profile ID;
   - if that profile ID is unavailable, raise `ValueError("layout_profile_unavailable")`.
3. Otherwise return `compact_ats`.

The selector must never infer layout from job-title keywords, free-form text, candidate identity, environment variables, or hidden global state.

The public default `track_layout_map` is empty. A private runtime may inject mappings outside the public repository, for example from a gitignored/private configuration layer. Tests use fictional public fixture IDs such as `tech` and `ops`; they do not commit private candidate track names.

## Loader contract

Create:

```python
def load_layout_profiles(path: str | Path) -> dict[str, LayoutProfile]:
```

Requirements:

- YAML root is a mapping;
- every key equals contained profile `id`;
- all and only the three V1 profile IDs are present;
- unexpected IDs fail through model validation;
- return mapping sorted by profile ID for deterministic iteration.

## Renderer integration

Change the renderer contract so layout is explicit per render:

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

The renderer resolves `layout_profile.design_path` against repository root.

Fail-closed requirements:

- missing design file → `ValueError("RenderCV/Typst render failed")`;
- path escaping repository root → fail;
- no renderer-level fallback from an explicit profile to another profile;
- renderer never inspects `CVStrategy`.

The rendered payload must be identical across profiles for the same `RecruiterDocumentModel` and source document; only the design file differs.

## Service integration

`CVPreparationService` gains:

```python
layout_profiles: Mapping[str, LayoutProfile] | None = None
track_layout_map: Mapping[str, str] | None = None
```

Defaults:

- `layout_profiles` loads `config/layout_profiles.yaml`;
- `track_layout_map` defaults to `{}`.

After strategy creation and Narrative QA, but before first render, the service resolves exactly one layout profile and stores it in a local variable for the entire preparation run.

If selection raises `layout_profile_unavailable`, preparation returns:

- status: `BLOCKED_RENDER`
- issue code: `layout_profile_unavailable`
- message: `Selected CV layout profile is unavailable`

The renderer must not be called and no PDF may remain.

## Reduction-loop behavior

The same selected `LayoutProfile` is reused for every render attempt, including reduction retries. A reduction may change optional recruiter content according to existing policy, but may not trigger layout re-selection.

## RenderCV design constraints

All V1 design files remain:

- single-column;
- text-first;
- no rasterized text;
- no semantic information conveyed only by color or iconography;
- no skill meters, charts, sidebars, or multi-column reading order;
- compatible with the current offline RenderCV/Typst runtime;
- `Source Sans 3`;
- no connection icons or external-link icons.

Differences are restrained to margins, spacing, heading emphasis, and typography scale. Visual quality scoring belongs to PR #48.

## Determinism requirements

For the same strategy, profile registry, track-layout mapping, recruiter document, source document, and policies, profile selection and design choice are identical regardless of mapping insertion order.

No current date, randomness, LLM call, job-title keyword inference, or private hardcoded track name may influence public-core selection.

## Test strategy

### Model/registry

Prove:

- all three profiles load;
- wrong version and unknown fields fail;
- key/id mismatch fails;
- incomplete registry fails;
- narrative and RenderPolicy fields are rejected;
- path traversal/absolute paths fail.

### Selector

Prove:

- explicit valid preference wins;
- explicit invalid preference fails closed;
- injected fictional `tech -> technical_clean` and `ops -> operations_clean` mappings work;
- absent mapping falls back to `compact_ats`;
- injected mapping to missing profile fails closed;
- registry and mapping insertion order do not change result;
- no private track IDs exist in public source/config/tests.

### Renderer

Prove:

- selected design is used;
- missing design fails;
- repository path escape is rejected by model/renderer boundary;
- identity/headline/skills remain extractable across all profiles;
- ATS-safe render metrics remain available.

### Service

Prove:

- service passes selected profile to renderer;
- private-style mapping can be injected without being committed as data;
- same profile is reused after a reduction retry;
- invalid explicit or mapped profile blocks before PDF creation;
- with no mapping/preference, current public fixture track falls back to `compact_ats`.

### CI previews

Render at least one fictional PDF per V1 profile and pass `RecruiterQualityQA` with existing `RenderPolicy`. Human preview artifacts are supplemental; PR #47 has no subjective Visual QA gate.

## Non-goals

PR #47 does not:

- decide visual beauty;
- calculate whitespace/density quality;
- modify narrative ordering;
- export JSON Resume;
- add another renderer;
- emulate commercial ATS software;
- change Gmail/outreach/send behavior;
- alter `ApplicationPacket` schema;
- commit Juan-specific/private track configuration.

## Success criteria

PR #47 is complete when:

1. all three V1 profiles exist and validate;
2. selection is deterministic and privacy-safe;
3. invalid explicit or injected mappings fail closed;
4. the public core contains no Juan-specific/private track IDs;
5. `CVPreparationService` resolves exactly one profile per preparation run;
6. the same profile survives reduction retries;
7. renderer consumes the profile without owning selection logic;
8. recruiter content is unchanged across profiles;
9. all semantic, narrative, render, privacy, preview, and offline-runtime CI gates remain green;
10. no Gmail, outreach, ApplicationPacket, Visual QA, JSON Resume, or second-renderer behavior changes.
