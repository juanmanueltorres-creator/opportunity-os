from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.cv.models import ApplicationPacket
from app.outreach.approval import ApprovalService
from app.outreach.contact import ContactResolutionService
from app.outreach.draft import build_draft_snapshot
from app.outreach.models import (
    ApprovalRecord,
    ApprovalRequest,
    ContactCandidate,
    ContactPolicy,
    ContactResolution,
    DraftAttachment,
    DraftSnapshot,
    DraftVerificationBasis,
    OutreachEvent,
    OutreachPolicy,
    OutreachPreparationResult,
    SendAuthorizationResult,
    SendReceipt,
    SendRequest,
    StretchPromotion,
)
from app.outreach.preparation import (
    OutreachPreparationService,
    application_packet_error,
)
from app.outreach.repository import SQLiteOutreachRepository
from app.outreach.send import (
    SendGate,
    create_send_request,
    record_successful_send,
)
from app.radar.models import RadarAssessment


class OutreachService:
    def __init__(
        self,
        *,
        repository: SQLiteOutreachRepository,
        contact_service: ContactResolutionService | None = None,
        preparation_service: OutreachPreparationService | None = None,
        approval_service: ApprovalService | None = None,
        send_gate: SendGate | None = None,
    ) -> None:
        self.repository = repository
        self.contact_service = contact_service or ContactResolutionService()
        self.preparation_service = preparation_service or OutreachPreparationService()
        self.approval_service = approval_service or ApprovalService()
        self.send_gate = send_gate or SendGate()

    def prepare_outreach(
        self,
        *,
        assessment: RadarAssessment,
        application_packet: ApplicationPacket,
        candidates: list[ContactCandidate],
        contact_policy: ContactPolicy,
        outreach_policy: OutreachPolicy,
        now: datetime,
        stretch_promotion: StretchPromotion | None = None,
    ) -> OutreachPreparationResult:
        packet_error = application_packet_error(assessment, application_packet)
        if packet_error is not None:
            return OutreachPreparationResult(
                status="BLOCKED_INVALID_PACKET",
                errors=[packet_error],
            )

        self.repository.append_event(
            self._event(
                opportunity_id=assessment.opportunity.id,
                event_type="PACKET_ACCEPTED",
                entity_key=application_packet.packet_sha256,
                now=now,
            )
        )

        contact_result = self.contact_service.resolve(
            opportunity=assessment.opportunity,
            enrichment=assessment.enrichment,
            candidates=candidates,
            policy=contact_policy,
            ledger=self.repository,
            now=now,
        )
        if contact_result.resolution is None:
            if contact_result.status == "BLOCKED_POLICY":
                return OutreachPreparationResult(
                    status="BLOCKED_POLICY",
                    errors=list(contact_result.errors),
                )
            return OutreachPreparationResult(
                status="BLOCKED_CONTACT",
                errors=list(contact_result.errors) or ["contact_unavailable"],
            )

        resolution = self.repository.save_contact_resolution(
            contact_result.resolution
        )
        if contact_result.status == "MANUAL_ONLY":
            self.repository.append_event(
                self._event(
                    opportunity_id=assessment.opportunity.id,
                    event_type="MANUAL_ROUTE",
                    entity_key=resolution.selected_candidate_id,
                    now=now,
                )
            )
            return OutreachPreparationResult(
                status="BLOCKED_CONTACT",
                errors=["manual_route"],
            )

        self.repository.append_event(
            self._event(
                opportunity_id=assessment.opportunity.id,
                event_type="CONTACT_RESOLVED",
                entity_key=resolution.selected_candidate_id,
                now=now,
            )
        )
        prepared = self.preparation_service.prepare(
            assessment=assessment,
            application_packet=application_packet,
            contact_resolution=resolution,
            policy=outreach_policy,
            now=now,
            stretch_promotion=stretch_promotion,
        )
        if prepared.brief is None:
            return prepared

        brief = self.repository.save_outreach_brief(prepared.brief)
        self.repository.append_event(
            self._event(
                opportunity_id=assessment.opportunity.id,
                event_type="OUTREACH_READY",
                entity_key=brief.brief_sha256,
                now=now,
            )
        )
        return prepared.model_copy(update={"brief": brief})

    def register_draft(
        self,
        *,
        brief,
        provider_draft_id: str,
        subject: str,
        body: str,
        content_type: str,
        verification_basis: DraftVerificationBasis,
        now: datetime,
        reply_message_id: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> DraftSnapshot:
        email = brief.contact_resolution.email
        if email is None:
            raise ValueError("draft registration requires actionable email")
        draft = build_draft_snapshot(
            opportunity_id=brief.opportunity_id,
            brief_sha256_value=brief.brief_sha256,
            application_packet_sha256=brief.application_packet_sha256,
            provider_draft_id=provider_draft_id,
            to=[email],
            cc=list(cc or []),
            bcc=list(bcc or []),
            subject=subject,
            body=body,
            attachments=[
                DraftAttachment(
                    filename=brief.cv_filename,
                    sha256=brief.cv_sha256,
                    role="CV",
                )
            ],
            cv_sha256=brief.cv_sha256,
            content_type=content_type,
            reply_message_id=reply_message_id,
            verification_basis=verification_basis,
            now=now,
        )
        saved = self.repository.save_draft_snapshot(draft)
        history = self.repository.list_events(brief.opportunity_id)
        is_replacement = any(
            event.event_type in {"DRAFT_CREATED", "DRAFT_REPLACED"}
            for event in history
        )
        self.repository.append_event(
            self._event(
                opportunity_id=brief.opportunity_id,
                event_type="DRAFT_REPLACED" if is_replacement else "DRAFT_CREATED",
                entity_key=saved.draft_sha256,
                now=now,
            )
        )
        return saved

    def approve_draft(
        self,
        *,
        draft_snapshot: DraftSnapshot,
        requested_by: str,
        now: datetime,
        expires_at: datetime | None = None,
    ) -> ApprovalRecord:
        request = ApprovalRequest(
            requested_by=requested_by,
            approval_scope="SINGLE",
            draft_sha256=draft_snapshot.draft_sha256,
            expires_at=expires_at,
        )
        return self.approval_service.approve(
            draft_snapshot=draft_snapshot,
            approval_request=request,
            ledger=self.repository,
            now=now,
        )

    def request_send(
        self,
        *,
        draft_snapshot: DraftSnapshot,
        approval_record: ApprovalRecord,
        requested_by: str,
        now: datetime,
    ) -> SendRequest:
        if approval_record.opportunity_id != draft_snapshot.opportunity_id:
            raise ValueError("approval opportunity does not match draft")
        if approval_record.draft_sha256 != draft_snapshot.draft_sha256:
            raise ValueError("approval draft hash does not match draft")
        request = create_send_request(
            opportunity_id=draft_snapshot.opportunity_id,
            draft_sha256=draft_snapshot.draft_sha256,
            approval_id=approval_record.approval_id,
            requested_by=requested_by,
            now=now,
            batch_manifest_sha256=approval_record.batch_manifest_sha256,
        )
        saved = self.repository.save_send_request(request)
        self.repository.append_event(
            self._event(
                opportunity_id=draft_snapshot.opportunity_id,
                event_type="SEND_REQUESTED",
                entity_key=saved.request_id,
                now=now,
            )
        )
        return saved

    def authorize_send(
        self,
        *,
        draft_snapshot: DraftSnapshot,
        approval_record: ApprovalRecord | None,
        send_request: SendRequest | None,
        contact_resolution: ContactResolution,
        policy: OutreachPolicy,
        now: datetime,
    ) -> SendAuthorizationResult:
        return self.send_gate.validate(
            draft_snapshot=draft_snapshot,
            approval_record=approval_record,
            send_request=send_request,
            contact_resolution=contact_resolution,
            ledger=self.repository,
            policy=policy,
            now=now,
        )

    def record_send_success(
        self,
        *,
        authorization: SendAuthorizationResult,
        approval_record: ApprovalRecord,
        send_request: SendRequest,
        draft_snapshot: DraftSnapshot,
        provider_message_id: str,
        provider_thread_id: str | None,
        now: datetime,
    ) -> SendReceipt:
        return record_successful_send(
            authorization=authorization,
            approval=approval_record,
            send_request=send_request,
            draft_snapshot=draft_snapshot,
            provider_message_id=provider_message_id,
            provider_thread_id=provider_thread_id,
            ledger=self.repository,
            now=now,
        )

    @staticmethod
    def _event(
        *,
        opportunity_id: str,
        event_type: str,
        entity_key: str | None,
        now: datetime,
    ) -> OutreachEvent:
        return OutreachEvent(
            event_id=str(uuid4()),
            opportunity_id=opportunity_id,
            event_type=event_type,
            entity_key=entity_key,
            occurred_at=now,
        )
