from datetime import datetime, timezone

from app.cv.composer import compose_cv
from app.cv.loaders import load_evidence_catalog, load_master_facts
from app.cv.models import (
    ClaimProvenance,
    CVClaim,
    CVDocumentModel,
    CVEntry,
    CVPolicy,
    EvidenceCatalogSnapshot,
    EvidenceModule,
    EvidenceSelection,
    MasterFact,
    MasterFactsSnapshot,
)
from app.cv.validator import validate_cv

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _fact(
    fact_id: str,
    kind: str,
    value: str,
    *,
    verified: bool = True,
    tracks: list[str] | None = None,
) -> MasterFact:
    method = "manual_confirmation" if kind in {"identity", "contact", "location", "summary_claim"} else "document_evidence"
    return MasterFact(
        id=fact_id,
        kind=kind,
        value=value,
        track_ids=tracks or ["tech"],
        verified=verified,
        verification_method=method if verified else None,
        verified_at=NOW if verified else None,
        source_ref=None if method == "manual_confirmation" or not verified else f"https://example.test/{fact_id}",
    )


def _selection(*, gaps: list[str] | None = None) -> EvidenceSelection:
    return EvidenceSelection(
        application_track_id="tech",
        selected_fact_ids=["name", "email", "employer", "title", "metric"],
        selected_evidence_ids=["module-tech"],
        unsupported_requirements=gaps or [],
    )


def _snapshots(*, metric_verified: bool = True) -> tuple[MasterFactsSnapshot, EvidenceCatalogSnapshot]:
    facts = MasterFactsSnapshot(
        schema_version="v1",
        content_sha256="a" * 64,
        facts=[
            _fact("name", "identity", "Alex Example"),
            _fact("email", "contact", "alex@example.test"),
            _fact("employer", "employment", "Example Labs"),
            _fact("title", "role", "Software Developer"),
            _fact("metric", "metric", "80%", verified=metric_verified),
        ],
    )
    catalog = EvidenceCatalogSnapshot(
        schema_version="v1",
        content_sha256="b" * 64,
        modules=[
            EvidenceModule(
                id="module-tech",
                track_ids=["tech"],
                label="Technical employment evidence",
                fact_ids=["employer", "title", "metric"],
                verified=True,
            )
        ],
    )
    return facts, catalog


def _document(
    *,
    employer_text: str = "Example Labs",
    title_text: str = "Software Developer",
    bullet_text: str = "Improved throughput by 80%.",
) -> CVDocumentModel:
    claims = [
        CVClaim(claim_id="employer", section="experience", kind="organization", text=employer_text),
        CVClaim(claim_id="title", section="experience", kind="title", text=title_text),
        CVClaim(claim_id="metric-bullet", section="experience", kind="bullet", text=bullet_text),
    ]
    return CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=claims,
        entries=[
            CVEntry(
                entry_id="section:experience",
                section="experience",
                claim_ids=[claim.claim_id for claim in claims],
            )
        ],
        provenance_map={
            "employer": ClaimProvenance(fact_ids=["employer"], evidence_ids=["module-tech"]),
            "title": ClaimProvenance(fact_ids=["title"], evidence_ids=["module-tech"]),
            "metric-bullet": ClaimProvenance(fact_ids=["employer", "metric"], evidence_ids=["module-tech"]),
        },
    )


def test_valid_document_passes_and_reports_gap_as_warning() -> None:
    facts, catalog = _snapshots()

    result = validate_cv(
        document=_document(),
        master_facts=facts,
        evidence_catalog=catalog,
        application_track_id="tech",
        selection=_selection(gaps=["Kubernetes"]),
    )

    assert result.valid
    assert result.errors == []
    assert {issue.code for issue in result.warnings} == {"unsupported_requirement"}
    assert set(result.validated_claim_ids) == {"employer", "title", "metric-bullet"}


def test_missing_referenced_fact_is_invalid() -> None:
    facts, catalog = _snapshots()
    document = _document()
    document.provenance_map["title"] = ClaimProvenance(
        fact_ids=["missing-fact"],
        evidence_ids=["module-tech"],
    )

    result = validate_cv(
        document=document,
        master_facts=facts,
        evidence_catalog=catalog,
        application_track_id="tech",
        selection=_selection(),
    )

    assert not result.valid
    assert any(issue.code == "missing_fact" for issue in result.errors)


