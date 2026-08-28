from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path
from typing import Any

import yaml


class SkillMatchLevel(StrEnum):
    EXACT_VERIFIED = "EXACT_VERIFIED"
    APPROVED_ALIAS = "APPROVED_ALIAS"
    TAXONOMY_RELATED = "TAXONOMY_RELATED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ResolvedSkill:
    term: str
    level: SkillMatchLevel
    matched_skill: str | None
    multiplier: float
    taxonomy_source: str | None = None


@dataclass(frozen=True)
class AliasEntry:
    canonical_skill: str
    aliases: tuple[str, ...]
    relationship: str
    confidence: float
    approved_by: str


class AliasRegistry:
    def __init__(self, *, version: str, entries: tuple[AliasEntry, ...]) -> None:
        self.version = version
        self.entries = entries

    @classmethod
    def load(cls, path: str | Path) -> "AliasRegistry":
        source = Path(path)
        try:
            payload = yaml.safe_load(source.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ValueError("Could not load skill alias registry") from exc

        if not isinstance(payload, dict):
            raise ValueError("Skill alias registry must be a mapping")

        version = str(payload.get("version", "")).strip()
        raw_entries = payload.get("entries")
        if not version or not isinstance(raw_entries, list):
            raise ValueError("Skill alias registry is missing version or entries")

        entries: list[AliasEntry] = []
        for raw in raw_entries:
            if not isinstance(raw, dict):
                raise ValueError("Skill alias registry contains an invalid entry")
            canonical = str(raw.get("canonical_skill", "")).strip()
            aliases = raw.get("aliases")
            relationship = str(raw.get("relationship", "")).strip().casefold()
            approved_by = str(raw.get("approved_by", "")).strip()
            try:
                confidence = float(raw.get("confidence"))
            except (TypeError, ValueError) as exc:
                raise ValueError("Skill alias registry contains invalid confidence") from exc

            if (
                not canonical
                or not isinstance(aliases, list)
                or relationship not in {"equivalence", "related"}
                or not approved_by
                or not 0.0 <= confidence <= 1.0
            ):
                raise ValueError("Skill alias registry contains an invalid entry")

            clean_aliases = tuple(
                alias.strip() for alias in map(str, aliases) if alias.strip()
            )
            if not clean_aliases:
                raise ValueError("Skill alias registry entry must contain aliases")

            entries.append(
                AliasEntry(
                    canonical_skill=canonical,
                    aliases=clean_aliases,
                    relationship=relationship,
                    confidence=confidence,
                    approved_by=approved_by,
                )
            )

        return cls(version=version, entries=tuple(entries))

    def equivalence_canonical(self, term: str) -> str | None:
        normalized = _normalize(term)
        for entry in self.entries:
            if entry.relationship != "equivalence":
                continue
            family = {_normalize(entry.canonical_skill), *map(_normalize, entry.aliases)}
            if normalized in family:
                return entry.canonical_skill
        return None

    def related_match(self, term: str, candidate_skill: str) -> float | None:
        term_key = _normalize(term)
        candidate_key = _normalize(candidate_skill)
        for entry in self.entries:
            if entry.relationship != "related":
                continue
            canonical_key = _normalize(entry.canonical_skill)
            aliases = {_normalize(alias) for alias in entry.aliases}
            if (
                term_key in aliases
                and candidate_key == canonical_key
                or candidate_key in aliases
                and term_key == canonical_key
            ):
                return entry.confidence
        return None


@dataclass(frozen=True)
class TaxonomyRelation:
    term: str
    candidate_skill: str
    relationship: str
    confidence: float


class LocalTaxonomySnapshot:
    def __init__(
        self,
        *,
        version: str,
        relations: tuple[TaxonomyRelation, ...],
    ) -> None:
        self.version = version
        self.relations = relations

    @classmethod
    def load_optional(cls, path: str | Path | None) -> "LocalTaxonomySnapshot | None":
        if path is None:
            return None
        source = Path(path)
        if not source.exists():
            return None

        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Could not load local taxonomy snapshot") from exc

        if not isinstance(payload, dict):
            raise ValueError("Local taxonomy snapshot must be a mapping")
        version = str(payload.get("version", "")).strip()
        raw_relations = payload.get("relations")
        if not version or not isinstance(raw_relations, list):
            raise ValueError("Local taxonomy snapshot is missing version or relations")

        relations: list[TaxonomyRelation] = []
        for raw in raw_relations:
            relation = _parse_taxonomy_relation(raw)
            if relation is not None:
                relations.append(relation)
        return cls(version=version, relations=tuple(relations))

    def related_match(self, term: str, candidate_skill: str) -> float | None:
        term_key = _normalize(term)
        candidate_key = _normalize(candidate_skill)
        for relation in self.relations:
            if relation.relationship != "related":
                continue
            if (
                _normalize(relation.term) == term_key
                and _normalize(relation.candidate_skill) == candidate_key
                or _normalize(relation.term) == candidate_key
                and _normalize(relation.candidate_skill) == term_key
            ):
                return relation.confidence
        return None


class TaxonomyResolver:
    def __init__(
        self,
        *,
        alias_registry: AliasRegistry,
        taxonomy_path: str | Path | None = None,
    ) -> None:
        self.alias_registry = alias_registry
        self.taxonomy_snapshot = LocalTaxonomySnapshot.load_optional(taxonomy_path)

    def resolve_skill(self, term: str, candidate_skills: list[str]) -> ResolvedSkill:
        clean_term = " ".join(term.split())
        term_key = _normalize(clean_term)

        for candidate_skill in candidate_skills:
            if term_key == _normalize(candidate_skill):
                return ResolvedSkill(
                    term=clean_term,
                    level=SkillMatchLevel.EXACT_VERIFIED,
                    matched_skill=candidate_skill,
                    multiplier=1.0,
                )

        term_equivalence = self.alias_registry.equivalence_canonical(clean_term)
        if term_equivalence is not None:
            term_canonical_key = _normalize(term_equivalence)
            for candidate_skill in candidate_skills:
                candidate_equivalence = self.alias_registry.equivalence_canonical(candidate_skill)
                if (
                    candidate_equivalence is not None
                    and _normalize(candidate_equivalence) == term_canonical_key
                ):
                    return ResolvedSkill(
                        term=clean_term,
                        level=SkillMatchLevel.APPROVED_ALIAS,
                        matched_skill=candidate_skill,
                        multiplier=1.0,
                        taxonomy_source=f"aliases:{self.alias_registry.version}",
                    )

        for candidate_skill in candidate_skills:
            confidence = self.alias_registry.related_match(clean_term, candidate_skill)
            if confidence is not None:
                return ResolvedSkill(
                    term=clean_term,
                    level=SkillMatchLevel.TAXONOMY_RELATED,
                    matched_skill=candidate_skill,
                    multiplier=min(confidence, 0.70),
                    taxonomy_source=f"aliases:{self.alias_registry.version}",
                )

        if self.taxonomy_snapshot is not None:
            for candidate_skill in candidate_skills:
                confidence = self.taxonomy_snapshot.related_match(clean_term, candidate_skill)
                if confidence is not None:
                    return ResolvedSkill(
                        term=clean_term,
                        level=SkillMatchLevel.TAXONOMY_RELATED,
                        matched_skill=candidate_skill,
                        multiplier=min(confidence, 0.70),
                        taxonomy_source=self.taxonomy_snapshot.version,
                    )

        return ResolvedSkill(
            term=clean_term,
            level=SkillMatchLevel.UNKNOWN,
            matched_skill=None,
            multiplier=0.0,
        )


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def _parse_taxonomy_relation(raw: Any) -> TaxonomyRelation | None:
    if not isinstance(raw, dict):
        return None
    term = str(raw.get("term", "")).strip()
    candidate_skill = str(raw.get("candidate_skill", "")).strip()
    relationship = str(raw.get("relationship", "")).strip().casefold()
    try:
        confidence = float(raw.get("confidence"))
    except (TypeError, ValueError):
        return None
    if (
        not term
        or not candidate_skill
        or relationship != "related"
        or not 0.0 <= confidence <= 1.0
    ):
        return None
    return TaxonomyRelation(
        term=term,
        candidate_skill=candidate_skill,
        relationship=relationship,
        confidence=confidence,
    )
