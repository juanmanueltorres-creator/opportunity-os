from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

from app.cv.hashing import canonical_sha256
from app.cv.models import ApplicationPacket, ClaimProvenance, CVClaim, CVDocumentModel
from app.cv.recruiter_models import RecruiterDocumentModel, TechnologyGroup
from app.models.domain import Opportunity
from app.outreach.models import ContactPolicy, OutreachPolicy
from app.outreach.repository import SQLiteOutreachRepository
from app.outreach.send import mark_send_attempted
from app.outreach.service import OutreachService
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.models import ConfidenceAssessment, EligibilityResult, RadarAssessment

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _opportunity() -> Opportunity:
    return Opportunity(
        id="opp-1",
        source="manual",
        source_id="fixture-1",
        source_url="https://example.test/jobs/1",
        company="Example Labs",
        title="GIS Developer",
        description="Send your CV to careers@example.test. Required: PostGIS.",
        discovered_at=NOW,
        published_at=NOW,
        required_skills=["PostGIS"],
    )


def _assessment() -> RadarAssessment:
    opportunity = _opportunity()
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
        enrichment=RuleBasedRequirementExtractor().extract(opportunity),
        eligibility=EligibilityResult(eligible=True),
        best_career_track="tech",
        career_match=88,
        best_income_track="tech",
        income_viability=78,
        confidence_score=90,
        confidence_breakdown=confidence,
        tier="HIGH",
        intent_tiers={"CAREER": "HIGH"},
        priority_score=88,
        selected_intent="CAREER",
        scoring_version="v0.2a1",
        extractor_version="rules-v1",
        alias_registry_version="aliases-v1",
        taxonomy_versions={},
    )


def _packet(tmp_path) -> ApplicationPacket:
    cv_path = tmp_path / "Alex_Example_CV.pdf"
    cv_bytes = b"fictional validated cv bytes"
    cv_path.write_bytes(cv_bytes)
    cv_sha = hashlib.sha256(cv_bytes).hexdigest()
    document = CVDocumentModel(
        document_version="cv-doc-v1",
        language="en",
        claims=[
            CVClaim(
                claim_id="skill-postgis",
                section="skills",
                kind="skill",
                text="PostGIS",
            )
        ],
        entries=[],
        provenance_map={
            "skill-postgis": ClaimProvenance(
                fact_ids=["fact-postgis"],
                evidence_ids=["evidence-geo"],
            )
        },
    )
    recruiter_document = RecruiterDocumentModel(
        source_cv_document_version=document.document_version,
        language="en",
        identity_claim_id="skill-postgis",
        headline_claim_id="skill-postgis",
        technology_groups=[
            TechnologyGroup(
                label_id="geospatial",
                skill_claim_ids=["skill-postgis"],
            )
        ],
    )
    opportunity = _opportunity()
    return ApplicationPacket(
        application_id="app-1",
        opportunity_id=opportunity.id,
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
        cv_document_version=document.document_version,
        recruiter_policy_version="recruiter-policy-v1",
        renderer_version="rendercv-typst-v1",
        selected_fact_ids=["fact-postgis"],
        selected_evidence_ids=["evidence-geo"],
        unresolved_gaps=[],
        cv_document=document,
        recruiter_document=recruiter_document,
        cv_pdf_path=str(cv_path),
        cv_sha256=cv_sha,
        packet_sha256="p" * 64,
        created_at=NOW,
    )


def _service(tmp_path) -> OutreachService:
    repository = SQLiteOutreachRepository(tmp_path / "outreach.sqlite3")
    repository.initialize()
    return OutreachService(repository=repository)


