from __future__ import annotations

from app.cv.hashing import canonical_sha256
from app.outreach.models import DraftSnapshot, OutreachBrief


def draft_semantic_payload(snapshot: DraftSnapshot) -> dict:
    return {
        "opportunity_id": snapshot.opportunity_id,
        "brief_sha256": snapshot.brief_sha256,
        "application_packet_sha256": snapshot.application_packet_sha256,
        "reply_message_id": snapshot.reply_message_id,
        "to": sorted(address.casefold().strip() for address in snapshot.to),
        "cc": sorted(address.casefold().strip() for address in snapshot.cc),
        "bcc": sorted(address.casefold().strip() for address in snapshot.bcc),
        "subject": snapshot.subject,
        "body_canonical": snapshot.body_canonical,
        "attachments": sorted(
            [
                attachment.model_dump(mode="json")
                for attachment in snapshot.attachments
            ],
            key=lambda item: (item["role"], item["filename"], item["sha256"]),
        ),
        "cv_sha256": snapshot.cv_sha256,
        "content_type": snapshot.content_type,
    }


def draft_sha256(snapshot: DraftSnapshot) -> str:
    return canonical_sha256(draft_semantic_payload(snapshot))


def brief_semantic_payload(brief: OutreachBrief) -> dict:
    return {
        "opportunity_id": brief.opportunity_id,
        "opportunity_snapshot_hash": brief.opportunity_snapshot_hash,
        "company": brief.company,
        "role": brief.role,
        "selected_intent": brief.selected_intent,
        "application_track_id": brief.application_track_id,
        "tier": brief.tier,
        "contact_resolution": brief.contact_resolution.model_dump(mode="json"),
        "application_mode": brief.application_mode,
        "why_fit": brief.why_fit,
        "strongest_evidence": [
            claim.model_dump(mode="json") for claim in brief.strongest_evidence
        ],
        "selected_fact_ids": brief.selected_fact_ids,
        "selected_evidence_ids": brief.selected_evidence_ids,
        "unresolved_gaps": brief.unresolved_gaps,
        "allowed_claims": [
            claim.model_dump(mode="json") for claim in brief.allowed_claims
        ],
        "forbidden_claims": brief.forbidden_claims,
        "language": brief.language,
        "tone_policy": brief.tone_policy,
        "call_to_action_policy": brief.call_to_action_policy,
        "cv_filename": brief.cv_filename,
        "cv_sha256": brief.cv_sha256,
        "application_packet_sha256": brief.application_packet_sha256,
        "brief_version": brief.brief_version,
    }


def brief_sha256(brief: OutreachBrief) -> str:
    return canonical_sha256(brief_semantic_payload(brief))


def batch_manifest_sha256(draft_hashes: list[str]) -> str:
    return canonical_sha256(sorted(set(draft_hashes)))


def send_idempotency_key(
    *,
    opportunity_id: str,
    primary_recipient: str,
    packet_sha256: str,
    draft_hash: str,
) -> str:
    return canonical_sha256(
        {
            "opportunity_id": opportunity_id,
            "primary_recipient": primary_recipient.casefold().strip(),
            "application_packet_sha256": packet_sha256,
            "draft_sha256": draft_hash,
        }
    )
