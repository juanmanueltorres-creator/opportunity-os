from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError
import yaml

from app.cv.hashing import canonical_sha256
from app.cv.models import (
    EvidenceCatalogSnapshot,
    EvidenceModule,
    MasterFact,
    MasterFactsSnapshot,
)


def _load_yaml_mapping(path: str | Path, label: str) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"Could not load {label}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a mapping")
    return payload


def _require_schema_version(payload: dict[str, Any], label: str) -> str:
    version = str(payload.get("schema_version", "")).strip()
    if not version:
        raise ValueError(f"{label} is missing schema_version")
    return version


def _require_unique_ids(items: list[Any], *, label: str) -> None:
    seen: set[str] = set()
    for item in items:
        if item.id in seen:
            raise ValueError(f"duplicate {label} id: {item.id}")
        seen.add(item.id)


def _validate_items(raw_items: Any, model: type[Any], *, label: str) -> list[Any]:
    if not isinstance(raw_items, list):
        raise ValueError(f"{label} must be a list")
    try:
        return [model.model_validate(item) for item in raw_items]
    except (ValidationError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {label}") from exc


def load_master_facts(path: str | Path) -> MasterFactsSnapshot:
    payload = _load_yaml_mapping(path, "master facts")
    schema_version = _require_schema_version(payload, "master facts")
    facts = _validate_items(payload.get("facts"), MasterFact, label="master facts")
    _require_unique_ids(facts, label="fact")
    ordered = sorted(facts, key=lambda fact: fact.id)
    content_sha256 = canonical_sha256(
        {
            "schema_version": schema_version,
            "facts": [fact.model_dump(mode="json") for fact in ordered],
        }
    )
    return MasterFactsSnapshot(
        schema_version=schema_version,
        content_sha256=content_sha256,
        facts=ordered,
    )


def load_evidence_catalog(path: str | Path) -> EvidenceCatalogSnapshot:
    payload = _load_yaml_mapping(path, "evidence catalog")
    schema_version = _require_schema_version(payload, "evidence catalog")
    modules = _validate_items(
        payload.get("modules"),
        EvidenceModule,
        label="evidence modules",
    )
    _require_unique_ids(modules, label="evidence module")
    ordered = sorted(modules, key=lambda module: module.id)
    content_sha256 = canonical_sha256(
        {
            "schema_version": schema_version,
            "modules": [module.model_dump(mode="json") for module in ordered],
        }
    )
    return EvidenceCatalogSnapshot(
        schema_version=schema_version,
        content_sha256=content_sha256,
        modules=ordered,
    )


def validate_catalog_against_facts(
    catalog: EvidenceCatalogSnapshot,
    facts: MasterFactsSnapshot,
) -> None:
    fact_by_id = {fact.id: fact for fact in facts.facts}
    for module in catalog.modules:
        referenced_ids = set(module.fact_ids)
        for claim in module.claims:
            referenced_ids.update(claim.fact_ids)

        missing = sorted(fact_id for fact_id in referenced_ids if fact_id not in fact_by_id)
        if missing:
            raise ValueError(
                "evidence catalog references missing fact: " + ", ".join(missing)
            )

        if module.verified:
            unverified = sorted(
                fact_id
                for fact_id in referenced_ids
                if not fact_by_id[fact_id].verified
            )
            if unverified:
                raise ValueError(
                    "verified evidence module depends on unverified fact: "
                    + ", ".join(unverified)
                )
