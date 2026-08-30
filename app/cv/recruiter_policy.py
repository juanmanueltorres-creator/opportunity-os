from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field, model_validator

from app.cv.models import StrictCVModel

RECRUITER_POLICY_VERSION = "recruiter-policy-v1"


class RecruiterSkillGroup(StrictCVModel):
    en: str = Field(min_length=1)
    es: str = Field(min_length=1)
    members: list[str] = Field(default_factory=list)

    @property
    def labels(self) -> dict[str, str]:
        return {"en": self.en, "es": self.es}


class RecruiterPolicy(StrictCVModel):
    version: str = Field(min_length=1)
    max_pages: int = Field(gt=0)
    min_body_font_pt: float = Field(ge=9.0)
    preferred_body_font_pt: float = Field(gt=0)
    max_projects: int = Field(ge=1, le=4)
    max_experience_entries: int = Field(ge=1, le=5)
    max_experience_bullets: int = Field(ge=0, le=1)
    max_skill_groups: int = Field(ge=1, le=4)
    max_skill_tokens: int = Field(ge=1, le=24)
    max_profile_claims: int = Field(ge=1, le=3)
    max_education_items: int = Field(ge=1, le=4)
    skill_groups: dict[str, RecruiterSkillGroup] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_one_page_contract(self) -> "RecruiterPolicy":
        if self.max_pages != 1:
            raise ValueError("max_pages must be exactly 1")
        if self.preferred_body_font_pt < self.min_body_font_pt:
            raise ValueError(
                "preferred_body_font_pt must be greater than or equal to min_body_font_pt"
            )
        if self.version != RECRUITER_POLICY_VERSION:
            raise ValueError(
                f"unsupported recruiter policy version: {self.version}"
            )
        return self


def load_recruiter_policy(path: str | Path) -> RecruiterPolicy:
    policy_path = Path(path)
    payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("recruiter policy root must be a mapping")
    return RecruiterPolicy.model_validate(payload)
