from datetime import datetime, timezone

from app.cv.models import (
    CVPolicy,
    EvidenceCatalogSnapshot,
    EvidenceModule,
    MasterFact,
    MasterFactsSnapshot,
)
from app.cv.selector import select_evidence
from app.radar.models import DerivedValue, OpportunityEnrichment, Requirement
from app.radar.taxonomy import AliasEntry, AliasRegistry, TaxonomyResolver

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _fact(
    fact_id: str,
    value: str,
    *,
    kind: str = "skill",
    tracks: list[str] | None = None,
) -> MasterFact:
    method = "manual_confirmation" if kind in {"identity", "contact", "location"} else "repository_evidence"
    return MasterFact(
        id=fact_id,
        kind=kind,
        value=value,
        track_ids=tracks or ["tech"],
        verified=True,
        verification_method=method,
        verified_at=NOW,
        source_ref=None if method == "manual_confirmation" else f"https://example.test/{fact_id}",
    )


def _requirement(value: str, *, importance: str = "mandatory", exactness: str = "conceptual") -> Requirement:
    return Requirement(
        kind="skill",
        value=value,
        importance=importance,
        exactness=exactness,
        provenance=DerivedValue[str](
            value=value,
            source_text=f"Required: {value}",
            source_field="description",
            extraction_method="explicit_rule",
            confidence=0.95,
        ),
    )


def _enrichment(*requirements: Requirement) -> OpportunityEnrichment:
    return OpportunityEnrichment(
        opportunity_id="opportunity-1",
        requirements=list(requirements),
        extractor_version="rules-v1",
        created_at=NOW,
    )


def _snapshots(
    facts: list[MasterFact],
    modules: list[EvidenceModule] | None = None,
) -> tuple[MasterFactsSnapshot, EvidenceCatalogSnapshot]:
    return (
        MasterFactsSnapshot(
            schema_version="v1",
            content_sha256="a" * 64,
            facts=facts,
        ),
        EvidenceCatalogSnapshot(
            schema_version="v1",
            content_sha256="b" * 64,
            modules=modules or [],
        ),
    )


def _policy() -> CVPolicy:
    return CVPolicy(
        language="en",
        required_identity_kinds=["identity", "contact"],
        required_sections=[],
    )


def _resolver(*entries: AliasEntry) -> TaxonomyResolver:
    return TaxonomyResolver(
        alias_registry=AliasRegistry(version="test-v1", entries=tuple(entries))
    )


def test_exact_verified_requirement_support_outranks_related_support() -> None:
    facts, catalog = _snapshots(
        [
            _fact("name", "Alex Example", kind="identity"),
            _fact("email", "alex@example.test", kind="contact"),
            _fact("python-exact", "Python"),
            _fact("pydata-related", "PyData"),
        ]
    )
    resolver = _resolver(
        AliasEntry(
            canonical_skill="PyData",
            aliases=("Python",),
            relationship="related",
            confidence=0.7,
            approved_by="test",
        )
    )

    selection = select_evidence(
        enrichment=_enrichment(_requirement("Python")),
        application_track_id="tech",
        master_facts=facts,
        evidence_catalog=catalog,
        policy=_policy(),
        resolver=resolver,
    )

    support = selection.requirement_support["Python"]
    assert support.support_level == "EXACT_VERIFIED"
    assert support.fact_ids == ["python-exact"]
    assert "Python" not in selection.unsupported_requirements


def test_approved_alias_gets_full_support() -> None:
    facts, catalog = _snapshots(
        [
            _fact("name", "Alex Example", kind="identity"),
            _fact("email", "alex@example.test", kind="contact"),
            _fact("postgres", "PostgreSQL"),
        ]
    )
    resolver = _resolver(
        AliasEntry(
            canonical_skill="PostgreSQL",
            aliases=("Postgres",),
            relationship="equivalence",
            confidence=1.0,
            approved_by="test",
        )
    )

    selection = select_evidence(
        enrichment=_enrichment(_requirement("Postgres")),
        application_track_id="tech",
        master_facts=facts,
        evidence_catalog=catalog,
        policy=_policy(),
        resolver=resolver,
    )

    assert selection.requirement_support["Postgres"].support_level == "APPROVED_ALIAS"
    assert selection.requirement_support["Postgres"].fact_ids == ["postgres"]


