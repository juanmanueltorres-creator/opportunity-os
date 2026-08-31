from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

from app.cv.hashing import canonical_sha256
from app.cv.models import (
    ApplicationPacket,
    ClaimProvenance,
    CVClaim,
    CVDocumentModel,
)
from app.cv.recruiter_models import RecruiterDocumentModel, TechnologyGroup
from app.models.domain import Opportunity
from app.outreach.models import (
    ContactResolution,
    OutreachPolicy,
    StretchPromotion,
)
from app.outreach.preparation import OutreachPreparationService
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.models import (
    ConfidenceAssessment,
    EligibilityResult,
    LanguageDecision,
    RadarAssessment,
)

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _opportunity() -> Opportunity:
    return Opportunity(
        id="opp-1",
        source="manual",
        source_id="fixture-1",
        source_url="https://example.test/jobs/1",
        company="Example Labs",
        title="GIS Developer",
        description="Send your CV to careers@example.test. Required: PostGIS and PySpark.",
        discovered_at=NOW,
        published_at=NOW,
        required_skills=["PostGIS", "PySpark"],
    )


def _assessment(*, tier: str = "HIGH", eligible: bool = True) -> RadarAssessment:
    opportunity = _opportunity()
    enrichment = RuleBasedRequirementExtractor().extract(opportunity)
    confidence = ConfidenceAssessment(
        score=90,
        requirement_extraction_quality=90,
        skill_normalization_coverage=90,
        evidence_traceability=90,
        seniority_location_legal_clarity=90,
        source_freshness_completeness=90,
    )
    return RadarAssessment(
        opportunity=opportunity,
        enrichment=enrichment,
        eligibility=EligibilityResult(eligible=eligible),
        best_career_track="tech",
        career_match=88,
        best_income_track="tech",
        income_viability=78,
        confidence_score=90,
        confidence_breakdown=confidence,
        tier=tier,
        intent_tiers={"CAREER": tier},
        priority_score=88,
        selected_intent="CAREER",
        scoring_version="v0.2a1",
        extractor_version="rules-v1",
        alias_registry_version="aliases-v1",
        taxonomy_versions={},
    )


def _document() -> CVDocumentModel:
    claims = [
        CVClaim(
            claim_id="identity-name",
            section="headline",
            kind="identity",
            text="Alex Example",
        ),
        CVClaim(
            claim_id="skill-postgis",
            section="skills",
            kind="skill",
            text="PostGIS",
        ),
        CVClaim(
            claim_id="project-geo",
            section="projects",
            kind="project",
            text="Built a geospatial platform with validated spatial workflows.",
        ),
    ]
    return CVDocumentModel(
        document_version="cv-doc-v1",
        language="en",
        claims=claims,
        entries=[],
        provenance_map={
            "identity-name": ClaimProvenance(fact_ids=["fact-name"]),
            "skill-postgis": ClaimProvenance(
                fact_ids=["fact-postgis"], evidence_ids=["evidence-geo"]
            ),
            "project-geo": ClaimProvenance(
                fact_ids=["fact-project"], evidence_ids=["evidence-geo"]
            ),
        },
    )


def _recruiter_document() -> RecruiterDocumentModel:
    return RecruiterDocumentModel(
        source_cv_document_version="cv-doc-v1",
        language="en",
        identity_claim_id="identity-name",
        headline_claim_id="identity-name",
        technology_groups=[
            TechnologyGroup(
                label_id="geospatial",
                skill_claim_ids=["skill-postgis"],
            )
        ],
        selected_project_claim_ids=["project-geo"],
    )


def _write_cv(tmp_path, payload: bytes = b"fictional cv pdf bytes"):
    path = tmp_path / "Alex_Example_CV.pdf"
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def _packet(
    tmp_path,
    *,
    opportunity_id: str = "opp-1",
    cv_payload: bytes = b"fictional cv pdf bytes",
) -> ApplicationPacket:
    path, cv_hash = _write_cv(tmp_path, cv_payload)
    opportunity = _opportunity()
    return ApplicationPacket(
        application_id="app-1",
        opportunity_id=opportunity_id,
        opportunity_snapshot_hash=canonical_sha256(opportunity.model_dump(mode="json")),
        selected_intent="CAREER",
        application_track_id="tech",
        career_match=88,
        income_viability=78,
        confidence_score=90,
        scoring_version="v0.2a1",
        extractor_version="rules-v1",
        alias_registry_version="aliases-v1",
        taxonomy_versions={},
        master_facts_version="m" * 64,
        evidence_catalog_version="e" * 64,
        composer_version="composer-v1",
        cv_document_version="cv-doc-v1",
        recruiter_policy_version="recruiter-policy-v1",
        renderer_version="rendercv-typst-v1",
        selected_fact_ids=["fact-name", "fact-postgis", "fact-project"],
        selected_evidence_ids=["evidence-geo"],
        unresolved_gaps=["PySpark"],
        language_decision=LanguageDecision(
            language="en",
            basis="posting_language",
            confidence=0.95,
            source_field="opportunity.title+description",
            source_text="GIS Developer Send your CV to careers@example.test.",
        ),
        cv_document=_document(),
        recruiter_document=_recruiter_document(),
        cv_pdf_path=str(path),
        cv_sha256=cv_hash,
        packet_sha256="p" * 64,
        created_at=NOW,
    )


