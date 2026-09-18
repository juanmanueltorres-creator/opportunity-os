from __future__ import annotations

import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


SourceCategory = Literal[
    "DIRECT_ATS",
    "DIRECT_OFFICIAL",
    "JOB_BOARD",
    "NICHE_JOB_BOARD",
    "FREELANCE_MARKETPLACE",
    "DISCOVERY_INDEX",
    "COMMUNITY_SIGNAL",
]
SourceAuthority = Literal[
    "DIRECT_OFFICIAL",
    "DIRECT_PLATFORM",
    "DISCOVERY_ONLY",
]
SourceFreshnessMode = Literal[
    "DIRECT_TIMESTAMP",
    "DELAYED_TIMESTAMP",
    "DISCOVERED_AT_ONLY",
    "UNKNOWN",
]

_SOURCE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class StrictSourceCatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _normalized_reference(value: str) -> str:
    return value.strip().casefold()


def _normalized_host(source_url: str | None) -> str | None:
    if source_url is None or not source_url.strip():
        return None
    try:
        host = (urlparse(source_url.strip()).hostname or "").casefold()
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host or None


class SourceCatalogEntry(StrictSourceCatalogModel):
    key: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    category: SourceCategory
    authority: SourceAuthority
    freshness_mode: SourceFreshnessMode
    default_channel_tags: list[str] = Field(default_factory=list)
    publishable: bool
    verification_required: bool

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        normalized = value.strip()
        if not _SOURCE_KEY_RE.fullmatch(normalized):
            raise ValueError("source key must be a lowercase slug")
        return normalized

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            alias = _normalized_reference(value)
            if not alias:
                raise ValueError("source aliases must not be blank")
            if alias in seen:
                raise ValueError("source aliases must be unique")
            seen.add(alias)
            normalized.append(alias)
        return normalized

    @field_validator("default_channel_tags")
    @classmethod
    def validate_channel_tags(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            tag = _normalized_reference(value)
            if not tag:
                raise ValueError("channel tags must not be blank")
            if tag in seen:
                raise ValueError("channel tags must be unique")
            seen.add(tag)
            normalized.append(tag)
        return normalized

    @model_validator(mode="after")
    def validate_authority_boundary(self) -> "SourceCatalogEntry":
        if self.authority == "DISCOVERY_ONLY":
            if self.publishable:
                raise ValueError("discovery-only sources cannot be directly publishable")
            if not self.verification_required:
                raise ValueError("discovery-only sources require verification")
        return self

    def matches(self, source: str) -> bool:
        normalized = _normalized_reference(source)
        return normalized == self.key or normalized in self.aliases


class SourceCatalog(StrictSourceCatalogModel):
    version: str = Field(min_length=1)
    sources: list[SourceCatalogEntry] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def normalize_version(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("source catalog version must not be blank")
        return normalized

    @model_validator(mode="after")
    def reject_reference_collisions(self) -> "SourceCatalog":
        owners: dict[str, str] = {}
        for entry in self.sources:
            for reference in [entry.key, *entry.aliases]:
                normalized = _normalized_reference(reference)
                owner = owners.get(normalized)
                if owner is not None and owner != entry.key:
                    raise ValueError("source keys and aliases must be globally unique")
                owners[normalized] = entry.key
        return self

    def resolve(
        self,
        source: str,
        source_url: str | None = None,
    ) -> SourceCatalogEntry | None:
        references = [_normalized_reference(source)]
        host = _normalized_host(source_url)
        if host is not None:
            references.append(host)

        for reference in references:
            if not reference:
                continue
            for entry in self.sources:
                if entry.matches(reference):
                    return entry
        return None


def load_source_catalog(path: str | Path) -> SourceCatalog:
    source_path = Path(path)
    try:
        payload = yaml.safe_load(source_path.read_text(encoding="utf-8"))
        return SourceCatalog.model_validate(payload)
    except (OSError, yaml.YAMLError, ValidationError, TypeError) as exc:
        raise ValueError(f"Invalid source catalog: {source_path}") from exc
