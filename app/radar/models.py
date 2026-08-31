from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.domain import Opportunity, OpportunityAssessment, SearchIntent

T = TypeVar("T")

ExtractionMethod = Literal[
    "source_structured",
    "explicit_rule",
    "approved_alias",
    "taxonomy_snapshot",
    "manual_override",
]
RequirementKind = Literal[
    "skill",
    "experience",
    "education",
    "license",
    "work_authorization",
    "location",
    "schedule",
    "language",
    "other",
]
RequirementImportance = Literal["mandatory", "preferred", "unknown"]
RequirementExactness = Literal["conceptual", "exact_product", "declarative"]
ApplicationMode = Literal[
    "DIRECT_EMAIL",
    "AUTHORIZED_API",
    "FORM_ASSIST",
    "HOSTED_MANUAL",
    "RESTRICTED_MANUAL",
    "UNKNOWN",
]
ApplicationContactHintKind = Literal[
    "PUBLISHED_EMAIL",
    "OFFICIAL_HR_EMAIL",
    "RECRUITER",
    "MANUAL_CHANNEL",
]
SourceReliability = Literal[
    "DIRECT_ATS",
    "DIRECT_OFFICIAL",
    "AGGREGATOR",
    "MANUAL",
    "UNKNOWN",
]
FreshnessQuality = Literal[
    "DIRECT_TIMESTAMP",
    "DELAYED_TIMESTAMP",
    "DISCOVERED_AT_ONLY",
    "UNKNOWN",
]
DiscoveryOrigin = Literal["targeted", "adjacent", "wildcard"]
Tier = Literal["HIGH", "MEDIUM", "STRETCH", "DISCARD"]
DiagnosticStatus = Literal["ok", "warning", "error"]
OutputLanguage = Literal["es", "en"]
LanguageDecisionBasis = Literal[
    "explicit_override",
    "posting_language",
    "market_location",
    "international_remote_fallback",
]


class StrictRadarModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LanguageDecision(StrictRadarModel):
    language: OutputLanguage
    basis: LanguageDecisionBasis
    confidence: float = Field(ge=0, le=1)
    source_field: str = Field(min_length=1)
    source_text: str | None = None


def _require_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


class DerivedValue(StrictRadarModel, Generic[T]):
    value: T
    source_text: str | None = None
    source_field: str = Field(min_length=1)
    extraction_method: ExtractionMethod
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_provenance(self) -> "DerivedValue[T]":
        if self.extraction_method != "source_structured":
            if self.source_text is None or not self.source_text.strip():
                raise ValueError(
                    "source_text is required for non-structured derived values"
                )
        if isinstance(self.value, datetime):
            _require_aware_datetime(self.value)
        return self


class Requirement(StrictRadarModel):
    kind: RequirementKind
    value: str = Field(min_length=1)
    importance: RequirementImportance = "unknown"
    exactness: RequirementExactness = "conceptual"
    provenance: DerivedValue[str]

    @model_validator(mode="after")
    def provenance_must_support_value(self) -> "Requirement":
        if _normalized_text(self.value) != _normalized_text(self.provenance.value):
            raise ValueError("requirement value must match provenance value")
        return self


class ApplicationContactHint(StrictRadarModel):
    kind: ApplicationContactHintKind
    value: str = Field(min_length=1)
    source_url: str | None = None
    source_field: str = Field(min_length=1)
    source_text: str | None = None
    extraction_method: ExtractionMethod
    confidence: float = Field(ge=0, le=1)
    discovered_at: datetime

    @field_validator("discovered_at")
    @classmethod
    def discovered_at_must_be_aware(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)


class OpportunityEnrichment(StrictRadarModel):
    opportunity_id: str = Field(min_length=1)
    normalized_title: DerivedValue[str] | None = None
    role_family: DerivedValue[str] | None = None
    seniority: DerivedValue[str] | None = None
    employment_type: DerivedValue[str] | None = None
    language: DerivedValue[str] | None = None
    country: DerivedValue[str] | None = None
    region: DerivedValue[str] | None = None
    work_authorization_requirement: DerivedValue[str] | None = None
    visa_sponsorship: DerivedValue[bool] | None = None
    salary_min: DerivedValue[float] | None = None
    salary_max: DerivedValue[float] | None = None
    salary_currency: DerivedValue[str] | None = None
    requirements: list[Requirement] = Field(default_factory=list)
    application_contact_hints: list[ApplicationContactHint] = Field(default_factory=list)
    application_mode: ApplicationMode = "UNKNOWN"
    source_reliability: SourceReliability = "UNKNOWN"
    source_freshness_quality: FreshnessQuality = "UNKNOWN"
    channel_tags: list[str] = Field(default_factory=list)
    sector: DerivedValue[str] | None = None
    application_deadline: DerivedValue[datetime] | None = None
    work_schedule: DerivedValue[str] | None = None
    contract_duration: DerivedValue[str] | None = None
    application_friction: DerivedValue[str] | None = None
    source_category: DerivedValue[str] | None = None
    extractor_version: str = Field(min_length=1)
    taxonomy_versions: dict[str, str] = Field(default_factory=dict)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_aware(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)


