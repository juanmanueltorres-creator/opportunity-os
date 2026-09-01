from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest
from pydantic import ValidationError

from app.metrics.history import (
    HistoricalImportBatch,
    HistoricalImportManifest,
    HistoricalObservation,
    SQLiteHistoricalRepository,
)
from app.metrics.import_history import import_manifest_file

UTC = timezone.utc

BASE = {
    "observation_id": "hist-reply-1",
    "kind": "REPLY_OBSERVED",
    "opportunity_id": None,
    "account_id": None,
    "company": "Example Labs",
    "role": None,
    "occurred_at": datetime(2026, 8, 20, tzinfo=UTC),
    "observed_at": datetime(2026, 8, 31, tzinfo=UTC),
    "provenance": "IMPORTED_GMAIL",
    "source_ref": "gmail-message-1",
    "provider_message_id": "m-1",
    "provider_thread_id": "t-1",
    "event_confidence": 1.0,
    "link_confidence": 0.0,
    "reconstruction_note": "provider-confirmed reply; opportunity unmatched",
}


def _observation(**overrides: object) -> HistoricalObservation:
    return HistoricalObservation.model_validate({**BASE, **overrides})


def _batch(**overrides: object) -> HistoricalImportBatch:
    payload = {
        "batch_id": "gmail-august-2026",
        "provider": "GMAIL",
        "window_start": datetime(2026, 8, 1, tzinfo=UTC),
        "window_end": datetime(2026, 9, 1, tzinfo=UTC),
        "selection_scope": "SELECTED_THREADS",
        "selected_message_count": 1,
        "selected_thread_count": 1,
        "completed_at": datetime(2026, 9, 1, tzinfo=UTC),
        "complete_for_declared_scope": True,
    }
    return HistoricalImportBatch.model_validate({**payload, **overrides})


def test_event_certainty_is_separate_from_link_certainty():
    observation = _observation()
    assert observation.event_confidence == 1.0
    assert observation.link_confidence == 0.0


@pytest.mark.parametrize("field", ["body", "subject", "snippet", "access_token", "credentials"])
def test_history_model_rejects_unallowlisted_private_payload_fields(field: str):
    with pytest.raises(ValidationError):
        HistoricalObservation.model_validate({**BASE, field: "private material"})


def test_history_model_rejects_naive_datetimes_and_invalid_confidence():
    with pytest.raises(ValidationError):
        _observation(occurred_at=datetime(2026, 8, 20))
    with pytest.raises(ValidationError):
        _observation(event_confidence=1.01)
    with pytest.raises(ValidationError):
        _observation(link_confidence=-0.01)


def test_history_model_bounds_reconstruction_note():
    with pytest.raises(ValidationError):
        _observation(reconstruction_note="x" * 501)


def test_batch_rejects_reverse_window():
    with pytest.raises(ValidationError):
        _batch(
            window_start=datetime(2026, 9, 2, tzinfo=UTC),
            window_end=datetime(2026, 9, 1, tzinfo=UTC),
        )


def test_identical_observation_import_is_idempotent(tmp_path):
    repo = SQLiteHistoricalRepository(tmp_path / "history.sqlite3")
    repo.initialize()
    observation = _observation()

    stored, inserted = repo.save_observation(observation)
    repeated, inserted_again = repo.save_observation(observation)

    assert inserted is True
    assert inserted_again is False
    assert repeated == stored == observation


def test_conflicting_observation_id_fails_closed(tmp_path):
    repo = SQLiteHistoricalRepository(tmp_path / "history.sqlite3")
    repo.initialize()
    repo.save_observation(_observation())

    with pytest.raises(ValueError, match="historical observation_id conflict"):
        repo.save_observation(_observation(event_confidence=0.5))


def test_identical_batch_import_is_idempotent_and_conflict_safe(tmp_path):
    repo = SQLiteHistoricalRepository(tmp_path / "history.sqlite3")
    repo.initialize()
    batch = _batch()

    _, inserted = repo.save_batch(batch)
    _, inserted_again = repo.save_batch(batch)
    assert inserted is True
    assert inserted_again is False

    with pytest.raises(ValueError, match="historical batch_id conflict"):
        repo.save_batch(_batch(selected_message_count=2))


def test_reading_missing_history_db_has_no_side_effect(tmp_path):
    path = tmp_path / "missing" / "history.sqlite3"
    repo = SQLiteHistoricalRepository(path)

    assert repo.list_observations() == []
    assert repo.list_batches() == []
    assert not path.exists()
    assert not path.parent.exists()


def test_manifest_is_fully_validated_before_database_initialization(tmp_path):
    manifest_path = tmp_path / "history-import.local.json"
    history_db = tmp_path / "state" / "history.local.sqlite3"
    invalid_observation = {
        **BASE,
        "occurred_at": BASE["occurred_at"].isoformat(),
        "observed_at": BASE["observed_at"].isoformat(),
        "body": "must never be imported",
    }
    manifest_path.write_text(
        json.dumps(
            {
                "batch": _batch().model_dump(mode="json"),
                "observations": [invalid_observation],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        import_manifest_file(manifest_path=manifest_path, history_db=history_db)

    assert not history_db.exists()
    assert not history_db.parent.exists()


def test_manifest_import_persists_only_validated_typed_rows(tmp_path):
    manifest_path = tmp_path / "history-import.local.json"
    history_db = tmp_path / "state" / "history.local.sqlite3"
    manifest = HistoricalImportManifest(
        batch=_batch(),
        observations=[_observation()],
    )
    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")

    result = import_manifest_file(manifest_path=manifest_path, history_db=history_db)

    assert result.batch_id == "gmail-august-2026"
    assert result.observations_inserted == 1
    assert result.observations_existing == 0
    assert history_db.exists()

    repo = SQLiteHistoricalRepository(history_db)
    assert repo.list_observations() == [_observation()]
    assert repo.list_batches() == [_batch()]
