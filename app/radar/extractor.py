from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Protocol

from app.models.domain import Opportunity
from app.radar.models import DerivedValue, OpportunityEnrichment, Requirement

MANDATORY_CUES = (
    "required",
    "must have",
    "must",
    "mandatory",
    "minimum",
    "requerido",
    "obligatorio",
    "excluyente",
    "mínimo",
    "minimo",
)
PREFERRED_CUES = (
    "preferred",
    "nice to have",
    "bonus",
    "preferido",
    "deseable",
    "será un plus",
    "sera un plus",
)

_DIRECT_ATS_SOURCES = {"greenhouse", "lever", "ashby"}
_LANGUAGE_TERMS = {
    "english",
    "inglés",
    "ingles",
    "spanish",
    "español",
    "espanol",
    "portuguese",
    "portugués",
    "portugues",
    "french",
    "francés",
    "frances",
}
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_SALARY_RE = re.compile(
    r"(?:compensation|salary|sueldo|remuneraci[oó]n)\s*:\s*"
    r"(?P<currency>USD|ARS|EUR|\$)\s*"
    r"(?P<minimum>[0-9][0-9.,]*)\s*(?:-|–|to|a)\s*"
    r"(?P<maximum>[0-9][0-9.,]*)",
    re.IGNORECASE,
)
_DEADLINE_RE = re.compile(
    r"(?:apply by|deadline|fecha l[ií]mite)\s*:?\s*"
    r"(?P<date>\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)


class RequirementExtractor(Protocol):
    def extract(self, opportunity: Opportunity) -> OpportunityEnrichment: ...


class RuleBasedRequirementExtractor:
    def __init__(self, *, extractor_version: str = "rules-v1") -> None:
        if not extractor_version.strip():
            raise ValueError("extractor_version is required")
        self.extractor_version = extractor_version.strip()

    def extract(self, opportunity: Opportunity) -> OpportunityEnrichment:
        requirements: dict[tuple[str, str], Requirement] = {}

        for skill in opportunity.required_skills:
            self._add_requirement(
                requirements,
                self._structured_skill(skill, importance="mandatory", source_field="required_skills"),
            )
        for skill in opportunity.preferred_skills:
            self._add_requirement(
                requirements,
                self._structured_skill(skill, importance="preferred", source_field="preferred_skills"),
            )

        free_text_requirements = self._extract_text_requirements(opportunity.description)
        for requirement in free_text_requirements:
            self._add_requirement(requirements, requirement)

        sentences = _sentences(opportunity.description)
        salary_min, salary_max, salary_currency = _extract_salary(sentences)
        application_deadline = _extract_deadline(sentences)
        language = next(
            (
                DerivedValue[str](
                    value=requirement.value,
                    source_text=requirement.provenance.source_text,
                    source_field=requirement.provenance.source_field,
                    extraction_method=requirement.provenance.extraction_method,
                    confidence=requirement.provenance.confidence,
                )
                for requirement in requirements.values()
                if requirement.kind == "language"
            ),
            None,
        )

        source_reliability = _source_reliability(opportunity.source)
        source_freshness_quality = _freshness_quality(
            opportunity,
            source_reliability=source_reliability,
        )

        region = None
        if opportunity.location and opportunity.location.strip():
            region = DerivedValue[str](
                value=_normalize_spaces(opportunity.location),
                source_field="location",
                extraction_method="source_structured",
                confidence=1.0,
            )

        return OpportunityEnrichment(
            opportunity_id=opportunity.id,
            normalized_title=DerivedValue[str](
                value=_normalize_spaces(opportunity.title),
                source_field="title",
                extraction_method="source_structured",
                confidence=1.0,
            ),
            language=language,
            region=region,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary_currency,
            requirements=list(requirements.values()),
            application_mode=_application_mode(opportunity),
            source_reliability=source_reliability,
            source_freshness_quality=source_freshness_quality,
            application_deadline=application_deadline,
            extractor_version=self.extractor_version,
            taxonomy_versions={},
            created_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _structured_skill(
        skill: str,
        *,
        importance: str,
        source_field: str,
    ) -> Requirement:
        value = _normalize_spaces(skill)
        return Requirement(
            kind="skill",
            value=value,
            importance=importance,
            exactness="conceptual",
            provenance=DerivedValue[str](
                value=value,
                source_field=source_field,
                extraction_method="source_structured",
                confidence=1.0,
            ),
        )

    def _extract_text_requirements(self, description: str) -> list[Requirement]:
        requirements: list[Requirement] = []
        for sentence in _sentences(description):
            parsed = _parse_explicit_requirement_sentence(sentence)
            if parsed is None:
                continue
            body, importance = parsed
            for raw_term in _split_requirement_terms(body):
                term = _clean_term(raw_term)
                if not term:
                    continue
                kind = _requirement_kind(term)
                requirements.append(
                    Requirement(
                        kind=kind,
                        value=term,
                        importance=importance,
                        exactness=(
                            "declarative"
                            if kind in {"license", "work_authorization"}
                            else "conceptual"
                        ),
                        provenance=DerivedValue[str](
                            value=term,
                            source_text=sentence,
                            source_field="description",
                            extraction_method="explicit_rule",
                            confidence=0.9,
                        ),
                    )
                )
        return requirements

    @staticmethod
    def _add_requirement(
        requirements: dict[tuple[str, str], Requirement],
        candidate: Requirement,
    ) -> None:
        key = (candidate.kind, _normalized_key(candidate.value))
        existing = requirements.get(key)
        if existing is None:
            requirements[key] = candidate
            return

        importance_rank = {"unknown": 0, "preferred": 1, "mandatory": 2}
        candidate_rank = importance_rank[candidate.importance]
        existing_rank = importance_rank[existing.importance]
        if candidate_rank > existing_rank:
            requirements[key] = candidate
            return
        if candidate_rank == existing_rank:
            if (
                candidate.provenance.extraction_method == "source_structured"
                and existing.provenance.extraction_method != "source_structured"
            ):
                requirements[key] = candidate


def _normalize_spaces(value: str) -> str:
    return " ".join(value.split())


def _normalized_key(value: str) -> str:
    return _normalize_spaces(value).casefold()


def _sentences(text: str) -> list[str]:
    chunks = re.findall(r"[^.!?\n]+[.!?]?", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _parse_explicit_requirement_sentence(sentence: str) -> tuple[str, str] | None:
    core = sentence.strip().rstrip(".!?").strip()
    lowered = core.casefold()

    prefix_patterns = (
        ("mandatory", MANDATORY_CUES),
        ("preferred", PREFERRED_CUES),
    )
    for importance, cues in prefix_patterns:
        for cue in sorted(cues, key=len, reverse=True):
            cue_cf = cue.casefold()
            if lowered.startswith(cue_cf):
                remainder = core[len(cue) :].lstrip(" :–—-").strip()
                if remainder:
                    return remainder, importance

    for cue in sorted(MANDATORY_CUES, key=len, reverse=True):
        pattern = rf"^(?P<body>.+?)\s+{re.escape(cue)}$"
        match = re.match(pattern, core, flags=re.IGNORECASE)
        if match and match.group("body").strip():
            return match.group("body").strip(), "mandatory"

    for cue in sorted(PREFERRED_CUES, key=len, reverse=True):
        pattern = rf"^(?P<body>.+?)\s+{re.escape(cue)}$"
        match = re.match(pattern, core, flags=re.IGNORECASE)
        if match and match.group("body").strip():
            return match.group("body").strip(), "preferred"

    return None


def _split_requirement_terms(body: str) -> list[str]:
    return re.split(r"\s+(?:and|y)\s+|[,;/]", body, flags=re.IGNORECASE)


def _clean_term(term: str) -> str:
    cleaned = term.strip().lstrip("-•* ").strip().rstrip(".:; ")
    return _normalize_spaces(cleaned) if cleaned else ""


def _requirement_kind(term: str) -> str:
    normalized = _normalized_key(term)
    if normalized in _LANGUAGE_TERMS:
        return "language"
    if re.search(r"\b(years?|años?|anos?|experience|experiencia)\b", normalized):
        return "experience"
    if re.search(r"\b(bachelor|master|degree|licenciatura|universitario|university)\b", normalized):
        return "education"
    if re.search(r"\b(license|licencia|certification|certificación|certificacion)\b", normalized):
        return "license"
    if re.search(r"\b(work authorization|work permit|visa|autorización laboral|autorizacion laboral)\b", normalized):
        return "work_authorization"
    if re.search(r"\b(location|located|reside|residencia|ubicación|ubicacion)\b", normalized):
        return "location"
    if re.search(r"\b(shift|schedule|horario|turno)\b", normalized):
        return "schedule"
    return "skill"


def _application_mode(opportunity: Opportunity) -> str:
    if _EMAIL_RE.search(opportunity.description):
        return "DIRECT_EMAIL"
    if opportunity.source.casefold() in _DIRECT_ATS_SOURCES:
        return "HOSTED_MANUAL"
    return "UNKNOWN"


def _source_reliability(source: str) -> str:
    normalized = source.casefold()
    if normalized in _DIRECT_ATS_SOURCES:
        return "DIRECT_ATS"
    if normalized == "remotive":
        return "AGGREGATOR"
    if normalized == "manual":
        return "MANUAL"
    return "UNKNOWN"


def _freshness_quality(opportunity: Opportunity, *, source_reliability: str) -> str:
    if opportunity.published_at is None:
        return "DISCOVERED_AT_ONLY"
    if source_reliability == "AGGREGATOR":
        return "DELAYED_TIMESTAMP"
    if source_reliability in {"DIRECT_ATS", "DIRECT_OFFICIAL"}:
        return "DIRECT_TIMESTAMP"
    return "UNKNOWN"


def _extract_salary(
    sentences: list[str],
) -> tuple[DerivedValue[float] | None, DerivedValue[float] | None, DerivedValue[str] | None]:
    for sentence in sentences:
        match = _SALARY_RE.search(sentence)
        if match is None:
            continue
        minimum = _parse_number(match.group("minimum"))
        maximum = _parse_number(match.group("maximum"))
        currency = match.group("currency").upper()
        provenance = {
            "source_text": sentence,
            "source_field": "description",
            "extraction_method": "explicit_rule",
            "confidence": 0.95,
        }
        return (
            DerivedValue[float](value=minimum, **provenance),
            DerivedValue[float](value=maximum, **provenance),
            DerivedValue[str](value=currency, **provenance),
        )
    return None, None, None


def _parse_number(value: str) -> float:
    raw = value.strip()
    if "," in raw and "." in raw:
        raw = raw.replace(",", "")
    elif raw.count(",") == 1 and len(raw.split(",")[-1]) <= 2:
        raw = raw.replace(",", ".")
    else:
        raw = raw.replace(",", "")
    return float(raw)


def _extract_deadline(sentences: list[str]) -> DerivedValue[datetime] | None:
    for sentence in sentences:
        match = _DEADLINE_RE.search(sentence)
        if match is None:
            continue
        raw_date = match.group("date")
        if "/" in raw_date:
            parsed = datetime.strptime(raw_date, "%d/%m/%Y")
        else:
            parsed = datetime.strptime(raw_date, "%Y-%m-%d")
        value = parsed.replace(tzinfo=timezone.utc)
        return DerivedValue[datetime](
            value=value,
            source_text=sentence,
            source_field="description",
            extraction_method="explicit_rule",
            confidence=0.95,
        )
    return None
