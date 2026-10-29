"""Evidence-only application readiness, independent of technology ranking.

Explicit verification flags must come from a source checker, not a score or
the language used to write a listing. Missing evidence always fails closed.
"""
from datetime import datetime, timedelta
import re
import unicodedata
from urllib.parse import urlsplit


def application_readiness(row: dict, *, now: datetime) -> dict:
    text = unicodedata.normalize("NFKD", str(row.get("title", "")) + " " + str(row.get("description", "")))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    blockers = []
    if re.search(r"\b(senior|sr|staff|principal|director|head)\b", text):
        blockers.append("Senior experience requires review outside the priority lane")
    if re.search(r"\b(c1|c2)\b|advanced english|fluent english|ingles avanzado|ingles fluido", text):
        blockers.append("Advanced English mentioned")
    if row.get("argentina_eligible") == "NO":
        blockers.append("Argentina not eligible")
    if blockers:
        return {"category": "EXPLORAR", "readiness_reasons": blockers}
    missing = []
    try:
        published = datetime.fromisoformat(str(row.get("published_at", "")).replace("Z", "+00:00"))
        fresh = published.tzinfo is not None and now - timedelta(days=30) <= published <= now
    except ValueError:
        fresh = False
    if not fresh:
        missing.append("Original publication date not verified as recent")
    for flag in ("seniority_compatible_verified", "language_compatible_verified",
                 "location_compatible_verified", "requirements_verified", "official_link_verified"):
        if row.get(flag) is not True:
            missing.append(flag)
    url = urlsplit(str(row.get("source_url") or ""))
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        missing.append("Safe official HTTPS application URL required")
    if not str(row.get("description") or "").strip():
        missing.append("Original requirements unavailable")
    return {"category": "REVISAR" if missing else "POSTULAR AHORA", "readiness_reasons": missing}
