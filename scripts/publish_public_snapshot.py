"""Explicit public-only JSON export for the standalone Vercel radar.

Safe by construction: allowlisted job attributes; no history, CV, contacts,
API keys, Supabase credentials, personal notes or persistence state.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone
from app.radar.source_evidence import observed_on_public_ats
from urllib.parse import urlsplit

PUBLIC_FIELDS = (
    "id", "source", "company", "title", "source_url", "location",
    "published_at", "discovered_at", "track", "score",
    "remote_mode", "argentina_eligible", "work_language", "listing_language", "search_lane",
    "eligibility_evidence", "language_evidence",
    "geographic_scope", "argentina_province", "topics",
    "source_check", "source_checked_at",
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
        item = {key: raw.get(key) for key in PUBLIC_FIELDS}
        # Do not accept arbitrary source-check claims from a raw report:
        # require a matching official ATS URL, provider-owned source id and
        # a capture timestamp near the report timestamp.
        valid_ats = observed_on_public_ats(
            source=str(item.get("source") or ""),
            source_url=str(item.get("source_url") or ""),
            source_id=str(item.get("id") or "").partition(":")[2],
        )
        try:
            checked_at = datetime.fromisoformat(str(item["source_checked_at"]).replace("Z", "+00:00"))
            generated_at = datetime.fromisoformat(str(report["generated_at"]).replace("Z", "+00:00"))
            fresh_capture = (checked_at.tzinfo is not None and generated_at.tzinfo is not None
                             and 0 <= (checked_at - generated_at).total_seconds() <= 900)
        except (TypeError, ValueError, KeyError):
            fresh_capture = False
        if not (item.get("source_check") == "LISTED_ON_PUBLIC_ATS"
                and valid_ats and fresh_capture):
            item["source_check"] = "NOT_CHECKED"
            item["source_checked_at"] = None
        else:
            item["source_checked_at"] = checked_at.astimezone(timezone.utc).isoformat()
        # Only classifier-produced provenance from a PUBLIC vacancy may cross
        # this boundary. This is neither manual verification nor a private note.
        evidence = item.get("eligibility_evidence")
        if not (isinstance(evidence, str)
                and evidence.startswith((
                    "Ubicación declarada: ",
                    "Cobertura geográfica declarada en el título: ",
                    "Restricción geográfica explícita: ",
                ))):
            item["eligibility_evidence"] = None
        else:
            item["eligibility_evidence"] = evidence[:350]
        if item.get("language_evidence") not in {
            "Requisito explícito en la descripción",
            "Inglés avanzado exigido explícitamente",
        }:
            item["language_evidence"] = None
        if item.get("argentina_eligible") not in {"YES", "NO"}:
            item["eligibility_evidence"] = None
        if item.get("work_language") not in {"ES", "EN"}:
            item["language_evidence"] = None
        # Verified company *industry*, not a claim that the vacancy is agronomy.
        # A designer at an AgTech startup can be discovered through Agro filter
        # while retaining the authentic design_web role track.
        if item["source"] == "ashby" and item["company"] in {"AgZen", "Klim", "FinAgra"}:
            item["company_industry"] = "agtech"
        jobs.append(item)
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
