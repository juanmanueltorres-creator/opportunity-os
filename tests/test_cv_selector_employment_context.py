from datetime import datetime, timezone

from app.cv.models import (
    ApprovedClaim,
    CVPolicy,
    EvidenceCatalogSnapshot,
    EvidenceModule,
    MasterFact,
    MasterFactsSnapshot,
)
from app.cv.selector import select_evidence
from app.radar.models import OpportunityEnrichment

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def _fact(
    fact_id: str,
    value: str,
    *,
    kind: str,
    tracks: list[str],
) -> MasterFact:
    method = "manual_confirmation" if kind in {"identity", "contact"} else "document_evidence"
    return MasterFact(
        id=fact_id,
        kind=kind,
        value=value,
        track_ids=tracks,
        verified=True,
        verification_method=method,
        verified_at=NOW,
        source_ref=None if method == "manual_confirmation" else f"library:{fact_id}",
    )


def _empty_enrichment() -> OpportunityEnrichment:
    return OpportunityEnrichment(
        opportunity_id="opportunity-1",
        requirements=[],
        extractor_version="rules-v1",
        created_at=NOW,
    )


def _policy() -> CVPolicy:
    return CVPolicy(
        language="en",
        required_identity_kinds=["identity", "contact"],
        required_sections=[],
    )


def test_verified_employment_on_selected_track_is_structural_recruiter_context() -> None:
    master_facts = MasterFactsSnapshot(
        schema_version="v1",
        content_sha256="a" * 64,
        facts=[
            _fact("name", "Alex Example", kind="identity", tracks=["tech"]),
            _fact("email", "alex@example.test", kind="contact", tracks=["tech"]),
            _fact(
                "employment-tech",
                "Software Developer | Example Labs | 2024 - Present",
                kind="employment",
                tracks=["tech"],
            ),
            _fact(
                "employment-operations",
                "Operations Coordinator | Example Co | 2020 - 2024",
                kind="employment",
                tracks=["operations"],
            ),
        ],
    )
    evidence_catalog = EvidenceCatalogSnapshot(
        schema_version="v1",
        content_sha256="b" * 64,
        modules=[],
    )

    selection = select_evidence(
        enrichment=_empty_enrichment(),
        application_track_id="tech",
        master_facts=master_facts,
        evidence_catalog=evidence_catalog,
        policy=_policy(),
    )

    assert "employment-tech" in selection.selected_fact_ids
    assert "employment-operations" not in selection.selected_fact_ids


def test_verified_project_on_selected_track_is_available_as_recruiter_fallback() -> None:
    master_facts = MasterFactsSnapshot(
        schema_version="v1",
        content_sha256="a" * 64,
        facts=[
            _fact("name", "Alex Example", kind="identity", tracks=["tech"]),
            _fact("email", "alex@example.test", kind="contact", tracks=["tech"]),
            _fact(
                "project-tech",
                "Auditable Application System",
                kind="project",
                tracks=["tech"],
            ),
            _fact(
                "project-operations",
                "Warehouse Operations Dashboard",
                kind="project",
                tracks=["operations"],
            ),
        ],
    )
    evidence_catalog = EvidenceCatalogSnapshot(
        schema_version="v1",
        content_sha256="b" * 64,
        modules=[],
    )

    selection = select_evidence(
        enrichment=_empty_enrichment(),
        application_track_id="tech",
        master_facts=master_facts,
        evidence_catalog=evidence_catalog,
        policy=_policy(),
    )

    assert "project-tech" in selection.selected_fact_ids
    assert "project-operations" not in selection.selected_fact_ids


def test_module_documenting_structural_employment_is_selected_for_approved_bullet() -> None:
    master_facts = MasterFactsSnapshot(
        schema_version="v1",
        content_sha256="a" * 64,
        facts=[
            _fact("name", "Alex Example", kind="identity", tracks=["tech"]),
            _fact("email", "alex@example.test", kind="contact", tracks=["tech"]),
            _fact(
                "employment-tech",
                "Software Developer | Example Labs | 2024 - Present",
                kind="employment",
                tracks=["tech"],
            ),
            _fact("testing", "Testing", kind="skill", tracks=["tech"]),
        ],
    )
    module = EvidenceModule(
        id="module-tech-experience",
        track_ids=["tech"],
        label="Tech experience",
        fact_ids=["employment-tech", "testing"],
        claims=[
            ApprovedClaim(
                id="approved-employment-tech",
                section="experience",
                kind="bullet",
                text_by_language={"en": "Built and tested production software."},
                fact_ids=["employment-tech", "testing"],
                keywords=["software", "testing"],
            )
        ],
        keywords=["software", "testing"],
        verified=True,
    )
    evidence_catalog = EvidenceCatalogSnapshot(
        schema_version="v1",
        content_sha256="b" * 64,
        modules=[module],
    )

    selection = select_evidence(
        enrichment=_empty_enrichment(),
        application_track_id="tech",
        master_facts=master_facts,
        evidence_catalog=evidence_catalog,
        policy=_policy(),
    )

    assert selection.selected_evidence_ids == ["module-tech-experience"]
    assert "testing" in selection.selected_fact_ids
