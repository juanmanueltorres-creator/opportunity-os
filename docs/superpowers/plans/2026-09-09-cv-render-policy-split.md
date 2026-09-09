# CV Render Policy Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate physical PDF constraints from recruiter composition policy while preserving the current one-page default behavior.

**Architecture:** Introduce a strict `RenderPolicy` consumed only by physical PDF QA. Keep `NarrativePolicy` for strategy/quality and make `RecruiterPolicy` composition-only. `CVPreparationService` loads both policies independently; RenderCV continues using recruiter composition policy for skill-group labels.

**Tech Stack:** Python 3.12/3.13, Pydantic v2, PyYAML, PyMuPDF, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-09-cv-render-policy-split-design.md`

## Global Constraints

- Default runtime remains exactly one page: `preferred_pages=1`, `max_pages=1`.
- `RenderPolicy` must permit an explicitly configured `max_pages=2`.
- `RecruiterPolicy` must contain no page-count or font-size fields after the split.
- Existing evidence, strategy, narrative, renderer, Gmail, outreach, and send semantics remain unchanged.
- No new dependency is added.
- TDD: each production change follows a failing test observed in CI.

---

### Task 1: RenderPolicy contract and configuration

**Files:**
- Create: `app/cv/render_policy.py`
- Create: `config/render_policy.yaml`
- Create: `tests/test_render_policy.py`

**Interfaces:**
- Produces: `RenderPolicy`, `load_render_policy(path: str | Path) -> RenderPolicy`, `RENDER_POLICY_VERSION = "render-policy-v1"`.
- Consumed later by: `RecruiterQualityQA` and `CVPreparationService`.

- [ ] **Step 1: Write the failing policy tests**

```python
from app.cv.render_policy import RenderPolicy, load_render_policy


def test_default_render_policy_preserves_one_page_behavior():
    policy = load_render_policy("config/render_policy.yaml")
    assert policy.preferred_pages == 1
    assert policy.max_pages == 1
    assert policy.page_size == "A4"
    assert policy.min_body_font_pt == 9.0
    assert policy.preferred_body_font_pt == 9.4


def test_render_policy_can_explicitly_allow_two_pages():
    policy = RenderPolicy(
        version="render-policy-v1",
        page_size="A4",
        preferred_pages=1,
        max_pages=2,
        min_body_font_pt=9.0,
        preferred_body_font_pt=9.4,
    )
    assert policy.max_pages == 2


def test_render_policy_rejects_preferred_pages_above_max():
    with pytest.raises(ValueError):
        RenderPolicy(
            version="render-policy-v1",
            page_size="A4",
            preferred_pages=2,
            max_pages=1,
            min_body_font_pt=9.0,
            preferred_body_font_pt=9.4,
        )


def test_render_policy_rejects_preferred_font_below_minimum():
    with pytest.raises(ValueError):
        RenderPolicy(
            version="render-policy-v1",
            page_size="A4",
            preferred_pages=1,
            max_pages=1,
            min_body_font_pt=9.5,
            preferred_body_font_pt=9.4,
        )
```

- [ ] **Step 2: Run CI and verify RED**

Expected failure: `ModuleNotFoundError: No module named 'app.cv.render_policy'`.

- [ ] **Step 3: Add minimal strict model and loader**

Implement:

```python
RENDER_POLICY_VERSION = "render-policy-v1"

class RenderPolicy(StrictCVModel):
    version: str = Field(min_length=1)
    page_size: Literal["A4", "LETTER"] = "A4"
    preferred_pages: int = Field(ge=1, le=2)
    max_pages: int = Field(ge=1, le=2)
    min_body_font_pt: float = Field(ge=9.0)
    preferred_body_font_pt: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_contract(self) -> "RenderPolicy":
        if self.version != RENDER_POLICY_VERSION:
            raise ValueError(f"unsupported render policy version: {self.version}")
        if self.preferred_pages > self.max_pages:
            raise ValueError("preferred_pages must be less than or equal to max_pages")
        if self.preferred_body_font_pt < self.min_body_font_pt:
            raise ValueError("preferred_body_font_pt must be greater than or equal to min_body_font_pt")
        return self
