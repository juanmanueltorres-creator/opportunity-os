from __future__ import annotations

import argparse
from datetime import date, datetime, time, timezone
import json
from pathlib import Path
from typing import Sequence

from app.metrics.models import CountMetric, RatioMetric, ReportWindow, SearchHealthReport
from app.metrics.projection import MetricsInput, project_search_health
from app.metrics.sources import (
    SourceRead,
    read_application_facts,
    read_historical_facts,
    read_opportunity_facts,
    read_outreach_facts,
    read_radar_facts,
    read_relationship_facts,
)

UTC = timezone.utc


def _parse_timestamp(value: str, *, end_of_day: bool) -> datetime:
    raw = value.strip()
    try:
        if len(raw) == 10:
            parsed_date = date.fromisoformat(raw)
            return datetime.combine(
                parsed_date,
                time.max if end_of_day else time.min,
                tzinfo=UTC,
            )
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid ISO date/datetime: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("report timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a local Search Health report")
    parser.add_argument("--from", dest="from_value", required=True)
    parser.add_argument("--to", dest="to_value")
    parser.add_argument("--as-of", dest="as_of_value")
    parser.add_argument("--opportunity-db", default="opportunities.db")
    parser.add_argument(
        "--relationships-db", default="state/relationships.local.sqlite3"
    )
    parser.add_argument("--outreach-db", default="state/outreach.local.sqlite3")
    parser.add_argument("--history-db", default="state/history.local.sqlite3")
    parser.add_argument("--applications-root", default="artifacts/applications")
    parser.add_argument("--radar-root", default="artifacts/radar")
    parser.add_argument("--output", default="artifacts/metrics/search-health.json")
    return parser


def _resolve_window(
    parser: argparse.ArgumentParser,
    *,
    from_value: str,
    to_value: str | None,
    as_of_value: str | None,
) -> tuple[ReportWindow, datetime]:
    if to_value is not None and as_of_value is not None:
        parser.error("--to and --as-of are mutually exclusive")

    try:
        start = _parse_timestamp(from_value, end_of_day=False)
        if to_value is not None:
            end = _parse_timestamp(to_value, end_of_day=True)
        elif as_of_value is not None:
            end = _parse_timestamp(as_of_value, end_of_day=True)
        else:
            end = datetime.now(UTC)
    except ValueError as exc:
        parser.error(str(exc))

    if end < start:
        parser.error("report window end must not precede start")

    return ReportWindow(start=start, end=end), end


def _count_text(metric: CountMetric) -> str:
    if metric.value is None:
        return "unknown"
    if metric.coverage == "PARTIAL":
        return f"{metric.value} (partial coverage)"
    if metric.coverage == "UNKNOWN":
        return "unknown"
    return str(metric.value)


def _ratio_text(metric: RatioMetric) -> str:
    if metric.value is None:
        if metric.coverage == "PARTIAL":
            return "unknown (partial coverage)"
        return "unknown"
    suffix = " (partial coverage)" if metric.coverage == "PARTIAL" else ""
    return f"{metric.value * 100:.1f}% ({metric.numerator}/{metric.denominator}){suffix}"


def _render_human(report: SearchHealthReport) -> str:
    count_sections = (
        (
            "DISCOVERY",
            (
                report.counts.opportunities_observed,
                report.counts.opportunities_new,
                report.counts.qualified_high,
                report.counts.qualified_medium,
            ),
        ),
        (
            "EXECUTION",
            (
                report.counts.packets_prepared,
                report.counts.drafts_verified,
                report.counts.confirmed_sends,
            ),
        ),
        (
            "OUTCOMES",
            (
                report.counts.replies_observed,
                report.counts.processes_opened,
                report.counts.processes_closed,
            ),
        ),
    )

    lines = [
        "OPPORTUNITY OS — SEARCH HEALTH",
        f"window: {report.window.start.isoformat()} -> {report.window.end.isoformat()}",
        "",
    ]
    for title, metrics in count_sections:
        lines.append(title)
        for metric in metrics:
            lines.append(f"{metric.name}: {_count_text(metric)}")
        lines.append("")

    lines.append("CONVERSION")
    for metric in (
        report.ratios.qualification_rate,
        report.ratios.draft_to_send_rate,
        report.ratios.send_to_reply_rate,
        report.ratios.reply_to_process_rate,
    ):
        lines.append(f"{metric.name}: {_ratio_text(metric)}")
    lines.append("")

    lines.append("COVERAGE")
    lines.extend(
        (
            f"radar: {report.coverage.radar.lower()}",
            f"outreach: {report.coverage.outreach.lower()}",
            f"replies: {report.coverage.replies.lower()}",
            f"processes: {report.coverage.processes.lower()}",
        )
    )
    return "\n".join(lines) + "\n"


def _history_source_read(history_read) -> SourceRead:
    return SourceRead(
        items=history_read.facts,
        coverage=history_read.coverage,
        basis=history_read.basis,
        warnings=history_read.warnings,
    )


def _write_report(path: Path, report: SearchHealthReport) -> None:
    payload = report.model_dump(mode="json")
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    window, generated_at = _resolve_window(
        parser,
        from_value=args.from_value,
        to_value=args.to_value,
        as_of_value=args.as_of_value,
    )

    opportunities = read_opportunity_facts(args.opportunity_db, window)
    qualifications = read_radar_facts(args.radar_root, window)
    packets = read_application_facts(args.applications_root, window)
    outreach = read_outreach_facts(args.outreach_db, window)
    relationships = read_relationship_facts(args.relationships_db, window)
    historical = read_historical_facts(args.history_db, window)

    report = project_search_health(
        MetricsInput(
            opportunities=opportunities,
            qualifications=qualifications,
            packets=packets,
            outreach=outreach,
            relationships=relationships,
            history=_history_source_read(historical),
            history_batches=historical.batches,
        ),
        window,
        generated_at=generated_at,
    )

    _write_report(Path(args.output), report)
    print(_render_human(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
