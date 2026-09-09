# CV Layout Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic ATS-safe CV layout profiles selected from `CVStrategy` and consumed by the existing RenderCV/Typst renderer without changing recruiter-facing content.

**Architecture:** Introduce `app.cv.layout` as a presentation-only layer. A strict registry loader provides three versioned `LayoutProfile` values; `select_layout_profile()` resolves one profile from explicit strategy preference or stable application-track mapping; `CVPreparationService` selects exactly once and passes that profile to every render attempt; `RenderCVTypstRenderer` uses only the profile's repository-relative design file and never inspects strategy.

**Tech Stack:** Python 3.12+, Pydantic v2, PyYAML, RenderCV 2.8.x, Typst, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-09-cv-layout-profiles-design.md`

## Global Constraints

- `LAYOUT_PROFILE_VERSION` is exactly `layout-profile-v1`.
- V1 profile IDs are exactly `technical_clean`, `operations_clean`, and `compact_ats`.
- All V1 layouts remain single-column, text-first, and ATS-safe.
- Layout code must not add, remove, rewrite, or reorder recruiter-facing claim IDs.
- Layout code must not change provenance, `CVStrategy`, `RecruiterDocumentModel`, or narrative policy.
- `RenderPolicy` remains the only authority for page size, preferred/max page count, and body-font constraints.
- Explicit unknown `preferred_layout_profile_id` fails closed with `ValueError("layout_profile_unavailable")`; unknown track without explicit preference falls back to `compact_ats`.
- The same selected profile is reused across every reduction-loop render attempt.
- No ApplicationPacket schema, Gmail, outreach, send behavior, Visual QA, JSON Resume, or second-renderer changes belong in this plan.

---

### Task 1: Layout profile contract and public registry

**Files:**
- Create: `app/cv/layout/__init__.py`
- Create: `app/cv/layout/models.py`
- Create: `app/cv/layout/registry.py`
- Create: `config/layout_profiles.yaml`
- Create: `tests/test_cv_layout_profiles.py`

**Interfaces:**
- Produces: `LAYOUT_PROFILE_VERSION: str`
- Produces: `LayoutProfile`
- Produces: `load_layout_profiles(path: str | Path) -> dict[str, LayoutProfile]`
- Later tasks consume the returned mapping by profile ID.

- [ ] **Step 1: Write the failing model/registry tests**

Create `tests/test_cv_layout_profiles.py` with tests covering the exact V1 contract:

```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.cv.layout import LayoutProfile, load_layout_profiles


def test_public_layout_registry_loads_all_v1_profiles() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    assert list(profiles) == ["compact_ats", "operations_clean", "technical_clean"]
    assert profiles["technical_clean"].density == "comfortable"
    assert profiles["operations_clean"].emphasis == "experience"
    assert profiles["compact_ats"].ats_mode == "strict"


def test_layout_profile_rejects_narrative_and_render_policy_fields() -> None:
    with pytest.raises(ValidationError):
        LayoutProfile.model_validate({
            "version": "layout-profile-v1",
            "id": "technical_clean",
            "design_path": "config/layouts/technical_clean.yaml",
            "density": "comfortable",
            "emphasis": "technical",
            "ats_mode": "strict",
            "section_order": ["skills", "experience"],
            "max_pages": 2,
        })


def test_layout_profile_rejects_wrong_version() -> None:
    with pytest.raises(ValidationError):
        LayoutProfile(
            version="layout-profile-v2",
            id="technical_clean",
            design_path="config/layouts/technical_clean.yaml",
            density="comfortable",
            emphasis="technical",
            ats_mode="strict",
        )


def test_layout_registry_rejects_key_id_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "profiles.yaml"
    path.write_text(
        "technical_clean:\n"
        "  version: layout-profile-v1\n"
        "  id: compact_ats\n"
        "  design_path: config/layouts/compact_ats.yaml\n"
        "  density: compact\n"
        "  emphasis: neutral\n"
        "  ats_mode: strict\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="layout profile registry key/id mismatch"):
        load_layout_profiles(path)


def test_layout_registry_requires_all_v1_profiles(tmp_path: Path) -> None:
    path = tmp_path / "profiles.yaml"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="layout profile registry incomplete"):
        load_layout_profiles(path)
