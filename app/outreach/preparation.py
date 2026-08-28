from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Callable
from uuid import uuid4

from app.cv.hashing import canonical_sha256
from app.cv.models import ApplicationPacket
from app.outreach.hashing import brief_sha256
from app.outreach.models import (
    ContactResolution,
    OutreachBrief,
    OutreachClaim,
    OutreachPolicy,
    OutreachPreparationResult,
    StretchPromotion,
)
from app.radar.models import RadarAssessment

_ACTIONABLE_EMAIL_STATUSES = {
    "VERIFIED_DIRECT",
    "VERIFIED_OFFICIAL",
    "VERIFIED_ENRICHED",
}
_EXCLUDED_EMAIL_EVIDENCE_KINDS = {"identity", "contact", "location", "link"}


class OutreachPreparationService:
    def __init__(
        self,
        *,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.id_factory = id_factory or (lambda: str(uuid4()))

    def prepare(
        self,
        *,
        assessment: RadarAssessment,
        application_packet: ApplicationPacket,
        contact_resolution: ContactResolution,
        policy: OutreachPolicy,
        now: datetime,
        stretch_promotion: StretchPromotion | None = None,
    ) -> OutreachPreparationResult:
        now_utc = _require_aware(now)

        if not assessment.eligibility.eligible:
            return _blocked("BLOCKED_POLICY", "outreach_policy_blocked")

        tier = _selected_tier(assessment)
        if tier is None:
            return _blocked("BLOCKED_POLICY", "outreach_policy_blocked")
        if tier not in policy.automatic_tiers:
            if tier != "STRETCH" or not _valid_stretch_promotion(
                stretch_promotion,
                opportunity_id=assessment.opportunity.id,
                now=now_utc,
            ):
                return _blocked("BLOCKED_STRETCH", "stretch_not_promoted")

        packet_error = application_packet_error(assessment, application_packet)
        if packet_error is not None:
            return _blocked("BLOCKED_INVALID_PACKET", packet_error)

        if (
            contact_resolution.opportunity_id != assessment.opportunity.id
            or contact_resolution.email is None
            or contact_resolution.verification_status not in _ACTIONABLE_EMAIL_STATUSES
        ):
            return _blocked("BLOCKED_CONTACT", "contact_unverified")

        cv_path = Path(application_packet.cv_pdf_path)
        if not cv_path.is_file():
            return _blocked("BLOCKED_INVALID_PACKET", "cv_artifact_missing")
        try:
            actual_cv_hash = _file_sha256(cv_path)
        except OSError:
            return _blocked("BLOCKED_INVALID_PACKET", "cv_artifact_missing")
        if actual_cv_hash != application_packet.cv_sha256:
            return _blocked("BLOCKED_CV_CHANGED", "cv_hash_mismatch")

        allowed_claims = _allowed_claims(application_packet, policy)
        strongest_evidence = allowed_claims[: policy.max_why_fit]
        why_fit = [claim.text for claim in strongest_evidence]
        gaps = list(application_packet.unresolved_gaps)
        forbidden_claims = [f"Do not claim support for: {gap}" for gap in gaps]

        brief = OutreachBrief(
            brief_id=self.id_factory(),
            opportunity_id=assessment.opportunity.id,
            opportunity_snapshot_hash=application_packet.opportunity_snapshot_hash,
            company=assessment.opportunity.company,
            role=assessment.opportunity.title,
            selected_intent=application_packet.selected_intent,
            application_track_id=application_packet.application_track_id,
            tier=tier,
            contact_resolution=contact_resolution,
            application_mode=assessment.enrichment.application_mode,
            why_fit=why_fit,
            strongest_evidence=strongest_evidence,
            selected_fact_ids=list(application_packet.selected_fact_ids),
            selected_evidence_ids=list(application_packet.selected_evidence_ids),
            unresolved_gaps=gaps,
            allowed_claims=allowed_claims,
            forbidden_claims=forbidden_claims,
            language=application_packet.cv_document.language,
            tone_policy=policy.tone_policy,
            call_to_action_policy=policy.call_to_action_policy,
            cv_pdf_path=str(cv_path),
            cv_filename=cv_path.name,
            cv_sha256=application_packet.cv_sha256,
            application_packet_sha256=application_packet.packet_sha256,
            brief_version=policy.brief_version,
            brief_sha256="0" * 64,
            created_at=now_utc,
        )
        final_brief = brief.model_copy(
            update={"brief_sha256": brief_sha256(brief)}
        )
        return OutreachPreparationResult(
            status="OUTREACH_READY",
            brief=final_brief,
        )


def _selected_tier(assessment: RadarAssessment) -> str | None:
    if assessment.selected_intent is not None:
        value = assessment.intent_tiers.get(assessment.selected_intent)
        if value is not None:
            return value
    return assessment.tier


def _valid_stretch_promotion(
    promotion: StretchPromotion | None,
    *,
    opportunity_id: str,
    now: datetime,
) -> bool:
    return bool(
        promotion is not None
        and promotion.opportunity_id == opportunity_id
        and promotion.promoted_at <= now
    )


def application_packet_error(
    assessment: RadarAssessment,
    packet: ApplicationPacket,
) -> str | None:
    opportunity = assessment.opportunity
    if packet.opportunity_id != opportunity.id:
        return "packet_opportunity_mismatch"
    if packet.opportunity_snapshot_hash != canonical_sha256(
        opportunity.model_dump(mode="json")
    ):
        return "packet_opportunity_mismatch"
    if assessment.selected_intent is None or packet.selected_intent != assessment.selected_intent:
        return "packet_intent_mismatch"

    expected_track = (
        assessment.best_career_track
        if assessment.selected_intent == "CAREER"
        else assessment.best_income_track
    )
    if expected_track is None or packet.application_track_id != expected_track:
        return "packet_track_mismatch"

    if packet.scoring_version != assessment.scoring_version:
        return "packet_version_mismatch"
    if packet.extractor_version != assessment.extractor_version:
        return "packet_version_mismatch"
    if packet.alias_registry_version != assessment.alias_registry_version:
        return "packet_version_mismatch"
    if dict(packet.taxonomy_versions) != dict(assessment.taxonomy_versions):
        return "packet_version_mismatch"
    return None


def _allowed_claims(
    packet: ApplicationPacket,
    policy: OutreachPolicy,
) -> list[OutreachClaim]:
    result: list[OutreachClaim] = []
    provenance_map = packet.cv_document.provenance_map
    for claim in packet.cv_document.claims:
        if len(result) >= policy.max_allowed_claims:
            break
        if claim.kind in _EXCLUDED_EMAIL_EVIDENCE_KINDS:
            continue
        provenance = provenance_map.get(claim.claim_id)
        if provenance is None:
            continue
        result.append(
            OutreachClaim(
                claim_id=claim.claim_id,
                text=claim.text,
                kind=claim.kind,
                fact_ids=list(provenance.fact_ids),
                evidence_ids=list(provenance.evidence_ids),
            )
        )
    return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _blocked(status: str, error: str) -> OutreachPreparationResult:
    return OutreachPreparationResult(status=status, errors=[error])


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)
