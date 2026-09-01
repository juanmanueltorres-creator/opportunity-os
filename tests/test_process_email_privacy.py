from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from app.adapters.gmail_content.models import GmailContentEnvelope
from app.adapters.gmail_content.normalizer import normalize_full_message_payload
from app.operator_bridge.models import ObservationImportRequest
from app.operator_bridge.service import OperatorBridgeService
from app.process_email.deterministic import DeterministicProcessClassifier
from app.process_email.models import ProcessEmailSelection
from app.process_email.projector import ProcessEventProjector
from app.process_email.service import ProcessEmailService
from app.relationships.models import RelationshipAccount, RelationshipEvent
from app.relationships.repository import SQLiteRelationshipRepository
from app.relationships.service import RelationshipService

NOW = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)
OWNED = "owner@example.com"
SUBJECT_SENTINEL = "PRIVATE SUBJECT SENTINEL"
BODY_SENTINEL = "PRIVATE BODY SENTINEL"
EVIDENCE_SENTINEL = "PRIVATE EVIDENCE SENTINEL"
INTERVIEW_SENTENCE = "We would like to invite you to an interview."


def _b64(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _full_payload(
    body: str,
    *,
    message_id: str = "m1",
    sender: str = "recruiter@example.com",
    recipient: str = OWNED,
    subject: str = SUBJECT_SENTINEL,
    labels: tuple[str, ...] = ("INBOX",),
    observed_at: datetime = NOW,
) -> dict[str, object]:
    return {
        "id": message_id,
        "threadId": f"thread-{message_id}",
        "internalDate": str(int(observed_at.timestamp() * 1000)),
        "labelIds": list(labels),
        "payload": {
            "mimeType": "text/plain",
            "filename": "",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "To", "value": recipient},
                {"name": "Subject", "value": subject},
            ],
            "body": {"data": _b64(body)},
        },
    }


class FullFixtureProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[str] = []

    async def get_message_content(self, message_id: str) -> GmailContentEnvelope:
        self.calls.append(message_id)
        envelope = normalize_full_message_payload(self.payload)
        assert envelope.message.message_id == message_id
        return envelope


def _stack(tmp_path, *, open_process: bool = False, payload: dict[str, object]):
    repo = SQLiteRelationshipRepository(tmp_path / "relationships.sqlite3")
    repo.initialize()
    repo.save_account(
        RelationshipAccount(
            account_id="example-co",
            company="Example Co",
            relationship_state="PROCESS_OPEN" if open_process else "UNTOUCHED",
            open_process=open_process,
            updated_at=NOW - timedelta(minutes=5),
        )
    )
    relationships = RelationshipService(repo)
    bridge = OperatorBridgeService(repo, relationships)
    provider = FullFixtureProvider(payload)
    service = ProcessEmailService(
        provider,
        DeterministicProcessClassifier(),
        ProcessEventProjector(),
        owned_addresses={OWNED},
        relationship_repository=repo,
        operator_bridge=bridge,
    )
    return repo, relationships, bridge, provider, service


def _selection(message_id: str = "m1") -> ProcessEmailSelection:
    return ProcessEmailSelection(
        account_id="example-co",
        message_id=message_id,
        selected_by="operator",
    )


def _confirm(bridge: OperatorBridgeService, preview, *, at: datetime = NOW + timedelta(minutes=1)):
    assert preview.proposed_observation is not None
    assert preview.operator_preview is not None
    return bridge.import_observation(
        ObservationImportRequest(
            observation=preview.proposed_observation,
            preview_sha256=preview.operator_preview.preview_sha256,
            confirmed_by="operator",
            confirmed_at=at,
        ),
        processed_at=at,
    )


def _all_persisted_json(db_path) -> str:
    with sqlite3.connect(db_path) as conn:
        rows = []
        for table in (
            "relationship_accounts",
            "relationship_contacts",
            "relationship_events",
        ):
            rows.extend(
                row[0]
                for row in conn.execute(f"SELECT payload_json FROM {table}").fetchall()
            )
    return "\n".join(rows)