```

- [ ] **Step 2: Run the new test file and verify RED**

Run:

```bash
pytest tests/test_cv_layout_profiles.py -q
```

Expected: collection/import failure because `app.cv.layout` does not exist.

- [ ] **Step 3: Implement the strict model and loader**

Create `app/cv/layout/models.py`:

```python
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, model_validator

from app.cv.models import StrictCVModel

LAYOUT_PROFILE_VERSION = "layout-profile-v1"
LayoutProfileId = Literal["technical_clean", "operations_clean", "compact_ats"]


class LayoutProfile(StrictCVModel):
    version: str = Field(min_length=1)
    id: LayoutProfileId
    design_path: str = Field(min_length=1)
    density: Literal["comfortable", "balanced", "compact"]
    emphasis: Literal["technical", "experience", "neutral"]
    ats_mode: Literal["strict"] = "strict"

    @model_validator(mode="after")
    def validate_contract(self) -> "LayoutProfile":
        if self.version != LAYOUT_PROFILE_VERSION:
            raise ValueError(f"unsupported layout profile version: {self.version}")
        path = PurePosixPath(self.design_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("layout profile design path must be repository-relative")
        return self
```

Create `app/cv/layout/registry.py`:

```python
from __future__ import annotations

from pathlib import Path

import yaml

from app.cv.layout.models import LayoutProfile

_REQUIRED_PROFILE_IDS = {"technical_clean", "operations_clean", "compact_ats"}


def load_layout_profiles(path: str | Path) -> dict[str, LayoutProfile]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("layout profile registry root must be a mapping")

    profiles: dict[str, LayoutProfile] = {}
    for key, value in payload.items():
        profile = LayoutProfile.model_validate(value)
        if key != profile.id:
            raise ValueError("layout profile registry key/id mismatch")
        profiles[profile.id] = profile

    if set(profiles) != _REQUIRED_PROFILE_IDS:
        raise ValueError("layout profile registry incomplete")
    return dict(sorted(profiles.items()))
```

Export these names from `app/cv/layout/__init__.py`.

Create `config/layout_profiles.yaml`:

```yaml
technical_clean:
  version: layout-profile-v1
  id: technical_clean
  design_path: config/layouts/technical_clean.yaml
  density: comfortable
  emphasis: technical
  ats_mode: strict

operations_clean:
  version: layout-profile-v1
  id: operations_clean
  design_path: config/layouts/operations_clean.yaml
  density: balanced
  emphasis: experience
  ats_mode: strict

compact_ats:
  version: layout-profile-v1
  id: compact_ats
  design_path: config/layouts/compact_ats.yaml
  density: compact
  emphasis: neutral
  ats_mode: strict
```

- [ ] **Step 4: Run focused + full tests**

Run:

```bash
pytest tests/test_cv_layout_profiles.py -q
pytest -q
python -m compileall app
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/cv/layout config/layout_profiles.yaml tests/test_cv_layout_profiles.py
git commit -m "feat: add CV layout profile registry"
```

---

### Task 2: Deterministic layout selector

**Files:**
- Create: `app/cv/layout/selector.py`
- Modify: `app/cv/layout/__init__.py`
- Create: `tests/test_cv_layout_selector.py`

**Interfaces:**
- Consumes: `CVStrategy`, `Mapping[str, LayoutProfile]`
- Produces: `select_layout_profile(*, strategy: CVStrategy, profiles: Mapping[str, LayoutProfile]) -> LayoutProfile`

- [ ] **Step 1: Write selector tests before production code**

Create `tests/test_cv_layout_selector.py` with a helper strategy and these assertions:

```python
from app.cv.layout import load_layout_profiles, select_layout_profile
from app.cv.strategy.models import CVStrategy, CoreMessage


def _strategy(track: str, preferred: str | None = None) -> CVStrategy:
    return CVStrategy(
        strategy_version="cv-strategy-v1",
        application_track_id=track,
        target_role="Example Role",
        target_company="Example Co",
        positioning="Verified Developer",
        recruiter_question="Can this candidate do the work?",
        core_messages=[
            CoreMessage(
                id="positioning",
                message="Verified Developer",
                fact_ids=["fact:role"],
                evidence_ids=[],
                importance=10.0,
                reason="validated positioning",
            )
        ],
        must_show_fact_ids=["fact:role"],
        supporting_fact_ids=[],
        optional_fact_ids=[],
        explicit_gaps=[],
        preferred_section_order=["summary", "skills", "experience"],
        preferred_layout_profile_id=preferred,
    )


def test_explicit_valid_layout_preference_wins() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    result = select_layout_profile(
        strategy=_strategy("operations-support", "technical_clean"),
        profiles=profiles,
    )
    assert result.id == "technical_clean"


def test_explicit_unknown_layout_preference_fails_closed() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    strategy = _strategy("operations-support").model_copy(
        update={"preferred_layout_profile_id": "missing_profile"}
    )
    try:
        select_layout_profile(strategy=strategy, profiles=profiles)
    except ValueError as exc:
        assert str(exc) == "layout_profile_unavailable"
    else:
        raise AssertionError("explicit unknown layout must fail closed")


def test_public_track_mapping_is_deterministic() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    assert select_layout_profile(strategy=_strategy("software-data-decision"), profiles=profiles).id == "technical_clean"
    assert select_layout_profile(strategy=_strategy("geospatial-mining-tech"), profiles=profiles).id == "technical_clean"
    assert select_layout_profile(strategy=_strategy("operations-support"), profiles=profiles).id == "operations_clean"
    assert select_layout_profile(strategy=_strategy("unknown-track"), profiles=profiles).id == "compact_ats"


def test_registry_insertion_order_does_not_change_selection() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    reversed_profiles = dict(reversed(list(profiles.items())))
    strategy = _strategy("software-data-decision")
    assert select_layout_profile(strategy=strategy, profiles=profiles) == select_layout_profile(
        strategy=strategy,
        profiles=reversed_profiles,
    )
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
pytest tests/test_cv_layout_selector.py -q
```

Expected: import failure because `select_layout_profile` is not implemented/exported.

- [ ] **Step 3: Implement deterministic selection**

Create `app/cv/layout/selector.py`:

```python
from __future__ import annotations

from collections.abc import Mapping

from app.cv.layout.models import LayoutProfile
from app.cv.strategy.models import CVStrategy

_TRACK_PROFILE_MAP = {
    "software-data-decision": "technical_clean",
    "geospatial-mining-tech": "technical_clean",
    "operations-support": "operations_clean",
}


def select_layout_profile(
    *,
    strategy: CVStrategy,
    profiles: Mapping[str, LayoutProfile],
) -> LayoutProfile:
    if strategy.preferred_layout_profile_id is not None:
        try:
            return profiles[strategy.preferred_layout_profile_id]
        except KeyError as exc:
            raise ValueError("layout_profile_unavailable") from exc

    profile_id = _TRACK_PROFILE_MAP.get(
        strategy.application_track_id,
        "compact_ats",
    )
    try:
        return profiles[profile_id]
    except KeyError as exc:
        raise ValueError("layout_profile_unavailable") from exc
```

Export from `app/cv/layout/__init__.py`.

- [ ] **Step 4: Run focused + full tests and compile**

```bash
pytest tests/test_cv_layout_selector.py -q
pytest -q
python -m compileall app
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/cv/layout tests/test_cv_layout_selector.py
git commit -m "feat: select CV layout from strategy"
```

---

### Task 3: Profile-specific RenderCV designs and renderer contract

**Files:**
- Create: `config/layouts/technical_clean.yaml`
- Create: `config/layouts/operations_clean.yaml`
- Create: `config/layouts/compact_ats.yaml`
- Modify: `app/cv/renderers/rendercv_typst.py`
- Modify: `tests/test_recruiter_renderer.py`
- Create: `tests/test_cv_layout_renderer_contract.py`

**Interfaces:**
- Consumes: `LayoutProfile`
- Changes renderer signature to:

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

- [ ] **Step 1: Add RED tests for explicit profile use and path safety**

Create `tests/test_cv_layout_renderer_contract.py` by importing `_source_document` and `_recruiter_document` from `test_recruiter_renderer`, then assert:

```python
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.cv.layout import LayoutProfile, load_layout_profiles
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.renderers.rendercv_typst import RenderCVTypstRenderer
from test_recruiter_renderer import _recruiter_document, _source_document


def test_renderer_requires_and_uses_selected_layout_profile(tmp_path: Path) -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    result = RenderCVTypstRenderer().render(
        recruiter_document=_recruiter_document(),
        source_document=_source_document(),
        output_path=tmp_path / "technical.pdf",
        policy=load_recruiter_policy("config/recruiter_policy.yaml"),
        layout_profile=profiles["technical_clean"],
    )
    assert Path(result.artifact.path).is_file()
    assert "Alex Example" in (PdfReader(result.artifact.path).pages[0].extract_text() or "")


def test_renderer_rejects_missing_layout_design(tmp_path: Path) -> None:
    profile = LayoutProfile(
        version="layout-profile-v1",
        id="technical_clean",
        design_path="config/layouts/missing.yaml",
        density="comfortable",
        emphasis="technical",
        ats_mode="strict",
    )
    with pytest.raises(ValueError, match="RenderCV/Typst render failed"):
        RenderCVTypstRenderer().render(
            recruiter_document=_recruiter_document(),
            source_document=_source_document(),
            output_path=tmp_path / "missing.pdf",
            policy=load_recruiter_policy("config/recruiter_policy.yaml"),
            layout_profile=profile,
        )


def test_same_recruiter_content_is_extractable_across_all_profiles(tmp_path: Path) -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    renderer = RenderCVTypstRenderer()
    policy = load_recruiter_policy("config/recruiter_policy.yaml")
    expected = {"Alex Example", "Software & Operations Developer", "Python", "SQL"}
    for profile in profiles.values():
        result = renderer.render(
            recruiter_document=_recruiter_document(),
            source_document=_source_document(),
            output_path=tmp_path / f"{profile.id}.pdf",
            policy=policy,
            layout_profile=profile,
        )
        text = "\n".join(page.extract_text() or "" for page in PdfReader(result.artifact.path).pages)
        assert expected.issubset(text)
```

The path-escape case remains covered at model validation level from Task 1.

- [ ] **Step 2: Run and verify RED**

```bash
pytest tests/test_cv_layout_renderer_contract.py -q
```

Expected: `TypeError` because current renderer does not accept `layout_profile`.

- [ ] **Step 3: Create restrained ATS-safe design files**

Start from `config/rendercv_one_page.yaml` and create three valid RenderCV design YAML files under `config/layouts/`.

Use these exact physical differences while preserving one-column reading order:

```yaml
# technical_clean.yaml key differences
page:
  top_margin: 0.48in
  bottom_margin: 0.48in
  left_margin: 0.55in
  right_margin: 0.55in
typography:
  line_spacing: 0.64em
  font_size:
    body: 10pt
    name: 22pt
    headline: 11pt
    connections: 9.6pt
    section_titles: 1.18em
section_titles:
  type: with_full_line
  line_thickness: 0.5pt
  space_above: 0.34cm
  space_below: 0.18cm
sections:
  space_between_regular_entries: 0.48em
  space_between_text_based_entries: 0.26em
```

```yaml
# operations_clean.yaml key differences
page:
  top_margin: 0.52in
  bottom_margin: 0.52in
  left_margin: 0.58in
  right_margin: 0.58in
typography:
  line_spacing: 0.62em
  font_size:
    body: 10pt
    name: 21pt
    headline: 10.6pt
    connections: 9.5pt
    section_titles: 1.12em
section_titles:
  type: with_full_line
  line_thickness: 0.4pt
  space_above: 0.30cm
  space_below: 0.16cm
sections:
  space_between_regular_entries: 0.52em
  space_between_text_based_entries: 0.25em
```

```yaml
# compact_ats.yaml key differences
page:
  top_margin: 0.45in
  bottom_margin: 0.45in
  left_margin: 0.50in
  right_margin: 0.50in
typography:
  line_spacing: 0.56em
  font_size:
    body: 9.6pt
    name: 20pt
    headline: 10.4pt
    connections: 9.3pt
    section_titles: 1.10em
section_titles:
  type: with_full_line
  line_thickness: 0.35pt
  space_above: 0.25cm
  space_below: 0.13cm
sections:
  space_between_regular_entries: 0.38em
  space_between_text_based_entries: 0.20em
```

Every design must also preserve `show_footer: false`, `show_top_note: false`, `show_icons: false`, `show_external_link_icon: false`, left alignment, Source Sans 3, no external-link icons, and the same RenderCV theme/runtime compatibility as the current design.

- [ ] **Step 4: Change renderer to resolve design from the profile**

In `RenderCVTypstRenderer.render`, replace the constructor-selected default design path with a per-call profile argument. Resolve safely:

```python
def _resolve_layout_design(profile: LayoutProfile) -> Path:
    repository_root = _PROJECT_ROOT.resolve()
    candidate = (repository_root / profile.design_path).resolve()
    try:
        candidate.relative_to(repository_root)
    except ValueError as exc:
        raise ValueError("RenderCV/Typst render failed") from exc
    if not candidate.is_file():
        raise ValueError("RenderCV/Typst render failed")
    return candidate
```

Use this path for `_configured_body_font_size()` and `_render_pdf_in_process()`.

Remove `_DEFAULT_DESIGN_PATH` and the renderer constructor's design selection; renderer must not own layout selection.

- [ ] **Step 5: Migrate existing renderer tests to pass `compact_ats`**

In `tests/test_recruiter_renderer.py`, create a helper:

```python
def _layout_profile():
    return load_layout_profiles("config/layout_profiles.yaml")["compact_ats"]
```

and pass `layout_profile=_layout_profile()` to every `RenderCVTypstRenderer().render(...)` invocation.

Update the current theme-contract test to inspect all three `config/layouts/*.yaml` files instead of only `config/rendercv_one_page.yaml`.

- [ ] **Step 6: Run renderer-focused and full gates**

```bash
pytest tests/test_cv_layout_renderer_contract.py tests/test_recruiter_renderer.py tests/test_recruiter_theme_contract.py -q
pytest -q
python -m compileall app
```

Expected: all PASS, with PDF text extractable for all profiles.

- [ ] **Step 7: Commit**

```bash
git add config/layouts app/cv/renderers/rendercv_typst.py tests/test_cv_layout_renderer_contract.py tests/test_recruiter_renderer.py tests/test_recruiter_theme_contract.py
git commit -m "feat: render recruiter CVs with layout profiles"
```

---

### Task 4: Service wiring, reduction-loop stability, and CI previews

**Files:**
- Modify: `app/cv/service.py`
- Modify: `scripts/render_recruiter_previews.py`
- Modify: `tests/test_cv_service.py`
- Create: `tests/test_cv_service_layout_profile.py`
- Modify: any renderer test double in `tests/` whose `render()` signature must accept `layout_profile`

**Interfaces:**
- `CVPreparationService.__init__` gains `layout_profiles: Mapping[str, LayoutProfile] | None = None`
- Default registry loads from `config/layout_profiles.yaml`
- The service calls `select_layout_profile(strategy=strategy, profiles=self.layout_profiles)` exactly once per preparation run.
- The selected profile is passed unchanged to every renderer call, including reduction retries.

- [ ] **Step 1: Write RED service tests with a capturing renderer**

Create `tests/test_cv_service_layout_profile.py` using existing helpers from `test_cv_service`:

```python
from pathlib import Path

from app.cv.layout import load_layout_profiles
from app.cv.recruiter_models import RecruiterQAResult
from app.cv.service import CVPreparationService
from test_cv_service import LANGUAGE_DECISION, NOW, _assessment, _inputs, _resolver


class CapturingRenderer:
    renderer_version = "capturing-layout-v1"

    def __init__(self) -> None:
        self.profiles = []

    def render(self, recruiter_document, source_document, output_path, policy, layout_profile):
        self.profiles.append(layout_profile)
        from app.cv.renderers.rendercv_typst import RenderCVTypstRenderer
        return RenderCVTypstRenderer().render(
            recruiter_document,
            source_document,
            output_path,
            policy,
            layout_profile,
        )


def test_service_selects_track_layout_and_passes_it_to_renderer(tmp_path: Path) -> None:
    master, catalog, policy = _inputs()
    renderer = CapturingRenderer()
    result = CVPreparationService(
        taxonomy_resolver=_resolver(),
        id_factory=lambda: "app-layout",
        recruiter_renderer=renderer,
        layout_profiles=load_layout_profiles("config/layout_profiles.yaml"),
    ).prepare(
        assessment=_assessment(),
        master_facts=master,
        evidence_catalog=catalog,
        policy=policy,
        output_root=tmp_path,
        now=NOW,
        language_decision=LANGUAGE_DECISION,
    )
    assert result.status == "PREPARED"
    assert len(renderer.profiles) >= 1
    assert len({profile.id for profile in renderer.profiles}) == 1
```

Add a fail-closed test by injecting a strategy preference through the existing assessment/track-config seam used in strategy tests; if the current service has no public track-config injection seam, use `monkeypatch` on `app.cv.service.build_cv_strategy` to return a copy with `preferred_layout_profile_id="missing_profile"`. Assert:

```python
assert result.status == "BLOCKED_RENDER"
assert result.errors[0].code == "layout_profile_unavailable"
assert not list(tmp_path.rglob("*.pdf"))
assert renderer.profiles == []
```

Add/reuse an overflow/reduction test double from `tests/test_cv_service.py` to force two render attempts and assert both received the same profile object or the same profile ID.

- [ ] **Step 2: Run and verify RED**

```bash
pytest tests/test_cv_service_layout_profile.py -q
```

Expected: constructor/signature failures because service does not yet accept or pass `layout_profiles`/`layout_profile`.

- [ ] **Step 3: Wire service selection before first render**

In `app/cv/service.py`:

```python
from collections.abc import Mapping
from app.cv.layout import LayoutProfile, load_layout_profiles, select_layout_profile

_DEFAULT_LAYOUT_PROFILES_PATH = _PROJECT_ROOT / "config" / "layout_profiles.yaml"
```

Add constructor argument:

```python
layout_profiles: Mapping[str, LayoutProfile] | None = None,
```

and initialize:

```python
self.layout_profiles = dict(layout_profiles) if layout_profiles is not None else load_layout_profiles(
    _DEFAULT_LAYOUT_PROFILES_PATH
)
```

After strategy creation/composition and before any renderer call, resolve once:

```python
try:
    selected_layout_profile = select_layout_profile(
        strategy=strategy,
        profiles=self.layout_profiles,
    )
except ValueError as exc:
    if str(exc) != "layout_profile_unavailable":
        raise
    return _blocked(
        "BLOCKED_RENDER",
        code="layout_profile_unavailable",
        message="Selected CV layout profile is unavailable",
        warnings=[*validation.warnings],
    )
```

Then pass `selected_layout_profile` to every `self.recruiter_renderer.render(...)` call in the reduction loop. Do not re-select after reduction.

- [ ] **Step 4: Update test doubles and preview script**

Every custom recruiter renderer under `tests/` must accept the new trailing `layout_profile` parameter; behavior should otherwise remain unchanged.

Update `scripts/render_recruiter_previews.py` so it loads the public registry once and renders fictional preview coverage for all three profile IDs. Each produced PDF must still run through `RecruiterQualityQA` with `RenderPolicy`.

Use filenames that make profile identity explicit, e.g.:

```text
recruiter_software__technical_clean.pdf
recruiter_tech_operations__operations_clean.pdf
recruiter_software__compact_ats.pdf
```

At minimum, ensure every V1 profile is exercised once; duplicate fixture/profile combinations are unnecessary.

- [ ] **Step 5: Run focused service tests and entire CI-equivalent gate**

```bash
pytest tests/test_cv_service_layout_profile.py tests/test_cv_service.py tests/test_recruiter_renderer.py -q
pytest -q
python -m compileall app
git diff --check origin/main...HEAD
python scripts/render_recruiter_previews.py --output-dir artifacts/ci/recruiter-preview
```

Expected: all PASS; preview script generates at least three PDFs and no existing CV/outreach behavior regresses.

- [ ] **Step 6: Verify offline runtime and privacy gates through GitHub Actions**

Push the final commit and require the PR-head workflow to pass:

```text
pytest
compile application
feature diff whitespace
private files guard
recruiter visual previews
offline runtime build Python 3.12
offline runtime build Python 3.13
offline runtime verify Python 3.12
offline runtime verify Python 3.13
```

Do not mark the PR ready or merge while any job is pending or failed.

- [ ] **Step 7: Commit**

```bash
git add app/cv/service.py scripts/render_recruiter_previews.py tests
git commit -m "feat: wire CV layout profiles into preparation"
```

---

## Final Review Gate

Before marking PR #47 ready:

1. Compare changed files against the spec and confirm no Gmail/outreach/ApplicationPacket/Visual QA/JSON Resume code changed.
2. Verify `CVStrategy` and `RecruiterDocumentModel` are not mutated by layout selection.
3. Verify all three layouts are repository-relative, single-column RenderCV designs with no semantic iconography or multi-column reading order.
4. Verify `RenderPolicy` remains the source of page/font constraints and is still passed only to `RecruiterQualityQA`.
5. Verify explicit invalid layout preference blocks before renderer invocation.
6. Verify one profile is selected per preparation run and reused through reduction retries.
7. Require a fresh successful Actions run on the final PR head SHA before integration.
