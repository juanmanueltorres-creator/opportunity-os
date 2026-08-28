from datetime import datetime, timezone
from importlib import import_module

from app.models.domain import Opportunity
from app.radar.models import DerivedValue, OpportunityEnrichment

NOW = datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc)


def _modules():
    return (
        import_module("app.repositories.opportunities"),
        import_module("app.repositories.enrichments"),
    )


def _opportunity() -> Opportunity:
    return Opportunity(
        id="manual:1",
        source="manual",
        source_id="1",
        source_url="https://example.com/jobs/1",
        company="Example Co",
        title="Data Role",
        description="Build data systems",
        discovered_at=NOW,
    )


def _enrichment(*, extractor_version: str, title: str, taxonomy: dict[str, str]) -> OpportunityEnrichment:
    return OpportunityEnrichment(
        opportunity_id="manual:1",
        normalized_title=DerivedValue(
            value=title,
            source_field="title",
            extraction_method="source_structured",
            confidence=1.0,
        ),
        extractor_version=extractor_version,
        taxonomy_versions=taxonomy,
        created_at=NOW,
    )


def test_enrichment_versions_coexist_without_mutating_opportunity(tmp_path) -> None:
    opportunity_module, enrichment_module = _modules()
    db_path = tmp_path / "opportunities.db"

    opportunities = opportunity_module.SQLiteOpportunityRepository(db_path)
    opportunities.initialize()
    original, created = opportunities.upsert(_opportunity())
    assert created is True

    enrichments = enrichment_module.SQLiteEnrichmentRepository(db_path)
    enrichments.initialize()

    v1_taxonomy = {"esco": "1.2.1"}
    v2_taxonomy = {"esco": "1.2.1", "onet": "31.0"}
    v1 = _enrichment(
        extractor_version="rules-v1",
        title="Data Role",
        taxonomy=v1_taxonomy,
    )
    v2 = _enrichment(
        extractor_version="rules-v2",
        title="Data Operations Role",
        taxonomy=v2_taxonomy,
    )

    enrichments.save(
        v1,
        extractor_version="rules-v1",
        alias_registry_version="1",
        taxonomy_versions=v1_taxonomy,
    )
    enrichments.save(
        v2,
        extractor_version="rules-v2",
        alias_registry_version="2",
        taxonomy_versions=v2_taxonomy,
    )

    assert enrichments.get_current(
        original.id,
        ("rules-v1", "1", v1_taxonomy),
    ) == v1
    assert enrichments.get_current(
        original.id,
        ("rules-v2", "2", v2_taxonomy),
    ) == v2
    assert enrichments.get_current(
        original.id,
        ("rules-v2", "1", v2_taxonomy),
    ) is None

    assert opportunities.get(original.id) == original
    assert len(opportunities.list()) == 1


def test_repeated_save_of_same_version_is_idempotent(tmp_path) -> None:
    _, enrichment_module = _modules()
    repository = enrichment_module.SQLiteEnrichmentRepository(tmp_path / "opportunities.db")
    repository.initialize()

    taxonomy = {"esco": "1.2.1"}
    enrichment = _enrichment(
        extractor_version="rules-v1",
        title="Data Role",
        taxonomy=taxonomy,
    )
    for _ in range(2):
        repository.save(
            enrichment,
            extractor_version="rules-v1",
            alias_registry_version="1",
            taxonomy_versions=taxonomy,
        )

    assert repository.get_current(
        enrichment.opportunity_id,
        ("rules-v1", "1", taxonomy),
    ) == enrichment


def test_taxonomy_version_identity_is_canonical_across_mapping_order(tmp_path) -> None:
    _, enrichment_module = _modules()
    repository = enrichment_module.SQLiteEnrichmentRepository(tmp_path / "opportunities.db")
    repository.initialize()

    saved_taxonomy = {"esco": "1.2.1", "onet": "31.0"}
    lookup_taxonomy = {"onet": "31.0", "esco": "1.2.1"}
    enrichment = _enrichment(
        extractor_version="rules-v2",
        title="Data Operations Role",
        taxonomy=saved_taxonomy,
    )

    repository.save(
        enrichment,
        extractor_version="rules-v2",
        alias_registry_version="2",
        taxonomy_versions=saved_taxonomy,
    )

    assert repository.get_current(
        enrichment.opportunity_id,
        ("rules-v2", "2", lookup_taxonomy),
    ) == enrichment
