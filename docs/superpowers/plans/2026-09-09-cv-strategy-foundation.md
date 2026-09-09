# CV Strategy Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, evidence-safe `CVStrategy` foundation that derives recruiter positioning, up to three core messages, explicit gaps, and fact priorities from the current Opportunity-OS CV pipeline without changing rendered PDFs or `ApplicationPacket` behavior.

**Architecture:** PR1 adds a pure strategy layer downstream of the existing semantic CV and upstream of the future narrative composer. It introduces strict strategy models, a versioned narrative-policy slice used only for strategy construction, deterministic requirement scoring, and a rules-first `build_cv_strategy()` function. The existing `CVPreparationService`, recruiter compositor, RenderCV renderer, QA gates, CLI, and packet schema remain untouched in this PR.

**Tech Stack:** Python 3.12+, Pydantic v2, PyYAML, pytest; existing Opportunity-OS `RadarAssessment`, `EvidenceSelection`, `CVDocumentModel`, selector, and composer contracts.

**Spec:** `docs/superpowers/specs/2026-09-09-cv-strategy-narrative-design.md`

## Global Constraints

- Python runtime remains `>=3.12`.
- Pydantic remains `>=2` and all new public models inherit `StrictCVModel` so unknown fields are rejected.
- `CVDocumentModel` remains the authoritative visible-claim/provenance model.
- This plan MUST NOT modify `app/cv/service.py`, `app/cv/recruiter_composer.py`, renderer code, PDF layout, `ApplicationPacket`, CLI output, or any generated PDF behavior.
- The strategy builder is rules-first and deterministic: identical normalized inputs and policy produce identical model dumps.
- `CVStrategy.core_messages` contains between 1 and 3 messages; three is the hard maximum.
- Candidate positioning MUST come from an existing evidence-backed headline claim in `CVDocumentModel`; opportunity title text is target context only and MUST NOT become candidate positioning automatically.
- Unsupported seniority/title inflation is a validation failure, not a ranking penalty.
- User-private career configuration is represented by a generic schema only. No real user identity, career-track values, or private state is committed to the public repository.
- Public tests use synthetic identities and synthetic evidence only.
- No LLM dependency or network call is introduced.
- No JSON Resume, visual layout, narrative QA, visual QA, ATS parser, or second renderer work belongs in this plan.
- Every task follows RED → GREEN → focused regression → commit.

---

## File Structure Locked for PR1

Create these files:

```text
app/cv/strategy/
├── __init__.py        # stable public exports for PR1 strategy API
├── models.py          # CoreMessage, CVStrategy, StrategyTrackConfig
├── policy.py          # NarrativePolicy slice + YAML loader
├── scoring.py         # deterministic supported-requirement ranking
└── builder.py         # build_cv_strategy orchestration

config/
└── narrative_policy.yaml

tests/
├── test_cv_strategy_models.py
├── test_cv_strategy_policy.py
├── test_cv_strategy_scoring.py
├── test_cv_strategy_builder.py
└── test_cv_strategy_pipeline_contract.py
```

Do not modify existing production files in PR1. The integration contract is proven by tests that call the existing `select_evidence()` and `compose_cv()` before `build_cv_strategy()`.

---

### Task 1: Strategy Contracts and Versioned Policy

**Files:**
- Create: `app/cv/strategy/__init__.py`
- Create: `app/cv/strategy/models.py`
- Create: `app/cv/strategy/policy.py`
- Create: `config/narrative_policy.yaml`
- Test: `tests/test_cv_strategy_models.py`
- Test: `tests/test_cv_strategy_policy.py`

**Interfaces:**
- Produces: `STRATEGY_VERSION: str = "cv-strategy-v1"`
- Produces: `CoreMessage`
- Produces: `StrategyTrackConfig`
- Produces: `CVStrategy`
- Produces: `NARRATIVE_POLICY_VERSION: str = "narrative-policy-v1"`
- Produces: `NarrativePolicy`
- Produces: `load_narrative_policy(path: str | Path) -> NarrativePolicy`
- Later tasks consume these names exactly.

- [ ] **Step 1: Write failing model-contract tests**

Create `tests/test_cv_strategy_models.py` with these behaviors:

```python
import pytest
from pydantic import ValidationError

from app.cv.strategy.models import CoreMessage, CVStrategy, StrategyTrackConfig


def _message(message_id: str, fact_id: str) -> CoreMessage:
    return CoreMessage(
        id=message_id,
        message=message_id,
        fact_ids=[fact_id],
        evidence_ids=[],
        importance=1.0,
        reason="synthetic test support",
    )


def test_strategy_accepts_at_most_three_core_messages() -> None:
    strategy = CVStrategy(
        strategy_version="cv-strategy-v1",
        application_track_id="tech",
        target_role="Data Analyst",
        target_company="Example Co",
        positioning="Data Engineer",
        recruiter_question="Can the candidate perform this role?",
        core_messages=[
            _message("positioning", "role-data"),
            _message("python", "skill-python"),
            _message("sql", "skill-sql"),
        ],
        must_show_fact_ids=["role-data", "skill-python"],
        supporting_fact_ids=["skill-sql"],
        optional_fact_ids=[],
        explicit_gaps=[],
        preferred_section_order=["summary", "skills", "experience"],
        preferred_layout_profile_id=None,
    )
    assert len(strategy.core_messages) == 3

    with pytest.raises(ValidationError):
        CVStrategy(
            **{
                **strategy.model_dump(),
                "core_messages": [
                    _message("one", "f1"),
                    _message("two", "f2"),
                    _message("three", "f3"),
                    _message("four", "f4"),
                ],
                "must_show_fact_ids": ["f1", "f2", "f3", "f4"],
                "supporting_fact_ids": [],
            }
        )


def test_strategy_rejects_overlapping_fact_buckets() -> None:
    with pytest.raises(ValueError, match="strategy fact buckets must be disjoint"):
        CVStrategy(
            strategy_version="cv-strategy-v1",
            application_track_id="tech",
            target_role="Data Analyst",
            target_company="Example Co",
            positioning="Data Engineer",
            recruiter_question="Can the candidate perform this role?",
            core_messages=[_message("positioning", "role-data")],
            must_show_fact_ids=["role-data"],
            supporting_fact_ids=["role-data"],
            optional_fact_ids=[],
            explicit_gaps=[],
            preferred_section_order=["summary", "skills"],
        )


def test_core_message_fact_must_exist_in_strategy_buckets() -> None:
    with pytest.raises(ValueError, match="core message facts must belong to strategy fact buckets"):
        CVStrategy(
            strategy_version="cv-strategy-v1",
            application_track_id="tech",
            target_role="Data Analyst",
            target_company="Example Co",
            positioning="Data Engineer",
            recruiter_question="Can the candidate perform this role?",
            core_messages=[_message("positioning", "role-data")],
            must_show_fact_ids=["different-fact"],
            supporting_fact_ids=[],
            optional_fact_ids=[],
            explicit_gaps=[],
            preferred_section_order=["summary", "skills"],
        )


def test_track_config_has_no_free_form_positioning_field() -> None:
    with pytest.raises(ValidationError):
        StrategyTrackConfig.model_validate(
            {
                "id": "tech",
                "positioning": "Senior BI Specialist",
            }
        )
```

