"""Conservative, public-source daily job discovery tailored to career tracks.

No personal CV/contacts are placed in public GitHub artifacts.
Location and language eligibility are UNKNOWN unless supported by evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import html
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.connectors.remotive import RemotiveConnector
from app.models.domain import Opportunity

GETONBRD_ENDPOINT = "https://www.getonbrd.com/api/v0/categories/{category}/jobs"
CATEGORIES = ("programming", "operations-management", "machine-learning-ai")
MAX_PAGES_PER_CATEGORY = 2

TRACKS: dict[str, dict[str, object]] = {
    "software_ai": {
        "label": "Software, datos e IA",
        "cv": "desarrollo_software_ia",
        "terms": ("developer", "desarrollador", "full stack", "fullstack", "frontend",
                  "backend", "python", "node.js", "typescript", "react", "software",
                  "data engineer", "data analyst", "analista de datos",
                  "automatización", "automation", "integraciones", "api engineer",
                  "machine learning", "inteligencia artificial", "qa automation"),
    },
    "gis_geoscience": {
        "label": "GIS, geociencias y minería",
        "cv": "gis_geociencias",
        "terms": ("gis", "sig", "geospatial", "geoespacial", "postgis", "qgis",
                  "geology", "geólogo", "geologia", "geología", "hydrogeology",
                  "hidrogeología", "teledetección", "remote sensing", "mining",
                  "minería", "cartografía", "cartography", "geodata", "geomatics"),
    },
    "management_operations": {
        "label": "Gestión, producto y operaciones",
        "cv": "management_ia",
        "terms": ("project manager", "product manager", "product owner", "operations",
                  "operaciones", "coordinador", "coordinator", "planificación",
                  "planning", "business analyst", "analista funcional",
                  "compras", "purchasing", "abastecimiento", "procurement",
                  "implementación", "implementation", "customer success", "erp",
                  "transformación digital", "digital transformation"),
    },
    "design_web": {
        "label": "Diseño web e interactivo",
        "cv": "desarrollo_software_ia",
        "terms": ("web designer", "creative developer", "three.js", "threejs",
                  "webgl", "3d developer", "interactive", "motion designer",
                  "designer developer", "creative technologist"),
    },
    "income_operations": {
        "label": "Ingresos inmediatos: gastronomía y abastecimiento",
        "cv": "management_ia",
        "terms": ("chef", "cocinero", "pizzero", "gastronomía", "gastronomia",
                  "kitchen manager", "restaurant manager", "encargado de cocina",
                  "compras", "abastecimiento", "stock", "inventarios"),
    },
}

# These are explicit geographic restrictions, not guesses based on job language.
LATAM_MARKERS = ("latam", "latin america", "latinoamerica", "latinoamérica",
                 "south america", "sudamérica", "sudamerica")
ARGENTINA_MARKERS = ("argentina", "córdoba", "cordoba", "san juan", "buenos aires")
NON_LATAM_EXCLUSIVE = re.compile(
    r"\b(?:united states only|us only|usa only|only us|only usa|"
    r"europe only|eu only|canada only|uk only|only europe|"
    r"residents of the united states only)\b", re.I)
# When an upstream API declares a country/countries as its remote work zone,
# a list entirely outside LATAM must never be interpreted as eligible in Argentina.
# Keep ANYWHERE/WORLDWIDE marked UNKNOWN, not YES.
RESTRICTED_LOCATIONS = frozenset({
    "united states", "usa", "us", "u.s.", "united kingdom", "uk",
    "canada", "philippines", "india", "poland", "israel",
    "sweden", "hungary", "europe", "european union", "eu",
    "germany", "spain", "portugal", "france", "italy",
    "netherlands", "australia", "singapore", "new zealand",
    "japan", "south korea", "united arab emirates", "uae",
    "new york", "london", "berlin", "stockholm", "toronto",
})
GLOBAL_LOCATION_MARKERS = ("anywhere", "worldwide", "global", "any location")


def _restricted_location(location: str) -> bool:
    if any(global_marker in location for global_marker in GLOBAL_LOCATION_MARKERS):
        return False
    parts = [part.strip(" .()") for part in re.split(r"[,;/]", location)]
    return bool(parts) and all(part in RESTRICTED_LOCATIONS for part in parts)
REQUIRES_ENGLISH = re.compile(
    r"\b(?:fluent english required|english (?:is )?required|"
    r"advanced english required|c1 english|english c1|"
    r"b2 english required|english b2 required|"
    r"nivel de ingl[eé]s (?:avanzado|c1)|ingl[eé]s excluyente)\b", re.I)
SPANISH_REQUIRED = re.compile(
    r"\b(?:spanish (?:is )?required|fluent spanish required|"
    r"espa[nñ]ol (?:nativo|excluyente)|"
    r"idioma de trabajo: espa[nñ]ol|working language:\s*spanish)\b", re.I)
REMOTE_WORDS = re.compile(r"\b(?:remote|remoto|remota|teletrabajo)\b", re.I)
ONSITE_WORDS = re.compile(r"\b(?:on.?site|presencial)\b", re.I)
SENIOR_WORDS = re.compile(r"\b(?:senior|sr\.?|principal|staff|director|head of)\b", re.I)
JUNIOR_WORDS = re.compile(r"\b(?:junior|jr\.?|trainee|analista|associate|semi.?senior|ssr)\b", re.I)
STRIP_HTML = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def text_only(value: object) -> str:
    return _SPACE.sub(" ", html.unescape(STRIP_HTML.sub(" ", str(value or "")))).strip()


def parse_date(value: object) -> datetime | None:
    if isinstance(value, (float, int)) and 946684800 <= value <= 4102444800:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _known_https(value: object, *, hosts: tuple[str, ...]) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    if host in hosts or any(host.endswith("." + suffix) for suffix in hosts):
        return value
    return None


def parse_getonbrd(payload: object, *, now: datetime) -> list[Opportunity]:
    """Tolerant JSON:API parser; never invent a job application URL."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("invalid Get on Board payload")
    results: list[Opportunity] = []
    included = {}
    for item in payload.get("included", []):
        if isinstance(item, dict) and item.get("type") == "company":
            company_attrs = item.get("attributes") or {}
            if isinstance(company_attrs, dict):
                included[str(item.get("id"))] = text_only(company_attrs.get("name"))
    for entry in payload["data"]:
        if not isinstance(entry, dict):
            continue
        attrs = entry.get("attributes")
        links = entry.get("links")
        if not isinstance(attrs, dict):
            continue
        links = links if isinstance(links, dict) else {}
        source_url = None
        for candidate in (links.get("public_url"), links.get("web"), attrs.get("url"),
                          attrs.get("public_url"), attrs.get("external_url"),
                          ):
            source_url = _known_https(candidate, hosts=("getonbrd.com", "getonbrd.cl", "getonbrd.com.ar"))
            if source_url:
                break
        if source_url is None:
            continue
        title = text_only(attrs.get("title"))
        company_obj = attrs.get("company")
        related = company_obj.get("data") if isinstance(company_obj, dict) else None
        rel_id = related.get("id") if isinstance(related, dict) else None
        related_attrs = related.get("attributes") if isinstance(related, dict) else None
        company = text_only(attrs.get("company_name") or (
            related_attrs.get("name") if isinstance(related_attrs, dict) else None
        ) or (company_obj.get("name") if isinstance(company_obj, dict) else None)
          or included.get(str(rel_id), ""))
        job_id = str(entry.get("id") or "").strip()
        if not job_id or not title or not company:
            continue
        description = text_only(attrs.get("description") or attrs.get("description_headline") or title)
        countries = attrs.get("countries")
        country_text = ", ".join(str(x) for x in countries) if isinstance(countries, list) else ""
        location = text_only(attrs.get("location") or attrs.get("location_name") or
                             attrs.get("remote_zone") or country_text)
        policy = text_only(attrs.get("remote_modality") or attrs.get("remote_type") or "")
        if attrs.get("remote") is True or REMOTE_WORDS.search(policy):
            policy = "remote"
        elif ONSITE_WORDS.search(policy):
            policy = "onsite"
        results.append(Opportunity(
            id=f"getonboard:{job_id}", source="getonboard", source_id=job_id,
            source_url=source_url, company=company, title=title,
            description=description, location=location or None,
            remote_policy=policy or None,
            discovered_at=now, published_at=parse_date(attrs.get("published_at")),
        ))
    return results


