from datetime import datetime, timezone

from app.metrics.history import HistoricalImportBatch
from app.metrics.models import ReportWindow
from app.metrics.projection import MetricsInput, project_search_health
from app.metrics.sources import MetricFact, OpportunityFact, QualificationFact, SourceRead

UTC = timezone.utc
START = datetime(2026, 8, 1, tzinfo=UTC)
END = datetime(2026, 9, 1, tzinfo=UTC)
WINDOW = ReportWindow(start=START, end=END)


def _source(items=(), coverage="COMPLETE", *, basis="fixture"):
    return SourceRead(items=tuple(items), coverage=coverage, basis=(basis,))


def _fact(
    fact_id: str,
    *,
    kind: str,
    opportunity_id: str | None = None,
    account_id: str | None = None,
    evidence_class: str = "NATIVE",
    exact_anchor: str | None = None,
    link_confidence: float = 1.0,
    draft_sha256: str | None = None,
    thread_anchor: str | None = None,
    occurred_at: datetime = datetime(2026, 8, 20, tzinfo=UTC),
):
    return MetricFact(
        fact_id=fact_id,
        kind=kind,
        opportunity_id=opportunity_id,
        account_id=account_id,
        occurred_at=occurred_at,
        evidence_class=evidence_class,
        exact_anchor=exact_anchor,
        link_confidence=link_confidence,
        draft_sha256=draft_sha256,
        thread_anchor=thread_anchor,
    )


def _complete_history_batch() -> HistoricalImportBatch:
    return HistoricalImportBatch(
        batch_id="complete-august",
        provider="GMAIL",
        window_start=START,
        window_end=END,
        selection_scope="ALL_DECLARED_OUTREACH_THREADS",
        selected_message_count=20,
        selected_thread_count=10,
        completed_at=END,
        complete_for_declared_scope=True,
    )


def _selected_history_batch() -> HistoricalImportBatch:
    return HistoricalImportBatch(
        batch_id="selected-august",
        provider="GMAIL",
        window_start=START,
        window_end=END,
        selection_scope="SELECTED_THREADS",
        selected_message_count=3,
        selected_thread_count=2,
        completed_at=END,
        complete_for_declared_scope=True,
    )


def _inputs(
    *,
    opportunities=(),
    opportunity_coverage="COMPLETE",
    qualifications=(),
    qualification_coverage="COMPLETE",
    packets=(),
    packet_coverage="COMPLETE",
    outreach=(),
    outreach_coverage="COMPLETE",
    relationships=(),
    relationship_coverage="COMPLETE",
    history=(),
    history_coverage="UNKNOWN",
    history_batches=(),
):
    return MetricsInput(
        opportunities=_source(opportunities, opportunity_coverage, basis="opportunity_db"),
        qualifications=_source(qualifications, qualification_coverage, basis="radar"),
        packets=_source(packets, packet_coverage, basis="applications"),
        outreach=_source(outreach, outreach_coverage, basis="outreach"),
        relationships=_source(relationships, relationship_coverage, basis="relationships"),
        history=_source(history, history_coverage, basis="history"),
        history_batches=tuple(history_batches),
    )


def _project(inputs: MetricsInput):
    return project_search_health(inputs, WINDOW, generated_at=END)


def test_persisted_opportunity_counts_once_and_unknown_radar_stays_unknown():
    report = _project(
        _inputs(
            opportunities=[OpportunityFact("opp-1", datetime(2026, 8, 5, tzinfo=UTC))],
            qualifications=(),
            qualification_coverage="UNKNOWN",
        )
    )

    assert report.counts.opportunities_observed.value == 1
    assert report.counts.opportunities_new.value == 1
    assert report.counts.opportunities_observed.coverage == "COMPLETE"
    assert report.counts.qualified_high.value is None
    assert report.counts.qualified_medium.value is None
    assert report.counts.qualified_high.coverage == "UNKNOWN"
    assert report.ratios.qualification_rate.value is None
    assert report.coverage.radar == "UNKNOWN"


