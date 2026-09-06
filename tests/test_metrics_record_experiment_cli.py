from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from app.metrics.history import SQLiteHistoricalRepository

ROOT = Path(__file__).resolve().parents[1]


def _run_cli(history_db: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "app.metrics.record_experiment",
            "--history-db",
            str(history_db),
            *args,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_record_experiment_cli_persists_one_initial_case(tmp_path):
    history_db = tmp_path / "state" / "history.local.sqlite3"

    result = _run_cli(
        history_db,
        "--opportunity-id",
        "opp-geospatial-1",
        "--outreach-type",
        "APPLICATION_PLUS_DIRECT",
        "--evidence",
        "cv",
        "--evidence",
        "sanjuangeo",
        "--observed-at",
        "2026-09-06T02:00:00+00:00",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "case_id": "search-experiment:opp-geospatial-1",
        "evidence_used": ["cv", "sanjuangeo"],
        "observed_at": "2026-09-06T02:00:00Z",
        "opportunity_id": "opp-geospatial-1",
        "outreach_type": "APPLICATION_PLUS_DIRECT",
        "status": "RECORDED",
    }

    stored = SQLiteHistoricalRepository(history_db).list_experiments()
    assert len(stored) == 1
    assert stored[0].case_id == "search-experiment:opp-geospatial-1"
    assert stored[0].opportunity_id == "opp-geospatial-1"
    assert stored[0].outcome is None


def test_record_experiment_cli_is_idempotent_for_same_strategy(tmp_path):
    history_db = tmp_path / "state" / "history.local.sqlite3"
    common = (
        "--opportunity-id",
        "opp-geospatial-2",
        "--outreach-type",
        "DIRECT_ONLY",
        "--evidence",
        "github-pr",
    )

    first = _run_cli(
        history_db,
        *common,
        "--observed-at",
        "2026-09-06T02:00:00+00:00",
    )
    second = _run_cli(
        history_db,
        *common,
        "--observed-at",
        "2026-09-06T05:00:00+00:00",
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["status"] == "EXISTING"

    stored = SQLiteHistoricalRepository(history_db).list_experiments()
    assert len(stored) == 1
    assert stored[0].observed_at.isoformat() == "2026-09-06T02:00:00+00:00"


def test_record_experiment_cli_fails_closed_if_strategy_changes(tmp_path):
    history_db = tmp_path / "state" / "history.local.sqlite3"

    first = _run_cli(
        history_db,
        "--opportunity-id",
        "opp-geospatial-3",
        "--outreach-type",
        "APPLICATION_ONLY",
        "--evidence",
        "cv",
        "--observed-at",
        "2026-09-06T02:00:00+00:00",
    )
    conflict = _run_cli(
        history_db,
        "--opportunity-id",
        "opp-geospatial-3",
        "--outreach-type",
        "APPLICATION_PLUS_DIRECT",
        "--evidence",
        "cv",
        "--evidence",
        "sanjuangeo",
        "--observed-at",
        "2026-09-06T03:00:00+00:00",
    )

    assert first.returncode == 0, first.stderr
    assert conflict.returncode == 2
    assert json.loads(conflict.stdout) == {
        "error": "experiment_case_conflict",
        "status": "ERROR",
    }

    stored = SQLiteHistoricalRepository(history_db).list_experiments()
    assert len(stored) == 1
    assert stored[0].outreach_type == "APPLICATION_ONLY"