def _contact() -> ContactResolution:
    return ContactResolution(
        opportunity_id="opp-1",
        selected_candidate_id="published-1",
        channel="PUBLISHED_VACANCY_EMAIL",
        email="careers@example.test",
        organization="Example Labs",
        source_kind="VACANCY",
        source_ref="https://example.test/jobs/1",
        confidence=1.0,
        verification_status="VERIFIED_DIRECT",
        resolution_reason="published vacancy email",
        resolved_at=NOW,
        resolver_version="contact-v1",
    )


def _prepare(tmp_path, *, tier="HIGH", packet=None, promotion=None, id_value="brief-1", now=NOW):
    assessment = _assessment(tier=tier)
    return OutreachPreparationService(id_factory=lambda: id_value).prepare(
        assessment=assessment,
        application_packet=packet or _packet(tmp_path),
        contact_resolution=_contact(),
        policy=OutreachPolicy(),
        now=now,
        stretch_promotion=promotion,
    )


def test_high_direct_email_prepares_outreach_brief(tmp_path) -> None:
    result = _prepare(tmp_path)
    assert result.status == "OUTREACH_READY"
    assert result.brief is not None
    assert result.brief.company == "Example Labs"
    assert result.brief.contact_resolution.email == "careers@example.test"
    assert result.brief.cv_filename == "Alex_Example_CV.pdf"
    assert result.brief.language == "en"
    assert len(result.brief.brief_sha256) == 64


def test_medium_prepares_automatically(tmp_path) -> None:
    assert _prepare(tmp_path, tier="MEDIUM").status == "OUTREACH_READY"


def test_stretch_without_promotion_blocks(tmp_path) -> None:
    result = _prepare(tmp_path, tier="STRETCH")
    assert result.status == "BLOCKED_STRETCH"
    assert result.brief is None


def test_stretch_with_explicit_promotion_can_prepare(tmp_path) -> None:
    promotion = StretchPromotion(
        opportunity_id="opp-1",
        promoted_by="user",
        reason="manual review",
        promoted_at=NOW,
    )
    result = _prepare(tmp_path, tier="STRETCH", promotion=promotion)
    assert result.status == "OUTREACH_READY"


def test_packet_opportunity_mismatch_blocks(tmp_path) -> None:
    result = _prepare(tmp_path, packet=_packet(tmp_path, opportunity_id="opp-other"))
    assert result.status == "BLOCKED_INVALID_PACKET"
    assert "packet_opportunity_mismatch" in result.errors


def test_packet_language_mismatch_blocks(tmp_path) -> None:
    packet = _packet(tmp_path).model_copy(
        update={"language_decision": LanguageDecision(
            language="es",
            basis="explicit_override",
            confidence=1.0,
            source_field="cli.language",
            source_text="es",
        )}
    )
    result = _prepare(tmp_path, packet=packet)
    assert result.status == "BLOCKED_INVALID_PACKET"
    assert "packet_language_mismatch" in result.errors


def test_missing_cv_file_blocks(tmp_path) -> None:
    packet = _packet(tmp_path)
    from pathlib import Path

    Path(packet.cv_pdf_path).unlink()
    result = _prepare(tmp_path, packet=packet)
    assert result.status == "BLOCKED_INVALID_PACKET"
    assert "cv_artifact_missing" in result.errors


def test_cv_hash_mismatch_blocks(tmp_path) -> None:
    packet = _packet(tmp_path)
    from pathlib import Path

    Path(packet.cv_pdf_path).write_bytes(b"mutated bytes")
    result = _prepare(tmp_path, packet=packet)
    assert result.status == "BLOCKED_CV_CHANGED"
    assert "cv_hash_mismatch" in result.errors


def test_unresolved_requirement_remains_gap_not_allowed_claim(tmp_path) -> None:
    result = _prepare(tmp_path)
    assert result.brief is not None
    assert result.brief.unresolved_gaps == ["PySpark"]
    assert "Do not claim support for: PySpark" in result.brief.forbidden_claims
    assert all("PySpark" not in claim.text for claim in result.brief.allowed_claims)


def test_allowed_claims_are_subset_of_packet_cv_claims(tmp_path) -> None:
    packet = _packet(tmp_path)
    result = _prepare(tmp_path, packet=packet)
    assert result.brief is not None
    packet_ids = {claim.claim_id for claim in packet.cv_document.claims}
    allowed_ids = {claim.claim_id for claim in result.brief.allowed_claims}
    assert allowed_ids <= packet_ids
    assert allowed_ids == {"skill-postgis", "project-geo"}


def test_same_semantics_produce_same_brief_hash_despite_new_brief_id_and_time(tmp_path) -> None:
    packet = _packet(tmp_path)
    left = _prepare(tmp_path, packet=packet, id_value="brief-a", now=NOW)
    right = _prepare(
        tmp_path,
        packet=packet,
        id_value="brief-b",
        now=NOW + timedelta(minutes=10),
    )
    assert left.brief is not None and right.brief is not None
    assert left.brief.brief_id != right.brief.brief_id
    assert left.brief.created_at != right.brief.created_at
    assert left.brief.brief_sha256 == right.brief.brief_sha256
