from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

from app.metrics.history import (
    HistoricalImportBatch,
    HistoricalImportManifest,
    SQLiteHistoricalRepository,
)
from app.metrics.import_history import import_manifest_file
from app.metrics.models import ReportWindow
from app.metrics.projection import MetricsInput, project_search_health
from app.metrics.sources import MetricFact, SourceRead

UTC = timezone.utc
START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 30, tzinfo=UTC)
WINDOW = ReportWindow(start=START, end=END)


def _source(items=(), coverage="COMPLETE", *, basis="fixture"):
    return SourceRead(items=tuple(items), coverage=coverage, basis=(basis,))


def _batch() -> HistoricalImportBatch:
    return HistoricalImportBatch(
        batch_id="experiment-september-2026",
        provider="MANUAL",
        window_start=START,
        window_end=END,
        selection_scope="SELECTED_THREADS",
        selected_message_count=0,
        selected_thread_count=0,
        completed_at=END,
        complete_for_declared_scope=False,
    )


def _experiment_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "case_id": "exp-1",
        "opportunity_id": "opp-1",
        "account_id": "account-1",
        "outreach_type": "APPLICATION_PLUS_DIRECT",
        "evidence_used": ["sanjuangeo", "github-pr"],
        "outcome": "TECHNICAL",
        "observed_at": datetime(2026, 9, 10, tzinfo=UTC).isoformat(),
    }
    payload.update(overrides)
    return payload


def test_historical_manifest_accepts_backward_compatible_experiment_cases():
    manifest = HistoricalImportManifest.model_validate(
        {
            "batch": _batch().model_dump(mode="json"),
            "observations": [],
            "experiments": [_experiment_payload()],
        }
    )

    case = manifest.experiments[0]
    assert case.case_id == "exp-1"
    assert case.outreach_type == "APPLICATION_PLUS_DIRECT"
    assert case.evidence_used == ["sanjuangeo", "github-pr"]
    assert case.outcome == "TECHNICAL"

    legacy = HistoricalImportManifest.model_validate(
        {
            "batch": _batch().model_dump(mode="json"),
            "observations": [],
        }
    )
    assert legacy.experiments == []


def test_manifest_import_persists_experiment_cases_idempotently(tmp_path):
    manifest_path = tmp_path / "history-import.local.json"
    history_db = tmp_path / "state" / "history.local.sqlite3"
    payload = {
        "batch": _batch().model_dump(mode="json"),
        "observations": [],
        "experiments": [_experiment_payload()],
    }
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    first = import_manifest_file(manifest_path=manifest_path, history_db=history_db)
    second = import_manifest_file(manifest_path=manifest_path, history_db=history_db)

    assert first.experiments_inserted == 1
    assert first.experiments_existing == 0
    assert second.experiments_inserted == 0
    assert second.experiments_existing == 1

    repository = SQLiteHistoricalRepository(history_db)
    stored = repository.list_experiments()
    assert len(stored) == 1
    assert stored[0].case_id == "exp-1"


def test_search_health_groups_experiment_funnel_by_outreach_type():
    app_only = SimpleNamespace(
        case_id="exp-app-only",
        opportunity_id="opp-a",
        account_id="account-a",
        outreach_type="APPLICATION_ONLY",
        evidence_used=("cv",),
        outcome="NO_RESPONSE",
        observed_at=datetime(2026, 9, 5, tzinfo=UTC),
    )
    app_plus_direct = SimpleNamespace(
        case_id="exp-app-direct",
        opportunity_id="opp-b",
        account_id="account-b",
        outreach_type="APPLICATION_PLUS_DIRECT",
        evidence_used=("cv", "sanjuangeo"),
        outcome="TECHNICAL",
        observed_at=datetime(2026, 9, 6, tzinfo=UTC),
    )
    reply = MetricFact(
        fact_id="reply-b",
        kind="REPLY",
        opportunity_id=None,
        account_id="account-b",
        occurred_at=datetime(2026, 9, 7, tzinfo=UTC),
        evidence_class="NATIVE",
        exact_anchor="source:reply-b",
        link_confidence=1.0,
    )
    process = MetricFact(
        fact_id="process-b",
        kind="PROCESS_OPENED",
        opportunity_id=None,
        account_id="account-b",
        occurred_at=datetime(2026, 9, 8, tzinfo=UTC),
        evidence_class="NATIVE",
        exact_anchor="source:process-b",
        link_confidence=1.0,
    )

    inputs = MetricsInput(
        opportunities=_source(),
        qualifications=_source(),
        packets=_source(),
        outreach=_source(),
        relationships=_source([reply, process]),
        history=_source(coverage="UNKNOWN"),
        experiments=_source(
            [app_only, app_plus_direct],
            coverage="PARTIAL",
            basis="manual_experiment_cases",
        ),
    )

    report = project_search_health(inputs, WINDOW, generated_at=END)
    cohorts = {cohort.outreach_type: cohort for cohort in report.experiments.cohorts}

    assert report.experiments.coverage == "PARTIAL"
    assert cohorts["APPLICATION_ONLY"].cases == 1
    assert cohorts["APPLICATION_ONLY"].replies == 0
    assert cohorts["APPLICATION_ONLY"].processes == 0
    assert cohorts["APPLICATION_ONLY"].outcomes == {"NO_RESPONSE": 1}

    assert cohorts["APPLICATION_PLUS_DIRECT"].cases == 1
    assert cohorts["APPLICATION_PLUS_DIRECT"].replies == 1
    assert cohorts["APPLICATION_PLUS_DIRECT"].processes == 1
    assert cohorts["APPLICATION_PLUS_DIRECT"].outcomes == {"TECHNICAL": 1}
