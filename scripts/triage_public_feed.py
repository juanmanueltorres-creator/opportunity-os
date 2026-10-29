"""Generate a small *investigation* shortlist from public Opportunity OS evidence.

Does not fetch job pages, certify vacancies, read private CVs, or make applications.
Do not pad to 20 jobs when fewer fit the documented Spanish-first criteria.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

SENIOR = re.compile(r"\b(senior|sr\.?|principal|staff|director|head|lead)\b", re.I)
JUNIOR = re.compile(r"\b(junior|jr\.?|trainee|entry.level|pasant[ií]a)\b", re.I)
DOMAIN = re.compile(r"\b(gis|sig|qgis|arcgis|postgis|geospatial|geoespacial|"
                    r"geolog[ií]a|minera|mining|geoai|geo ai|business intelligence|"\n                    r"analista de performance|python|fastapi|backend|"
                    r"back.end|soporte t[eé]cnico|technical support|"
                    r"analista de datos|data analyst|sql|postgresql|integrations)\b", re.I)
UNRELATED = re.compile(r"\b(liferay|snowflake|outsystems|talent pool|talent community)\b", re.I)


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def priority(job: dict, *, now: datetime) -> int | None:
    if not isinstance(job, dict):
        return None
    try:
        url = urlsplit(str(job.get("source_url") or ""))
    except ValueError:
        return None
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        return None
    title = normalize(job.get("title"))
    ident = normalize(job.get("id"))
    if (job.get("category") == "EXPLORAR"
            or SENIOR.search(title) or "senior" in ident or UNRELATED.search(title)):
        return None
    if job.get("work_language") in {"EN", "BILINGUAL"} or job.get("argentina_eligible") == "NO":
        return None
    if job.get("work_language") != "ES" and job.get("listing_language") != "ES":
        return None
    if not DOMAIN.search(title) and not JUNIOR.search(title):
        return None
    score = 0
    if re.search(r"\b(gis|sig|qgis|arcgis|postgis|geoespacial|geoai|geolog|miner)\w*\b", title):
        score += 28
    if DOMAIN.search(title):
        score += 12
    if JUNIOR.search(title):
        score += 25
    if job.get("argentina_eligible") == "YES":
        score += 20
    if job.get("work_language") == "ES":
        score += 8
    if job.get("listing_language") == "ES":
        score += 5
    if job.get("remote_mode") == "REMOTE":
        score += 5
    if job.get("source_check") == "LISTED_ON_PUBLIC_ATS":
        score += 3
    location = normalize(job.get("location"))
    if any(x in location for x in ("chile", "peru", "colombia", "santiago", "bogota", "lima")):
        if job.get("argentina_eligible") != "YES":
            score -= 14
    if isinstance(job.get("description"), str) and job["description"].strip():
        score += 4
    published = job.get("published_at")
    if published:
        try:
            date = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
            if date.tzinfo is not None and timedelta(0) <= now - date <= timedelta(days=14):
                score += 4
        except ValueError:
            pass
    return score


def unknowns(job: dict) -> str:
    pending = []
    if job.get("work_language") != "ES":
        pending.append("idioma laboral")
    if job.get("argentina_eligible") != "YES":
        pending.append("admisión desde Argentina")
    if not job.get("description"):
        pending.append("requisitos originales")
    if not job.get("published_at"):
        pending.append("fecha publicada")
    place = normalize(job.get("location"))
    if "caba" in place or "buenos aires" in place:
        pending.append("disponibilidad para trabajar en Buenos Aires")
    if job.get("remote_mode") == "ONSITE" and not place:
        pending.append("ciudad del puesto presencial")
    pending.append("apertura / postulación vigentes")
    return ", ".join(pending)


def shortlist(feed: dict, *, now: datetime, limit: int = 20) -> list[dict]:
    matched = []
    for row in feed.get("atlas", []):
        score = priority(row, now=now)
        if score is not None:
            matched.append({"job": row, "priority": score})
    matched.sort(key=lambda x: (-x["priority"],
                 str(x["job"].get("company") or ""), str(x["job"].get("title") or "")))
    return matched[:max(0, limit)]


def markdown(feed: dict, *, now: datetime, limit: int = 20) -> str:
    rows = shortlist(feed, now=now, limit=limit)
    def clean(value: object) -> str:
        return str(value or "No informado").replace("|", "/").replace("\n", " ")[:160]
    lines = [
        "# Opportunity OS — Vacantes para investigar",
        "",
        "**No son vacantes confirmadas para postular**. Revisión humana requerida.",
        "Un aviso en español no acredita que el trabajo sea en español.",
        f"Captura: {clean(feed.get('generated_at'))}; análisis: {now.isoformat()}",
        "",
        "| Empresa y puesto | Ubicación del aviso | Motivo de revisión | Fuente |",
        "|---|---|---|---|",
    ]
    for item in rows:
        j = item["job"]
        lines.append(
            f"| {clean(j.get('company'))} — {clean(j.get('title'))} "
            f"| {clean(j.get('location'))} | {clean(unknowns(j))} "
            f"| [Aviso]({j['source_url']}) |"
        )
    lines.extend(["", f"**{len(rows)} candidatas para investigar** (máximo {limit}; sin completar con ofertas incompatibles).", ""])
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    feed = json.loads(args.feed.read_text(encoding="utf-8"))
    content = markdown(feed, now=datetime.now(timezone.utc), limit=args.limit)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(f"Reporte guardado: {args.output}")
    else:
        print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
