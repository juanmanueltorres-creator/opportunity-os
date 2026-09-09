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
