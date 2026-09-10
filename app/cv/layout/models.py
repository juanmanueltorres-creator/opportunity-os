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
