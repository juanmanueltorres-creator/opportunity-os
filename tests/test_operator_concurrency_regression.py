from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.operator_bridge.models import ObservationImportRequest, OperatorObservation
from app.operator_bridge.service import OperatorBridgeService
from app.relationships.models import RelationshipAccount
from app.relationships.repository import SQLiteRelationshipRepository
from app.relationships.service import RelationshipService

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


class RacingRelationshipRepository(SQLiteRelationshipRepository):
    inject_concurrent_change = False

    def apply_event_transaction(self, event, projector):
        if self.inject_concurrent_change:
            self.inject_concurrent_change = False
            account = self.get_account(event.account_id)
            assert account is not None
            self.save_account(
                account.model_copy(update={"last_reason": "concurrent state change"})
            )
        return super().apply_event_transaction(event, projector)


def test_state_change_between_preview_recheck_and_record_is_rejected_atomically(
    tmp_path: Path,
) -> None:
    repo = RacingRelationshipRepository(tmp_path / "relationships.sqlite3")
    repo.initialize()
    relationships = RelationshipService(repo)
    relationships.register_account(
        RelationshipAccount(
            account_id="example-co",
            company="Example Co",
            updated_at=NOW - timedelta(days=1),
        )
    )
    bridge = OperatorBridgeService(repo, relationships)
    observation = OperatorObservation(
        observation_id="provider-message-race",
        source_type="EMAIL_PROVIDER",
        source_name="gmail",
        source_ref="message:provider-message-race",
        kind="MESSAGE_SENT",
        account_id="example-co",
        observed_at=NOW,
        reason="authorized normalized fact",
    )
    preview = bridge.preview(observation)
    assert preview.status == "IMPORTABLE"

    repo.inject_concurrent_change = True
    result = bridge.import_observation(
        ObservationImportRequest(
            observation=observation,
            preview_sha256=preview.preview_sha256,
            confirmed_by="operator",
            confirmed_at=NOW,
        ),
        processed_at=NOW,
    )

    assert result.status == "BLOCKED_STALE_PREVIEW"
    assert result.receipt is None
    assert result.errors == ["stale_preview"]
    assert repo.list_events("example-co") == []
    stored = repo.get_account("example-co")
    assert stored is not None
    assert stored.last_reason == "concurrent state change"
    assert stored.relationship_state == "UNTOUCHED"
