"""Conservative location/work-language lanes for a Córdoba-based job search.

A job-board remote label does not establish legal/work-country eligibility.
Only source-evidenced REMOTE + Argentina/LATAM or local Córdoba on-site/hybrid
belongs in the confirmed shortlist. Everything else is review or excluded.
No personal candidate/contact information is included in this public module.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.radar.daily_search import JobMatch

_CORDOBA = re.compile(r"(?<!\w)(?:c[oó]rdoba)(?!\w)", re.I)
_FOREIGN_CORDOBA = re.compile(
    r"(?<!\w)(?:spain|espa[nñ]a|andaluc[ií]a)(?!\w)", re.I
)


def is_cordoba_location(location: str | None) -> bool:
    """Require an explicit Córdoba place, not only an Argentina country flag.

    Reject Córdoba, Spain as a same-name foreign place. If the location is
    ambiguous (e.g. 'Argentina' with no city), do not assume proximity.
    """
    value = str(location or "")
    return bool(_CORDOBA.search(value)) and not _FOREIGN_CORDOBA.search(value)


def candidate_lane(match: JobMatch) -> str:
    """Return REMOTE_ARGENTINA, CORDOBA_LOCAL, REVIEW or EXCLUDED.

    REVIEW never implies verified eligibility and is not automatically sent
    into the confirmed shortlist or the DB's eligible opportunities feed.
    """
    if match.work_language == "EN" or match.argentina_eligible == "NO":
        return "EXCLUDED"

    if match.remote_mode == "REMOTE":
        if match.argentina_eligible == "YES":
            return "REMOTE_ARGENTINA"
        return "REVIEW"

    if is_cordoba_location(match.job.location):
        if match.remote_mode in {"ONSITE", "HYBRID"}:
            return "CORDOBA_LOCAL"
        return "REVIEW"

    return "EXCLUDED"


def partition_cordoba_matches(
    matches: list[JobMatch],
) -> tuple[list[JobMatch], list[JobMatch]]:
    """Separate confirmed local/Argentina-remote from unverified candidates.

    Preserves caller score ordering in both lanes. Excludes other Argentine
    on-site cities, other-country hybrid roles and explicit English-mandatory
    postings. UNKNOWN remote eligibility is review-only.
    """
    confirmed: list[JobMatch] = []
    review: list[JobMatch] = []
    for item in matches:
        lane = candidate_lane(item)
        if lane in {"REMOTE_ARGENTINA", "CORDOBA_LOCAL"}:
            confirmed.append(item)
        elif lane == "REVIEW":
            review.append(item)
    return confirmed, review
