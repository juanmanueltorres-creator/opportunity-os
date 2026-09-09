# CV Layout Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic ATS-safe CV layout profiles selected from `CVStrategy` and consumed by the existing RenderCV/Typst renderer without changing recruiter-facing content or committing private candidate track configuration.

**Architecture:** Introduce `app.cv.layout` as a presentation-only layer. A strict public registry provides three versioned profiles; `select_layout_profile()` resolves an explicit strategy preference first, then an injected privacy-safe `track_layout_map`, otherwise `compact_ats`. `CVPreparationService` selects exactly once per preparation run and passes the same profile to every render attempt. `RenderCVTypstRenderer` uses only the selected profile's repository-relative design file and never inspects strategy.

**Tech Stack:** Python 3.12+, Pydantic v2, PyYAML, RenderCV 2.8.x, Typst, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-09-cv-layout-profiles-design.md`

## Global Constraints

- `LAYOUT_PROFILE_VERSION` is exactly `layout-profile-v1`.
- V1 profile IDs are exactly `technical_clean`, `operations_clean`, `compact_ats`.
- All V1 designs remain one-column, text-first, ATS-safe, Source Sans 3.
- Layout must not add/remove/rewrite/reorder recruiter-facing claim IDs.
- Layout must not change provenance, `CVStrategy`, `RecruiterDocumentModel`, or narrative policy.
- `RenderPolicy` remains sole authority for page size, preferred/max pages, and body-font limits.
- Explicit unavailable profile and injected mapping to unavailable profile fail closed with `ValueError("layout_profile_unavailable")`.
- No explicit preference and no track mapping falls back to `compact_ats`.
- Public code/config/tests must not contain Juan-specific/private track IDs.
- The same profile is reused through reduction retries.
- No Visual QA, JSON Resume, second renderer, ApplicationPacket, Gmail, outreach, or send changes belong in PR #47.

---

### Task 1: Layout profile model and registry

**Files:**
- Create: `app/cv/layout/__init__.py`
- Create: `app/cv/layout/models.py`
- Create: `app/cv/layout/registry.py`
- Create: `config/layout_profiles.yaml`
- Create: `tests/test_cv_layout_profiles.py`

**Interfaces:**
- Produces `LAYOUT_PROFILE_VERSION`
- Produces `LayoutProfile`
- Produces `load_layout_profiles(path: str | Path) -> dict[str, LayoutProfile]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cv_layout_profiles.py`:

```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.cv.layout import LayoutProfile, load_layout_profiles


def test_public_registry_loads_exact_v1_profiles() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    assert list(profiles) == ["compact_ats", "operations_clean", "technical_clean"]
    assert profiles["technical_clean"].density == "comfortable"
    assert profiles["operations_clean"].emphasis == "experience"
    assert profiles["compact_ats"].ats_mode == "strict"


def test_profile_rejects_narrative_and_render_fields() -> None:
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


def test_profile_rejects_wrong_version_and_path_escape() -> None:
    with pytest.raises(ValidationError):
        LayoutProfile(
            version="layout-profile-v2",
            id="technical_clean",
            design_path="config/layouts/technical_clean.yaml",
            density="comfortable",
            emphasis="technical",
        )
    with pytest.raises(ValidationError):
        LayoutProfile(
            version="layout-profile-v1",
            id="technical_clean",
            design_path="../private.yaml",
            density="comfortable",
            emphasis="technical",
        )


def test_registry_rejects_key_id_mismatch(tmp_path: Path) -> None:
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


def test_registry_requires_all_v1_profiles(tmp_path: Path) -> None:
    path = tmp_path / "profiles.yaml"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="layout profile registry incomplete"):
        load_layout_profiles(path)
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_cv_layout_profiles.py -q
```

Expected: import/collection failure because `app.cv.layout` does not exist.

- [ ] **Step 3: Implement the minimal model and loader**

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

Export model/loader from `app/cv/layout/__init__.py`.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/test_cv_layout_profiles.py -q
pytest -q
python -m compileall app
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/cv/layout config/layout_profiles.yaml tests/test_cv_layout_profiles.py
git commit -m "feat: add CV layout profile registry"
```

