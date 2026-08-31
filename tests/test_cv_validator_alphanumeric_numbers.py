from datetime import datetime, timezone

from app.cv.models import (
    ClaimProvenance,
    CVClaim,
    CVDocumentModel,
    CVEntry,
    EvidenceCatalogSnapshot,
    EvidenceModule,
    EvidenceSelection,
    MasterFact,
    MasterFactsSnapshot,
)
from app.cv.validator import validate_cv


NOW = datetime(2026, 8, 31, 2, 55, tzinfo=timezone.utc)


def test_alphanumeric_3d_token_is_not_treated_as_numeric_metric() -> None:
    fact = MasterFact(
        id="skill-cesium",
        kind="skill",
        value="CesiumJS",
        track_ids=["tech"],
        verified=True,
        verification_method="repository_evidence",
        verified_at=NOW,
        source_ref="https://example.test/cesium",
    )
    facts = MasterFactsSnapshot(
        schema_version="v1",
        content_sha256="a" * 64,
        facts=[fact],
    )
    module = EvidenceModule(
        id="module-tech",
        track_ids=["tech"],
        label="Cesium project evidence",
        fact_ids=[fact.id],
        verified=True,
    )
    catalog = EvidenceCatalogSnapshot(
        schema_version="v1",
        content_sha256="b" * 64,
        modules=[module],
    )
    selection = EvidenceSelection(
        application_track_id="tech",
        selected_fact_ids=[fact.id],
        selected_evidence_ids=[module.id],
    )
    claim = CVClaim(
        claim_id="cesium-3d",
        section="projects",
        kind="bullet",
        text="Built Cesium 3D views for geospatial decision support.",
    )
    document = CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=[claim],
        entries=[
            CVEntry(
                entry_id="section:projects",
                section="projects",
                claim_ids=[claim.claim_id],
            )
        ],
        provenance_map={
            claim.claim_id: ClaimProvenance(
                fact_ids=[fact.id],
                evidence_ids=[module.id],
            )
        },
    )

    result = validate_cv(
        document=document,
        master_facts=facts,
        evidence_catalog=catalog,
        application_track_id="tech",
        selection=selection,
    )

    assert result.valid
    assert not any(issue.code == "unsupported_metric" for issue in result.errors)