```

Add `config/render_policy.yaml` with the backward-compatible one-page values from the spec.

- [ ] **Step 4: Run full CI and verify GREEN**

Expected: policy tests pass; existing suite remains green.

- [ ] **Step 5: Commit**

Commit message: `feat: add standalone CV render policy`.

---

### Task 2: Make RecruiterPolicy composition-only and move physical QA to RenderPolicy

**Files:**
- Modify: `app/cv/recruiter_policy.py`
- Modify: `config/recruiter_policy.yaml`
- Modify: `app/cv/recruiter_qa.py`
- Modify: `tests/test_recruiter_policy.py`
- Modify: `tests/test_recruiter_qa.py`

**Interfaces:**
- `RecruiterPolicy`: composition caps and `skill_groups` only.
- `RecruiterQualityQA.evaluate(..., policy: RenderPolicy) -> RecruiterQAResult`.

- [ ] **Step 1: Write failing split-contract tests**

Add assertions that:

```python
policy = load_recruiter_policy("config/recruiter_policy.yaml")
assert not hasattr(policy, "max_pages")
assert not hasattr(policy, "min_body_font_pt")
assert not hasattr(policy, "preferred_body_font_pt")
```

Add QA tests proving:

```python
one_page_policy = RenderPolicy(... preferred_pages=1, max_pages=1 ...)
# a two-page PDF fails with existing recruiter_one_page_failed behavior

two_page_policy = RenderPolicy(... preferred_pages=1, max_pages=2 ...)
# a two-page PDF does not fail page-count validation and emits
# recruiter_preferred_page_count_exceeded warning
```

- [ ] **Step 2: Run CI and verify RED**

Expected: current `RecruiterPolicy` still exposes the physical fields and `RecruiterQualityQA` still consumes them.

- [ ] **Step 3: Remove physical fields from RecruiterPolicy**

Keep exactly these responsibilities in `RecruiterPolicy`:

```text
version
max_projects
max_experience_entries
max_experience_bullets
max_skill_groups
max_skill_tokens
max_profile_claims
max_education_items
skill_groups
```

Delete the `max_pages == 1` invariant. Remove the three physical fields from `config/recruiter_policy.yaml`.

- [ ] **Step 4: Switch RecruiterQualityQA to RenderPolicy**

Rules:

```text
if max_pages == 1 and page_count != 1:
    hard error recruiter_one_page_failed
elif page_count > max_pages:
    hard error recruiter_page_count_exceeded
elif page_count > preferred_pages:
    warning recruiter_preferred_page_count_exceeded
```

Use `policy.min_body_font_pt` for font validation. Validate page geometry against `policy.page_size` with deterministic A4 and LETTER dimensions.

- [ ] **Step 5: Run full CI and verify GREEN**

Expected: recruiter policy/QA tests and all unrelated suites pass.

- [ ] **Step 6: Commit**

Commit message: `refactor: separate recruiter composition from render constraints`.

---

### Task 3: Wire RenderPolicy into CVPreparationService without changing CLI behavior

**Files:**
- Modify: `app/cv/service.py`
- Modify: `tests/test_cv_service.py`
- Modify: `tests/test_cv_service_narrative_gate.py` only if fake recruiter QA signatures require it.

**Interfaces:**
- `CVPreparationService.__init__(..., render_policy: RenderPolicy | None = None)`.
- Default: `load_render_policy(config/render_policy.yaml)`.
- `RecruiterQualityQA.evaluate` receives `self.render_policy`.
- RenderCV renderer and recruiter-document reduction continue receiving `self.recruiter_policy`.

- [ ] **Step 1: Write failing service wiring test**

Use a fake recruiter QA that records the policy object passed to `evaluate` and assert it receives the injected `RenderPolicy`, not `RecruiterPolicy`.

Also retain the existing integration test where a two-page render blocks preparation under defaults.

- [ ] **Step 2: Run CI and verify RED**

Expected: service constructor does not yet accept `render_policy` and recruiter QA still receives recruiter policy.

- [ ] **Step 3: Implement minimal service wiring**

Add `_DEFAULT_RENDER_POLICY_PATH`, constructor injection/default loading, and pass `self.render_policy` only to recruiter physical QA.

Do not change renderer, reduction, strategy, narrative, packet, or outreach code.

- [ ] **Step 4: Run full regression suite**

Required gates:

```text
pytest: PASS
compile: PASS
diff whitespace: PASS
private-file guard: PASS
recruiter previews: PASS
offline runtime build/verify Python 3.12: PASS
offline runtime build/verify Python 3.13: PASS
```

- [ ] **Step 5: Review scope**

Changed production files must be limited to policy/QA/service boundaries. No Gmail/outreach/send changes. No layout-profile or visual-QA implementation in this PR.

- [ ] **Step 6: Commit**

Commit message: `refactor: wire render policy into CV preparation`.