def test_unverified_referenced_fact_is_invalid() -> None:
    facts, catalog = _snapshots(metric_verified=False)

    result = validate_cv(
        document=_document(),
        master_facts=facts,
        evidence_catalog=catalog,
        application_track_id="tech",
        selection=_selection(),
    )

    assert not result.valid
    assert any(issue.code == "unverified_fact" for issue in result.errors)


def test_cross_track_fact_is_invalid() -> None:
    facts, catalog = _snapshots()
    changed = []
    for fact in facts.facts:
        if fact.id == "title":
            changed.append(_fact("title", "role", "Software Developer", tracks=["hospitality"]))
        else:
            changed.append(fact)
    facts = MasterFactsSnapshot(
        schema_version="v1",
        content_sha256=facts.content_sha256,
        facts=changed,
    )

    result = validate_cv(
        document=_document(),
        master_facts=facts,
        evidence_catalog=catalog,
        application_track_id="tech",
        selection=_selection(),
    )

    assert not result.valid
    assert any(issue.code == "cross_track_fact" for issue in result.errors)


def test_changed_employer_is_invalid() -> None:
    facts, catalog = _snapshots()

    result = validate_cv(
        document=_document(employer_text="Famous Real Company"),
        master_facts=facts,
        evidence_catalog=catalog,
        application_track_id="tech",
        selection=_selection(),
    )

    assert not result.valid
    assert any(issue.code == "fact_text_mismatch" and issue.claim_id == "employer" for issue in result.errors)


def test_changed_title_is_invalid() -> None:
    facts, catalog = _snapshots()

    result = validate_cv(
        document=_document(title_text="Senior Engineering Director"),
        master_facts=facts,
        evidence_catalog=catalog,
        application_track_id="tech",
        selection=_selection(),
    )

    assert not result.valid
    assert any(issue.code == "fact_text_mismatch" and issue.claim_id == "title" for issue in result.errors)


def test_unsupported_numeric_metric_is_invalid() -> None:
    facts, catalog = _snapshots()

    result = validate_cv(
        document=_document(bullet_text="Improved throughput by 95%."),
        master_facts=facts,
        evidence_catalog=catalog,
        application_track_id="tech",
        selection=_selection(),
    )

    assert not result.valid
    assert any(issue.code == "unsupported_metric" for issue in result.errors)


def test_missing_evidence_module_is_invalid() -> None:
    facts, catalog = _snapshots()
    document = _document()
    document.provenance_map["employer"] = ClaimProvenance(
        fact_ids=["employer"],
        evidence_ids=["missing-module"],
    )

    result = validate_cv(
        document=document,
        master_facts=facts,
        evidence_catalog=catalog,
        application_track_id="tech",
        selection=_selection(),
    )

    assert not result.valid
    assert any(issue.code == "missing_evidence" for issue in result.errors)


def test_model_constructed_orphan_claim_is_caught_by_validator() -> None:
    facts, catalog = _snapshots()
    orphan = CVClaim(
        claim_id="orphan",
        section="summary",
        kind="summary",
        text="Expert in everything",
    )
    document = CVDocumentModel.model_construct(
        document_version="cvdoc-v1",
        language="en",
        claims=[orphan],
        entries=[],
        provenance_map={},
    )

    result = validate_cv(
        document=document,
        master_facts=facts,
        evidence_catalog=catalog,
        application_track_id="tech",
        selection=_selection(),
    )

    assert not result.valid
    assert any(issue.code == "missing_provenance" for issue in result.errors)


def test_composer_output_from_fictional_example_validates() -> None:
    facts = load_master_facts("config/master_facts.example.yaml")
    catalog = load_evidence_catalog("config/evidence_catalog.example.yaml")
    selection = EvidenceSelection(
        application_track_id="tech",
        selected_fact_ids=[
            "identity-name",
            "contact-email",
            "skill-python",
            "project-geospatial-api",
        ],
        selected_evidence_ids=["module-tech"],
    )
    document = compose_cv(
        selection=selection,
        master_facts=facts,
        evidence_catalog=catalog,
        policy=CVPolicy(language="en", required_sections=["projects"]),
    )

    result = validate_cv(
        document=document,
        master_facts=facts,
        evidence_catalog=catalog,
        application_track_id="tech",
        selection=selection,
    )

    assert result.valid