def _normalize(value: str) -> str:
    return _SPACE.sub(" ", value.casefold()).strip()


def _contains_term(text: str, term: str) -> bool:
    # Do not match 'GIS' within reGIStered or 'SIG' within deSIGn.
    return re.search(r"(?<!\w)" + re.escape(term.casefold()) + r"(?!\w)", text) is not None


@dataclass(frozen=True)
class JobMatch:
    job: Opportunity
    track: str
    cv_track: str
    score: int
    reasons: tuple[str, ...]
    remote_mode: str
    argentina_eligible: str
    eligibility_evidence: str | None
    work_language: str
    language_evidence: str | None

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.job.id, "source": self.job.source,
            "company": self.job.company, "title": self.job.title,
            "source_url": self.job.source_url, "location": self.job.location,
            "published_at": self.job.published_at.isoformat() if self.job.published_at else None,
            "discovered_at": self.job.discovered_at.isoformat(),
            "track": self.track, "cv_track_sugerido": self.cv_track,
            "cv_pdf_generado": False, "score": self.score,
            "reasons": list(self.reasons), "remote_mode": self.remote_mode,
            "argentina_eligible": self.argentina_eligible,
            "eligibility_evidence": self.eligibility_evidence,
            "work_language": self.work_language,
            "language_evidence": self.language_evidence,
            "historial_postulaciones_cruzado": False,
            "verification_status": "PENDING",
        }


