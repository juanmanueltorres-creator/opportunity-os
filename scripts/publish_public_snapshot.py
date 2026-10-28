"""Explicit public-only JSON export for the standalone Vercel radar.

Safe by construction: allowlisted job attributes; no history, CV, contacts,
API keys, Supabase credentials, personal notes or persistence state.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

PUBLIC_FIELDS = (
    "id", "source", "company", "title", "source_url", "location",
    "published_at", "discovered_at", "track", "score",
    "remote_mode", "argentina_eligible", "work_language", "search_lane",
)


def _https_url(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https" and bool(parsed.netloc)
            and parsed.username is None and parsed.password is None
        )
    except ValueError:
        return False


def public_snapshot(report: dict) -> dict:
    seen: set[str] = set()
    jobs: list[dict] = []
    for raw in report.get("atlas", []):
        if not isinstance(raw, dict):
            continue
        ident = raw.get("id")
        if not isinstance(ident, str) or not ident.strip() or ident in seen:
            continue
        if not _https_url(raw.get("source_url")):
            continue
        seen.add(ident)
        jobs.append({key: raw.get(key) for key in PUBLIC_FIELDS})
        if len(jobs) >= 300:
            break
    statuses = report.get("sources", {})
    sources = (
        {str(key)[:80]: str(value)[:120] for key, value in statuses.items()}
        if isinstance(statuses, dict) else {}
    )
    return {
        "schema_version": 1,
        "generated_at": report.get("generated_at"),
        "raw_jobs_seen": report.get("raw_jobs_seen", 0),
        "sources": sources,
        "atlas": jobs,
        "disclaimer": "Public listings only; work eligibility and active status must be checked at source.",
    }


def export_public_snapshot(source: Path, destination: Path) -> None:
    report = json.loads(source.read_text(encoding="utf-8"))
    snapshot = public_snapshot(report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        raise SystemExit("usage: publish_public_snapshot.py input.json output.json")
    export_public_snapshot(Path(sys.argv[1]), Path(sys.argv[2]))