---

### Task 2: Privacy-safe deterministic selector

**Files:**
- Create: `app/cv/layout/selector.py`
- Modify: `app/cv/layout/__init__.py`
- Create: `tests/test_cv_layout_selector.py`

**Interfaces:**

```python
def select_layout_profile(
    *,
    strategy: CVStrategy,
    profiles: Mapping[str, LayoutProfile],
    track_layout_map: Mapping[str, str] | None = None,
) -> LayoutProfile:
```

- [ ] **Step 1: Write failing selector tests with fictional public track IDs**

Create `tests/test_cv_layout_selector.py`:

```python
import pytest

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
        core_messages=[CoreMessage(
            id="positioning",
            message="Verified Developer",
            fact_ids=["fact:role"],
            evidence_ids=[],
            importance=10.0,
            reason="validated positioning",
        )],
        must_show_fact_ids=["fact:role"],
        supporting_fact_ids=[],
        optional_fact_ids=[],
        explicit_gaps=[],
        preferred_section_order=["summary", "skills", "experience"],
        preferred_layout_profile_id=preferred,
    )


def test_explicit_valid_preference_wins_over_mapping() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    result = select_layout_profile(
        strategy=_strategy("ops", "technical_clean"),
        profiles=profiles,
        track_layout_map={"ops": "operations_clean"},
    )
    assert result.id == "technical_clean"


def test_explicit_unknown_preference_fails_closed() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    strategy = _strategy("ops").model_copy(
        update={"preferred_layout_profile_id": "missing_profile"}
    )
    with pytest.raises(ValueError, match="layout_profile_unavailable"):
        select_layout_profile(strategy=strategy, profiles=profiles)


def test_injected_track_mapping_selects_profile() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    mapping = {"tech": "technical_clean", "ops": "operations_clean"}
    assert select_layout_profile(
        strategy=_strategy("tech"), profiles=profiles, track_layout_map=mapping
    ).id == "technical_clean"
    assert select_layout_profile(
        strategy=_strategy("ops"), profiles=profiles, track_layout_map=mapping
    ).id == "operations_clean"


def test_absent_track_mapping_uses_compact_ats() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    assert select_layout_profile(
        strategy=_strategy("unknown"), profiles=profiles
    ).id == "compact_ats"


def test_mapping_to_missing_profile_fails_closed() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    with pytest.raises(ValueError, match="layout_profile_unavailable"):
        select_layout_profile(
            strategy=_strategy("tech"),
            profiles=profiles,
            track_layout_map={"tech": "missing_profile"},
        )


def test_mapping_insertion_order_does_not_change_selection() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    strategy = _strategy("tech")
    first = {"tech": "technical_clean", "ops": "operations_clean"}
    second = dict(reversed(list(first.items())))
    assert select_layout_profile(
        strategy=strategy, profiles=profiles, track_layout_map=first
    ) == select_layout_profile(
        strategy=strategy, profiles=profiles, track_layout_map=second
    )
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_cv_layout_selector.py -q
```

Expected: import failure because selector is not implemented/exported.

- [ ] **Step 3: Implement selector**

Create `app/cv/layout/selector.py`:

```python
from __future__ import annotations

from collections.abc import Mapping

from app.cv.layout.models import LayoutProfile
from app.cv.strategy.models import CVStrategy


def select_layout_profile(
    *,
    strategy: CVStrategy,
    profiles: Mapping[str, LayoutProfile],
    track_layout_map: Mapping[str, str] | None = None,
) -> LayoutProfile:
    if strategy.preferred_layout_profile_id is not None:
        profile_id = strategy.preferred_layout_profile_id
    else:
        mapping = track_layout_map or {}
        profile_id = mapping.get(strategy.application_track_id, "compact_ats")

    try:
        return profiles[profile_id]
    except KeyError as exc:
        raise ValueError("layout_profile_unavailable") from exc
```

Export it from `app/cv/layout/__init__.py`.

- [ ] **Step 4: Verify GREEN and privacy**

```bash
pytest tests/test_cv_layout_selector.py -q
pytest -q
python -m compileall app
grep -R "software-data-decision\|geospatial-mining-tech\|operations-support" app config tests && exit 1 || true
```