- [ ] **Step 2: Run the model tests and verify RED**

Run:

```bash
python -m pytest tests/test_cv_strategy_models.py -q
```

Expected: collection/import failure because `app.cv.strategy.models` does not exist.

- [ ] **Step 3: Implement the strict strategy models**

Create `app/cv/strategy/models.py`:

```python
from __future__ import annotations

from pydantic import Field, model_validator

from app.cv.models import CVSection, StrictCVModel

STRATEGY_VERSION = "cv-strategy-v1"


class CoreMessage(StrictCVModel):
    id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    fact_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    importance: float = Field(ge=0)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def references_must_be_unique(self) -> "CoreMessage":
        if len(self.fact_ids) != len(set(self.fact_ids)):
            raise ValueError("core message fact ids must be unique")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("core message evidence ids must be unique")
        return self


class StrategyTrackConfig(StrictCVModel):
    id: str = Field(min_length=1)
    positioning_claim_id: str | None = None
    priority_requirements: list[str] = Field(default_factory=list)
    preferred_section_order: list[CVSection] = Field(default_factory=list)
    preferred_layout_profile_id: str | None = None

    @model_validator(mode="after")
    def ordered_values_must_be_unique(self) -> "StrategyTrackConfig":
        if len(self.priority_requirements) != len(set(self.priority_requirements)):
            raise ValueError("priority requirements must be unique")
        if len(self.preferred_section_order) != len(set(self.preferred_section_order)):
            raise ValueError("preferred section order must be unique")
        return self


class CVStrategy(StrictCVModel):
    strategy_version: str = Field(min_length=1)
    application_track_id: str = Field(min_length=1)
    target_role: str = Field(min_length=1)
    target_company: str | None = None
    positioning: str = Field(min_length=1)
    recruiter_question: str = Field(min_length=1)
    core_messages: list[CoreMessage] = Field(min_length=1, max_length=3)
    must_show_fact_ids: list[str] = Field(default_factory=list)
    supporting_fact_ids: list[str] = Field(default_factory=list)
    optional_fact_ids: list[str] = Field(default_factory=list)
    explicit_gaps: list[str] = Field(default_factory=list)
    preferred_section_order: list[CVSection] = Field(min_length=1)
    preferred_layout_profile_id: str | None = None

    @model_validator(mode="after")
    def validate_strategy_references(self) -> "CVStrategy":
        if self.strategy_version != STRATEGY_VERSION:
            raise ValueError(f"unsupported strategy version: {self.strategy_version}")

        buckets = [
            self.must_show_fact_ids,
            self.supporting_fact_ids,
            self.optional_fact_ids,
        ]
        if any(len(bucket) != len(set(bucket)) for bucket in buckets):
            raise ValueError("strategy fact bucket ids must be unique")

        bucket_sets = [set(bucket) for bucket in buckets]
        if (
            bucket_sets[0] & bucket_sets[1]
            or bucket_sets[0] & bucket_sets[2]
            or bucket_sets[1] & bucket_sets[2]
        ):
            raise ValueError("strategy fact buckets must be disjoint")

        if len(self.preferred_section_order) != len(set(self.preferred_section_order)):
            raise ValueError("preferred section order must be unique")

        message_ids = [message.id for message in self.core_messages]
        if len(message_ids) != len(set(message_ids)):
            raise ValueError("core message ids must be unique")

        known_facts = set().union(*bucket_sets)
        message_facts = {
            fact_id
            for message in self.core_messages
            for fact_id in message.fact_ids
        }
        if not message_facts.issubset(known_facts):
            raise ValueError("core message facts must belong to strategy fact buckets")
        return self
```

Create `app/cv/strategy/__init__.py` initially with only model exports:

```python
from app.cv.strategy.models import (
    STRATEGY_VERSION,
    CoreMessage,
    CVStrategy,
    StrategyTrackConfig,
)

__all__ = [
    "STRATEGY_VERSION",
    "CoreMessage",
    "CVStrategy",
    "StrategyTrackConfig",
]
```

- [ ] **Step 4: Run the model tests and verify GREEN**

Run:

```bash
python -m pytest tests/test_cv_strategy_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Write failing policy tests**

Create `tests/test_cv_strategy_policy.py`:

```python
from pathlib import Path

import pytest

from app.cv.strategy.policy import NarrativePolicy, load_narrative_policy


def _payload() -> dict:
    return {
        "version": "narrative-policy-v1",
        "max_core_messages": 3,
        "positioning_message_importance": 10.0,
        "default_section_order": [
            "summary",
            "skills",
            "experience",
            "projects",
            "education",
            "languages",
            "links",
        ],
        "requirement_importance_weights": {
            "mandatory": 3.0,
            "preferred": 2.0,
            "unknown": 1.0,
        },
        "support_level_weights": {
            "EXACT_VERIFIED": 3.0,
            "APPROVED_ALIAS": 2.5,
            "TAXONOMY_RELATED": 1.0,
            "UNKNOWN": 0.0,
        },
        "priority_requirement_bonus": 1.0,
    }