def test_partial_qualification_history_emits_lower_bound_counts_without_rate():
    report = _project(
        _inputs(
            opportunities=[
                OpportunityFact("opp-1", datetime(2026, 8, 5, tzinfo=UTC)),
                OpportunityFact("opp-2", datetime(2026, 8, 6, tzinfo=UTC)),
                OpportunityFact("opp-3", datetime(2026, 8, 7, tzinfo=UTC)),
            ],
            qualifications=[
                QualificationFact("opp-1", "MEDIUM", datetime(2026, 8, 8, tzinfo=UTC), "v1"),
                QualificationFact("opp-1", "HIGH", datetime(2026, 8, 9, tzinfo=UTC), "v2"),
                QualificationFact("opp-2", "MEDIUM", datetime(2026, 8, 9, tzinfo=UTC), "v2"),
            ],
            qualification_coverage="PARTIAL",
        )
    )

    assert report.counts.qualified_high.value == 1
    assert report.counts.qualified_medium.value == 1
    assert report.counts.qualified_high.coverage == "PARTIAL"
    assert report.ratios.qualification_rate.value is None
    assert any("multiple scoring versions" in warning for warning in report.warnings)


def test_complete_qualification_history_uses_observed_opportunity_denominator():
    report = _project(
        _inputs(
            opportunities=[
                OpportunityFact("opp-1", datetime(2026, 8, 5, tzinfo=UTC)),
                OpportunityFact("opp-2", datetime(2026, 8, 6, tzinfo=UTC)),
            ],
            qualifications=[
                QualificationFact("opp-1", "HIGH", datetime(2026, 8, 8, tzinfo=UTC), "v1"),
                QualificationFact("opp-2", "DISCARD", datetime(2026, 8, 8, tzinfo=UTC), "v1"),
            ],
            qualification_coverage="COMPLETE",
        )
    )

    metric = report.ratios.qualification_rate
    assert metric.numerator == 1
    assert metric.denominator == 2
    assert metric.value == 0.5
    assert metric.coverage == "COMPLETE"


def test_packet_count_uses_only_packet_prepared_facts():
    report = _project(
        _inputs(
            packets=[
                _fact("packet-1", kind="PACKET_PREPARED", opportunity_id="opp-1"),
                _fact("not-a-packet", kind="SEND", opportunity_id="opp-1"),
            ]
        )
    )

    assert report.counts.packets_prepared.value == 1


def test_exact_native_and_imported_duplicate_send_counts_once():
    native = _fact(
        "native-send",
        kind="SEND",
        opportunity_id="opp-1",
        exact_anchor="gmail-message:m-1",
        evidence_class="NATIVE",
        draft_sha256="a" * 64,
        thread_anchor="gmail-thread:t-1",
    )
    imported = _fact(
        "historical-send",
        kind="SEND",
        opportunity_id="opp-1",
        exact_anchor="gmail-message:m-1",
        evidence_class="IMPORTED_PROVIDER",
        thread_anchor="gmail-thread:t-1",
    )
    report = _project(
        _inputs(
            outreach=[native],
            history=[imported],
            history_coverage="PARTIAL",
            history_batches=[_selected_history_batch()],
        )
    )

    assert report.counts.confirmed_sends.value == 1
    assert report.counts.confirmed_sends.coverage == "PARTIAL"


def test_unmatched_historical_reply_is_counted_as_partial_but_cannot_inflate_ratio():
    reply = _fact(
        "historical-reply",
        kind="REPLY",
        opportunity_id=None,
        account_id=None,
        exact_anchor="gmail-message:r-1",
        evidence_class="IMPORTED_PROVIDER",
        link_confidence=0.0,
        thread_anchor="gmail-thread:t-1",
    )
    report = _project(
        _inputs(
            history=[reply],
            history_coverage="PARTIAL",
            history_batches=[_selected_history_batch()],
        )
    )

    assert report.counts.replies_observed.value == 1
    assert report.counts.replies_observed.coverage == "PARTIAL"
    assert report.ratios.send_to_reply_rate.value is None
    assert report.ratios.send_to_reply_rate.numerator == 0
    assert report.ratios.send_to_reply_rate.denominator == 0


