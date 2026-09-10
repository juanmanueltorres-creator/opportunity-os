from __future__ import annotations

from pydantic import Field, model_validator

from app.cv.models import StrictCVModel, ValidationIssue


class VisualMetrics(StrictCVModel):
    page_count: int = Field(ge=0)
    content_bottom_ratio: float | None = Field(default=None, ge=0, le=1)
    largest_internal_gap_ratio: float | None = Field(default=None, ge=0, le=1)
    nonempty_line_count: int = Field(ge=0)
    lines_per_page_inch: float = Field(ge=0)
    max_text_block_lines: int = Field(ge=0)
    max_text_block_chars: int = Field(ge=0)
    headline_line_count: int = Field(ge=0)
    body_font_size: float = Field(gt=0)
    observed_font_size_levels: list[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_font_levels(self) -> "VisualMetrics":
        if any(value <= 0 for value in self.observed_font_size_levels):
            raise ValueError("observed font sizes must be positive")
        if self.observed_font_size_levels != sorted(set(self.observed_font_size_levels)):
            raise ValueError("observed font sizes must be sorted and unique")
        return self


class VisualQAResult(StrictCVModel):
    valid: bool
    metrics: VisualMetrics
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_matches_errors(self) -> "VisualQAResult":
        if self.valid != (len(self.errors) == 0):
            raise ValueError("visual QA valid flag must match error presence")
        return self