class EligibilityResult(StrictRadarModel):
    eligible: bool
    hard_fail_reasons: list[str] = Field(default_factory=list)
    soft_risks: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


class IncomeAssessment(StrictRadarModel):
    track_id: str = Field(min_length=1)
    income_viability: float = Field(ge=0, le=100)
    capability_fit: float = Field(ge=0, le=100)
    logistics_fit: float = Field(ge=0, le=100)
    schedule_fit: float = Field(ge=0, le=100)
    entry_friction_fit: float = Field(ge=0, le=100)
    freshness_fit: float = Field(ge=0, le=100)
    matched_capabilities: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    unknown_barriers: list[str] = Field(default_factory=list)


class TrackCareerAssessment(StrictRadarModel):
    track_id: str = Field(min_length=1)
    assessment: OpportunityAssessment


class TrackAssessment(StrictRadarModel):
    track_id: str = Field(min_length=1)
    intents: list[SearchIntent] = Field(default_factory=list)
    career: OpportunityAssessment | None = None
    income: IncomeAssessment | None = None


class ConfidenceAssessment(StrictRadarModel):
    score: float = Field(ge=0, le=100)
    requirement_extraction_quality: float = Field(ge=0, le=100)
    skill_normalization_coverage: float = Field(ge=0, le=100)
    evidence_traceability: float = Field(ge=0, le=100)
    seniority_location_legal_clarity: float = Field(ge=0, le=100)
    source_freshness_completeness: float = Field(ge=0, le=100)


class RankingPenalty(StrictRadarModel):
    code: str = Field(min_length=1)
    value: float = Field(ge=0)
    explanation: str = Field(min_length=1)


class SourceDiagnostic(StrictRadarModel):
    source: str = Field(min_length=1)
    status: DiagnosticStatus
    code: str | None = None
    message: str | None = None


class RadarAssessment(StrictRadarModel):
    opportunity: Opportunity
    enrichment: OpportunityEnrichment
    eligibility: EligibilityResult
    match_assessment: OpportunityAssessment | None = None
    track_assessments: list[TrackAssessment] = Field(default_factory=list)
    best_career_track: str | None = None
    career_match: float | None = Field(default=None, ge=0, le=100)
    best_income_track: str | None = None
    income_viability: float | None = Field(default=None, ge=0, le=100)
    confidence_score: float = Field(ge=0, le=100)
    confidence_breakdown: ConfidenceAssessment
    tier: Tier | None = None
    intent_tiers: dict[str, Tier] = Field(default_factory=dict)
    channel_tags: list[str] = Field(default_factory=list)
    discovery_origin: DiscoveryOrigin = "targeted"
    priority_score: float = Field(ge=0)
    ranking_penalties: list[RankingPenalty] = Field(default_factory=list)
    selected_intent: SearchIntent | None = None
    scoring_version: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    alias_registry_version: str = Field(min_length=1)
    taxonomy_versions: dict[str, str] = Field(default_factory=dict)


class DailyRadarBatch(StrictRadarModel):
    batch_id: str = Field(min_length=1)
    generated_at: datetime
    policy: dict[str, Any] = Field(default_factory=dict)
    profile_fingerprint: str = Field(min_length=1)
    scoring_version: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    alias_registry_version: str = Field(min_length=1)
    taxonomy_versions: dict[str, str] = Field(default_factory=dict)
    items: list[RadarAssessment] = Field(default_factory=list)
    count: int = Field(ge=0)
    high_count: int = Field(ge=0)
    medium_count: int = Field(ge=0)
    intent_counts: dict[str, int] = Field(default_factory=dict)
    tier_counts: dict[str, int] = Field(default_factory=dict)
    source_diagnostics: list[SourceDiagnostic] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_aware(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)
