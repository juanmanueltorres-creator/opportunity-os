from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Sequence

from app.metrics.history import ExperimentCase, SQLiteHistoricalRepository

OUTREACH_TYPES = (
    "APPLICATION_ONLY",
    "APPLICATION_PLUS_DIRECT",
    "DIRECT_ONLY",
    "NONE",
)


def _parse_observed_at(raw: str | None) -> datetime:
    if raw is None:
        return datetime.now(timezone.utc)
    value = raw.strip()
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("observed_at must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("observed_at must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _normalize_evidence(values: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.strip()
        if not value:
            raise ValueError("evidence labels must be non-empty")
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _case_id(opportunity_id: str) -> str:
    return f"search-experiment:{opportunity_id}"


def _same_registration(
    existing: ExperimentCase,
    *,
    opportunity_id: str,
    outreach_type: str,
    evidence_used: list[str],
) -> bool:
    return (
        existing.opportunity_id == opportunity_id
        and existing.account_id is None
        and existing.outreach_type == outreach_type
        and existing.evidence_used == evidence_used
        and existing.outcome is None
    )


def _render_success(experiment: ExperimentCase, *, status: str) -> str:
    payload = {
        "case_id": experiment.case_id,
        "evidence_used": experiment.evidence_used,
        "observed_at": experiment.model_dump(mode="json")["observed_at"],
        "opportunity_id": experiment.opportunity_id,
        "outreach_type": experiment.outreach_type,
        "status": status,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record one immutable search-strategy experiment for an opportunity."
    )
    parser.add_argument("--opportunity-id", required=True)
    parser.add_argument("--outreach-type", required=True, choices=OUTREACH_TYPES)
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--observed-at")
    parser.add_argument(
        "--history-db",
        type=Path,
        default=Path("state/history.local.sqlite3"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    opportunity_id = args.opportunity_id.strip()
    if not opportunity_id:
        parser.error("--opportunity-id must be non-empty")

    try:
        evidence_used = _normalize_evidence(args.evidence)
        observed_at = _parse_observed_at(args.observed_at)
    except (ValueError, argparse.ArgumentTypeError) as exc:
        parser.error(str(exc))

    repository = SQLiteHistoricalRepository(args.history_db)
    repository.initialize()

    case_id = _case_id(opportunity_id)
    existing = repository.get_experiment(case_id)
    if existing is not None:
        if not _same_registration(
            existing,
            opportunity_id=opportunity_id,
            outreach_type=args.outreach_type,
            evidence_used=evidence_used,
        ):
            print(
                json.dumps(
                    {"error": "experiment_case_conflict", "status": "ERROR"},
                    sort_keys=True,
                )
            )
            return 2
        print(_render_success(existing, status="EXISTING"))
        return 0

    experiment = ExperimentCase(
        case_id=case_id,
        opportunity_id=opportunity_id,
        account_id=None,
        outreach_type=args.outreach_type,
        evidence_used=evidence_used,
        outcome=None,
        observed_at=observed_at,
    )
    saved, inserted = repository.save_experiment(experiment)
    print(_render_success(saved, status="RECORDED" if inserted else "EXISTING"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
