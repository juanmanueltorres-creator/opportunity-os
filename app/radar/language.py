from __future__ import annotations

import re
import unicodedata
from typing import Literal

from app.radar.models import LanguageDecision, OutputLanguage, RadarAssessment

_SPANISH_MARKERS = frozenset(
    {
        "buscamos",
        "buscar",
        "persona",
        "sumarse",
        "equipo",
        "puesto",
        "requiere",
        "experiencia",
        "trabajo",
        "datos",
        "ofrecemos",
        "modalidad",
        "oportunidades",
        "aprendizaje",
        "desarrollo",
        "clientes",
        "locales",
        "hola",
        "búsqueda",
        "interesa",
        "gracias",
        "tiempo",
    }
)
_ENGLISH_MARKERS = frozenset(
    {
        "looking",
        "join",
        "team",
        "role",
        "position",
        "experience",
        "work",
        "build",
        "product",
        "engineering",
        "customers",
        "opening",
        "interested",
        "thank",
        "time",
        "help",
        "improve",
        "hi",
    }
)
_SPANISH_MARKETS = frozenset(
    {
        "argentina",
        "bolivia",
        "chile",
        "colombia",
        "costa rica",
        "cuba",
        "ecuador",
        "el salvador",
        "spain",
        "espana",
        "guatemala",
        "honduras",
        "mexico",
        "nicaragua",
        "panama",
        "paraguay",
        "peru",
        "dominican republic",
        "republica dominicana",
        "uruguay",
        "venezuela",
    }
)
_TOKEN_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")


def resolve_output_language(
    assessment: RadarAssessment,
    *,
    override: Literal["es", "en"] | None = None,
) -> LanguageDecision:
    if override is not None:
        return LanguageDecision(
            language=override,
            basis="explicit_override",
            confidence=1.0,
            source_field="cli.language",
            source_text=override,
        )

    posting_text = f"{assessment.opportunity.title}\n{assessment.opportunity.description}"
    detected = detect_text_language(posting_text)
    if detected is not None:
        return LanguageDecision(
            language=detected,
            basis="posting_language",
            confidence=0.95,
            source_field="opportunity.title+description",
            source_text=_excerpt(posting_text),
        )

    for source_field, value in _market_candidates(assessment):
        if value is not None and _matches_spanish_market(value):
            return LanguageDecision(
                language="es",
                basis="market_location",
                confidence=0.80,
                source_field=source_field,
                source_text=value,
            )

    return LanguageDecision(
        language="en",
        basis="international_remote_fallback",
        confidence=0.60,
        source_field="fallback",
        source_text=None,
    )


def detect_text_language(text: str) -> OutputLanguage | None:
    tokens = {_normalize_token(token) for token in _TOKEN_RE.findall(text)}
    spanish_hits = len(tokens.intersection(_normalized_markers(_SPANISH_MARKERS)))
    english_hits = len(tokens.intersection(_normalized_markers(_ENGLISH_MARKERS)))

    if spanish_hits >= 3 and spanish_hits - english_hits >= 2:
        return "es"
    if english_hits >= 3 and english_hits - spanish_hits >= 2:
        return "en"
    return None


def _market_candidates(assessment: RadarAssessment) -> list[tuple[str, str | None]]:
    country = getattr(assessment.enrichment, "country", None)
    region = getattr(assessment.enrichment, "region", None)
    return [
        ("enrichment.country", getattr(country, "value", None)),
        ("enrichment.region", getattr(region, "value", None)),
        ("opportunity.location", assessment.opportunity.location),
    ]


def _matches_spanish_market(value: str) -> bool:
    normalized = _normalize_phrase(value)
    return any(
        normalized == market
        or normalized.startswith(f"{market} ")
        or normalized.endswith(f" {market}")
        or f" {market} " in f" {normalized} "
        for market in _SPANISH_MARKETS
    )


def _normalized_markers(markers: frozenset[str]) -> frozenset[str]:
    return frozenset(_normalize_token(marker) for marker in markers)


def _normalize_token(value: str) -> str:
    return _strip_accents(value.casefold())


def _normalize_phrase(value: str) -> str:
    tokens = [_normalize_token(token) for token in _TOKEN_RE.findall(value)]
    return " ".join(tokens)


def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _excerpt(value: str, limit: int = 180) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"
