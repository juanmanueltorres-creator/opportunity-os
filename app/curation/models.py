from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.radar.models import StrictRadarModel


PublicationChannel = Literal["WHATSAPP", "MANUAL_OTHER"]
PublicationPreviewStatus = Literal["READY", "BLOCKED"]


class CurationRunRecord(StrictRadarModel):
    run_id: str = Field(min_length=1)
    generated_at: datetime
    recorded_at: datetime
    payload_sha256: str = Field(min_length=64, max_length=64)
    digest_id: str = Field(min_length=1)
    publishable_opportunity_ids: list[str] = Field(default_factory=list)
    review_opportunity_ids: list[str] = Field(default_factory=list)
    held_displayed_opportunity_ids: list[str] = Field(default_factory=list)

    @field_validator("generated_at", "recorded_at")
    @classmethod
    def datetimes_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)


class CurationRunRecordResult(StrictRadarModel):
    status: Literal["NEW", "IDENTICAL", "BLOCKED", "CONFLICT"]
    record: CurationRunRecord | None = None
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_shape(self) -> "CurationRunRecordResult":
        if self.status in {"NEW", "IDENTICAL"}:
            if self.record is None or self.errors:
                raise ValueError("successful run record result requires record")
        else:
            if self.record is not None or not self.errors:
                raise ValueError("blocked/conflict result requires errors only")
        return self


class PublicationCheckpointEvidence(StrictRadarModel):
    run_id: str = Field(min_length=1)
    digest_id: str = Field(min_length=1)
    opportunity_ids: list[str] = Field(min_length=1, max_length=100)
    channel: PublicationChannel

    @field_validator("opportunity_ids")
    @classmethod
    def opportunity_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("opportunity_ids must not contain blank values")
        if len(normalized) != len(set(normalized)):
            raise ValueError("opportunity_ids must be unique")
        return normalized


class PublicationCheckpointPreview(StrictRadarModel):
    status: PublicationPreviewStatus
    preview_sha256: str = Field(min_length=64, max_length=64)
    evidence: PublicationCheckpointEvidence
    run_payload_sha256: str | None = None
    eligible_opportunity_ids: list[str] = Field(default_factory=list)
    already_published_opportunity_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    publication_count_before: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_shape(self) -> "PublicationCheckpointPreview":
        if self.status == "READY":
            if self.errors:
                raise ValueError("ready preview cannot contain errors")
            if not self.eligible_opportunity_ids:
                raise ValueError("ready preview requires eligible opportunities")
            if self.run_payload_sha256 is None:
                raise ValueError("ready preview requires run payload hash")
        elif not self.errors:
            raise ValueError("blocked preview requires errors")
        return self


class PublicationCheckpointConfirmRequest(StrictRadarModel):
    preview: PublicationCheckpointPreview
    confirmed_by: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9._:@-]+$",
    )
    confirmed_at: datetime
    note: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("confirmed_at")
    @classmethod
    def confirmed_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("confirmed_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("note must not be blank")
        return normalized


class PublicationCheckpoint(StrictRadarModel):
    checkpoint_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    digest_id: str = Field(min_length=1)
    opportunity_ids: list[str] = Field(min_length=1)
    channel: PublicationChannel
    confirmed_by: str = Field(min_length=1)
    confirmed_at: datetime
    note: str | None = None
    preview_sha256: str = Field(min_length=64, max_length=64)

    @field_validator("confirmed_at")
    @classmethod
    def confirmed_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("confirmed_at must be timezone-aware")
        return value.astimezone(timezone.utc)


class PublicationConfirmResult(StrictRadarModel):
    status: Literal["RECORDED", "ALREADY_RECORDED", "BLOCKED"]
    checkpoint: PublicationCheckpoint | None = None
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_shape(self) -> "PublicationConfirmResult":
        if self.status in {"RECORDED", "ALREADY_RECORDED"}:
            if self.checkpoint is None or self.errors:
                raise ValueError("recorded result requires checkpoint only")
        else:
            if self.checkpoint is not None or not self.errors:
                raise ValueError("blocked result requires errors only")
        return self


class CurationRunHistoryItem(StrictRadarModel):
    run_id: str = Field(min_length=1)
    generated_at: datetime
    recorded_at: datetime
    source_count: int = Field(ge=0)
    source_ok_count: int = Field(ge=0)
    source_error_count: int = Field(ge=0)
    failed_sources: list[str] = Field(default_factory=list)
    fetched_opportunity_count: int = Field(ge=0)
    new_opportunity_count: int = Field(ge=0)
    existing_opportunity_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    publishable_count: int = Field(ge=0)
    held_count: int = Field(ge=0)
    review_opportunity_ids: list[str] = Field(default_factory=list)
    publishable_opportunity_ids: list[str] = Field(default_factory=list)
    held_displayed_opportunity_ids: list[str] = Field(default_factory=list)
    publication_checkpoint_count: int = Field(ge=0)
    published_opportunity_ids: list[str] = Field(default_factory=list)
    publication_channels: list[PublicationChannel] = Field(default_factory=list)
    latest_published_at: datetime | None = None
    partial_source_failure: bool

    @field_validator("generated_at", "recorded_at", "latest_published_at")
    @classmethod
    def history_datetimes_must_be_aware(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)


class CurationRunHistory(StrictRadarModel):
    limit: int = Field(ge=1, le=100)
    count: int = Field(ge=0)
    items: list[CurationRunHistoryItem] = Field(default_factory=list)
    external_actions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_history_shape(self) -> "CurationRunHistory":
        if self.count != len(self.items):
            raise ValueError("history count must match items")
        if self.external_actions:
            raise ValueError("history cannot contain external actions")
        return self
