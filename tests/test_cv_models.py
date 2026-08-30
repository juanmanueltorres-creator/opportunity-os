from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.cv.hashing import canonical_sha256
from app.cv.models import (
    ApplicationPacket,
    ApprovedClaim,
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
    PreparationResult,
    RenderedCVArtifact,
    RequirementSupport,
    ValidationIssue,
    ValidationResult,
)
from app.cv.recruiter_models import RecruiterDocumentModel, TechnologyGroup

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def verified_fact(*, fact_id: str = "skill-python", value: str = "Python") -> MasterFact:
    return MasterFact(
        id=fact_id,
        kind="skill",
        value=value,
        track_ids=["tech"],
        verified=True,
        verification_method="repository_evidence",
        verified_at=NOW,
        source_ref="https://example.test/evidence",
    )


def sample_document() -> CVDocumentModel:
    claims = [
        CVClaim(
            claim_id="claim-name",
            section="headline",
            kind="identity",
            text="Alex Example",
        ),
        CVClaim(
            claim_id="claim-role",
            section="headline",
            kind="headline",
            text="Software Developer",
        ),
        CVClaim(
            claim_id="claim-email",
            section="headline",
            kind="contact",
            text="alex@example.test",
        ),
        CVClaim(
            claim_id="claim-python",
            section="skills",
            kind="skill",
            text="Python",
        ),
    ]
    return CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=claims,
        entries=[
            CVEntry(
                entry_id="skills-main",
                section="skills",
                claim_ids=["claim-python"],
            )
        ],
        provenance_map={
            "claim-name": ClaimProvenance(fact_ids=["identity-name"]),
            "claim-role": ClaimProvenance(fact_ids=["role-primary"]),
            "claim-email": ClaimProvenance(fact_ids=["contact-email"]),
            "claim-python": ClaimProvenance(
                fact_ids=["skill-python"],
                evidence_ids=["module-tech"],
                approved_claim_id="approved-python",
            ),
        },
    )


def sample_recruiter_document() -> RecruiterDocumentModel:
    return RecruiterDocumentModel(
        source_cv_document_version="cvdoc-v1",
        language="en",
        identity_claim_id="claim-name",
        headline_claim_id="claim-role",
        contact_claim_ids=["claim-email"],
        technology_groups=[
            TechnologyGroup(
                label_id="software_data",
                skill_claim_ids=["claim-python"],
            )
        ],
    )


def sample_packet() -> ApplicationPacket:
    return ApplicationPacket(
        application_id="application-1",
        opportunity_id="opportunity-1",
        opportunity_snapshot_hash="a" * 64,
        radar_batch_id="batch-1",
        selected_intent="CAREER",
        application_track_id="tech",
        career_match=88.0,
        income_viability=70.0,
        confidence_score=90.0,
        scoring_version="v0.2a.1",
        extractor_version="rules-v1",
        alias_registry_version="aliases-v1",
        taxonomy_versions={"esco": "1.2.1"},
        master_facts_version="b" * 64,
        evidence_catalog_version="c" * 64,
        composer_version="composer-v1",
        cv_document_version="cvdoc-v1",
        recruiter_policy_version="recruiter-policy-v1",
        renderer_version="rendercv-typst-v1",
        selected_fact_ids=["skill-python"],
        selected_evidence_ids=["module-tech"],
        unresolved_gaps=["Kubernetes"],
        cv_document=sample_document(),
        recruiter_document=sample_recruiter_document(),
        cv_pdf_path="artifacts/applications/application-1/cv.pdf",
        cv_sha256="d" * 64,
        packet_sha256="e" * 64,
        created_at=NOW,
    )


def test_verified_fact_requires_verification_metadata() -> None:
    with pytest.raises(ValidationError):
        MasterFact(
            id="skill-postgis",
            kind="skill",
            value="PostGIS",
            track_ids=["tech"],
            verified=True,
        )


def test_manual_confirmation_allows_self_attested_contact_without_source_ref() -> None:
    fact = MasterFact(
        id="contact-email",
        kind="contact",
        value="alex@example.test",
        track_ids=["tech", "hospitality"],
        verified=True,
        verification_method="manual_confirmation",
        verified_at=NOW,
    )

    assert fact.source_ref is None


def test_evidence_backed_fact_requires_source_ref() -> None:
    with pytest.raises(ValidationError):
        MasterFact(
            id="skill-python",
            kind="skill",
            value="Python",
            track_ids=["tech"],
            verified=True,
            verification_method="repository_evidence",
            verified_at=NOW,
        )


def test_verified_fact_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        MasterFact(
            id="contact-city",
            kind="location",
            value="Cordoba, Argentina",
            track_ids=["tech"],
            verified=True,
            verification_method="manual_confirmation",
            verified_at=datetime(2026, 8, 28, 12, 0),
        )


