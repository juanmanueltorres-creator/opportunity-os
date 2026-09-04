from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from app.contributions.models import ContributionEvent, PublicContributionEntry
from app.contributions.observations import ContributionImportReceipt
from app.contributions.projector import ContributionProjector
from app.contributions.repository import SQLiteContributionRepository

NOW = datetime(2026, 9, 4, 7, 0, tzinfo=timezone.utc)
TASK = "https://github.com/owner/repo/issues/1"
PR = "https://github.com/owner/repo/pull/2"


def entry(**overrides) -> PublicContributionEntry:
    payload = dict(
        entry_id="contrib-1",
        repository_full_name="owner/repo",
        repository_url="https://github.com/owner/repo",
        origin="PUBLIC_ISSUE",
        need_basis="OBSERVED",
        need_statement="Bug",
        evidence_refs=[TASK],
        task_ref=TASK,
        bounded_task="Bug",
        task_claim_state="AVAILABLE",
        discovered_at=NOW,
    )
    payload.update(overrides)
    return PublicContributionEntry(**payload)


def event(*, event_id="event-1", observed_at=NOW, kind="TASK_CLAIMED_SELF", **overrides):
    payload = dict(
        event_id=event_id,
        entry_id="contrib-1",
        kind=kind,
        source_type="PUBLIC_GITHUB",
        source_ref=TASK,
        observed_at=observed_at,
        task_ref=TASK,
    )
    payload.update(overrides)
    return ContributionEvent(**payload)


def receipt(*, observation_id="obs-1", receipt_id="receipt-1", event_id=None, **overrides):
    payload = dict(
        receipt_id=receipt_id,
        observation_id=observation_id,
        observation_sha256="a" * 64,
        preview_sha256="b" * 64,
        entry_id="contrib-1",
        contribution_event_id=event_id,
        source_ref=TASK,
        confirmed_by="juan",
        confirmed_at=NOW,
        processed_at=NOW,
        status="IMPORTED",
    )
    payload.update(overrides)
    return ContributionImportReceipt(**payload)


def test_missing_db_reads_are_side_effect_free(tmp_path: Path):
    db = tmp_path / "nested" / "contributions.sqlite3"
    repo = SQLiteContributionRepository(db)
    assert repo.get_entry("missing") is None
    assert repo.get_event("missing") is None
    assert repo.list_events("missing") == []
    assert repo.get_receipt_for_observation("missing") is None
    assert not db.exists()
    assert not db.parent.exists()


def test_initialize_creates_exact_three_tables(tmp_path: Path):
    db = tmp_path / "contributions.sqlite3"
    repo = SQLiteContributionRepository(db)
    repo.initialize()
    with sqlite3.connect(db) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    assert tables == {
        "contribution_entries",
        "contribution_events",
        "contribution_import_receipts",
    }


def test_write_requires_explicit_initialize(tmp_path: Path):
    repo = SQLiteContributionRepository(tmp_path / "missing.sqlite3")
    with pytest.raises(RuntimeError, match="not initialized"):
        repo.insert_entry_with_receipt(entry(), receipt())


def test_identical_entry_and_receipt_replay_is_idempotent(tmp_path: Path):
    repo = SQLiteContributionRepository(tmp_path / "db.sqlite3")
    repo.initialize()
    first_entry, first_receipt, inserted = repo.insert_entry_with_receipt(entry(), receipt())
    assert inserted is True
    again_entry, again_receipt, inserted = repo.insert_entry_with_receipt(entry(), receipt())
    assert inserted is False
    assert again_entry == first_entry
    assert again_receipt == first_receipt


def test_entry_id_conflict_is_rejected(tmp_path: Path):
    repo = SQLiteContributionRepository(tmp_path / "db.sqlite3")
    repo.initialize()
    repo.insert_entry_with_receipt(entry(), receipt())
    with pytest.raises(ValueError, match="contribution entry_id conflict"):
        repo.insert_entry_with_receipt(
            entry(need_statement="Different", bounded_task="Different"),
            receipt(observation_id="obs-2", receipt_id="receipt-2"),
        )


def test_events_list_in_deterministic_order(tmp_path: Path):
    repo = SQLiteContributionRepository(tmp_path / "db.sqlite3")
    repo.initialize()
    repo.insert_entry_with_receipt(entry(), receipt())
    e1 = event(event_id="a", observed_at=NOW + timedelta(seconds=1))
    e2 = event(event_id="b", observed_at=NOW + timedelta(seconds=2), kind="TASK_RELEASED")
    repo.append_event_with_receipt(
        e1,
        receipt(observation_id="obs-e1", receipt_id="r-e1", event_id="a"),
        ContributionProjector(),
    )
    repo.append_event_with_receipt(
        e2,
        receipt(observation_id="obs-e2", receipt_id="r-e2", event_id="b"),
        ContributionProjector(),
    )
    assert [item.event_id for item in repo.list_events("contrib-1")] == ["a", "b"]


