from pydantic import Field

from app.cv.models import StrictCVModel, ValidationIssue


class NarrativeQAResult(StrictCVModel):
    valid: bool
    core_message_coverage: dict[str, float] = Field(default_factory=dict)
    off_strategy_claim_ratio: float = Field(ge=0, le=1)
    competing_identity_count: int = Field(ge=0)
    scanability_score: float = Field(ge=0, le=1)
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)

    def model_post_init(self, __context: object) -> None:
        if any(value < 0 or value > 1 for value in self.core_message_coverage.values()):
            raise ValueError("core message coverage values must be between zero and one")