def test_cv_models_forbid_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MasterFact(
            id="contact-name",
            kind="identity",
            value="Alex Example",
            verified=False,
            invented_field="not allowed",
        )


def test_snapshot_contracts_hold_canonical_content_fingerprints() -> None:
    fact = verified_fact()
    facts = MasterFactsSnapshot(
        schema_version="v1",
        content_sha256="a" * 64,
        facts=[fact],
    )
    claim = ApprovedClaim(
        id="approved-python",
        section="skills",
        kind="skill",
        text_by_language={"en": "Python", "es": "Python"},
        fact_ids=[fact.id],
        keywords=["python"],
    )
    module = EvidenceModule(
        id="module-tech",
        track_ids=["tech"],
        label="Technical evidence",
        fact_ids=[fact.id],
        claims=[claim],
        keywords=["python"],
        source_refs=["https://example.test/evidence"],
        verified=True,
    )
    catalog = EvidenceCatalogSnapshot(
        schema_version="v1",
        content_sha256="b" * 64,
        modules=[module],
    )

    assert facts.facts[0].id == "skill-python"
    assert catalog.modules[0].claims[0].id == "approved-python"


def test_selection_contract_records_support_and_unresolved_requirements() -> None:
    selection = EvidenceSelection(
        application_track_id="tech",
        selected_fact_ids=["skill-python"],
        selected_evidence_ids=["module-tech"],
        requirement_support={
            "Python": RequirementSupport(
                requirement="Python",
                support_level="EXACT_VERIFIED",
                fact_ids=["skill-python"],
                evidence_ids=["module-tech"],
                explanation="Verified exact skill",
            )
        },
        unsupported_requirements=["Kubernetes"],
        selection_explanations=["Python is directly verified"],
    )

    assert selection.requirement_support["Python"].support_level == "EXACT_VERIFIED"
    assert selection.unsupported_requirements == ["Kubernetes"]


def test_cv_document_requires_provenance_for_each_visible_claim() -> None:
    document = sample_document()
    assert document.provenance_map["claim-python"].fact_ids == ["skill-python"]

    with pytest.raises(ValidationError):
        CVDocumentModel(
            document_version="cvdoc-v1",
            language="en",
            claims=[
                CVClaim(
                    claim_id="orphan",
                    section="summary",
                    kind="summary",
                    text="Unprovenanced claim",
                )
            ],
            entries=[],
            provenance_map={},
        )


def test_validation_result_separates_errors_and_warnings() -> None:
    result = ValidationResult(
        valid=False,
        errors=[ValidationIssue(code="missing_provenance", message="Missing provenance")],
        warnings=[ValidationIssue(code="unsupported_requirement", message="Kubernetes")],
        validated_claim_ids=[],
    )
    assert result.errors[0].code == "missing_provenance"
    assert result.warnings[0].code == "unsupported_requirement"


def test_rendered_artifact_requires_sha256_and_renderer_version() -> None:
    artifact = RenderedCVArtifact(
        path="artifacts/applications/application-1/cv.pdf",
        sha256="f" * 64,
        renderer_version="renderer-v1",
    )
    assert artifact.sha256 == "f" * 64


def test_application_packet_is_prepared_only_and_requires_aware_timestamp() -> None:
    packet = sample_packet()
    assert packet.status == "PREPARED"
    assert packet.recruiter_document.document_version == "recruiter-doc-v1"

    payload = packet.model_dump()
    payload["created_at"] = datetime(2026, 8, 28, 12, 0)
    with pytest.raises(ValidationError):
        ApplicationPacket.model_validate(payload)


def test_prepared_result_requires_packet() -> None:
    with pytest.raises(ValidationError):
        PreparationResult(status="PREPARED")

    result = PreparationResult(status="PREPARED", packet=sample_packet())
    assert result.packet is not None


def test_blocked_preparation_result_cannot_contain_packet() -> None:
    with pytest.raises(ValidationError):
        PreparationResult(
            status="BLOCKED_VALIDATION",
            packet=sample_packet(),
            errors=[
                ValidationIssue(
                    code="claim_validation_failed",
                    message="blocked",
                )
            ],
        )


def test_cv_policy_is_explicit_about_language_sections_and_identity_requirements() -> None:
    policy = CVPolicy(
        language="en",
        required_identity_kinds=["identity", "contact"],
        required_sections=["skills"],
        section_order=["summary", "skills", "experience", "projects", "education"],
    )
    assert policy.language == "en"
    assert policy.required_sections == ["skills"]


def test_canonical_hash_ignores_mapping_key_order() -> None:
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})


def test_canonical_hash_preserves_visible_list_order() -> None:
    assert canonical_sha256({"bullets": ["A", "B"]}) != canonical_sha256(
        {"bullets": ["B", "A"]}
    )