def test_draft_to_send_uses_verified_native_draft_cohort():
    draft_a = _fact(
        "draft-a",
        kind="DRAFT",
        opportunity_id="opp-1",
        exact_anchor=f"draft:{'a' * 64}",
        draft_sha256="a" * 64,
    )
    draft_b = _fact(
        "draft-b",
        kind="DRAFT",
        opportunity_id="opp-2",
        exact_anchor=f"draft:{'b' * 64}",
        draft_sha256="b" * 64,
    )
    send_a = _fact(
        "send-a",
        kind="SEND",
        opportunity_id="opp-1",
        exact_anchor="gmail-message:m-a",
        draft_sha256="a" * 64,
        thread_anchor="gmail-thread:t-a",
    )

    report = _project(_inputs(outreach=[draft_a, draft_b, send_a]))

    metric = report.ratios.draft_to_send_rate
    assert report.counts.drafts_verified.value == 2
    assert report.counts.confirmed_sends.value == 1
    assert metric.numerator == 1
    assert metric.denominator == 2
    assert metric.value == 0.5
    assert metric.coverage == "COMPLETE"


def test_send_to_reply_uses_complete_declared_reply_observation_cohort():
    sends = [
        _fact(
            "send-a",
            kind="SEND",
            opportunity_id="opp-1",
            exact_anchor="gmail-message:m-a",
            draft_sha256="a" * 64,
            thread_anchor="gmail-thread:t-a",
        ),
        _fact(
            "send-b",
            kind="SEND",
            opportunity_id="opp-2",
            exact_anchor="gmail-message:m-b",
            draft_sha256="b" * 64,
            thread_anchor="gmail-thread:t-b",
        ),
    ]
    reply = _fact(
        "reply-a",
        kind="REPLY",
        opportunity_id="opp-1",
        exact_anchor="gmail-message:r-a",
        evidence_class="IMPORTED_PROVIDER",
        thread_anchor="gmail-thread:t-a",
    )

    report = _project(
        _inputs(
            outreach=sends,
            history=[reply],
            history_coverage="COMPLETE",
            history_batches=[_complete_history_batch()],
        )
    )

    metric = report.ratios.send_to_reply_rate
    assert metric.numerator == 1
    assert metric.denominator == 2
    assert metric.value == 0.5
    assert metric.coverage == "COMPLETE"
    assert report.coverage.replies == "COMPLETE"


def test_selected_thread_history_does_not_turn_all_sends_into_reply_denominator():
    sends = [
        _fact(
            "send-a",
            kind="SEND",
            opportunity_id="opp-1",
            exact_anchor="gmail-message:m-a",
            thread_anchor="gmail-thread:t-a",
        ),
        _fact(
            "send-b",
            kind="SEND",
            opportunity_id="opp-2",
            exact_anchor="gmail-message:m-b",
            thread_anchor="gmail-thread:t-b",
        ),
    ]
    reply = _fact(
        "reply-a",
        kind="REPLY",
        opportunity_id="opp-1",
        exact_anchor="gmail-message:r-a",
        evidence_class="IMPORTED_PROVIDER",
        thread_anchor="gmail-thread:t-a",
    )

    report = _project(
        _inputs(
            outreach=sends,
            history=[reply],
            history_coverage="PARTIAL",
            history_batches=[_selected_history_batch()],
        )
    )

    metric = report.ratios.send_to_reply_rate
    assert metric.value is None
    assert metric.numerator == 0
    assert metric.denominator == 0
    assert metric.coverage == "PARTIAL"


def test_reply_to_process_uses_exact_account_lineage_when_outcome_scope_is_complete():
    reply = _fact(
        "reply-native",
        kind="REPLY",
        account_id="account-1",
        exact_anchor="source:reply-1",
    )
    process = _fact(
        "process-native",
        kind="PROCESS_OPENED",
        account_id="account-1",
        exact_anchor="source:process-1",
    )

    report = _project(
        _inputs(
            relationships=[reply, process],
            history_coverage="COMPLETE",
            history_batches=[_complete_history_batch()],
        )
    )

    metric = report.ratios.reply_to_process_rate
    assert metric.numerator == 1
    assert metric.denominator == 1
    assert metric.value == 1.0
    assert metric.coverage == "COMPLETE"
    assert report.counts.processes_opened.value == 1


def test_zero_denominator_remains_unknown_instead_of_zero_percent():
    report = _project(
        _inputs(
            history_coverage="COMPLETE",
            history_batches=[_complete_history_batch()],
        )
    )

    for metric in (
        report.ratios.qualification_rate,
        report.ratios.draft_to_send_rate,
        report.ratios.send_to_reply_rate,
        report.ratios.reply_to_process_rate,
    ):
        assert metric.value is None
