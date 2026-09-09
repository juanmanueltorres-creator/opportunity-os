from __future__ import annotations

from pydantic import Field, model_validator

from app.cv.models import CVSection, StrictCVModel

STRATEGY_VERSION = "cv-strategy-v1"


class CoreMessage(StrictCVModel):
    id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    fact_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    importance: float = Field(ge=0)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def references_must_be_unique(self) -> "CoreMessage":
        if len(self.fact_ids) != len(set(self.fact_ids)):
            raise ValueError("core message fact ids must be unique")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("core message evidence ids must be unique")
        return self


class StrategyTrackConfig(StrictCVModel):
    id: str = Field(min_length=1)
    positioning_claim_id: str | None = None
    priority_requirements: list[str] = Field(default_factory=list)
    preferred_section_order: list[CVSection] = Field(default_factory=list)
    preferred_layout_profile_id: str | None = None

    @model_validator(mode="after")
    def ordered_values_must_be_unique(self) -> "StrategyTrackConfig":
        if len(self.priority_requirements) != len(set(self.priority_requirements)):
            raise ValueError("priority requirements must be unique")
        if len(self.preferred_section_order) != len(set(self.preferred_section_order)):
            raise ValueError("preferred section order must be unique")
        return self


class CVStrategy(StrictCVModel):
    strategy_version: str = Field(min_length=1)
    application_track_id: str = Field(min_length=1)
    target_role: str = Field(min_length=1)
    target_company: str | None = None
    positioning: str = Field(min_length=1)
    recruiter_question: str = Field(min_length=1)
    core_messages: list[CoreMessage] = Field(min_length=1, max_length=3)
    must_show_fact_ids: list[str] = Field(default_factory=list)
    supporting_fact_ids: list[str] = Field(default_factory=list)
    optional_fact_ids: list[str] = Field(default_factory=list)
    explicit_gaps: list[str] = Field(default_factory=list)
    preferred_section_order: list[CVSection] = Field(min_length=1)
    preferred_layout_profile_id: str | None = None

    @model_validator(mode="after")
    def validate_strategy_references(self) -> "CVStrategy":
        if self.strategy_version != STRATEGY_VERSION:
            raise ValueError(f"unsupported strategy version: {self.strategy_version}")

        buckets = [
            self.must_show_fact_ids,
            self.supporting_fact_ids,
            self.optional_fact_ids,
        ]
        if any(len(bucket) != len(set(bucket)) for bucket in buckets):
            raise ValueError("strategy fact bucket ids must be unique")

        bucket_sets = [set(bucket) for bucket in buckets]
        if (
            bucket_sets[0] & bucket_sets[1]
            or bucket_sets[0] & bucket_sets[2]
            or bucket_sets[1] & bucket_sets[2]
        ):
            raise ValueError("strategy fact buckets must be disjoint")

        if len(self.preferred_section_order) != len(set(self.preferred_section_order)):
            raise ValueError("preferred section order must be unique")

        message_ids = [message.id for message in self.core_messages]
        if len(message_ids) != len(set(message_ids)):
            raise ValueError("core message ids must be unique")

        known_facts = set().union(*bucket_sets)
        message_facts = {
            fact_id
            for message in self.core_messages
            for fact_id in message.fact_ids
        }
        if not message_facts.issubset(known_facts):
            raise ValueError("core message facts must belong to strategy fact buckets")
        return self
