"""Discovery-first geography and thematic context for the public jobs atlas.

Crucial separation:
* candidate_lane() is an *actionability* check for Córdoba/Argentina-remote.
* discovery_lane() is a *research* classification, never a hiring authorization.
We never turn an inferred province into remote-work eligibility.
"""
from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from app.radar.cordoba_filters import candidate_lane, is_cordoba_location

if TYPE_CHECKING:
    from app.radar.daily_search import JobMatch


def _norm(value: str | None) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", (value or "").casefold())
        if not unicodedata.combining(char)
    )


def _contains(value: str, term: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", value) is not None


# Provinces explicitly named in an employer listing. Unknown and overseas
# locations are NOT coerced to a province, even when a company has an HQ in AR.
ARGENTINA_PROVINCES = (
    "Buenos Aires", "Catamarca", "Chaco", "Chubut", "Córdoba",
    "Corrientes", "Entre Ríos", "Formosa", "Jujuy", "La Pampa",
    "La Rioja", "Mendoza", "Misiones", "Neuquén", "Río Negro",
    "Salta", "San Juan", "San Luis", "Santa Cruz", "Santa Fe",
    "Santiago del Estero", "Tierra del Fuego", "Tucumán",
)
# Exact well-known locations in Argentina (not arbitrary fuzzy geocoding).
CITY_TO_PROVINCE = {
    "rosario": "Santa Fe",
    "rafaela": "Santa Fe",
    "comodoro rivadavia": "Chubut",
    "trelew": "Chubut",
    "ushuaia": "Tierra del Fuego",
    "rio gallegos": "Santa Cruz",
    "anelo": "Neuquén",
    "tandil": "Buenos Aires",
    "mar del plata": "Buenos Aires",
    "la plata": "Buenos Aires",
    "san miguel de tucuman": "Tucumán",
}
FOREIGN_TERMS = (
    "spain", "espana", "united states", "usa", "united kingdom",
    "canada", "germany", "berlin", "france", "paris", "poland",
    "portugal", "india", "philippines", "australia", "europe",
    "london", "new york", "brazil", "brasil", "colombia", "chile",
    "uruguay", "mexico", "peru", "sweden", "netherlands",
)
LATAM_TERMS = ("latam", "latin america", "latinoamerica", "south america")
GLOBAL_TERMS = ("worldwide", "anywhere", "global", "remote", "remoto")


def geographic_context(location: str | None) -> tuple[str, str | None]:
    """Return (scope, province) from declared vacancy location; never the HQ."""
    loc = _norm(location)
    if not loc.strip():
        return "UNKNOWN", None
    if any(_contains(loc, term) for term in ("spain", "espana", "andalucia")):
        # Córdoba, Spain is not an Argentine opportunity.
        return "INTERNATIONAL", None
    for province in ARGENTINA_PROVINCES:
        if _contains(loc, _norm(province)):
            return "ARGENTINA", province
    for city, province in CITY_TO_PROVINCE.items():
        if _contains(loc, city):
            return "ARGENTINA", province
    if _contains(loc, "argentina"):
        return "ARGENTINA", None
    if any(_contains(loc, term) for term in LATAM_TERMS):
        return "LATAM", None
    if any(_contains(loc, term) for term in FOREIGN_TERMS):
        return "INTERNATIONAL", None
    if any(_contains(loc, term) for term in GLOBAL_TERMS):
        return "GLOBAL_UNSPECIFIED", None
    return "UNKNOWN", None


# A theme is selected from role-title evidence, not inferred from the company's
# headquarters or unconstrained description-wide text.
TOPIC_TERMS = {
    "gis": ("gis", "sig", "geospatial", "geoespacial", "geomatics", "geomatica",
            "arcgis", "qgis", "postgis", "geodata", "cartografia", "topografia",
            "remote sensing", "spatial analyst", "spatial data"),
    "geology_mining": ("geologo", "geologa", "geologist", "geology", "geologia",
                      "hydrogeology", "hidrogeologia", "geotechnical",
                      "mining", "mineria", "mineral exploration",
                      "exploracion minera", "petroleum", "oil and gas"),
    "agro": ("agro", "agtech", "agriculture", "agricultural", "agronomy",
             "agronomia", "agribusiness", "agropecuario", "agroindustria"),
    "environment": ("environmental", "ambiental", "sustainability",
                    "sostenibilidad", "climate", "biodiversidad", "forestry",
                    "forestal", "ecology", "ecologia", "recursos naturales"),
    "urban_tech": ("urban tech", "urbantech", "smart city", "smart cities",
                   "urban planning", "planeamiento urbano", "urbanismo"),
    "mining_tech": ("mining tech", "miningtech", "minetech", "mining software"),
    "software_data": ("software", "python", "developer", "desarrollador",
                      "backend", "frontend", "data engineer", "data analyst",
                      "fullstack", "full stack", "data scientist"),
    "technical_business": ("business development", "desarrollo comercial",
                           "technical sales", "ventas tecnicas",
                           "sales engineer", "consultor tecnico",
                           "customer success"),
}


def thematic_tags(title: str | None, company_industry: str | None = None) -> list[str]:
    value = _norm(title)
    tags = [
        topic for topic, terms in TOPIC_TERMS.items()
        if any(_contains(value, _norm(term)) for term in terms)
    ]
    if company_industry == "agtech" and "agro" not in tags:
        tags.append("agro")  # Industry, not proof that the role is an agronomy role.
    return tags


def discovery_lane(match: JobMatch) -> str:
    """Non-exclusionary exploration buckets, independent of candidate_lanes."""
    base = candidate_lane(match)
    if base in {"REMOTE_ARGENTINA", "CORDOBA_LOCAL"}:
        return base
    scope, province = geographic_context(match.job.location)
    if match.remote_mode in {"ONSITE", "HYBRID"} and scope == "ARGENTINA":
        if province is None:
            return "ARGENTINA_REVIEW"  # Country known, city/province not stated.
        if province == "Córdoba" and is_cordoba_location(match.job.location):
            return "REVIEW"
        return "ARGENTINA_RELOCATION"
    if scope == "ARGENTINA" and match.remote_mode == "UNKNOWN":
        return "ARGENTINA_REVIEW"
    if base == "REVIEW":
        return "REVIEW"
    if match.remote_mode in {"ONSITE", "HYBRID"}:
        return "RELOCATION_REVIEW"
    return "REVIEW_RESTRICTED"
