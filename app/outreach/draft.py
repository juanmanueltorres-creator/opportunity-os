from __future__ import annotations

from datetime import datetime
from typing import Callable, Literal
from uuid import uuid4

from app.outreach.hashing import draft_sha256
from app.outreach.models import (
    DraftAttachment,
    DraftSnapshot,
    DraftVerificationBasis,
)


def build_draft_snapshot(
    *,
    opportunity_id: str,
    brief_sha256_value: str,
    application_packet_sha256: str,
    provider_draft_id: str,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    body: str,
    attachments: list[DraftAttachment],
    cv_sha256: str,
    content_type: str,
    reply_message_id: str | None,
    verification_basis: DraftVerificationBasis,
    now: datetime,
    language: Literal["es", "en"] = "en",
    id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> DraftSnapshot:
    body_canonical = body.replace("\r\n", "\n").replace("\r", "\n")
    snapshot = DraftSnapshot(
        draft_snapshot_id=id_factory(),
        opportunity_id=opportunity_id,
        brief_sha256=brief_sha256_value,
        application_packet_sha256=application_packet_sha256,
        provider="gmail",
        provider_draft_id=provider_draft_id,
        reply_message_id=reply_message_id,
        to=list(to),
        cc=list(cc),
        bcc=list(bcc),
        subject=subject,
        body_canonical=body_canonical,
        language=language,
        attachments=list(attachments),
        cv_sha256=cv_sha256,
        content_type=content_type,
        verification_basis=verification_basis,
        draft_sha256="0" * 64,
        created_at=now,
        verified_at=now,
    )
    return snapshot.model_copy(update={"draft_sha256": draft_sha256(snapshot)})


def is_send_ready(snapshot: DraftSnapshot) -> bool:
    if snapshot.verification_basis == "UNVERIFIABLE":
        return False
    return draft_sha256(snapshot) == snapshot.draft_sha256
