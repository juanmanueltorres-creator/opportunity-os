from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.contributions.models import (
    ContributionOrigin,
    ExpectedEffort,
    NeedBasis,
    RiskLevel,
    TaskClaimState,
)


QUESTION_RESEARCH_CONTRACT = "question-research-handoff/v0.1"
RESEARCH_OPPORTUNITY_CONTRACT = "research-opportunity-handoff/v0.1"
PUBLIC_CONTRIBUTION_ROUTE = "PUBLIC_CONTRIBUTION_RESEARCH"
SOURCE_FRESHNESS = "AS_OF_EXPORT"


class StrictHandoffModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _aware(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


class QuestionHandoffSource(StrictHandoffModel):
    system: Literal["question-radar"]
    question_id: str = Field(min_length=1)
    question_profile_ref: str | None = Field(default=None, min_length=1)
    decision_id: str = Field(min_length=1)
    decision_fingerprint: str = Field(
        pattern=r"^sha256:[0-9a-fA-F]{64}$",
    )


class HandoffQuestion(StrictHandoffModel):
    raw: str = Field(min_length=1)
    canonical: str = Field(min_length=1)


class HandoffInvestigation(StrictHandoffModel):
    decision: Literal["DO_NOW", "RESEARCH"]
    rationale: str = Field(min_length=1)
    next_test: str = Field(min_length=1)


class PublicContributionRouting(StrictHandoffModel):
    kind: Literal["PUBLIC_CONTRIBUTION_RESEARCH"]
    destination: Literal["opportunity-os"]


class QuestionResearchHandoff(StrictHandoffModel):
    contract: Literal["question-research-handoff/v0.1"]
    handoff_id: str = Field(min_length=1)
    created_at: datetime
    source: QuestionHandoffSource
    question: HandoffQuestion
    investigation: HandoffInvestigation
    routing: PublicContributionRouting
    constraints: list[str]

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _aware(value, field="created_at")

    @field_validator("constraints")
    @classmethod
    def validate_constraints(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("constraints must contain only non-empty strings")
        return value

    @property
    def source_freshness(self) -> str:
        return SOURCE_FRESHNESS


class HandoffSource(StrictHandoffModel):
    system: Literal["andes-context-os", "question-radar"]
    source_question_ref: str = Field(min_length=1)
    research_intent_ref: str | None = Field(default=None, min_length=1)
    hypothesis_ref: str | None = Field(default=None, min_length=1)


class ActorNeedHypothesisCandidate(StrictHandoffModel):
    kind: Literal["ACTOR_NEED_HYPOTHESIS"]
    need_category: str = Field(min_length=1)
    statement: str = Field(min_length=1, max_length=1000)
    actor_refs: list[str]
    evidence_refs: list[str]
    assumptions: list[str]
    missing_context: list[str]
    research_status: Literal[
        "proposed",
        "researching",
        "supported",
        "contradicted",
        "discarded",
    ]

    @field_validator("actor_refs")
    @classmethod
    def validate_actor_refs(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("actor_refs must contain only non-empty strings")
        return value

    @model_validator(mode="after")
    def validate_evidence_backed_status(self) -> "ActorNeedHypothesisCandidate":
        if self.research_status in {"supported", "contradicted"} and not self.evidence_refs:
            raise ValueError(f"{self.research_status} requires evidence_refs")
        return self


class PublicContributionCandidate(StrictHandoffModel):
    kind: Literal["PUBLIC_CONTRIBUTION_CANDIDATE"]
    repository_full_name: str = Field(min_length=1)
    repository_url: str = Field(min_length=1)
    origin: ContributionOrigin
    need_basis: NeedBasis
    need_statement: str = Field(min_length=1, max_length=500)
    evidence_refs: list[str]
    task_ref: str | None = Field(default=None, min_length=1)
    bounded_task: str | None = Field(default=None, min_length=1, max_length=500)
    task_claim_state: TaskClaimState
    expected_effort: ExpectedEffort
    risk_level: RiskLevel


ResearchOpportunityCandidate = Annotated[
    ActorNeedHypothesisCandidate | PublicContributionCandidate,
    Field(discriminator="kind"),
]


class ResearchOpportunityHandoff(StrictHandoffModel):
    contract: Literal["research-opportunity-handoff/v0.1"]
    handoff_id: str = Field(min_length=1)
    created_at: datetime
    source: HandoffSource
    candidate: ResearchOpportunityCandidate

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _aware(value, field="created_at")

    @model_validator(mode="after")
    def validate_source_semantics(self) -> "ResearchOpportunityHandoff":
        if isinstance(self.candidate, ActorNeedHypothesisCandidate):
            if self.source.system != "andes-context-os":
                raise ValueError("ACTOR_NEED_HYPOTHESIS source.system must be andes-context-os")
            if self.source.research_intent_ref is None:
                raise ValueError("ACTOR_NEED_HYPOTHESIS requires research_intent_ref")
            if self.source.hypothesis_ref is None:
                raise ValueError("ACTOR_NEED_HYPOTHESIS requires hypothesis_ref")
        else:
            if self.source.system != "question-radar":
                raise ValueError("PUBLIC_CONTRIBUTION_CANDIDATE source.system must be question-radar")
            if self.source.research_intent_ref is not None:
                raise ValueError("PUBLIC_CONTRIBUTION_CANDIDATE research_intent_ref must be null")
            if self.source.hypothesis_ref is not None:
                raise ValueError("PUBLIC_CONTRIBUTION_CANDIDATE hypothesis_ref must be null")
        return self

    @property
    def source_freshness(self) -> str:
        return SOURCE_FRESHNESS