def test_out_of_order_event_is_rejected(tmp_path: Path):
    repo = SQLiteContributionRepository(tmp_path / "db.sqlite3")
    repo.initialize()
    repo.insert_entry_with_receipt(entry(), receipt())
    later = event(event_id="later", observed_at=NOW + timedelta(seconds=2))
    repo.append_event_with_receipt(
        later,
        receipt(observation_id="obs-later", receipt_id="r-later", event_id="later"),
        ContributionProjector(),
    )
    earlier = event(event_id="earlier", observed_at=NOW + timedelta(seconds=1))
    with pytest.raises(ValueError, match="out-of-order contribution event"):
        repo.append_event_with_receipt(
            earlier,
            receipt(observation_id="obs-earlier", receipt_id="r-earlier", event_id="earlier"),
            ContributionProjector(),
        )


def test_identical_event_replay_is_idempotent(tmp_path: Path):
    repo = SQLiteContributionRepository(tmp_path / "db.sqlite3")
    repo.initialize()
    repo.insert_entry_with_receipt(entry(), receipt())
    e = event()
    r = receipt(observation_id="obs-event", receipt_id="receipt-event", event_id=e.event_id)
    _, _, inserted = repo.append_event_with_receipt(e, r, ContributionProjector())
    assert inserted is True
    stored, stored_receipt, inserted = repo.append_event_with_receipt(e, r, ContributionProjector())
    assert inserted is False
    assert stored == e
    assert stored_receipt == r


def test_same_event_id_with_changed_payload_conflicts(tmp_path: Path):
    repo = SQLiteContributionRepository(tmp_path / "db.sqlite3")
    repo.initialize()
    repo.insert_entry_with_receipt(entry(), receipt())
    e = event()
    repo.append_event_with_receipt(
        e,
        receipt(observation_id="obs-event", receipt_id="receipt-event", event_id=e.event_id),
        ContributionProjector(),
    )
    changed = event(actor_ref="someone")
    with pytest.raises(ValueError, match="contribution event_id conflict"):
        repo.append_event_with_receipt(
            changed,
            receipt(observation_id="obs-2", receipt_id="receipt-2", event_id=changed.event_id),
            ContributionProjector(),
        )


def _seed_conflicting_receipt(db: Path, *, observation_id: str, entry_id: str = "other"):
    seeded = receipt(
        observation_id=observation_id,
        receipt_id="seeded-receipt",
        entry_id=entry_id,
        observation_sha256="c" * 64,
    )
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO contribution_import_receipts (receipt_id, observation_id, entry_id, payload_json, processed_at) VALUES (?, ?, ?, ?, ?)",
            (
                seeded.receipt_id,
                seeded.observation_id,
                seeded.entry_id,
                seeded.model_dump_json(),
                seeded.processed_at.isoformat(),
            ),
        )


def test_conflicting_receipt_rolls_back_new_entry(tmp_path: Path):
    db = tmp_path / "db.sqlite3"
    repo = SQLiteContributionRepository(db)
    repo.initialize()
    _seed_conflicting_receipt(db, observation_id="obs-1")
    with pytest.raises(ValueError, match="contribution receipt observation conflict"):
        repo.insert_entry_with_receipt(entry(), receipt())
    assert repo.get_entry("contrib-1") is None


def test_conflicting_receipt_rolls_back_new_event(tmp_path: Path):
    db = tmp_path / "db.sqlite3"
    repo = SQLiteContributionRepository(db)
    repo.initialize()
    repo.insert_entry_with_receipt(entry(), receipt(observation_id="entry-obs"))
    _seed_conflicting_receipt(db, observation_id="obs-event")
    e = event()
    with pytest.raises(ValueError, match="contribution receipt observation conflict"):
        repo.append_event_with_receipt(
            e,
            receipt(observation_id="obs-event", receipt_id="receipt-event", event_id=e.event_id),
            ContributionProjector(),
        )
    assert repo.get_event(e.event_id) is None


def test_candidate_sequence_is_projected_before_commit(tmp_path: Path):
    repo = SQLiteContributionRepository(tmp_path / "db.sqlite3")
    repo.initialize()
    repo.insert_entry_with_receipt(entry(), receipt())
    invalid = ContributionEvent(
        event_id="merge-without-open",
        entry_id="contrib-1",
        kind="PR_MERGED",
        source_type="PUBLIC_GITHUB",
        source_ref=PR,
        observed_at=NOW + timedelta(seconds=1),
        work_ref=PR,
    )
    with pytest.raises(ValueError, match="prior PR_OPENED"):
        repo.append_event_with_receipt(
            invalid,
            receipt(
                observation_id="obs-merge",
                receipt_id="r-merge",
                event_id=invalid.event_id,
                source_ref=PR,
            ),
            ContributionProjector(),
        )
    assert repo.get_event(invalid.event_id) is None
