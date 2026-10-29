"""Explicit public-only JSON export for the standalone Vercel radar.

Safe by construction: allowlisted job attributes; no history, CV, contacts,
API keys, Supabase credentials, personal notes or persistence state.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone
from app.radar.source_evidence import observed_on_public_ats, observed_on_public_source_page
from urllib.parse import urlsplit
import re
import html

# Export only provider-origin PUBLIC descriptions. Not a profile or a CV.
PUBLIC_JOB_HOSTS = {
    "ashby": ("jobs.ashbyhq.com",),
    "lever": ("jobs.lever.co",),
    "greenhouse": ("boards.greenhouse.io", "job-boards.greenhouse.io"),
    "getonboard": ("getonbrd.com", "getonbrd.cl"),
    "remotive": ("remotive.com",),
    "jobicy": ("jobicy.com",),
    "remoteok": ("remoteok.com",),
    "arbeitnow": ("arbeitnow.com",),
    "himalayas": ("himalayas.app",),
    "publicpage": ("aeroterra.com", "portalseu.frc.utn.edu.ar"),
}
MAX_PUBLIC_DESCRIPTION = 2200
SAFE_READINESS_REASONS = {
    "Senior experience requires review outside the priority lane",
    "Advanced English mentioned", "Argentina not eligible",
    "Original publication date not verified as recent",
    "seniority_compatible_verified", "language_compatible_verified",
    "location_compatible_verified", "requirements_verified",
    "official_link_verified", "Safe official HTTPS application URL required",
    "Original requirements unavailable",
}


def _public_description(raw: dict) -> tuple[str | None, bool]:
    hosts = PUBLIC_JOB_HOSTS.get(raw.get("source"), ())
    try:
        hostname = urlsplit(str(raw.get("source_url") or "")).hostname
    except ValueError:
        hostname = None
    if not hostname or not any(hostname == h or hostname.endswith("." + h) for h in hosts):
        return None, False
    content = raw.get("description")
    if not isinstance(content, str) or content.strip() in {"", "No verificado"}:
        return None, False
    # The collector has already removed HTML. Sanitize at the export boundary too.
    cleaned = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", content)).split())
    return (cleaned[:MAX_PUBLIC_DESCRIPTION], len(cleaned) > MAX_PUBLIC_DESCRIPTION) if cleaned else (None, False)


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
        description, truncated = _public_description(raw)
        item["description"] = description
        item["description_truncated"] = truncated
        category = raw.get("category")
        item["category"] = category if category in {"POSTULAR AHORA", "REVISAR", "EXPLORAR"} else "REVISAR"
        reasons = raw.get("readiness_reasons")
        item["readiness_reasons"] = [
            reason for reason in reasons[:12]
            if isinstance(reason, str) and reason in SAFE_READINESS_REASONS
        ] if isinstance(reasons, list) else []
        # Do not accept arbitrary source-check claims from a raw report:
        # require a matching official ATS URL, provider-owned source id and
        # a capture timestamp near the report timestamp.
        valid_source_page = observed_on_public_source_page(
            source=str(item.get("source") or ""),
            source_url=str(item.get("source_url") or ""),
            source_id=str(item.get("id") or "").partition(":")[2],
        )
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
        valid_status = ((item.get("source_check") == "LISTED_ON_PUBLIC_ATS" and valid_ats)
                        or (item.get("source_check") == "LISTED_ON_OFFICIAL_SOURCE" and valid_source_page))
        if not (valid_status and fresh_capture):
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
