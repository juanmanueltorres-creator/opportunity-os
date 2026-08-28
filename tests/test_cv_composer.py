from datetime import datetime, timezone

from app.cv.composer import compose_cv
from app.cv.loaders import load_evidence_catalog, load_master_facts
from app.cv.models import (
    ApprovedClaim,
    CVPolicy,
    EvidenceCatalogSnapshot,
    EvidenceModule,
    EvidenceSelection,
    MasterFact,
    MasterFactsSnapshot,
)

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _verified_fact(
    fact_id: str,
    kind: str,
    value: str,
    *,
    track_ids: list[str] | None = None,
    display_values: dict[str, str] | None = None,
) -> MasterFact:
    method = "manual_confirmation" if kind in {"identity", "contact", "location", "summary_claim"} else "repository_evidence"
    return MasterFact(
        id=fact_id,
        kind=kind,
        value=value,
        display_values=display_values or {},
        track_ids=track_ids or ["tech"],
        verified=True,
        verification_method=method,
        verified_at=NOW,
        source_ref=None if method == "manual_confirmation" else f"https://example.test/{fact_id}",
    )


def _example_snapshots() -> tuple[MasterFactsSnapshot, EvidenceCatalogSnapshot]:
    return (
        load_master_facts("config/master_facts.example.yaml"),
        load_evidence_catalog("config/evidence_catalog.example.yaml"),
    )


def _tech_selection(*, reverse_facts: bool = False) -> EvidenceSelection:
    fact_ids = [
        "identity-name",
        "contact-email",
        "skill-python",
        "project-geospatial-api",
    ]
    if reverse_facts:
        fact_ids.reverse()
    return EvidenceSelection(
        application_track_id="tech",
        selected_fact_ids=fact_ids,
        selected_evidence_ids=["module-tech"],
        requirement_support={},
        unsupported_requirements=["Kubernetes"],
        selection_explanations=["Selected verified tech evidence"],
    )


def _policy(language: str = "en") -> CVPolicy:
    return CVPolicy(
        language=language,
        required_identity_kinds=["identity", "contact"],
        required_sections=["projects"],
        section_order=["summary", "skills", "experience", "projects", "education", "languages", "links"],
    )


def test_every_visible_claim_has_fact_provenance() -> None:
    facts, catalog = _example_snapshots()

    document = compose_cv(
        selection=_tech_selection(),
        master_facts=facts,
        evidence_catalog=catalog,
        policy=_policy("en"),
    )

    assert document.claims
    assert all(claim.claim_id in document.provenance_map for claim in document.claims)
    assert all(
        document.provenance_map[claim.claim_id].fact_ids
        for claim in document.claims
    )


def test_composer_uses_only_approved_spanish_translation() -> None:
    facts, catalog = _example_snapshots()

    document = compose_cv(
        selection=_tech_selection(),
        master_facts=facts,
        evidence_catalog=catalog,
        policy=_policy("es"),
    )

    texts = [claim.text for claim in document.claims]
    assert "Desarrolló una API geoespacial verificable con Python." in texts
    assert "Built a verifiable geospatial API with Python." not in texts


def test_composer_does_not_promote_project_to_employment() -> None:
    facts, catalog = _example_snapshots()

    document = compose_cv(
        selection=_tech_selection(),
        master_facts=facts,
        evidence_catalog=catalog,
        policy=_policy("en"),
    )

    project_claims = [
        claim for claim in document.claims if claim.text == "Geospatial API"
    ]
    assert len(project_claims) == 1
    assert project_claims[0].section == "projects"
    assert project_claims[0].kind == "project"
    assert not any(
        claim.text == "Geospatial API" and claim.section == "experience"
        for claim in document.claims
    )


def test_unselected_hospitality_facts_do_not_appear_in_tech_document() -> None:
    facts, catalog = _example_snapshots()

    document = compose_cv(
        selection=_tech_selection(),
        master_facts=facts,
        evidence_catalog=catalog,
        policy=_policy("es"),
    )

    text = "\n".join(claim.text for claim in document.claims)
    assert "Example Bistro" not in text
    assert "Atención al cliente" not in text
    assert "operación gastronómica" not in text


def test_composition_is_deterministic_across_selected_fact_order() -> None:
    facts, catalog = _example_snapshots()

    first = compose_cv(
        selection=_tech_selection(),
        master_facts=facts,
        evidence_catalog=catalog,
        policy=_policy("en"),
    )
    second = compose_cv(
        selection=_tech_selection(reverse_facts=True),
        master_facts=facts,
        evidence_catalog=catalog,
        policy=_policy("en"),
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_missing_requested_translation_keeps_approved_canonical_wording() -> None:
    fact = _verified_fact("project-one", "project", "Example Project")
    facts = MasterFactsSnapshot(
        schema_version="v1",
        content_sha256="a" * 64,
        facts=[fact],
    )
    approved = ApprovedClaim(
        id="approved-en-only",
        section="projects",
        kind="bullet",
        text_by_language={"en": "Built an evidence-backed project."},
        fact_ids=[fact.id],
    )
    catalog = EvidenceCatalogSnapshot(
        schema_version="v1",
        content_sha256="b" * 64,
        modules=[
            EvidenceModule(
                id="module-one",
                track_ids=["tech"],
                label="Project evidence",
                fact_ids=[fact.id],
                claims=[approved],
                verified=True,
            )
        ],
    )
    selection = EvidenceSelection(
        application_track_id="tech",
        selected_fact_ids=[fact.id],
        selected_evidence_ids=["module-one"],
    )

    document = compose_cv(
        selection=selection,
        master_facts=facts,
        evidence_catalog=catalog,
        policy=_policy("es"),
    )

    assert "Built an evidence-backed project." in [
        claim.text for claim in document.claims
    ]


def test_metric_fact_is_not_auto_emitted_without_approved_claim() -> None:
    metric = _verified_fact("metric-one", "metric", "80%")
    project = _verified_fact("project-one", "project", "Example Project")
    facts = MasterFactsSnapshot(
        schema_version="v1",
        content_sha256="a" * 64,
        facts=[metric, project],
    )
    catalog = EvidenceCatalogSnapshot(
        schema_version="v1",
        content_sha256="b" * 64,
        modules=[],
    )
    selection = EvidenceSelection(
        application_track_id="tech",
        selected_fact_ids=[metric.id, project.id],
        selected_evidence_ids=[],
    )

    document = compose_cv(
        selection=selection,
        master_facts=facts,
        evidence_catalog=catalog,
        policy=_policy("en"),
    )

    assert "80%" not in [claim.text for claim in document.claims]
    assert "Example Project" in [claim.text for claim in document.claims]


def test_section_entries_follow_policy_order_after_header_claims() -> None:
    facts, catalog = _example_snapshots()

    document = compose_cv(
        selection=_tech_selection(),
        master_facts=facts,
        evidence_catalog=catalog,
        policy=_policy("en"),
    )

    sections = [entry.section for entry in document.entries]
    assert sections[0] == "headline"
    assert sections.index("skills") < sections.index("projects")