def classify(job: Opportunity) -> JobMatch | None:
    title = _normalize(job.title)
    if re.search(r"\b(?:contrato\s+sena|sena\s+apprentice)\b", title):
        return None
    body = _normalize(text_only(job.description)[:4500])
    scores: list[tuple[int, str, list[str]]] = []
    for track, opts in TRACKS.items():
        found_title = [kw for kw in opts["terms"] if _contains_term(title, kw)]
        found_body = [kw for kw in opts["terms"] if _contains_term(body, kw)]
        if not found_title:
            # Pure body matches too often produce tangential job recommendations.
            continue
        score = min(75, 45 + min(3, len(found_title)) * 12 + min(3, len(found_body)) * 2)
        if track == "income_operations":
            score += 3
        scores.append((score, track, found_title))
    if not scores:
        return None
    score, track, found = max(scores, key=lambda x: (x[0], x[1] == "gis_geoscience"))
    location = _normalize(job.location or "")
    remote = bool(REMOTE_WORDS.search(job.remote_policy or "") or REMOTE_WORDS.search(location)
                  or re.search(r"\\b(?:100%|fully|totalmente)\\s+(?:remote|remoto|remota)\\b", body, re.I))
    if not remote and not any(k in location for k in ARGENTINA_MARKERS):
        # A non-remote job outside Argentina is not a viable short-term target.
        return None
    if remote:
        mode = "REMOTE"
    elif ONSITE_WORDS.search(job.remote_policy or ""):
        mode = "ONSITE"
    else:
        mode = "UNKNOWN"

    eligible = "UNKNOWN"
    evidence = None
    if any(k in location for k in LATAM_MARKERS + ARGENTINA_MARKERS):
        eligible = "YES"
        evidence = "Ubicación declarada: " + (job.location or "")
        score += 14 if remote else 8
    elif NON_LATAM_EXCLUSIVE.search(location) or _restricted_location(location):
        eligible = "NO"
        evidence = "Restricción geográfica explícita: " + (job.location or "")
        score -= 60
    elif remote:
        # "Worldwide"/global remote is NOT proof of employment eligibility from Argentina.
        score += 4
    if "córdoba" in location or "cordoba" in location or "san juan" in location:
        score += 14
    if job.source == "getonboard" and remote:
        # Ranking preference for a regional platform, NOT evidence of AR eligibility.
        score += 12

    work_language = "UNKNOWN"
    language_evidence = None
    if SPANISH_REQUIRED.search(body):
        work_language = "ES"
        language_evidence = "Requisito explícito en la descripción"
        score += 10
    elif REQUIRES_ENGLISH.search(body):
        work_language = "EN"
        language_evidence = "Inglés avanzado exigido explícitamente"
        score -= 27
    if SENIOR_WORDS.search(title) and not JUNIOR_WORDS.search(title):
        score -= 17
    if JUNIOR_WORDS.search(title):
        score += 7
    published = job.published_at
    if published:
        days = max(0, (job.discovered_at - published).days)
        if days <= 7:
            score += 9
        elif days > 30:
            score -= 14
    reasons = [f"Coincide con {track}: {', '.join(found[:3])}"]
    if evidence:
        reasons.append(evidence)
    else:
        reasons.append("Elegibilidad Argentina aún no verificada")
    if language_evidence:
        reasons.append(language_evidence)
    else:
        reasons.append("Idioma laboral sin evidencia; revisar publicación")
    return JobMatch(job, track, str(TRACKS[track]["cv"]), max(0, min(100, score)),
                    tuple(reasons), mode, eligible, evidence, work_language, language_evidence)