def test_exact_product_remains_gap_when_only_related_evidence_exists() -> None:
    facts, catalog = _snapshots(
        [
            _fact("name", "Alex Example", kind="identity"),
            _fact("email", "alex@example.test", kind="contact"),
            _fact("spatial-db", "spatial database"),
        ]
    )
    resolver = _resolver(
        AliasEntry(
            canonical_skill="PostGIS",
            aliases=("spatial database",),
            relationship="related",
            confidence=0.7,
            approved_by="test",
        )
    )

    selection = select_evidence(
        enrichment=_enrichment(_requirement("PostGIS", exactness="exact_product")),
        application_track_id="tech",
        master_facts=facts,
        evidence_catalog=catalog,
        policy=_policy(),
        resolver=resolver,
    )

    assert selection.requirement_support["PostGIS"].support_level == "TAXONOMY_RELATED"
    assert "PostGIS" in selection.unsupported_requirements


def test_unsupported_mandatory_requirement_remains_gap() -> None:
    facts, catalog = _snapshots(
        [
            _fact("name", "Alex Example", kind="identity"),
            _fact("email", "alex@example.test", kind="contact"),
            _fact("python", "Python"),
        ]
    )

    selection = select_evidence(
        enrichment=_enrichment(_requirement("Kubernetes")),
        application_track_id="tech",
        master_facts=facts,
        evidence_catalog=catalog,
        policy=_policy(),
    )

    assert selection.requirement_support["Kubernetes"].support_level == "UNKNOWN"
    assert selection.unsupported_requirements == ["Kubernetes"]


def test_selector_never_crosses_track_boundary() -> None:
    facts, catalog = _snapshots(
        [
            _fact("name", "Alex Example", kind="identity"),
            _fact("email", "alex@example.test", kind="contact"),
            _fact("hospitality-service", "Customer service", tracks=["hospitality"]),
        ],
        [
            EvidenceModule(
                id="hospitality-module",
                track_ids=["hospitality"],
                label="Hospitality service",
                fact_ids=["hospitality-service"],
                keywords=["customer service"],
                verified=True,
            )
        ],
    )

    selection = select_evidence(
        enrichment=_enrichment(_requirement("Customer service")),
        application_track_id="tech",
        master_facts=facts,
        evidence_catalog=catalog,
        policy=_policy(),
    )

    assert "hospitality-service" not in selection.selected_fact_ids
    assert "hospitality-module" not in selection.selected_evidence_ids
    assert "Customer service" in selection.unsupported_requirements


def test_relevant_module_brings_its_verified_facts_into_selection() -> None:
    facts, catalog = _snapshots(
        [
            _fact("name", "Alex Example", kind="identity"),
            _fact("email", "alex@example.test", kind="contact"),
            _fact("python", "Python"),
            _fact("project", "Geospatial API", kind="project"),
        ],
        [
            EvidenceModule(
                id="module-api",
                track_ids=["tech"],
                label="API project",
                fact_ids=["python", "project"],
                keywords=["python", "api"],
                verified=True,
            )
        ],
    )

    selection = select_evidence(
        enrichment=_enrichment(_requirement("Python")),
        application_track_id="tech",
        master_facts=facts,
        evidence_catalog=catalog,
        policy=_policy(),
    )

    assert selection.selected_evidence_ids == ["module-api"]
    assert {"name", "email", "python", "project"}.issubset(selection.selected_fact_ids)


def test_selection_is_deterministic_across_input_order() -> None:
    base_facts = [
        _fact("name", "Alex Example", kind="identity"),
        _fact("email", "alex@example.test", kind="contact"),
        _fact("python", "Python"),
        _fact("project", "Geospatial API", kind="project"),
    ]
    module = EvidenceModule(
        id="module-api",
        track_ids=["tech"],
        label="API project",
        fact_ids=["project", "python"],
        keywords=["api", "python"],
        verified=True,
    )
    facts_a, catalog_a = _snapshots(base_facts, [module])
    facts_b, catalog_b = _snapshots(list(reversed(base_facts)), [module])

    kwargs = {
        "enrichment": _enrichment(_requirement("Python")),
        "application_track_id": "tech",
        "policy": _policy(),
    }
    first = select_evidence(
        master_facts=facts_a,
        evidence_catalog=catalog_a,
        **kwargs,
    )
    second = select_evidence(
        master_facts=facts_b,
        evidence_catalog=catalog_b,
        **kwargs,
    )

    assert first.selected_fact_ids == second.selected_fact_ids
    assert first.selected_evidence_ids == second.selected_evidence_ids
