from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

from app.cv.models import StrictCVModel

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
            raise ValueError(
                "preferred_pages must be less than or equal to max_pages"
            )
        if self.preferred_body_font_pt < self.min_body_font_pt:
            raise ValueError(
                "preferred_body_font_pt must be greater than or equal to min_body_font_pt"
            )
        return self


def load_render_policy(path: str | Path) -> RenderPolicy:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("render policy root must be a mapping")
    return RenderPolicy.model_validate(payload)
