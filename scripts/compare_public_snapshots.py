"""Compare two consecutive PUBLIC-only radar snapshots. Missing != closed."""
from __future__ import annotations
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

FIELDS = ("id", "company", "title", "source_url", "source", "published_at",
          "remote_mode", "argentina_eligible", "work_language", "listing_language",
          "location", "track", "score", "topics", "company_industry")

def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo is not None else None

def _safe_url(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        u = urlsplit(value)
        return u.scheme == "https" and bool(u.hostname) and u.username is None and u.password is None
    except ValueError:
        return False

def _records(snapshot: dict) -> dict[str, dict]:
    result = {}
    for row in snapshot.get("atlas", []):
        if not isinstance(row, dict):
            continue
        ident = row.get("id")
        if not isinstance(ident, str) or not (0 < len(ident) <= 240):
            continue
        if not _safe_url(row.get("source_url")) or ident in result:
            continue
        safe = {}
        for field in FIELDS:
            value = row.get(field)
            if field == "topics":
                safe[field] = [x[:75] for x in value[:12] if isinstance(x, str)] if isinstance(value, list) else []
            elif field == "score":
                safe[field] = max(0, min(100, value)) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None
            elif isinstance(value, str):
                safe[field] = value[:2048] if field == "source_url" else value[:180]
            else:
                safe[field] = None
        result[ident] = safe
        if len(result) >= 300:
            break
    return result

def compare_public_snapshots(previous: dict | None, current: dict) -> dict:
    if not isinstance(current, dict) or current.get("schema_version") != 1 or not isinstance(current.get("atlas"), list):
        raise ValueError("Current public snapshot is not valid")
    now = _timestamp(current.get("generated_at"))
    if now is None:
        raise ValueError("Current public snapshot is missing an aware timestamp")
    latest = _records(current)
    result = {
        "schema_version": 1,
        "comparison_type": "consecutive_public_snapshots",
        "available": False,
        "current_generated_at": current["generated_at"],
        "previous_generated_at": None,
        "current_count": len(latest),
        "previous_count": None,
        "newly_observed_count": None,
        "no_longer_observed_count": None,
        "continuing_count": None,
        "new_jobs": [],
        "no_longer_observed_jobs": [],
        "caution": ("Newly observed means present in the latest capture and missing from the prior capture. "
                    "It does not prove first publication, current availability or hiring eligibility. "
                    "Missing from a capture does NOT prove a vacancy closed."),
    }
    if not isinstance(previous, dict) or previous.get("schema_version") != 1 or not isinstance(previous.get("atlas"), list):
        result["unavailable_reason"] = "No comparable previous public snapshot"
        return result
    before = _timestamp(previous.get("generated_at"))
    if before is None or before >= now:
        result["unavailable_reason"] = "Previous snapshot has an invalid or non-earlier timestamp"
        return result
    prior = _records(previous)
    current_ids, previous_ids = set(latest), set(prior)
    newly = sorted(current_ids - previous_ids)
    missing = sorted(previous_ids - current_ids)
    result.update({
        "available": True,
        "previous_generated_at": previous["generated_at"],
        "previous_count": len(prior),
        "newly_observed_count": len(newly),
        "no_longer_observed_count": len(missing),
        "continuing_count": len(current_ids & previous_ids),
        "new_jobs": [latest[x] for x in newly],
        "no_longer_observed_jobs": [prior[x] for x in missing],
    })
    return result

def main(previous: Path, current: Path, output: Path) -> None:
    latest = json.loads(current.read_text(encoding="utf-8"))
    try:
        old = json.loads(previous.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        old = None
    delta = compare_public_snapshots(old, latest)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(delta, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: compare_public_snapshots.py previous.json current.json changes.json")
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