Expected: tests PASS and grep finds no private track IDs.

- [ ] **Step 5: Commit**

```bash
git add app/cv/layout tests/test_cv_layout_selector.py
git commit -m "feat: select CV layout from injected track mapping"
```

---

### Task 3: Profile-specific RenderCV designs and renderer contract

**Files:**
- Create: `config/layouts/technical_clean.yaml`
- Create: `config/layouts/operations_clean.yaml`
- Create: `config/layouts/compact_ats.yaml`
- Modify: `app/cv/renderers/rendercv_typst.py`
- Modify: `tests/test_recruiter_renderer.py`
- Modify: `tests/test_recruiter_theme_contract.py`
- Create: `tests/test_cv_layout_renderer_contract.py`

**Interfaces:**

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

- [ ] **Step 1: Write RED tests**

Create `tests/test_cv_layout_renderer_contract.py`:

```python
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.cv.layout import LayoutProfile, load_layout_profiles
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.renderers.rendercv_typst import RenderCVTypstRenderer
from test_recruiter_renderer import _recruiter_document, _source_document


def test_renderer_accepts_selected_layout_profile(tmp_path: Path) -> None:
    profile = load_layout_profiles("config/layout_profiles.yaml")["technical_clean"]
    result = RenderCVTypstRenderer().render(
        recruiter_document=_recruiter_document(),
        source_document=_source_document(),
        output_path=tmp_path / "technical.pdf",
        policy=load_recruiter_policy("config/recruiter_policy.yaml"),
        layout_profile=profile,
    )
    assert Path(result.artifact.path).is_file()


def test_renderer_rejects_missing_design(tmp_path: Path) -> None:
    profile = LayoutProfile(
        version="layout-profile-v1",
        id="technical_clean",
        design_path="config/layouts/missing.yaml",
        density="comfortable",
        emphasis="technical",
    )
    with pytest.raises(ValueError, match="RenderCV/Typst render failed"):
        RenderCVTypstRenderer().render(
            _recruiter_document(),
            _source_document(),
            tmp_path / "missing.pdf",
            load_recruiter_policy("config/recruiter_policy.yaml"),
            profile,
        )


def test_same_content_is_extractable_across_all_profiles(tmp_path: Path) -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    renderer = RenderCVTypstRenderer()
    policy = load_recruiter_policy("config/recruiter_policy.yaml")
    expected = ["Alex Example", "Software & Operations Developer", "Python", "SQL"]
    for profile in profiles.values():
        result = renderer.render(
            _recruiter_document(),
            _source_document(),
            tmp_path / f"{profile.id}.pdf",
            policy,
            profile,
        )
        text = "\n".join(
            page.extract_text() or "" for page in PdfReader(result.artifact.path).pages
        )
        assert all(value in text for value in expected)
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_cv_layout_renderer_contract.py -q
```

Expected: `TypeError` because current renderer does not accept `layout_profile`.

- [ ] **Step 3: Create the three restrained ATS-safe designs**

Each file copies the structural settings from current `config/rendercv_one_page.yaml`: `theme: sb2nov`, A4, left alignment, `Source Sans 3`, footer/top-note off, connection icons off, external-link icons off, one-column sections.

Use these profile differences:

| Setting | technical_clean | operations_clean | compact_ats |
|---|---:|---:|---:|
| top/bottom margin | 0.48in | 0.52in | 0.45in |
| left/right margin | 0.55in | 0.58in | 0.50in |
| line spacing | 0.64em | 0.62em | 0.56em |
| body font | 10pt | 10pt | 9.6pt |
| name font | 22pt | 21pt | 20pt |
| headline | 11pt | 10.6pt | 10.4pt |
| connections | 9.6pt | 9.5pt | 9.3pt |
| section titles | 1.18em | 1.12em | 1.10em |
| title line | 0.5pt | 0.4pt | 0.35pt |
| title space above | 0.34cm | 0.30cm | 0.25cm |
| title space below | 0.18cm | 0.16cm | 0.13cm |
| regular entries | 0.48em | 0.52em | 0.38em |
| text entries | 0.26em | 0.25em | 0.20em |

