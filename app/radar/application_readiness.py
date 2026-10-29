"""Evidence-only application readiness, independent of technology ranking.

Explicit verification flags must come from a source checker, not a score or
the language used to write a listing. Missing evidence always fails closed.
"""
from datetime import datetime, timedelta
import re
import unicodedata
from urllib.parse import urlsplit


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


# Only hard requirements disqualify. A junior position working with senior
# engineers, or an English course as a desirable skill, does not.
ADVANCED_ENGLISH_REQUIRED = (
    r"\b(?:c1|c2|b2|advanced|fluent|near.native)\s+(?:english|ingles)\b"
    r".{0,45}\b(?:required|mandatory|must|essential|obligatorio|excluyente)\b",
    r"\b(?:english|ingles)\b.{0,25}\b(?:c1|c2|b2|avanzado|fluido)\b"
    r".{0,45}\b(?:required|mandatory|obligatorio|excluyente|indispensable)\b",
    r"\b(?:requires?|exige|must have)\b.{0,45}"
    r"\b(?:fluent|advanced|c1|c2)\s+(?:english|ingles)\b",
)


def application_readiness(row: dict, *, now: datetime) -> dict:
    title = _normalize(row.get("title", ""))
    description = _normalize(row.get("description", ""))
    blockers = []
    if re.search(r"\b(?:senior|sr\.?|staff|principal|director|head(?:\s+of)?)\b", title):
        blockers.append("Senior experience requires review outside the priority lane")
    clauses = re.split(r"[.;\\n]", title + ". " + description)
    required_english = any(
        not re.search(r"\\b(?:deseable|no\\s+excluyente|optional|preferred|not\\s+required)\\b", clause)
        and any(re.search(pattern, clause) for pattern in ADVANCED_ENGLISH_REQUIRED)
        for clause in clauses
    )
    if row.get("work_language") in {"EN", "BILINGUAL"} or required_english:
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
