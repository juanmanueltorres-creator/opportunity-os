from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.metrics.models import (
    CountMetric,
    CoverageSummary,
    RatioMetric,
    ReportWindow,
    SearchHealthCounts,
    SearchHealthRatios,
    SearchHealthReport,
    SourceSummary,
)

UTC = timezone.utc


def _count(name: str, value: int | None = 0) -> CountMetric:
    return CountMetric(
        name=name,
        value=value,
        coverage="COMPLETE" if value is not None else "UNKNOWN",
        basis=["fixture"],
    )


def _ratio(name: str) -> RatioMetric:
    return RatioMetric(
        name=name,
        value=None,
        numerator=0,
        denominator=0,
        coverage="UNKNOWN",
        basis=[],
    )


def test_report_window_rejects_reverse_range():
    with pytest.raises(ValidationError):
        ReportWindow(
            start=datetime(2026, 8, 2, tzinfo=UTC),
            end=datetime(2026, 8, 1, tzinfo=UTC),
        )


def test_report_window_rejects_naive_datetime():
    with pytest.raises(ValidationError):
        ReportWindow(
            start=datetime(2026, 8, 1),
            end=datetime(2026, 8, 2, tzinfo=UTC),
        )


def test_count_metric_rejects_negative_values_and_extra_fields():
    with pytest.raises(ValidationError):
        CountMetric(name="confirmed_sends", value=-1, coverage="COMPLETE")
    with pytest.raises(ValidationError):
        CountMetric.model_validate(
            {
                "name": "confirmed_sends",
                "value": 1,
                "coverage": "COMPLETE",
                "unexpected": "nope",
            }
        )


def test_unknown_ratio_keeps_observed_numbers_without_fabricating_zero():
    metric = RatioMetric(
        name="send_to_reply_rate",
        value=None,
        numerator=2,
        denominator=5,
        coverage="PARTIAL",
        basis=["historical_gmail"],
        warnings=["reply coverage incomplete"],
    )
    assert metric.value is None
    assert metric.denominator == 5


def test_zero_denominator_cannot_publish_numeric_ratio():
    with pytest.raises(ValidationError):
        RatioMetric(
            name="send_to_reply_rate",
            value=0.0,
            numerator=0,
            denominator=0,
            coverage="COMPLETE",
            basis=["native_outreach"],
        )


def test_numeric_ratio_must_match_numerator_and_denominator():
    with pytest.raises(ValidationError):
        RatioMetric(
            name="send_to_reply_rate",
            value=0.9,
            numerator=1,
            denominator=2,
            coverage="COMPLETE",
        )


def test_ratio_value_is_bounded():
    with pytest.raises(ValidationError):
        RatioMetric(
            name="send_to_reply_rate",
            value=1.1,
            numerator=11,
            denominator=10,
            coverage="COMPLETE",
        )


def test_search_health_report_has_exact_v1_shape_and_version():
    counts = SearchHealthCounts(
        opportunities_observed=_count("opportunities_observed", 4),
        opportunities_new=_count("opportunities_new", 4),
        qualified_high=_count("qualified_high", None),
        qualified_medium=_count("qualified_medium", None),
        packets_prepared=_count("packets_prepared", 2),
        drafts_verified=_count("drafts_verified", 2),
        confirmed_sends=_count("confirmed_sends", 1),
        replies_observed=_count("replies_observed", None),
        processes_opened=_count("processes_opened", None),
        processes_closed=_count("processes_closed", None),
    )
    ratios = SearchHealthRatios(
        qualification_rate=_ratio("qualification_rate"),
        draft_to_send_rate=_ratio("draft_to_send_rate"),
        send_to_reply_rate=_ratio("send_to_reply_rate"),
        reply_to_process_rate=_ratio("reply_to_process_rate"),
    )
    report = SearchHealthReport(
        generated_at=datetime(2026, 9, 1, tzinfo=UTC),
        window=ReportWindow(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 9, 1, tzinfo=UTC),
        ),
        counts=counts,
        ratios=ratios,
        coverage=CoverageSummary(
            radar="UNKNOWN",
            outreach="PARTIAL",
            replies="UNKNOWN",
            processes="UNKNOWN",
        ),
        source_summary=[
            SourceSummary(name="opportunity_db", coverage="COMPLETE"),
            SourceSummary(name="outreach_db", coverage="PARTIAL"),
        ],
    )

    payload = report.model_dump(mode="json")
    assert report.report_version == "search-health-v1"
    assert list(payload) == [
        "report_version",
        "generated_at",
        "window",
        "counts",
        "ratios",
        "coverage",
        "warnings",
        "source_summary",
    ]

    with pytest.raises(ValidationError):
        SearchHealthReport(
            report_version="search-health-v2",
            generated_at=report.generated_at,
            window=report.window,
            counts=report.counts,
            ratios=report.ratios,
            coverage=report.coverage,
            source_summary=report.source_summary,
        )