No profile introduces columns, bars, charts, sidebars, semantic icons, or color-dependent information.

- [ ] **Step 4: Implement safe design resolution and explicit renderer parameter**

In `app/cv/renderers/rendercv_typst.py` import `LayoutProfile`, remove renderer-owned default design selection, and add:

```python
def _resolve_layout_design(profile: LayoutProfile) -> Path:
    root = _PROJECT_ROOT.resolve()
    candidate = (root / profile.design_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("RenderCV/Typst render failed") from exc
    if not candidate.is_file():
        raise ValueError("RenderCV/Typst render failed")
    return candidate
```

In `render(...)`, compute `design = _resolve_layout_design(layout_profile)` and use that path for both `_configured_body_font_size()` and `_render_pdf_in_process()`.

- [ ] **Step 5: Migrate existing renderer callers/tests**

In `tests/test_recruiter_renderer.py`, add:

```python
from app.cv.layout import load_layout_profiles


def _layout_profile():
    return load_layout_profiles("config/layout_profiles.yaml")["compact_ats"]
```

Pass `layout_profile=_layout_profile()` to every direct `RenderCVTypstRenderer.render()` call.

Update `tests/test_recruiter_theme_contract.py` to inspect every `config/layouts/*.yaml` profile and assert:

```python
assert design["design"]["header"]["connections"]["show_icons"] is False
assert design["design"]["links"]["show_external_link_icon"] is False
assert design["design"]["typography"]["font_family"] == "Source Sans 3"
```

- [ ] **Step 6: Verify GREEN**

```bash
pytest tests/test_cv_layout_renderer_contract.py tests/test_recruiter_renderer.py tests/test_recruiter_theme_contract.py -q
pytest -q
python -m compileall app
```

Expected: PASS and extractable text across all profiles.

- [ ] **Step 7: Commit**

```bash
git add config/layouts app/cv/renderers/rendercv_typst.py tests/test_cv_layout_renderer_contract.py tests/test_recruiter_renderer.py tests/test_recruiter_theme_contract.py
git commit -m "feat: render recruiter CVs with layout profiles"
```

---

### Task 4: Service wiring, stable reduction behavior, and previews

**Files:**
- Modify: `app/cv/service.py`
- Modify: `scripts/render_recruiter_previews.py`
- Create: `tests/test_cv_service_layout_profile.py`
- Modify: renderer doubles/callers in existing `tests/` as required by signature migration

**Interfaces:**

`CVPreparationService.__init__` gains:

```python
layout_profiles: Mapping[str, LayoutProfile] | None = None,
track_layout_map: Mapping[str, str] | None = None,
```

Defaults:

```python
self.layout_profiles = (
    dict(layout_profiles)
    if layout_profiles is not None
    else load_layout_profiles(_DEFAULT_LAYOUT_PROFILES_PATH)
)
self.track_layout_map = dict(track_layout_map or {})
```

- [ ] **Step 1: Write RED service tests**

Create `tests/test_cv_service_layout_profile.py` using `NOW`, `LANGUAGE_DECISION`, `_assessment`, `_inputs`, `_resolver` from `test_cv_service`.

Use a capturing wrapper:

```python
class CapturingRenderer:
    renderer_version = "capturing-layout-v1"

    def __init__(self) -> None:
        self.profile_ids: list[str] = []

    def render(self, recruiter_document, source_document, output_path, policy, layout_profile):
        self.profile_ids.append(layout_profile.id)
        from app.cv.renderers.rendercv_typst import RenderCVTypstRenderer
        return RenderCVTypstRenderer().render(
            recruiter_document,
            source_document,
            output_path,
            policy,
            layout_profile,
        )
```

Test injected fictional mapping:

```python
result = CVPreparationService(
    taxonomy_resolver=_resolver(),
    id_factory=lambda: "app-layout",
    recruiter_renderer=renderer,
    track_layout_map={"tech": "technical_clean"},
).prepare(...)
assert result.status == "PREPARED"
assert set(renderer.profile_ids) == {"technical_clean"}
```

Test public default fallback with no mapping:

