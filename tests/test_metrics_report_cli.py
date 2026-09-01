from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.metrics.history import HistoricalImportBatch, HistoricalObservation, SQLiteHistoricalRepository
from app.metrics.report import main

UTC = timezone.utc


def _base_args(tmp_path):
    return [
        "--from",
        "2026-08-01",
        "--as-of",
        "2026-08-31T23:00:00+00:00",
        "--opportunity-db",
        str(tmp_path / "opportunity-source" / "opportunities.sqlite3"),
        "--relationships-db",
        str(tmp_path / "relationship-source" / "relationships.sqlite3"),
        "--outreach-db",
        str(tmp_path / "outreach-source" / "outreach.sqlite3"),
        "--history-db",
        str(tmp_path / "history-source" / "history.sqlite3"),
        "--applications-root",
        str(tmp_path / "application-source" / "applications"),
        "--radar-root",
        str(tmp_path / "radar-source" / "radar"),
        "--output",
        str(tmp_path / "reports" / "search-health.json"),
    ]


def test_cli_fixed_as_of_writes_deterministic_aggregate_json(tmp_path, capsys):
    args = _base_args(tmp_path)

    assert main(args) == 0
    first_stdout = capsys.readouterr().out
    output = tmp_path / "reports" / "search-health.json"
    first_bytes = output.read_bytes()

    assert main(args) == 0
    second_stdout = capsys.readouterr().out
    second_bytes = output.read_bytes()

    assert first_bytes == second_bytes
    assert first_stdout == second_stdout

    payload = json.loads(first_bytes)
    assert payload["report_version"] == "search-health-v1"
    assert payload["generated_at"] == "2026-08-31T23:00:00Z"
    assert payload["window"]["start"] == "2026-08-01T00:00:00Z"
    assert payload["window"]["end"] == "2026-08-31T23:00:00Z"
    assert "unknown" in first_stdout.lower()


def test_cli_missing_sources_are_not_created_by_reporting(tmp_path):
    args = _base_args(tmp_path)

    assert main(args) == 0

    for directory in (
        "opportunity-source",
        "relationship-source",
        "outreach-source",
        "history-source",
        "application-source",
        "radar-source",
    ):
        assert not (tmp_path / directory).exists()
    assert (tmp_path / "reports" / "search-health.json").exists()


def test_cli_rejects_reverse_window(tmp_path):
    args = _base_args(tmp_path)
    args[1] = "2026-09-01"

    with pytest.raises(SystemExit) as exc:
        main(args)

    assert exc.value.code != 0


def test_cli_rejects_to_and_as_of_together(tmp_path):
    args = _base_args(tmp_path)
    args.extend(["--to", "2026-08-31"])

    with pytest.raises(SystemExit) as exc:
        main(args)

    assert exc.value.code != 0


def test_aggregate_json_does_not_serialize_private_historical_identifiers(tmp_path):
    history_path = tmp_path / "history.sqlite3"
    repository = SQLiteHistoricalRepository(history_path)
    repository.initialize()
    start = datetime(2026, 8, 1, tzinfo=UTC)
    end = datetime(2026, 8, 31, 23, tzinfo=UTC)
    repository.save_batch(
        HistoricalImportBatch(
            batch_id="private-batch-id",
            provider="GMAIL",
            window_start=start,
            window_end=end,
            selection_scope="SELECTED_THREADS",
            selected_message_count=1,
            selected_thread_count=1,
            completed_at=end,
            complete_for_declared_scope=True,
        )
    )
    repository.save_observation(
        HistoricalObservation(
            observation_id="private-observation-id",
            kind="REPLY_OBSERVED",
            opportunity_id=None,
            account_id=None,
            company="Private Company Name",
            role="Private Role Name",
            occurred_at=datetime(2026, 8, 20, tzinfo=UTC),
            observed_at=end,
            provenance="IMPORTED_GMAIL",
            source_ref="private-source-ref",
            provider_message_id="private-message-id",
            provider_thread_id="private-thread-id",
            event_confidence=1.0,
            link_confidence=0.0,
            reconstruction_note="private reconstruction note",
        )
    )

    output = tmp_path / "reports" / "search-health.json"
    args = [
        "--from",
        "2026-08-01",
        "--as-of",
        "2026-08-31T23:00:00+00:00",
        "--history-db",
        str(history_path),
        "--opportunity-db",
        str(tmp_path / "missing-opportunities.sqlite3"),
        "--relationships-db",
        str(tmp_path / "missing-relationships.sqlite3"),
        "--outreach-db",
        str(tmp_path / "missing-outreach.sqlite3"),
        "--applications-root",
        str(tmp_path / "missing-applications"),
        "--radar-root",
        str(tmp_path / "missing-radar"),
        "--output",
        str(output),
    ]

    assert main(args) == 0
    text = output.read_text(encoding="utf-8")

    for forbidden in (
        "private-batch-id",
        "private-observation-id",
        "Private Company Name",
        "Private Role Name",
        "private-source-ref",
        "private-message-id",
        "private-thread-id",
        "private reconstruction note",
    ):
        assert forbidden not in text
