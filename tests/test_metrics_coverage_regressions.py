from datetime import datetime, timezone

from app.metrics.history import HistoricalImportBatch
from app.metrics.models import ReportWindow
from app.metrics.projection import MetricsInput, project_search_health
from app.metrics.sources import MetricFact, SourceRead

UTC = timezone.utc
START = datetime(2026, 8, 1, tzinfo=UTC)
END = datetime(2026, 9, 1, tzinfo=UTC)
WINDOW = ReportWindow(start=START, end=END)


def _fact(
    fact_id: str,
    *,
    kind: str,
    opportunity_id: str,
    exact_anchor: str,
    thread_anchor: str,
    evidence_class: str = "NATIVE",
) -> MetricFact:
    return MetricFact(
        fact_id=fact_id,
        kind=kind,
        opportunity_id=opportunity_id,
        account_id=None,
        occurred_at=datetime(2026, 8, 20, tzinfo=UTC),
        evidence_class=evidence_class,
        exact_anchor=exact_anchor,
        link_confidence=1.0,
        thread_anchor=thread_anchor,
    )


def test_complete_reply_history_cannot_upgrade_partial_send_denominator():
    sends = (
        _fact(
            "send-a",
            kind="SEND",
            opportunity_id="opp-a",
            exact_anchor="gmail-message:m-a",
            thread_anchor="gmail-thread:t-a",
        ),
        _fact(
            "send-b",
            kind="SEND",
            opportunity_id="opp-b",
            exact_anchor="gmail-message:m-b",
            thread_anchor="gmail-thread:t-b",
        ),
    )
    reply = _fact(
        "reply-a",
        kind="REPLY",
        opportunity_id="opp-a",
        exact_anchor="gmail-message:r-a",
        thread_anchor="gmail-thread:t-a",
        evidence_class="IMPORTED_PROVIDER",
    )
    complete_batch = HistoricalImportBatch(
        batch_id="complete-window",
        provider="GMAIL",
        window_start=START,
        window_end=END,
        selection_scope="ALL_DECLARED_OUTREACH_THREADS",
        selected_message_count=3,
        selected_thread_count=2,
        completed_at=END,
        complete_for_declared_scope=True,
    )

    report = project_search_health(
        MetricsInput(
            opportunities=SourceRead(items=(), coverage="UNKNOWN"),
            qualifications=SourceRead(items=(), coverage="UNKNOWN"),
            packets=SourceRead(items=(), coverage="UNKNOWN"),
            outreach=SourceRead(items=sends, coverage="PARTIAL"),
            relationships=SourceRead(items=(), coverage="COMPLETE"),
            history=SourceRead(items=(reply,), coverage="COMPLETE"),
            history_batches=(complete_batch,),
        ),
        WINDOW,
        generated_at=END,
    )

    metric = report.ratios.send_to_reply_rate
    assert report.coverage.outreach == "PARTIAL"
    assert metric.coverage == "PARTIAL"
    assert metric.value is None
    assert metric.numerator == 1
    assert metric.denominator == 2
