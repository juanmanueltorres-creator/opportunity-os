from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field, model_validator

from app.cv.layout.models import LayoutProfile
from app.cv.models import StrictCVModel

VISUAL_POLICY_VERSION = "visual-policy-v1"
_DENSITY_KEYS = {"comfortable", "balanced", "compact"}


class VisualPolicy(StrictCVModel):
    version: str = Field(min_length=1)
    min_substantive_claims_for_underfill: int = Field(ge=1)
    underfill_warning_bottom_ratio: float = Field(gt=0, lt=1)
    underfill_error_bottom_ratio: float = Field(gt=0, lt=1)
    isolated_bottom_start_ratio: float = Field(gt=0, lt=1)
    isolated_bottom_min_gap_pt: float = Field(gt=0)
    max_headline_lines: int = Field(ge=1)
    wall_text_warning_lines: int = Field(ge=1)
    wall_text_error_lines: int = Field(ge=1)
    wall_text_warning_chars: int = Field(ge=1)
    wall_text_error_chars: int = Field(ge=1)
    wall_text_max_list_marker_ratio: float = Field(ge=0, le=1)
    large_gap_warning_ratio: float = Field(gt=0, lt=1)
    large_gap_error_ratio: float = Field(gt=0, lt=1)
    density_warning_lines_per_page_inch: float = Field(gt=0)
    density_error_lines_per_page_inch: float = Field(gt=0)
    density_multipliers: dict[str, float]
    hierarchy_min_delta_pt: float = Field(ge=0)
    orphan_heading_bottom_ratio: float = Field(gt=0, lt=1)
    orphan_heading_max_following_lines: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_contract(self) -> "VisualPolicy":
        if self.version != VISUAL_POLICY_VERSION:
            raise ValueError(f"unsupported visual policy version: {self.version}")
        if not (
            self.underfill_error_bottom_ratio
            < self.underfill_warning_bottom_ratio
        ):
            raise ValueError("underfill error threshold must be below warning threshold")
        if not (self.large_gap_warning_ratio < self.large_gap_error_ratio):
            raise ValueError("large-gap warning threshold must be below error threshold")
        if not (self.wall_text_warning_lines < self.wall_text_error_lines):
            raise ValueError("wall-text warning line threshold must be below error threshold")
        if not (self.wall_text_warning_chars < self.wall_text_error_chars):
            raise ValueError("wall-text warning char threshold must be below error threshold")
        if not (
            self.density_warning_lines_per_page_inch
            < self.density_error_lines_per_page_inch
        ):
            raise ValueError("density warning threshold must be below error threshold")
        if set(self.density_multipliers) != _DENSITY_KEYS:
            raise ValueError("density multipliers must define exactly the public layout densities")
        if any(value <= 0 for value in self.density_multipliers.values()):
            raise ValueError("density multipliers must be positive")
        return self


def load_visual_policy(path: str | Path) -> VisualPolicy:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("visual policy root must be a mapping")
    return VisualPolicy.model_validate(payload)


def density_thresholds_for_profile(
    policy: VisualPolicy,
    profile: LayoutProfile,
) -> tuple[float, float]:
    multiplier = policy.density_multipliers[profile.density]
    return (
        policy.density_warning_lines_per_page_inch * multiplier,
        policy.density_error_lines_per_page_inch * multiplier,
    )