def test_direct_email_application_flow_requires_approval_and_separate_send(tmp_path) -> None:
    service = _service(tmp_path)
    assessment = _assessment()
    packet = _packet(tmp_path)

    prepared = service.prepare_outreach(
        assessment=assessment,
        application_packet=packet,
        candidates=[],
        contact_policy=ContactPolicy(),
        outreach_policy=OutreachPolicy(),
        now=NOW,
    )
    assert prepared.status == "OUTREACH_READY"
    assert prepared.brief is not None
    brief = prepared.brief

    draft = service.register_draft(
        brief=brief,
        provider_draft_id="draft-reviewed",
        subject="Application — GIS Developer",
        body="Hello\n\nPlease find my CV attached.",
        content_type="text/plain",
        verification_basis="CREATED_EXACT",
        now=NOW + timedelta(minutes=1),
    )
    approval = service.approve_draft(
        draft_snapshot=draft,
        requested_by="user",
        now=NOW + timedelta(minutes=2),
    )

    blocked = service.authorize_send(
        draft_snapshot=draft,
        approval_record=approval,
        send_request=None,
        contact_resolution=brief.contact_resolution,
        policy=OutreachPolicy(),
        now=NOW + timedelta(minutes=3),
    )
    assert blocked.authorized is False
    assert blocked.error_code == "send_request_missing"

    request = service.request_send(
        draft_snapshot=draft,
        approval_record=approval,
        requested_by="user",
        now=NOW + timedelta(minutes=4),
    )
    authorization = service.authorize_send(
        draft_snapshot=draft,
        approval_record=approval,
        send_request=request,
        contact_resolution=brief.contact_resolution,
        policy=OutreachPolicy(),
        now=NOW + timedelta(minutes=5),
    )
    assert authorization.authorized is True

    mark_send_attempted(
        authorization=authorization,
        send_request=request,
        ledger=service.repository,
        now=NOW + timedelta(minutes=6),
        id_factory=lambda: "attempt-1",
    )
    receipt = service.record_send_success(
        authorization=authorization,
        approval_record=approval,
        send_request=request,
        draft_snapshot=draft,
        provider_message_id="gmail-message-1",
        provider_thread_id="gmail-thread-1",
        now=NOW + timedelta(minutes=7),
    )
    assert receipt.status == "SENT"
    assert receipt.provider_message_id == "gmail-message-1"

    second = service.authorize_send(
        draft_snapshot=draft,
        approval_record=approval,
        send_request=request,
        contact_resolution=brief.contact_resolution,
        policy=OutreachPolicy(),
        now=NOW + timedelta(minutes=8),
    )
    assert second.authorized is False
    assert second.error_code == "already_sent"

    event_types = [event.event_type for event in service.repository.list_events("opp-1")]
    assert event_types == [
        "PACKET_ACCEPTED",
        "CONTACT_RESOLVED",
        "OUTREACH_READY",
        "DRAFT_CREATED",
        "APPROVED",
        "SEND_REQUESTED",
        "SEND_ATTEMPTED",
        "SENT",
    ]


def test_recreated_exact_draft_can_use_same_approval_hash(tmp_path) -> None:
    service = _service(tmp_path)
    prepared = service.prepare_outreach(
        assessment=_assessment(),
        application_packet=_packet(tmp_path),
        candidates=[],
        contact_policy=ContactPolicy(),
        outreach_policy=OutreachPolicy(),
        now=NOW,
    )
    assert prepared.brief is not None
    brief = prepared.brief

    reviewed = service.register_draft(
        brief=brief,
        provider_draft_id="draft-reviewed",
        subject="Application — GIS Developer",
        body="Hello\n\nPlease find my CV attached.",
        content_type="text/plain",
        verification_basis="CREATED_EXACT",
        now=NOW + timedelta(minutes=1),
    )
    approval = service.approve_draft(
        draft_snapshot=reviewed,
        requested_by="user",
        now=NOW + timedelta(minutes=2),
    )

    recreated = service.register_draft(
        brief=brief,
        provider_draft_id="draft-send-copy",
        subject="Application — GIS Developer",
        body="Hello\n\nPlease find my CV attached.",
        content_type="text/plain",
        verification_basis="RECREATED_EXACT",
        now=NOW + timedelta(minutes=3),
    )
    assert recreated.provider_draft_id != reviewed.provider_draft_id
    assert recreated.draft_sha256 == reviewed.draft_sha256

    request = service.request_send(
        draft_snapshot=recreated,
        approval_record=approval,
        requested_by="user",
        now=NOW + timedelta(minutes=4),
    )
    authorization = service.authorize_send(
        draft_snapshot=recreated,
        approval_record=approval,
        send_request=request,
        contact_resolution=brief.contact_resolution,
        policy=OutreachPolicy(),
        now=NOW + timedelta(minutes=5),
    )
    assert authorization.authorized is True


def test_invalid_packet_is_not_recorded_as_accepted(tmp_path) -> None:
    service = _service(tmp_path)
    mismatched_packet = _packet(tmp_path).model_copy(
        update={"opportunity_id": "opp-other"}
    )

    result = service.prepare_outreach(
        assessment=_assessment(),
        application_packet=mismatched_packet,
        candidates=[],
        contact_policy=ContactPolicy(),
        outreach_policy=OutreachPolicy(),
        now=NOW,
    )

    assert result.status == "BLOCKED_INVALID_PACKET"
    assert result.errors == ["packet_opportunity_mismatch"]
    assert service.repository.list_events("opp-1") == []
