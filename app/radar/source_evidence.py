"""Evidence that a vacancy was listed on a company's public ATS at capture.

Only positive source observations; never infer closed from absence or
429/404/network errors. This is not proof that applications are accepted.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

ALLOWED_HOSTS = {
    "ashby": ("jobs.ashbyhq.com",),
    "lever": ("jobs.lever.co",),
    "greenhouse": ("boards.greenhouse.io", "job-boards.greenhouse.io"),
}


def observed_on_public_ats(*, source: str, source_url: str, source_id: str) -> bool:
    """A listing seen through our official ATS connector must match its host/id."""
    hosts = ALLOWED_HOSTS.get(source)
    if hosts is None or not isinstance(source_url, str) or not source_id:
        return False
    try:
        url = urlsplit(source_url)
    except ValueError:
        return False
    if url.scheme != "https" or url.hostname not in hosts:
        return False
    if url.username is not None or url.password is not None:
        return False
    parts = [part for part in url.path.split("/") if part]
    if len(parts) < 3:
        return False
    # Greenhouse URLs end /jobs/<id>, Ashby/Lever /<board>/<id>.
    if source == "greenhouse":
        return parts[-2] == "jobs" and parts[-1] == source_id
    return parts[-1] == source_id


def source_evidence(job) -> dict:
    """Call only for live, newly fetched official-connector Opportunity objects."""
    if not observed_on_public_ats(
        source=job.source, source_url=job.source_url, source_id=job.source_id,
    ):
        return {"source_check": "NOT_CHECKED", "source_checked_at": None}
    if not isinstance(job.discovered_at, datetime):
        return {"source_check": "NOT_CHECKED", "source_checked_at": None}
    checked_at = job.discovered_at
    if checked_at.tzinfo is None:
        return {"source_check": "NOT_CHECKED", "source_checked_at": None}
    return {
        "source_check": "LISTED_ON_PUBLIC_ATS",
        "source_checked_at": checked_at.astimezone(timezone.utc).isoformat(),
    }
