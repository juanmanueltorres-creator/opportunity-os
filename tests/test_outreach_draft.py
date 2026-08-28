from datetime import datetime, timedelta, timezone

from app.outreach.draft import build_draft_snapshot, is_send_ready
from app.outreach.models import DraftAttachment

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _build(
    *,
    provider_draft_id="draft-a",
    to=None,
    subject="Application — GIS Developer",
    body="Hello\r\n\r\nAttached is my CV.",
    filename="Alex_Example_CV.pdf",
    attachment_sha="c" * 64,
    reply_message_id=None,
    verification_basis="CREATED_EXACT",
    now=NOW,
):
    return build_draft_snapshot(
        opportunity_id="opp-1",
        brief_sha256_value="a" * 64,
        application_packet_sha256="b" * 64,
        provider_draft_id=provider_draft_id,
        to=to or ["careers@example.test"],
        cc=[],
        bcc=[],
        subject=subject,
        body=body,
        attachments=[
            DraftAttachment(
                filename=filename,
                sha256=attachment_sha,
                role="CV",
            )
        ],
        cv_sha256=attachment_sha,
        content_type="text/plain",
        reply_message_id=reply_message_id,
        verification_basis=verification_basis,
        now=now,
        id_factory=lambda: f"snapshot-{provider_draft_id}",
    )


def test_build_snapshot_hashes_exact_semantic_payload() -> None:
    snapshot = _build()
    assert snapshot.body_canonical == "Hello\n\nAttached is my CV."
    assert snapshot.draft_sha256 != "0" * 64
    assert len(snapshot.draft_sha256) == 64


def test_new_gmail_draft_id_preserves_hash_for_exact_replica() -> None:
    left = _build(provider_draft_id="draft-reviewed", verification_basis="CREATED_EXACT")
    right = _build(
        provider_draft_id="draft-send-copy",
        verification_basis="RECREATED_EXACT",
        now=NOW + timedelta(minutes=5),
    )
    assert left.provider_draft_id != right.provider_draft_id
    assert left.draft_sha256 == right.draft_sha256


def test_subject_change_changes_hash() -> None:
    assert _build(subject="Application").draft_sha256 != _build(subject="Hello").draft_sha256


def test_body_change_changes_hash() -> None:
    assert _build(body="One").draft_sha256 != _build(body="Two").draft_sha256


def test_recipient_change_changes_hash() -> None:
    assert _build(to=["a@example.test"]).draft_sha256 != _build(to=["b@example.test"]).draft_sha256


def test_reply_target_change_changes_hash() -> None:
    assert _build(reply_message_id="msg-a").draft_sha256 != _build(reply_message_id="msg-b").draft_sha256


def test_attachment_filename_change_changes_hash() -> None:
    assert _build(filename="cv.pdf").draft_sha256 != _build(filename="wrong.pdf").draft_sha256


def test_attachment_hash_change_changes_hash() -> None:
    assert _build(attachment_sha="c" * 64).draft_sha256 != _build(attachment_sha="d" * 64).draft_sha256


def test_unverifiable_basis_cannot_be_send_ready() -> None:
    snapshot = _build(verification_basis="UNVERIFIABLE")
    assert is_send_ready(snapshot) is False