```python
assert set(renderer.profile_ids) == {"compact_ats"}
```

Test fail-closed mapped profile:

```python
result = CVPreparationService(
    taxonomy_resolver=_resolver(),
    recruiter_renderer=renderer,
    track_layout_map={"tech": "missing_profile"},
).prepare(...)
assert result.status == "BLOCKED_RENDER"
assert result.errors[0].code == "layout_profile_unavailable"
assert renderer.profile_ids == []
assert not list(tmp_path.rglob("*.pdf"))
```

For reduction stability, reuse/extend the existing overflow QA/renderer fixture from `tests/test_cv_service.py` so two render attempts occur, then assert every captured profile ID is identical.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_cv_service_layout_profile.py -q
```

Expected: constructor/signature failures because service does not yet accept/pass layout configuration.

- [ ] **Step 3: Wire selection exactly once**

In `app/cv/service.py`:

```python
from collections.abc import Mapping
from app.cv.layout import LayoutProfile, load_layout_profiles, select_layout_profile

_DEFAULT_LAYOUT_PROFILES_PATH = _PROJECT_ROOT / "config" / "layout_profiles.yaml"
```

After strategy creation and Narrative QA, before output/render loop:

```python
try:
    selected_layout_profile = select_layout_profile(
        strategy=strategy,
        profiles=self.layout_profiles,
        track_layout_map=self.track_layout_map,
    )
except ValueError as exc:
    if str(exc) != "layout_profile_unavailable":
        raise
    return _blocked(
        "BLOCKED_RENDER",
        code="layout_profile_unavailable",
        message="Selected CV layout profile is unavailable",
        warnings=[
            *validation.warnings,
            *recruiter_validation.warnings,
            *narrative_warnings,
        ],
    )
```

Pass `selected_layout_profile` to every `self.recruiter_renderer.render(...)` invocation. Never call the selector again inside the reduction loop.

- [ ] **Step 4: Migrate preview script and test doubles**

Every test renderer double must accept the new trailing `layout_profile` argument without changing unrelated behavior.

Update `scripts/render_recruiter_previews.py` to load:

```python
profiles = load_layout_profiles("config/layout_profiles.yaml")
```

and render at least one fictional fixture with each profile. Use explicit filenames:

```text
recruiter_software__technical_clean.pdf
recruiter_tech_operations__operations_clean.pdf
recruiter_software__compact_ats.pdf
```

Run every output through existing `RecruiterQualityQA` using `RenderPolicy`, not `RecruiterPolicy`.

- [ ] **Step 5: Run local/CI-equivalent verification**

```bash
pytest tests/test_cv_service_layout_profile.py tests/test_cv_service.py tests/test_recruiter_renderer.py -q
pytest -q
python -m compileall app
git diff --check origin/main...HEAD
python scripts/render_recruiter_previews.py --output-dir artifacts/ci/recruiter-preview
grep -R "software-data-decision\|geospatial-mining-tech\|operations-support" app config tests && exit 1 || true
```

Expected: all tests/compile/previews PASS and privacy grep empty.

- [ ] **Step 6: Require final GitHub Actions gate on final head SHA**

Require success for:

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

Do not mark ready or merge with pending/failed jobs.

- [ ] **Step 7: Commit**

```bash
git add app/cv/service.py scripts/render_recruiter_previews.py tests
git commit -m "feat: wire CV layout profiles into preparation"
```

---

## Final Review Gate

Before marking PR #47 ready:

1. Confirm changed source/config/tests contain no private candidate track IDs.
2. Confirm `CVStrategy` and `RecruiterDocumentModel` are never mutated by layout selection.
3. Confirm all three layouts are repository-relative, single-column, text-first RenderCV designs.
4. Confirm `RenderPolicy` still owns page/font constraints and `RecruiterPolicy` still owns composition.
5. Confirm invalid explicit or injected profile selection blocks before renderer invocation and leaves no PDF.
6. Confirm one profile is selected per preparation run and reused through reduction retries.
7. Confirm no Gmail/outreach/ApplicationPacket/Visual QA/JSON Resume/second-renderer code changed.
8. Require a fresh successful Actions run on the final PR head SHA before integration.
