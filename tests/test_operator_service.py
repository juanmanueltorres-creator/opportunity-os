from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.operator_bridge.models import ObservationImportRequest, OperatorObservation
from app.operator_bridge.normalizer import normalize_observation
from app.operator_bridge.service import OperatorBridgeService
from app.relationships.models import CareerContact, RelationshipAccount, RelationshipEvent
from app.relationships.repository import SQLiteRelationshipRepository
from app.relationships.service import RelationshipService

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def _bridge(tmp_path: Path, *, with_contact: bool = False):
    repo = SQLiteRelationshipRepository(tmp_path / "relationships.sqlite3")
    repo.initialize()
    relationships = RelationshipService(repo)
    relationships.register_account(
        RelationshipAccount(
            account_id="example-co",
            company="Example Co",
            updated_at=NOW - timedelta(days=1),
        )
    )
    if with_contact:
        relationships.register_contact(
            CareerContact(
                contact_id="contact-1",
                account_id="example-co",
                person="Private Person",
                role="Recruiter",
                contact_type="RECRUITER",
                verification_status="VERIFIED",
                observed_at=NOW - timedelta(days=10),
                disposition="AVAILABLE",
                active=True,
            )
        )
    return repo, relationships, OperatorBridgeService(repo, relationships)


def _observation(kind: str = "MESSAGE_SENT", **updates) -> OperatorObservation:
    values = {
        "observation_id": "provider-observation-1",
        "source_type": "EMAIL_PROVIDER",
        "source_name": "gmail",
        "source_ref": "message:provider-observation-1",
        "kind": kind,
        "account_id": "example-co",
        "observed_at": NOW,
        "reason": "authorized normalized fact",
    }
    values.update(updates)
    return OperatorObservation(**values)


def _request(observation: OperatorObservation, preview_sha256: str) -> ObservationImportRequest:
    return ObservationImportRequest(
        observation=observation,
        preview_sha256=preview_sha256,
        confirmed_by="operator",
        confirmed_at=NOW,
    )


def test_preview_is_read_only_and_returns_importable_projection(tmp_path: Path) -> None:
    repo, _, bridge = _bridge(tmp_path)
    original = repo.get_account("example-co")
    before_events = repo.list_events("example-co")

    preview = bridge.preview(_observation())

    assert preview.status == "IMPORTABLE"
    assert preview.event_kind == "CONTACTED"
    assert preview.state_before == "UNTOUCHED"
    assert preview.state_after == "CONTACTED"
    assert preview.external_actions == []
    assert repo.get_account("example-co") == original
    assert repo.list_events("example-co") == before_events


def test_same_observation_and_same_state_produce_same_preview_hash(tmp_path: Path) -> None:
    _, _, bridge = _bridge(tmp_path)
    observation = _observation()

    assert bridge.preview(observation).preview_sha256 == bridge.preview(observation).preview_sha256


def test_changed_observation_reason_changes_preview_hash(tmp_path: Path) -> None:
    _, _, bridge = _bridge(tmp_path)
    first = _observation(reason="first reason")
    second = first.model_copy(update={"reason": "second reason"})

    assert bridge.preview(first).preview_sha256 != bridge.preview(second).preview_sha256


def test_changed_account_state_changes_preview_hash(tmp_path: Path) -> None:
    repo, _, bridge = _bridge(tmp_path)
    observation = _observation()
    first = bridge.preview(observation)
    account = repo.get_account("example-co")
    assert account is not None
    repo.save_account(account.model_copy(update={"last_reason": "concurrent change"}))

    second = bridge.preview(observation)

    assert first.preview_sha256 != second.preview_sha256


def test_changed_referenced_contact_changes_preview_hash(tmp_path: Path) -> None:
    repo, _, bridge = _bridge(tmp_path, with_contact=True)
    observation = _observation(kind="REPLY_RECEIVED", contact_id="contact-1")
    first = bridge.preview(observation)
    contact = repo.get_contact("contact-1")
    assert contact is not None
    repo.save_contact(contact.model_copy(update={"disposition": "HELD"}))

    second = bridge.preview(observation)

    assert first.preview_sha256 != second.preview_sha256


def test_preview_identity_conflict_is_blocked_without_write(tmp_path: Path) -> None:
    repo, _, bridge = _bridge(tmp_path)
    observation = _observation()
    expected = normalize_observation(observation)
    conflicting = expected.model_copy(update={"reason": "different semantic payload"})
    repo.append_event(conflicting)
    before = repo.list_events("example-co")

    preview = bridge.preview(observation)

    assert preview.status == "BLOCKED"
    assert preview.errors == ["observation_identity_conflict"]
    assert repo.list_events("example-co") == before