def test_narrative_policy_loads_default_contract(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    import yaml

    path.write_text(yaml.safe_dump(_payload(), sort_keys=False), encoding="utf-8")
    policy = load_narrative_policy(path)

    assert policy.version == "narrative-policy-v1"
    assert policy.max_core_messages == 3
    assert policy.support_level_weights["EXACT_VERIFIED"] == 3.0


def test_narrative_policy_rejects_missing_support_weight() -> None:
    payload = _payload()
    payload["support_level_weights"].pop("TAXONOMY_RELATED")

    with pytest.raises(ValueError, match="support_level_weights"):
        NarrativePolicy.model_validate(payload)


def test_narrative_policy_rejects_more_than_three_core_messages() -> None:
    payload = _payload()
    payload["max_core_messages"] = 4

    with pytest.raises(ValueError):
        NarrativePolicy.model_validate(payload)


def test_narrative_policy_rejects_unknown_fields() -> None:
    payload = _payload()
    payload["secret_override"] = True

    with pytest.raises(ValueError):
        NarrativePolicy.model_validate(payload)
```

- [ ] **Step 6: Run policy tests and verify RED**

Run:

```bash
python -m pytest tests/test_cv_strategy_policy.py -q
```

Expected: import failure because `app.cv.strategy.policy` does not exist.

- [ ] **Step 7: Implement `NarrativePolicy`, loader, and default YAML**

Create `app/cv/strategy/policy.py`:

```python
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field, model_validator

from app.cv.models import CVSection, StrictCVModel

NARRATIVE_POLICY_VERSION = "narrative-policy-v1"
_REQUIRED_IMPORTANCE_KEYS = {"mandatory", "preferred", "unknown"}
_REQUIRED_SUPPORT_KEYS = {
    "EXACT_VERIFIED",
    "APPROVED_ALIAS",
    "TAXONOMY_RELATED",
    "UNKNOWN",
}


class NarrativePolicy(StrictCVModel):
    version: str = Field(min_length=1)
    max_core_messages: int = Field(ge=1, le=3)
    positioning_message_importance: float = Field(ge=0)
    default_section_order: list[CVSection] = Field(min_length=1)
    requirement_importance_weights: dict[str, float]
    support_level_weights: dict[str, float]
    priority_requirement_bonus: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_contract(self) -> "NarrativePolicy":
        if self.version != NARRATIVE_POLICY_VERSION:
            raise ValueError(f"unsupported narrative policy version: {self.version}")
        if set(self.requirement_importance_weights) != _REQUIRED_IMPORTANCE_KEYS:
            raise ValueError("requirement_importance_weights must contain the exact supported keys")
        if set(self.support_level_weights) != _REQUIRED_SUPPORT_KEYS:
            raise ValueError("support_level_weights must contain the exact supported keys")
        if any(value < 0 for value in self.requirement_importance_weights.values()):
            raise ValueError("requirement importance weights must be non-negative")
        if any(value < 0 for value in self.support_level_weights.values()):
            raise ValueError("support level weights must be non-negative")
        if len(self.default_section_order) != len(set(self.default_section_order)):
            raise ValueError("default section order must be unique")
        return self


def load_narrative_policy(path: str | Path) -> NarrativePolicy:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("narrative policy root must be a mapping")
    return NarrativePolicy.model_validate(payload)
```

Create `config/narrative_policy.yaml`:

```yaml
version: narrative-policy-v1
max_core_messages: 3
positioning_message_importance: 10.0

default_section_order:
  - summary
  - skills
  - experience
  - projects
  - education
  - languages
  - links

requirement_importance_weights:
  mandatory: 3.0
  preferred: 2.0
  unknown: 1.0

support_level_weights:
  EXACT_VERIFIED: 3.0
  APPROVED_ALIAS: 2.5
  TAXONOMY_RELATED: 1.0
  UNKNOWN: 0.0

priority_requirement_bonus: 1.0
```

Update `app/cv/strategy/__init__.py` to export `NarrativePolicy`, `NARRATIVE_POLICY_VERSION`, and `load_narrative_policy`.

- [ ] **Step 8: Run focused Task 1 tests**

Run:

```bash
python -m pytest tests/test_cv_strategy_models.py tests/test_cv_strategy_policy.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

```bash
git add app/cv/strategy/__init__.py app/cv/strategy/models.py app/cv/strategy/policy.py config/narrative_policy.yaml tests/test_cv_strategy_models.py tests/test_cv_strategy_policy.py
git commit -m "feat: add CV strategy contracts"
```

---

### Task 2: Deterministic Supported-Requirement Ranking

**Files:**
- Create: `app/cv/strategy/scoring.py`
- Test: `tests/test_cv_strategy_scoring.py`
- Modify: `app/cv/strategy/__init__.py`

**Interfaces:**
- Consumes: `NarrativePolicy`, `EvidenceSelection`, `Requirement`, `RequirementSupport`
- Produces: `RankedRequirement`
- Produces: `rank_supported_requirements(*, requirements, selection, policy, priority_requirements=()) -> list[RankedRequirement]`
- Builder in Task 3 consumes this function exactly.

- [ ] **Step 1: Write failing ranking tests**

Create `tests/test_cv_strategy_scoring.py`:

```python
from app.cv.models import EvidenceSelection, RequirementSupport
from app.cv.strategy.policy import NarrativePolicy
from app.cv.strategy.scoring import rank_supported_requirements
from app.radar.models import DerivedValue, Requirement


def _policy() -> NarrativePolicy:
    return NarrativePolicy(
        version="narrative-policy-v1",
        max_core_messages=3,
        positioning_message_importance=10.0,
        default_section_order=["summary", "skills", "experience"],
        requirement_importance_weights={
            "mandatory": 3.0,
            "preferred": 2.0,
            "unknown": 1.0,
        },
        support_level_weights={
            "EXACT_VERIFIED": 3.0,
            "APPROVED_ALIAS": 2.5,
            "TAXONOMY_RELATED": 1.0,
            "UNKNOWN": 0.0,
        },
        priority_requirement_bonus=1.0,
    )


def _requirement(value: str, importance: str) -> Requirement:
    return Requirement(
        kind="skill",
        value=value,
        importance=importance,
        exactness="conceptual",
        provenance=DerivedValue[str](
            value=value,
            source_text=f"Required: {value}",
            source_field="description",
            extraction_method="explicit_rule",
            confidence=1.0,
        ),
    )


def _support(value: str, level: str, fact_id: str) -> RequirementSupport:
    return RequirementSupport(
        requirement=value,
        support_level=level,
        fact_ids=[fact_id],
        evidence_ids=[],
        explanation=f"{value} supported by {fact_id}",
    )


def test_mandatory_exact_support_ranks_above_preferred_exact_support() -> None:
    requirements = [
        _requirement("SQL", "preferred"),
        _requirement("Python", "mandatory"),
    ]
    selection = EvidenceSelection(
        application_track_id="tech",
        requirement_support={
            "SQL": _support("SQL", "EXACT_VERIFIED", "skill-sql"),
            "Python": _support("Python", "EXACT_VERIFIED", "skill-python"),
        },
    )

    ranked = rank_supported_requirements(
        requirements=requirements,
        selection=selection,
        policy=_policy(),
    )

    assert [item.requirement.value for item in ranked] == ["Python", "SQL"]


def test_priority_requirement_bonus_breaks_equal_score_deterministically() -> None:
    requirements = [
        _requirement("SQL", "preferred"),
        _requirement("Python", "preferred"),
    ]
    selection = EvidenceSelection(
        application_track_id="tech",
        requirement_support={
            "SQL": _support("SQL", "EXACT_VERIFIED", "skill-sql"),
            "Python": _support("Python", "EXACT_VERIFIED", "skill-python"),
        },
    )

    ranked = rank_supported_requirements(
        requirements=requirements,
        selection=selection,
        policy=_policy(),
        priority_requirements=["SQL"],
    )

    assert [item.requirement.value for item in ranked] == ["SQL", "Python"]


def test_unknown_or_explicit_gap_is_never_ranked_as_supported_message() -> None:
    requirements = [
        _requirement("Power BI", "mandatory"),
        _requirement("PostGIS", "mandatory"),
    ]
    selection = EvidenceSelection(
        application_track_id="tech",
        requirement_support={
            "Power BI": _support("Power BI", "UNKNOWN", "placeholder"),
            "PostGIS": _support("PostGIS", "TAXONOMY_RELATED", "spatial-db"),
        },
        unsupported_requirements=["Power BI", "PostGIS"],
    )

    ranked = rank_supported_requirements(
        requirements=requirements,
        selection=selection,
        policy=_policy(),
    )

    assert ranked == []


def test_ranking_is_independent_of_requirement_input_order() -> None:
    python = _requirement("Python", "mandatory")
    sql = _requirement("SQL", "preferred")
    selection = EvidenceSelection(
        application_track_id="tech",
        requirement_support={
            "Python": _support("Python", "EXACT_VERIFIED", "skill-python"),
            "SQL": _support("SQL", "EXACT_VERIFIED", "skill-sql"),
        },
    )

    first = rank_supported_requirements(
        requirements=[python, sql],
        selection=selection,
        policy=_policy(),
    )
    second = rank_supported_requirements(
        requirements=[sql, python],
        selection=selection,
        policy=_policy(),
    )

    assert [item.model_key for item in first] == [item.model_key for item in second]
```

- [ ] **Step 2: Run scoring tests and verify RED**

Run:

```bash
python -m pytest tests/test_cv_strategy_scoring.py -q
```

Expected: import failure because `app.cv.strategy.scoring` does not exist.

- [ ] **Step 3: Implement deterministic scoring**

Create `app/cv/strategy/scoring.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from app.cv.models import EvidenceSelection, RequirementSupport
from app.cv.strategy.policy import NarrativePolicy
from app.radar.models import Requirement


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


@dataclass(frozen=True)
class RankedRequirement:
    requirement: Requirement
    support: RequirementSupport
    score: float

    @property
    def model_key(self) -> tuple[str, str, str]:
        return (
            _normalize(self.requirement.value),
            self.requirement.kind,
            self.requirement.importance,
        )


def rank_supported_requirements(
    *,
    requirements: list[Requirement],
    selection: EvidenceSelection,
    policy: NarrativePolicy,
    priority_requirements: list[str] | tuple[str, ...] = (),
) -> list[RankedRequirement]:
    unsupported = {_normalize(value) for value in selection.unsupported_requirements}
    priorities = {_normalize(value) for value in priority_requirements}
    seen: set[str] = set()
    ranked: list[RankedRequirement] = []

    for requirement in requirements:
        normalized = _normalize(requirement.value)
        if normalized in seen or normalized in unsupported:
            continue
        seen.add(normalized)

        support = selection.requirement_support.get(requirement.value)
        if support is None or support.support_level == "UNKNOWN" or not support.fact_ids:
            continue

        score = (
            policy.requirement_importance_weights[requirement.importance]
            + policy.support_level_weights[support.support_level]
            + (policy.priority_requirement_bonus if normalized in priorities else 0.0)
        )
        ranked.append(
            RankedRequirement(
                requirement=requirement,
                support=support,
                score=score,
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.score,
            _normalize(item.requirement.value),
            item.requirement.kind,
            item.requirement.importance,
        )
    )
    return ranked
```

Update `app/cv/strategy/__init__.py` to export `RankedRequirement` and `rank_supported_requirements`.

- [ ] **Step 4: Run scoring tests and verify GREEN**

Run:

```bash
python -m pytest tests/test_cv_strategy_scoring.py -q
```

Expected: PASS.

- [ ] **Step 5: Run Task 1 + Task 2 regression**

Run:

```bash
python -m pytest tests/test_cv_strategy_models.py tests/test_cv_strategy_policy.py tests/test_cv_strategy_scoring.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add app/cv/strategy/__init__.py app/cv/strategy/scoring.py tests/test_cv_strategy_scoring.py
git commit -m "feat: rank CV strategy requirements deterministically"
```

---

### Task 3: Evidence-Safe `CVStrategyBuilder`

**Files:**
- Create: `app/cv/strategy/builder.py`
- Test: `tests/test_cv_strategy_builder.py`
- Modify: `app/cv/strategy/__init__.py`

**Interfaces:**
- Consumes: `RadarAssessment`, `EvidenceSelection`, `CVDocumentModel`, `NarrativePolicy`, optional `StrategyTrackConfig`
- Produces exactly:

```python
def build_cv_strategy(
    *,
    assessment: RadarAssessment,
    selection: EvidenceSelection,
    document: CVDocumentModel,
    policy: NarrativePolicy,
    track_config: StrategyTrackConfig | None = None,
) -> CVStrategy:
    ...
```

- Builder does not accept free-form candidate positioning.
- Builder does not mutate `document` or `selection`.

- [ ] **Step 1: Write failing builder tests for positioning and gaps**

Create `tests/test_cv_strategy_builder.py`. Use a small direct semantic document rather than the full selector/composer pipeline; Task 4 covers full integration.

```python
from datetime import datetime, timezone

import pytest

from app.cv.models import (
    ClaimProvenance,
    CVClaim,
    CVDocumentModel,
    CVEntry,
    EvidenceSelection,
    RequirementSupport,
)
from app.cv.strategy.builder import build_cv_strategy
from app.cv.strategy.models import StrategyTrackConfig
from app.cv.strategy.policy import NarrativePolicy
from app.models.domain import Opportunity
from app.radar.models import (
    ConfidenceAssessment,
    DerivedValue,
    EligibilityResult,
    OpportunityEnrichment,
    RadarAssessment,
    Requirement,
)

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def _policy() -> NarrativePolicy:
    return NarrativePolicy(
        version="narrative-policy-v1",
        max_core_messages=3,
        positioning_message_importance=10.0,
        default_section_order=[
            "summary",
            "skills",
            "experience",
            "projects",
            "education",
            "languages",
            "links",
        ],
        requirement_importance_weights={
            "mandatory": 3.0,
            "preferred": 2.0,
            "unknown": 1.0,
        },
        support_level_weights={
            "EXACT_VERIFIED": 3.0,
            "APPROVED_ALIAS": 2.5,
            "TAXONOMY_RELATED": 1.0,
            "UNKNOWN": 0.0,
        },
        priority_requirement_bonus=1.0,
    )


def _requirement(value: str, importance: str) -> Requirement:
    return Requirement(
        kind="skill",
        value=value,
        importance=importance,
        exactness="conceptual",
        provenance=DerivedValue[str](
            value=value,
            source_text=f"Required: {value}",
            source_field="description",
            extraction_method="explicit_rule",
            confidence=1.0,
        ),
    )


def _assessment(*requirements: Requirement, title: str = "Senior BI Specialist") -> RadarAssessment:
    opportunity = Opportunity(
        id="opp-1",
        source="synthetic",
        source_id="source-1",
        source_url="https://example.test/job/1",
        company="Example Co",
        title=title,
        description="Synthetic job description",
        discovered_at=NOW,
    )
    enrichment = OpportunityEnrichment(
        opportunity_id=opportunity.id,
        normalized_title=DerivedValue[str](
            value=title,
            source_field="title",
            extraction_method="source_structured",
            confidence=1.0,
        ),
        requirements=list(requirements),
        extractor_version="test-v1",
        created_at=NOW,
    )
    return RadarAssessment(
        opportunity=opportunity,
        enrichment=enrichment,
        eligibility=EligibilityResult(eligible=True),
        confidence_score=100.0,
        confidence_breakdown=ConfidenceAssessment(
            score=100.0,
            requirement_extraction_quality=100.0,
            skill_normalization_coverage=100.0,
            evidence_traceability=100.0,
            seniority_location_legal_clarity=100.0,
            source_freshness_completeness=100.0,
        ),
        priority_score=100.0,
        selected_intent="CAREER",
        scoring_version="test-v1",
        extractor_version="test-v1",
        alias_registry_version="test-v1",
    )


def _document() -> CVDocumentModel:
    claims = [
        CVClaim(
            claim_id="fact:role-data",
            section="headline",
            kind="headline",
            text="Data Engineer",
        ),
        CVClaim(
            claim_id="fact:skill-python",
            section="skills",
            kind="skill",
            text="Python",
        ),
        CVClaim(
            claim_id="fact:skill-sql",
            section="skills",
            kind="skill",
            text="SQL",
        ),
    ]
    return CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=claims,
        entries=[
            CVEntry(entry_id="section:headline", section="headline", claim_ids=["fact:role-data"]),
            CVEntry(
                entry_id="section:skills",
                section="skills",
                claim_ids=["fact:skill-python", "fact:skill-sql"],
            ),
        ],
        provenance_map={
            "fact:role-data": ClaimProvenance(fact_ids=["role-data"], evidence_ids=[]),
            "fact:skill-python": ClaimProvenance(fact_ids=["skill-python"], evidence_ids=["module-python"]),
            "fact:skill-sql": ClaimProvenance(fact_ids=["skill-sql"], evidence_ids=[]),
        },
    )


def _selection() -> EvidenceSelection:
    return EvidenceSelection(
        application_track_id="tech",
        selected_fact_ids=["role-data", "skill-python", "skill-sql"],
        selected_evidence_ids=["module-python"],
        requirement_support={
            "Python": RequirementSupport(
                requirement="Python",
                support_level="EXACT_VERIFIED",
                fact_ids=["skill-python"],
                evidence_ids=[],
                explanation="Python exactly supported",
            ),
            "SQL": RequirementSupport(
                requirement="SQL",
                support_level="EXACT_VERIFIED",
                fact_ids=["skill-sql"],
                evidence_ids=[],
                explanation="SQL exactly supported",
            ),
            "Power BI": RequirementSupport(
                requirement="Power BI",
                support_level="UNKNOWN",
                fact_ids=[],
                evidence_ids=[],
                explanation="No verified support for Power BI",
            ),
        },
        unsupported_requirements=["Power BI"],
    )


def test_target_seniority_does_not_become_candidate_positioning() -> None:
    strategy = build_cv_strategy(
        assessment=_assessment(
            _requirement("Python", "mandatory"),
            _requirement("SQL", "preferred"),
            _requirement("Power BI", "mandatory"),
        ),
        selection=_selection(),
        document=_document(),
        policy=_policy(),
    )

    assert strategy.target_role == "Senior BI Specialist"
    assert strategy.positioning == "Data Engineer"
    assert strategy.positioning != strategy.target_role
    assert strategy.explicit_gaps == ["Power BI"]


def test_strategy_uses_no_more_than_three_core_messages() -> None:
    strategy = build_cv_strategy(
        assessment=_assessment(
            _requirement("Python", "mandatory"),
            _requirement("SQL", "preferred"),
            _requirement("Power BI", "mandatory"),
        ),
        selection=_selection(),
        document=_document(),
        policy=_policy(),
    )

    assert [message.message for message in strategy.core_messages] == [
        "Data Engineer",
        "Python",
        "SQL",
    ]


def test_configured_positioning_must_reference_existing_headline_claim() -> None:
    config = StrategyTrackConfig(
        id="tech",
        positioning_claim_id="fact:senior-bi-specialist",
    )

    with pytest.raises(ValueError, match="strategy_positioning_claim_invalid"):
        build_cv_strategy(
            assessment=_assessment(_requirement("Python", "mandatory")),
            selection=_selection(),
            document=_document(),
            policy=_policy(),
            track_config=config,
        )


def test_track_config_must_match_selected_application_track() -> None:
    config = StrategyTrackConfig(id="hospitality")

    with pytest.raises(ValueError, match="strategy_track_config_mismatch"):
        build_cv_strategy(
            assessment=_assessment(_requirement("Python", "mandatory")),
            selection=_selection(),
            document=_document(),
            policy=_policy(),
            track_config=config,
        )
```

- [ ] **Step 2: Run builder tests and verify RED**

Run:

```bash
python -m pytest tests/test_cv_strategy_builder.py -q
```

Expected: import failure because `app.cv.strategy.builder` does not exist.

- [ ] **Step 3: Implement the minimal deterministic builder**

Create `app/cv/strategy/builder.py`:

```python
from __future__ import annotations

import re

from app.cv.models import CVClaim, CVDocumentModel, EvidenceSelection
from app.cv.strategy.models import (
    STRATEGY_VERSION,
    CoreMessage,
    CVStrategy,
    StrategyTrackConfig,
)
from app.cv.strategy.policy import NarrativePolicy
from app.cv.strategy.scoring import rank_supported_requirements
from app.radar.models import RadarAssessment


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _message_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _normalize(value)).strip("-")
    return f"requirement:{slug or 'supported'}"


def _resolve_positioning_claim(
    document: CVDocumentModel,
    track_config: StrategyTrackConfig | None,
) -> CVClaim:
    headlines = sorted(
        (
            claim
            for claim in document.claims
            if claim.section == "headline" and claim.kind == "headline"
        ),
        key=lambda claim: claim.claim_id,
    )
    if track_config is not None and track_config.positioning_claim_id is not None:
        for claim in headlines:
            if claim.claim_id == track_config.positioning_claim_id:
                return claim
        raise ValueError("strategy_positioning_claim_invalid")
    if not headlines:
        raise ValueError("strategy_positioning_unavailable")
    return headlines[0]


def _evidence_for_fact_ids(
    document: CVDocumentModel,
    fact_ids: list[str],
) -> list[str]:
    target = set(fact_ids)
    evidence: set[str] = set()
    for provenance in document.provenance_map.values():
        if target & set(provenance.fact_ids):
            evidence.update(provenance.evidence_ids)
    return sorted(evidence)


def _preferred_section_order(
    document: CVDocumentModel,
    policy: NarrativePolicy,
    track_config: StrategyTrackConfig | None,
) -> list[str]:
    base = (
        track_config.preferred_section_order
        if track_config is not None and track_config.preferred_section_order
        else policy.default_section_order
    )
    ordered = list(base)
    for entry in document.entries:
        if entry.section == "headline" or entry.section in ordered:
            continue
        ordered.append(entry.section)
    return ordered


def build_cv_strategy(
    *,
    assessment: RadarAssessment,
    selection: EvidenceSelection,
    document: CVDocumentModel,
    policy: NarrativePolicy,
    track_config: StrategyTrackConfig | None = None,
) -> CVStrategy:
    if track_config is not None and track_config.id != selection.application_track_id:
        raise ValueError("strategy_track_config_mismatch")

    positioning_claim = _resolve_positioning_claim(document, track_config)
    positioning_provenance = document.provenance_map[positioning_claim.claim_id]
    ranked = rank_supported_requirements(
        requirements=assessment.enrichment.requirements,
        selection=selection,
        policy=policy,
        priority_requirements=(
            track_config.priority_requirements if track_config is not None else []
        ),
    )

    core_messages = [
        CoreMessage(
            id="positioning",
            message=positioning_claim.text,
            fact_ids=sorted(positioning_provenance.fact_ids),
            evidence_ids=sorted(positioning_provenance.evidence_ids),
            importance=policy.positioning_message_importance,
            reason="Primary evidence-backed positioning claim",
        )
    ]
    for candidate in ranked:
        if len(core_messages) >= policy.max_core_messages:
            break
        core_messages.append(
            CoreMessage(
                id=_message_id(candidate.requirement.value),
                message=candidate.requirement.value,
                fact_ids=sorted(candidate.support.fact_ids),
                evidence_ids=sorted(
                    set(candidate.support.evidence_ids)
                    | set(_evidence_for_fact_ids(document, candidate.support.fact_ids))
                ),
                importance=candidate.score,
                reason=candidate.support.explanation,
            )
        )

    unsupported = {_normalize(value) for value in selection.unsupported_requirements}
    must_show = set(positioning_provenance.fact_ids)
    supporting: set[str] = set()
    for requirement in assessment.enrichment.requirements:
        if _normalize(requirement.value) in unsupported:
            continue
        support = selection.requirement_support.get(requirement.value)
        if support is None or support.support_level == "UNKNOWN" or not support.fact_ids:
            continue
        if requirement.importance == "mandatory":
            must_show.update(support.fact_ids)
        else:
            supporting.update(support.fact_ids)

    supporting.difference_update(must_show)
    optional = set(selection.selected_fact_ids) - must_show - supporting

    target_role = (
        assessment.enrichment.normalized_title.value
        if assessment.enrichment.normalized_title is not None
        else assessment.opportunity.title
    )
    company = assessment.opportunity.company

    return CVStrategy(
        strategy_version=STRATEGY_VERSION,
        application_track_id=selection.application_track_id,
        target_role=target_role,
        target_company=company,
        positioning=positioning_claim.text,
        recruiter_question=(
            f"Can this candidate credibly perform {target_role} at {company} "
            "using verified evidence?"
        ),
        core_messages=core_messages,
        must_show_fact_ids=sorted(must_show),
        supporting_fact_ids=sorted(supporting),
        optional_fact_ids=sorted(optional),
        explicit_gaps=sorted(
            selection.unsupported_requirements,
            key=_normalize,
        ),
        preferred_section_order=_preferred_section_order(
            document,
            policy,
            track_config,
        ),
        preferred_layout_profile_id=(
            track_config.preferred_layout_profile_id
            if track_config is not None
            else None
        ),
    )
```

Update `app/cv/strategy/__init__.py` to export `build_cv_strategy`.

- [ ] **Step 4: Run builder tests and verify GREEN**

Run:

```bash
python -m pytest tests/test_cv_strategy_builder.py -q
```

Expected: PASS.

- [ ] **Step 5: Add explicit no-headline failure test**

Append to `tests/test_cv_strategy_builder.py`:

```python
def test_strategy_requires_evidence_backed_headline_positioning() -> None:
    document = _document().model_copy(
        update={
            "claims": [claim for claim in _document().claims if claim.kind != "headline"],
            "entries": [entry for entry in _document().entries if entry.section != "headline"],
            "provenance_map": {
                key: value
                for key, value in _document().provenance_map.items()
                if key != "fact:role-data"
            },
        }
    )

    with pytest.raises(ValueError, match="strategy_positioning_unavailable"):
        build_cv_strategy(
            assessment=_assessment(_requirement("Python", "mandatory")),
            selection=_selection(),
            document=document,
            policy=_policy(),
        )
```

- [ ] **Step 6: Run all strategy-unit tests**

Run:

```bash
python -m pytest tests/test_cv_strategy_models.py tests/test_cv_strategy_policy.py tests/test_cv_strategy_scoring.py tests/test_cv_strategy_builder.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add app/cv/strategy/__init__.py app/cv/strategy/builder.py tests/test_cv_strategy_builder.py
git commit -m "feat: build evidence-safe CV strategies"
```

---

### Task 4: Current-Pipeline Strategy Contract and Full Regression

**Files:**
- Create: `tests/test_cv_strategy_pipeline_contract.py`
- No production files modified.

**Interfaces:**
- Consumes existing `select_evidence()` from `app/cv/selector.py`.
- Consumes existing `compose_cv()` from `app/cv/composer.py`.
- Consumes new `build_cv_strategy()`.
- Proves PR1 works with actual current pipeline models without touching rendering.

- [ ] **Step 1: Write the end-to-end semantic-to-strategy contract test**

Create `tests/test_cv_strategy_pipeline_contract.py`:

```python
from datetime import datetime, timezone

from app.cv.composer import compose_cv
from app.cv.models import (
    CVPolicy,
    EvidenceCatalogSnapshot,
    MasterFact,
    MasterFactsSnapshot,
)
from app.cv.selector import select_evidence
from app.cv.strategy.builder import build_cv_strategy
from app.cv.strategy.policy import NarrativePolicy
from app.models.domain import Opportunity
from app.radar.models import (
    ConfidenceAssessment,
    DerivedValue,
    EligibilityResult,
    OpportunityEnrichment,
    RadarAssessment,
    Requirement,
)

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def _fact(fact_id: str, kind: str, value: str) -> MasterFact:
    method = "manual_confirmation" if kind in {"identity", "contact"} else "repository_evidence"
    return MasterFact(
        id=fact_id,
        kind=kind,
        value=value,
        track_ids=["tech"],
        verified=True,
        verification_method=method,
        verified_at=NOW,
        source_ref=None if method == "manual_confirmation" else f"https://example.test/{fact_id}",
    )


def _requirement(value: str, importance: str) -> Requirement:
    return Requirement(
        kind="skill",
        value=value,
        importance=importance,
        exactness="conceptual",
        provenance=DerivedValue[str](
            value=value,
            source_text=f"Required: {value}",
            source_field="description",
            extraction_method="explicit_rule",
            confidence=1.0,
        ),
    )


def _assessment(requirements: list[Requirement]) -> RadarAssessment:
    opportunity = Opportunity(
        id="opp-strategy-contract",
        source="synthetic",
        source_id="source-strategy-contract",
        source_url="https://example.test/jobs/data-analyst",
        company="Example Analytics",
        title="Data Analyst",
        description="Python SQL Power BI",
        discovered_at=NOW,
    )
    enrichment = OpportunityEnrichment(
        opportunity_id=opportunity.id,
        normalized_title=DerivedValue[str](
            value="Data Analyst",
            source_field="title",
            extraction_method="source_structured",
            confidence=1.0,
        ),
        requirements=requirements,
        extractor_version="test-v1",
        created_at=NOW,
    )
    return RadarAssessment(
        opportunity=opportunity,
        enrichment=enrichment,
        eligibility=EligibilityResult(eligible=True),
        best_career_track="tech",
        confidence_score=100.0,
        confidence_breakdown=ConfidenceAssessment(
            score=100.0,
            requirement_extraction_quality=100.0,
            skill_normalization_coverage=100.0,
            evidence_traceability=100.0,
            seniority_location_legal_clarity=100.0,
            source_freshness_completeness=100.0,
        ),
        priority_score=100.0,
        selected_intent="CAREER",
        scoring_version="test-v1",
        extractor_version="test-v1",
        alias_registry_version="test-v1",
    )


def _narrative_policy() -> NarrativePolicy:
    return NarrativePolicy(
        version="narrative-policy-v1",
        max_core_messages=3,
        positioning_message_importance=10.0,
        default_section_order=[
            "summary",
            "skills",
            "experience",
            "projects",
            "education",
            "languages",
            "links",
        ],
        requirement_importance_weights={
            "mandatory": 3.0,
            "preferred": 2.0,
            "unknown": 1.0,
        },
        support_level_weights={
            "EXACT_VERIFIED": 3.0,
            "APPROVED_ALIAS": 2.5,
            "TAXONOMY_RELATED": 1.0,
            "UNKNOWN": 0.0,
        },
        priority_requirement_bonus=1.0,
    )


def _build(facts: list[MasterFact], requirements: list[Requirement]):
    master = MasterFactsSnapshot(
        schema_version="v1",
        content_sha256="a" * 64,
        facts=facts,
    )
    catalog = EvidenceCatalogSnapshot(
        schema_version="v1",
        content_sha256="b" * 64,
        modules=[],
    )
    assessment = _assessment(requirements)
    cv_policy = CVPolicy(
        language="en",
        required_identity_kinds=["identity", "contact"],
        required_sections=["skills", "projects"],
    )
    selection = select_evidence(
        enrichment=assessment.enrichment,
        application_track_id="tech",
        master_facts=master,
        evidence_catalog=catalog,
        policy=cv_policy,
    )
    document = compose_cv(
        selection=selection,
        master_facts=master,
        evidence_catalog=catalog,
        policy=cv_policy,
        language="en",
    )
    return build_cv_strategy(
        assessment=assessment,
        selection=selection,
        document=document,
        policy=_narrative_policy(),
    )


def test_current_selector_and_composer_feed_deterministic_strategy() -> None:
    facts = [
        _fact("identity", "identity", "Alex Example"),
        _fact("contact", "contact", "alex@example.test"),
        _fact("role", "role", "Data & Automation Engineer"),
        _fact("python", "skill", "Python"),
        _fact("sql", "skill", "SQL"),
        _fact("project", "project", "Decision Support API"),
    ]
    requirements = [
        _requirement("Python", "mandatory"),
        _requirement("SQL", "preferred"),
        _requirement("Power BI", "mandatory"),
    ]

    first = _build(facts, requirements)
    second = _build(list(reversed(facts)), list(reversed(requirements)))

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.positioning == "Data & Automation Engineer"
    assert [message.message for message in first.core_messages] == [
        "Data & Automation Engineer",
        "Python",
        "SQL",
    ]
    assert first.explicit_gaps == ["Power BI"]
    assert {"role", "python"}.issubset(first.must_show_fact_ids)
    assert "sql" in first.supporting_fact_ids
```

- [ ] **Step 2: Run the pipeline contract test**

Run:

```bash
python -m pytest tests/test_cv_strategy_pipeline_contract.py -q
```

Expected: PASS once Tasks 1–3 are complete.

- [ ] **Step 3: Run all PR1-focused tests**

Run:

```bash
python -m pytest tests/test_cv_strategy_models.py tests/test_cv_strategy_policy.py tests/test_cv_strategy_scoring.py tests/test_cv_strategy_builder.py tests/test_cv_strategy_pipeline_contract.py -q
```

Expected: PASS with zero failures.

- [ ] **Step 4: Run existing CV regression tests that PR1 must not disturb**

Run:

```bash
python -m pytest tests/test_cv_selector.py tests/test_cv_composer.py tests/test_recruiter_policy.py tests/test_application_prepare_cli.py -q
```

Expected: PASS with zero failures. Any failure is a regression because PR1 is not allowed to change current preparation behavior.

- [ ] **Step 5: Run the full repository test suite**

Run:

```bash
python -m pytest -q
```

Expected: exit code 0, zero failed tests.

- [ ] **Step 6: Verify PR1 changed only strategy/config/tests/docs surfaces**

Run:

```bash
git diff --name-only HEAD~3..HEAD
```

Before the final Task 4 commit, inspect the complete branch diff against the implementation base instead if commit count differs:

```bash
git diff --name-only origin/main...HEAD
```

Expected production changes for PR1 are restricted to:

```text
app/cv/strategy/**
config/narrative_policy.yaml
```

plus strategy tests and approved docs. In particular, these MUST NOT appear:

```text
app/cv/service.py
app/cv/recruiter_composer.py
app/cv/renderers/**
app/application/prepare.py
```

- [ ] **Step 7: Commit Task 4**

```bash
git add tests/test_cv_strategy_pipeline_contract.py
git commit -m "test: cover CV strategy pipeline contract"
```

- [ ] **Step 8: Final PR1 verification after the commit**

Run fresh:

```bash
python -m pytest -q
```

Expected: exit code 0, zero failures.

Then run:

```bash
git status --short
```

Expected: no uncommitted implementation/test changes.

---

## PR1 Acceptance Checklist

The reviewer should reject PR1 unless every item is true:

- [ ] `CVStrategy` has a hard maximum of three core messages.
- [ ] Every core message references fact IDs present in one of the strategy fact buckets.
- [ ] Must-show, supporting, and optional fact buckets are disjoint.
- [ ] `StrategyTrackConfig` does not allow arbitrary candidate positioning text.
- [ ] Candidate positioning resolves only from an existing `headline/headline` claim with semantic provenance.
- [ ] A target vacancy named `Senior ...` does not promote candidate positioning to `Senior ...` unless that exact supported headline claim already exists and is explicitly selected.
- [ ] Unsupported mandatory requirements remain explicit gaps and never become core messages.
- [ ] Supported requirement ranking is deterministic and policy-versioned.
- [ ] Input ordering of facts/requirements does not change the final strategy model dump.
- [ ] Existing selector/composer can feed the builder directly.
- [ ] No production PDF path, recruiter compositor, renderer, CLI, or packet schema changes are included.
- [ ] No personal/private candidate configuration is committed.
- [ ] Full repository tests pass fresh after the final commit.

## Explicitly Deferred to Later Plans

These requirements are part of the approved architecture but intentionally not implemented in this PR1 plan:

- strategy-aware `RecruiterDocumentModel` composition (PR2);
- narrative coverage/off-strategy/identity scanability QA (PR3);
- full narrative/render policy split and page-count migration (PR4);
- layout profiles and layout selector (PR5);
- deterministic visual PDF QA (PR6);
- JSON Resume projection (PR7);
- optional human-first second renderer (PR8);
- ATS recoverability parser and round-trip comparison (PR9);
- `ApplicationPacket` strategy/QA fields and packet-hash migration (added when those stages become authoritative).

This scope boundary is deliberate: PR1 must create a useful, testable strategy API while leaving the currently working PDF preparation path unchanged.
