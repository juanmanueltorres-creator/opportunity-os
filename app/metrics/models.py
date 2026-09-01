from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Coverage = Literal["COMPLETE", "PARTIAL", "UNKNOWN"]


class StrictMetricsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReportWindow(StrictMetricsModel):
    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def timestamps_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("report timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def end_must_not_precede_start(self) -> "ReportWindow":
        if self.end < self.start:
            raise ValueError("report window end must not precede start")
        return self


class CountMetric(StrictMetricsModel):
    name: str = Field(min_length=1)
    value: int | None = Field(default=None, ge=0)
    coverage: Coverage
    basis: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RatioMetric(StrictMetricsModel):
    name: str = Field(min_length=1)
    value: float | None = Field(default=None, ge=0, le=1)
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    coverage: Coverage
    basis: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ratio(self) -> "RatioMetric":
        if self.denominator == 0 and self.value is not None:
            raise ValueError("zero denominator requires unknown ratio value")
        if self.value is not None:
            expected = self.numerator / self.denominator
            if abs(self.value - expected) > 1e-9:
                raise ValueError("ratio value must match numerator/denominator")
        return self


class SearchHealthCounts(StrictMetricsModel):
    opportunities_observed: CountMetric
    opportunities_new: CountMetric
    qualified_high: CountMetric
    qualified_medium: CountMetric
    packets_prepared: CountMetric
    drafts_verified: CountMetric
    confirmed_sends: CountMetric
    replies_observed: CountMetric
    processes_opened: CountMetric
    processes_closed: CountMetric


class SearchHealthRatios(StrictMetricsModel):
    qualification_rate: RatioMetric
    draft_to_send_rate: RatioMetric
    send_to_reply_rate: RatioMetric
    reply_to_process_rate: RatioMetric


class CoverageSummary(StrictMetricsModel):
    radar: Coverage
    outreach: Coverage
    replies: Coverage
    processes: Coverage


class SourceSummary(StrictMetricsModel):
    name: str = Field(min_length=1)
    coverage: Coverage
    warnings: list[str] = Field(default_factory=list)


class SearchHealthReport(StrictMetricsModel):
    report_version: Literal["search-health-v1"] = "search-health-v1"
    generated_at: datetime
    window: ReportWindow
    counts: SearchHealthCounts
    ratios: SearchHealthRatios
    coverage: CoverageSummary
    warnings: list[str] = Field(default_factory=list)
    source_summary: list[SourceSummary] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value