def test_preview_out_of_order_is_blocked_without_write(tmp_path: Path) -> None:
    repo, _, bridge = _bridge(tmp_path)
    repo.append_event(
        RelationshipEvent(
            event_id="later-event",
            account_id="example-co",
            kind="NOTE_RECORDED",
            occurred_at=NOW + timedelta(days=1),
        )
    )
    before = repo.list_events("example-co")

    preview = bridge.preview(_observation())

    assert preview.status == "BLOCKED"
    assert preview.errors == ["out_of_order_observation"]
    assert repo.list_events("example-co") == before


def test_preview_unknown_contact_returns_stable_safe_error(tmp_path: Path) -> None:
    _, _, bridge = _bridge(tmp_path)

    preview = bridge.preview(_observation(kind="REPLY_RECEIVED", contact_id="missing"))

    assert preview.status == "BLOCKED"
    assert preview.errors == ["unknown_or_invalid_contact"]


def test_exact_confirmed_preview_imports_once(tmp_path: Path) -> None:
    repo, _, bridge = _bridge(tmp_path)
    observation = _observation()
    preview = bridge.preview(observation)

    result = bridge.import_observation(
        _request(observation, preview.preview_sha256),
        processed_at=NOW,
    )

    assert result.status == "IMPORTED"
    assert result.receipt is not None
    assert result.receipt.status == "IMPORTED"
    assert len(repo.list_events("example-co")) == 1
    assert repo.get_account("example-co").relationship_state == "CONTACTED"


def test_exact_retry_returns_already_imported_before_stale_check(tmp_path: Path) -> None:
    repo, _, bridge = _bridge(tmp_path)
    observation = _observation()
    preview = bridge.preview(observation)
    request = _request(observation, preview.preview_sha256)

    first = bridge.import_observation(request, processed_at=NOW)
    second = bridge.import_observation(request, processed_at=NOW + timedelta(seconds=1))

    assert first.status == "IMPORTED"
    assert second.status == "ALREADY_IMPORTED"
    assert first.receipt is not None
    assert second.receipt is not None
    assert first.receipt.receipt_id == second.receipt.receipt_id
    assert second.receipt.processed_at == NOW + timedelta(seconds=1)
    assert len(repo.list_events("example-co")) == 1


def test_import_identity_conflict_precedes_stale_check(tmp_path: Path) -> None:
    repo, _, bridge = _bridge(tmp_path)
    observation = _observation()
    preview = bridge.preview(observation)
    expected = normalize_observation(observation)
    repo.append_event(expected.model_copy(update={"reason": "conflicting stored payload"}))

    result = bridge.import_observation(
        _request(observation, preview.preview_sha256),
        processed_at=NOW,
    )

    assert result.status == "CONFLICT"
    assert result.receipt is None
    assert result.errors == ["observation_identity_conflict"]


def test_stale_state_before_first_import_blocks_without_write(tmp_path: Path) -> None:
    repo, _, bridge = _bridge(tmp_path)
    observation = _observation()
    preview = bridge.preview(observation)
    account = repo.get_account("example-co")
    assert account is not None
    repo.save_account(account.model_copy(update={"last_reason": "concurrent state change"}))

    result = bridge.import_observation(
        _request(observation, preview.preview_sha256),
        processed_at=NOW,
    )

    assert result.status == "BLOCKED_STALE_PREVIEW"
    assert result.receipt is None
    assert result.errors == ["stale_preview"]
    assert repo.list_events("example-co") == []


def test_blocked_domain_transition_imports_nothing(tmp_path: Path) -> None:
    repo, _, bridge = _bridge(tmp_path)
    observation = _observation(kind="PROCESS_CLOSED")
    preview = bridge.preview(observation)
    assert preview.status == "BLOCKED"

    result = bridge.import_observation(
        _request(observation, preview.preview_sha256),
        processed_at=NOW,
    )

    assert result.status == "BLOCKED_DOMAIN"
    assert result.receipt is None
    assert result.errors == ["invalid_relationship_transition"]
    assert repo.list_events("example-co") == []


def test_receipt_identity_is_stable_for_same_relationship_event(tmp_path: Path) -> None:
    _, _, bridge = _bridge(tmp_path)
    observation = _observation()
    preview = bridge.preview(observation)
    request = _request(observation, preview.preview_sha256)

    first = bridge.import_observation(request, processed_at=NOW)
    second = bridge.import_observation(request, processed_at=NOW + timedelta(minutes=1))

    assert first.receipt is not None
    assert second.receipt is not None
    assert first.receipt.receipt_id == second.receipt.receipt_id
    assert first.receipt.relationship_event_id == second.receipt.relationship_event_id


def test_import_rejects_naive_processed_at_before_any_write(tmp_path: Path) -> None:
    repo, _, bridge = _bridge(tmp_path)
    observation = _observation()
    preview = bridge.preview(observation)

    with pytest.raises(ValueError, match="processed_at must be timezone-aware"):
        bridge.import_observation(
            _request(observation, preview.preview_sha256),
            processed_at=datetime(2026, 8, 29, 12, 0),
        )

    assert repo.list_events("example-co") == []
