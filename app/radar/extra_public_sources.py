"""Additional documented public job APIs, fetched conservatively once per daily run.

Attribution and listing URLs are retained. No scraping, authorization bypass,
private candidate information, automatic applications, or implicit verified status.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from urllib.parse import urlparse

import httpx

from app.models.domain import Opportunity
from app.radar.daily_search import parse_date, text_only

JOBICY = "https://jobicy.com/api/v2/remote-jobs"
HIMALAYAS = "https://himalayas.app/jobs/api"
REMOTEOK = "https://remoteok.com/api"
ARBEITNOW = "https://www.arbeitnow.com/api/job-board-api"


def https_link(value: object, *allowed_hosts: str) -> str | None:
    """Never fabricate a link or accept non-HTTPS/application script URLs."""
    if not isinstance(value, str) or len(value) > 2048:
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    if allowed_hosts and not any(
        parsed.hostname.lower() == host or parsed.hostname.lower().endswith("." + host)
        for host in allowed_hosts
    ):
        return None
    return value


def epoch_date(value: object) -> datetime | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    # Provider specifications differ between seconds and milliseconds.
    if 10**12 <= value <= 10**13:
        value /= 1000
    if not 946684800 <= value <= 4102444800:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _job_id(source: str, key: str) -> str:
    return source + ":" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:26]


def _salary(minimum: object, maximum: object, currency: object, period: object) -> str | None:
    bounds = []
    for val in (minimum, maximum):
        if isinstance(val, (int, float)) and not isinstance(val, bool) and val > 0:
            bounds.append(f"{val:g}")
    if not bounds:
        return None
    return " - ".join(bounds) + " " + text_only(currency or "") + " / " + text_only(period or "unspecified")


def parse_jobicy(payload: object, now: datetime) -> list[Opportunity]:
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise ValueError("Jobicy API schema mismatch")
    results = []
    for entry in payload["jobs"]:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("id") or "").strip()
        url = https_link(entry.get("url"), "jobicy.com")
        title = text_only(entry.get("jobTitle"))
        company = text_only(entry.get("companyName"))
        if not (key and url and title and company):
            continue
        results.append(Opportunity(
            id=_job_id("jobicy", key), source="jobicy", source_id=key,
            source_url=url, company=company, title=title,
            description=text_only(entry.get("jobDescription") or entry.get("jobExcerpt") or title)[:24000],
            location=text_only(entry.get("jobGeo")) or None, remote_policy="remote",
            discovered_at=now, published_at=parse_date(entry.get("pubDate")),
            compensation=_salary(entry.get("salaryMin"), entry.get("salaryMax"),
                                 entry.get("salaryCurrency"), entry.get("salaryPeriod")),
        ))
    return results


def _country_names(values: object) -> str:
    if not isinstance(values, list):
        return ""
    countries = []
    for obj in values:
        if isinstance(obj, str):
            name = obj
        elif isinstance(obj, dict):
            name = str(obj.get("name") or obj.get("alpha2") or "")
        else:
            continue
        if name.strip().lower() == "ar":
            name = "Argentina"
        if name.strip():
            countries.append(name.strip())
    return ", ".join(countries[:30])


def parse_himalayas(payload: object, now: datetime) -> list[Opportunity]:
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise ValueError("Himalayas API schema mismatch")
    results = []
    for entry in payload["jobs"]:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("guid") or "").strip()
        # Himalayas terms require retaining the supplied applicationLink.
        link = https_link(entry.get("applicationLink"))
        title = text_only(entry.get("title"))
        company = text_only(entry.get("companyName"))
        expires = epoch_date(entry.get("expiryDate"))
        if expires is not None and expires <= now:
            continue
        if not (key and link and title and company):
            continue
        restrictions = _country_names(entry.get("locationRestrictions"))
        results.append(Opportunity(
            id=_job_id("himalayas", key), source="himalayas", source_id=key,
            source_url=link, company=company, title=title,
            description=text_only(entry.get("description") or entry.get("excerpt") or title)[:24000],
            location=restrictions or "Worldwide (no country restriction specified)",
            remote_policy="remote", discovered_at=now,
            published_at=epoch_date(entry.get("pubDate")),
            compensation=_salary(entry.get("minSalary"), entry.get("maxSalary"),
                                 entry.get("currency"), entry.get("salaryPeriod")),
        ))
    return results


def parse_remoteok(payload: object, now: datetime) -> list[Opportunity]:
    if not isinstance(payload, list):
        raise ValueError("Remote OK API schema mismatch")
    results = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("id") or "").strip()
        url = https_link(entry.get("url"), "remoteok.com")
        title = text_only(entry.get("position"))
        company = text_only(entry.get("company"))
        # The API may begin with a terms notice; this is not a job.
        if not (key and url and title and company):
            continue
        results.append(Opportunity(
            id=_job_id("remoteok", key), source="remoteok", source_id=key,
            source_url=url, company=company, title=title,
            description=text_only(entry.get("description") or title)[:24000],
            location=text_only(entry.get("location")) or None,
            remote_policy="remote", discovered_at=now,
            published_at=parse_date(entry.get("date")) or epoch_date(entry.get("epoch")),
            compensation=_salary(entry.get("salary_min"), entry.get("salary_max"), "USD", "annual"),
        ))
    return results


def parse_arbeitnow(payload: object, now: datetime) -> list[Opportunity]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Arbeitnow API schema mismatch")
    results = []
    for entry in payload["data"]:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("slug") or "").strip()
        url = https_link(entry.get("url"), "arbeitnow.com")
        title = text_only(entry.get("title"))
        company = text_only(entry.get("company_name"))
        if not (key and url and title and company):
            continue
        results.append(Opportunity(
            id=_job_id("arbeitnow", key), source="arbeitnow", source_id=key,
            source_url=url, company=company, title=title,
            description=text_only(entry.get("description") or title)[:24000],
            location=text_only(entry.get("location")) or None,
            remote_policy="remote" if entry.get("remote") is True else "onsite",
            discovered_at=now, published_at=epoch_date(entry.get("created_at")),
        ))
    return results


async def collect_extended_sources(
    client: httpx.AsyncClient, *, now: datetime,
) -> tuple[list[Opportunity], dict[str, str]]:
    """Bounded API calls. One failed source never stops another."""
    jobs: list[Opportunity] = []
    diagnostics: dict[str, str] = {}

    async def run_one(name: str, url: str, parser, *,
                      params: dict | None = None, max_pages: int = 1) -> None:
        found = 0
        cursor = None
        visited: set[str] = set()
        error = None
        for _ in range(max_pages):
            request_params = dict(params or {})
            if cursor:
                if cursor in visited:
                    error = "PaginationLoop"
                    break
                visited.add(cursor)
                request_params["cursor"] = cursor
            try:
                response = await client.get(url, params=request_params, timeout=18)
                response.raise_for_status()
                payload = response.json()
                parsed = parser(payload, now)
                jobs.extend(parsed)
                found += len(parsed)
                cursor = payload.get("nextCursor") if isinstance(payload, dict) else None
                if not isinstance(cursor, str) or not cursor:
                    break
            except (httpx.HTTPError, ValueError, TypeError, OverflowError) as exc:
                error = type(exc).__name__
                break
        diagnostics[name] = f"ERROR:{error} ({found} parsed)" if error else f"OK ({found} parsed)"

    await run_one("jobicy", JOBICY, parse_jobicy, params={"count": 100})
    await run_one("himalayas", HIMALAYAS, parse_himalayas,
                  params={"limit": 20}, max_pages=3)
    await run_one("remoteok", REMOTEOK, parse_remoteok)
    await run_one("arbeitnow", ARBEITNOW, parse_arbeitnow)
    return jobs, diagnostics