@pytest.mark.asyncio
async def test_full_interview_preview_requires_explicit_existing_import_and_persists_no_source_text(tmp_path) -> None:
    body = f"{BODY_SENTINEL}\n{INTERVIEW_SENTENCE}\n{EVIDENCE_SENTINEL}"
    repo, _, bridge, provider, service = _stack(
        tmp_path,
        payload=_full_payload(body),
    )

    preview = await service.preview(_selection())

    assert provider.calls == ["m1"]
    assert repo.list_events("example-co") == []
    assert preview.status == "CLASSIFIED"
    assert preview.proposed_observation is not None
    assert preview.operator_preview is not None
    assert preview.operator_preview.status == "IMPORTABLE"
    assert [signal.kind for signal in preview.signals] == ["INTERVIEW_PROPOSED"]

    result = _confirm(bridge, preview)

    assert result.status == "IMPORTED"
    events = repo.list_events("example-co")
    assert len(events) == 1
    assert events[0].kind == "PROCESS_OPENED"
    assert events[0].metadata == {
        "operator_source_type": "EMAIL_PROVIDER",
        "operator_source_name": "gmail",
        "operator_observation_id": "gmail-message:m1:process-signal:INTERVIEW_PROPOSED",
        "operator_observation_sha256": preview.operator_preview.observation_sha256,
        "semantic_producer": "PROCESS_EMAIL_CLASSIFIER",
        "semantic_producer_version": "deterministic-process-email-v1",
        "semantic_policy_version": "es-en-2026-09-v1",
        "semantic_classification": "INTERVIEW_PROPOSED",
        "semantic_reason_code": "INTERVIEW_INVITATION_EXPLICIT",
    }

    persisted = _all_persisted_json(repo.path)
    for forbidden in (
        SUBJECT_SENTINEL,
        BODY_SENTINEL,
        EVIDENCE_SENTINEL,
        INTERVIEW_SENTENCE,
    ):
        assert forbidden not in persisted


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "expected_status"),
    [
        ("We received your application.", "CLASSIFIED"),
        ("The compensation range for this role is USD 80k-100k.", "AMBIGUOUS"),
        ("If selected, you may be invited to interview.", "AMBIGUOUS"),
        ("We will share next steps soon.", "CLASSIFIED"),
        (
            "We would like to invite you to an interview. "
            "We will not be moving forward with your application.",
            "AMBIGUOUS",
        ),
    ],
)
async def test_non_authoritative_semantics_never_persist_process_event(
    tmp_path,
    body: str,
    expected_status: str,
) -> None:
    repo, _, _, _, service = _stack(tmp_path, payload=_full_payload(body))

    preview = await service.preview(_selection())

    assert preview.status == expected_status
    assert preview.proposed_observation is None
    assert preview.operator_preview is None
    assert repo.list_events("example-co") == []


@pytest.mark.asyncio
async def test_outbound_operator_message_is_invalid_and_never_persists(tmp_path) -> None:
    payload = _full_payload(
        INTERVIEW_SENTENCE,
        sender=OWNED,
        recipient="recruiter@example.com",
        labels=("SENT",),
    )
    repo, _, _, _, service = _stack(tmp_path, payload=payload)

    preview = await service.preview(_selection())

    assert preview.status == "INVALID_SELECTION"
    assert preview.warnings == ["message_not_inbound"]
    assert preview.proposed_observation is None
    assert repo.list_events("example-co") == []


@pytest.mark.asyncio
async def test_rejection_without_open_process_does_not_fabricate_close_event(tmp_path) -> None:
    repo, _, _, _, service = _stack(
        tmp_path,
        payload=_full_payload("We will not be moving forward with your application."),
    )

    preview = await service.preview(_selection())

    assert preview.status == "CLASSIFIED"
    assert preview.warnings == ["no_open_process_to_close"]
    assert preview.proposed_observation is None
    assert repo.list_events("example-co") == []


@pytest.mark.asyncio
async def test_current_rejection_with_quoted_old_interview_closes_only_existing_process(tmp_path) -> None:
    body = (
        "We will not be moving forward with your application.\n"
        "On Mon, Aug 31, 2026 at 10:00 AM Juan wrote:\n"
        "We would like to invite you to an interview."
    )
    repo, _, bridge, _, service = _stack(
        tmp_path,
        open_process=True,
        payload=_full_payload(body),
    )

    preview = await service.preview(_selection())

    assert [signal.kind for signal in preview.signals] == ["REJECTED"]
    assert preview.proposed_observation is not None
    assert preview.proposed_observation.kind == "PROCESS_CLOSED"

    result = _confirm(bridge, preview)

    assert result.status == "IMPORTED"
    events = repo.list_events("example-co")
    assert [event.kind for event in events] == ["PROCESS_CLOSED"]


@pytest.mark.asyncio
async def test_old_process_email_preview_is_blocked_after_relationship_state_changes(tmp_path) -> None:
    repo, relationships, bridge, _, service = _stack(
        tmp_path,
        payload=_full_payload(INTERVIEW_SENTENCE),
    )
    preview = await service.preview(_selection())
    assert preview.operator_preview is not None
    assert preview.operator_preview.status == "IMPORTABLE"

    relationships.record(
        RelationshipEvent(
            event_id="manual-contact-after-preview",
            account_id="example-co",
            kind="CONTACTED",
            occurred_at=NOW + timedelta(seconds=30),
            reason="separate confirmed contact",
            source_ref="manual:contact",
            metadata={"official_channel": "manual-confirmed-channel"},
        )
    )
    assert [event.kind for event in repo.list_events("example-co")] == ["CONTACTED"]

    result = _confirm(bridge, preview, at=NOW + timedelta(minutes=1))

    assert result.status == "BLOCKED_STALE_PREVIEW"
    assert result.errors == ["stale_preview"]
    assert [event.kind for event in repo.list_events("example-co")] == ["CONTACTED"]


@pytest.mark.asyncio
async def test_explicit_process_email_import_is_idempotent(tmp_path) -> None:
    repo, _, bridge, _, service = _stack(
        tmp_path,
        payload=_full_payload(INTERVIEW_SENTENCE),
    )
    preview = await service.preview(_selection())

    first = _confirm(bridge, preview, at=NOW + timedelta(minutes=1))
    second = _confirm(bridge, preview, at=NOW + timedelta(minutes=2))

    assert first.status == "IMPORTED"
    assert second.status == "ALREADY_IMPORTED"
    assert len(repo.list_events("example-co")) == 1
