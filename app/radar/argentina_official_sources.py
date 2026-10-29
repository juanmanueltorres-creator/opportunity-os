"""Bounded official Argentina vacancy pages; no search-engine scraping.

Each newly collected vacancy must be visible at its exact employer / university
source page on *this run*. An unknown HTML schema, login wall or outdated
description produces no Opportunity, not a fabricated or stale opening.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
import unicodedata

import httpx

from app.models.domain import Opportunity

# Source IDs and URLs are deliberately narrow, audited public job pages.
OFFICIAL_PAGES = (
    ("aeroterra-geoai", "Aeroterra", "Analista GeoAI",
     "https://www.aeroterra.com/es-ar/trabaja-con-nosotros/busquedas-actuales/geo-ai"),
    ("aeroterra-funcional-gis", "Aeroterra", "Analista Funcional GIS",
     "https://www.aeroterra.com/es-ar/trabaja-con-nosotros/busquedas-actuales/analista-funcional-gis"),
    ("utn-ammazy-bi", "AMMAZY Argentina", "Analista de Performance – Business Intelligence",
     "https://portalseu.frc.utn.edu.ar/oportunidades-laborales/analista-de-performance-business-intelligence/"),
)
OFFICIAL_PAGE_URLS = {source_id: url for source_id, _, _, url in OFFICIAL_PAGES}


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden += 1
        elif self.hidden == 0 and tag in {"p", "h1", "h2", "h3", "li", "div", "br"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden = max(0, self.hidden - 1)
        elif self.hidden == 0:
            self.parts.append(" ")

    def handle_data(self, data):
        if self.hidden == 0:
            self.parts.append(data)


def _normalized(value: str) -> str:
    text = unicodedata.normalize("NFD", value)
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def parse_official_page(html: str, source_id: str, *, now: datetime) -> Opportunity | None:
    target = next((item for item in OFFICIAL_PAGES if item[0] == source_id), None)
    if target is None or not html:
        return None
    _, company, title, url = target
    parser = _VisibleText()
    parser.feed(html[:350_000])
    text = " ".join("".join(parser.parts).split())[:12000]
    lower = _normalized(text)
    if _normalized(title) not in lower:
        return None
    closed_markers = (
        "esta busqueda ya finalizo",
        "busqueda finalizada",
        "convocatoria cerrada",
        "ya no se aceptan solicitudes",
        "no estamos recibiendo nuevas postulaciones",
        "applications are closed",
        "this position is closed",
        "position has been filled",
        "job is no longer available",
    )
    if any(marker in lower for marker in closed_markers):
        return None
    # Direct application affordance present on official sources, but opening
    # is *still unverified* until the visitor checks the actual application.
    if not any(term in lower for term in ("postulate", "postularte", "aplicar")):
        return None
    if len(text) < 150:
        return None
    location = None
    policy = None
    published = None
    if source_id.startswith("aeroterra-"):
        # Verified in page copy, not inferred from headquarters / company name.
        if not ("caba" in lower or "retiro" in lower or "catalinas" in lower):
            return None
        location = "CABA, Argentina"
        # Office is stated, but '100% presencial' is not: keep modality UNKNOWN.
    elif source_id == "utn-ammazy-bi":
        if "100% presencial" in lower:
            policy = "onsite"
        # Institution is in Córdoba, NOT proof the employer's job is.
        location = None
        if "publicado el 5 de octubre, 2026" in lower:
            published = datetime(2026, 10, 5, tzinfo=timezone.utc)
    return Opportunity(
        id="publicpage:" + source_id,
        source="publicpage",
        source_id=source_id,
        source_url=url,
        company=company,
        title=title,
        description=text[:7000],
        location=location,
        remote_policy=policy,
        discovered_at=now,
        published_at=published,
    )


async def collect_argentina_official_pages(
    client: httpx.AsyncClient, *, now: datetime,
) -> tuple[list[Opportunity], dict[str, str]]:
    limiter = asyncio.Semaphore(3)

    async def one(source_id: str, company: str, title: str, url: str):
        async with limiter:
            key = "publicpage:" + source_id
            try:
                response = await client.get(url, timeout=15.0)
                response.raise_for_status()
                if response.url.scheme != "https" or str(response.url) != url:
                    return None, key, "NOT_CONFIRMED: redirect or host changed"
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type:
                    return None, key, "NOT_CONFIRMED: not HTML"
                found = parse_official_page(response.text, source_id, now=now)
                return found, key, "OK (1 source page)" if found else "NOT_CONFIRMED: title or application missing"
            except (httpx.HTTPError, ValueError):
                return None, key, "ERROR: source unavailable"

    found = await asyncio.gather(*(one(*row) for row in OFFICIAL_PAGES))
    return ([job for job, _, _ in found if job is not None],
            {key: state for _, key, state in found})