def rank(jobs: list[Opportunity], *, now: datetime, max_age_days: int = 30,
         limit: int = 30) -> list[JobMatch]:
    matched: dict[tuple[str, str], JobMatch] = {}
    for job in jobs:
        if job.published_at and job.published_at < now - timedelta(days=max_age_days):
            continue
        match = classify(job)
        if not match or match.argentina_eligible == "NO" or match.score < 45:
            continue
        # Cross-source duplicates often appear on more than one public job board.
        # Preserve the most useful source link, never duplicate the same employer+role.
        key = ("company-role", _normalize(job.company), _normalize(job.title))
        prior = matched.get(key)
        if prior is None or match.score > prior.score:
            matched[key] = match
    return sorted(matched.values(), key=lambda m: (-m.score, m.job.company.casefold(),
                                                   m.job.title.casefold()))[:limit]


async def discover() -> tuple[list[Opportunity], dict[str, str]]:
    jobs: list[Opportunity] = []
    diagnostics: dict[str, str] = {}
    now = datetime.now(timezone.utc)
    async with httpx.AsyncClient(timeout=20, follow_redirects=False,
                                 headers={"User-Agent": "OpportunityOS-PersonalRadar/1.0"}) as client:
        # Import lazily to avoid the parsers' text/date utilities import cycle.
        from app.radar.extra_public_sources import collect_extended_sources
        additional_jobs, additional_diagnostics = await collect_extended_sources(client, now=now)
        jobs.extend(additional_jobs)
        diagnostics.update(additional_diagnostics)
        try:
            jobs.extend(await RemotiveConnector(client, timeout_seconds=20).fetch())
            diagnostics["remotive"] = "OK"
        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
            diagnostics["remotive"] = type(exc).__name__
        except Exception as exc:  # connector custom HTTP exception types
            diagnostics["remotive"] = type(exc).__name__

        for category in CATEGORIES:
            source_key = f"getonbrd:{category}"
            count = 0
            errors = []
            for page in range(1, MAX_PAGES_PER_CATEGORY + 1):
                try:
                    response = await client.get(GETONBRD_ENDPOINT.format(category=category),
                                                params=[("page", page), ("per_page", 30), ("expand[]", "company")])
                    response.raise_for_status()
                    part = parse_getonbrd(response.json(), now=now)
                    count += len(part)
                    jobs.extend(part)
                    if not part:
                        break
                except (httpx.HTTPError, ValueError) as exc:
                    errors.append(type(exc).__name__)
                    break
            diagnostics[source_key] = (f"OK ({count} parsed)" if count and not errors else "EMPTY_OR_UNMAPPED" if not errors
                                       else "ERROR " + ",".join(errors))
    return jobs, diagnostics
