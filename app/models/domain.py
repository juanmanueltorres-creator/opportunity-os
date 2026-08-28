from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EvidenceType = Literal["project", "skill", "experience", "education", "document"]
Recommendation = Literal["apply", "stretch", "nurture", "discard"]
SearchIntent = Literal["CAREER", "INCOME_NOW"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceItem(StrictModel):
    label: str = Field(min_length=1)
    type: EvidenceType
    skills: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    url: str | None = None
    verified: bool


class CandidateTrack(StrictModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    intents: list[SearchIntent] = Field(min_length=1)
    roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    accepted_work_modes: list[str] = Field(default_factory=list)
    no_go_constraints: list[str] = Field(default_factory=list)


class CandidateProfile(StrictModel):
    name: str = Field(min_length=1)
    roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(min_length=1)
    domains: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    remote_preferences: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    tracks: list[CandidateTrack] = Field(default_factory=list)
    target_role_families: list[str] = Field(default_factory=list)
    verified_licenses: list[str] = Field(default_factory=list)
    work_authorizations: list[str] = Field(default_factory=list)
    no_go_constraints: list[str] = Field(default_factory=list)
    relocation_preferences: list[str] = Field(default_factory=list)


class Opportunity(StrictModel):
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    discovered_at: datetime
    status: str = "found"
    location: str | None = None
    remote_policy: str | None = None
    published_at: datetime | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    compensation: str | None = None

    @field_validator("discovered_at", "published_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)


class OpportunityAssessment(StrictModel):
    opportunity_id: str = Field(min_length=1)
    overall_score: float = Field(ge=0, le=100)
    mandatory_fit: float = Field(ge=0, le=100)
    domain_fit: float = Field(ge=0, le=100)
    evidence_fit: float = Field(ge=0, le=100)
    location_fit: float = Field(ge=0, le=100)
    freshness_fit: float = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    recommendation: Recommendation
    explanation: str
