from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from app.radar.models import OpportunityEnrichment

EnrichmentVersion = tuple[str, str, dict[str, str]]


class SQLiteEnrichmentRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS opportunity_enrichments (
                    opportunity_id TEXT NOT NULL,
                    extractor_version TEXT NOT NULL,
                    alias_registry_version TEXT NOT NULL,
                    taxonomy_versions_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (
                        opportunity_id,
                        extractor_version,
                        alias_registry_version,
                        taxonomy_versions_json
                    )
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_enrichments_opportunity_id
                ON opportunity_enrichments(opportunity_id)
                """
            )

    def save(
        self,
        enrichment: OpportunityEnrichment,
        *,
        extractor_version: str,
        alias_registry_version: str,
        taxonomy_versions: dict[str, str],
    ) -> None:
        extractor = extractor_version.strip()
        alias_version = alias_registry_version.strip()
        if not extractor or not alias_version:
            raise ValueError("enrichment versions must be non-empty")
        if extractor != enrichment.extractor_version:
            raise ValueError("extractor version does not match enrichment payload")
        if dict(taxonomy_versions) != dict(enrichment.taxonomy_versions):
            raise ValueError("taxonomy versions do not match enrichment payload")

        taxonomy_json = _canonical_taxonomy_versions(taxonomy_versions)
        payload_json = enrichment.model_dump_json()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO opportunity_enrichments (
                    opportunity_id,
                    extractor_version,
                    alias_registry_version,
                    taxonomy_versions_json,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (
                    opportunity_id,
                    extractor_version,
                    alias_registry_version,
                    taxonomy_versions_json
                ) DO UPDATE SET payload_json = excluded.payload_json
                """,
                (
                    enrichment.opportunity_id,
                    extractor,
                    alias_version,
                    taxonomy_json,
                    payload_json,
                ),
            )

    def get_current(
        self,
        opportunity_id: str,
        version_tuple: EnrichmentVersion,
    ) -> OpportunityEnrichment | None:
        extractor_version, alias_registry_version, taxonomy_versions = version_tuple
        taxonomy_json = _canonical_taxonomy_versions(taxonomy_versions)

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM opportunity_enrichments
                WHERE opportunity_id = ?
                  AND extractor_version = ?
                  AND alias_registry_version = ?
                  AND taxonomy_versions_json = ?
                LIMIT 1
                """,
                (
                    opportunity_id,
                    extractor_version.strip(),
                    alias_registry_version.strip(),
                    taxonomy_json,
                ),
            ).fetchone()

        if row is None:
            return None
        return OpportunityEnrichment.model_validate_json(row["payload_json"])


def _canonical_taxonomy_versions(taxonomy_versions: dict[str, str]) -> str:
    normalized = {str(key): str(value) for key, value in taxonomy_versions.items()}
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))
