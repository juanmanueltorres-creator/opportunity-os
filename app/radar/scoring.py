from __future__ import annotations

import re
from datetime import datetime, timezone

from app.matching.scorer import assess_opportunity
from app.models.domain import (
    CandidateProfile,
    CandidateTrack,
    EvidenceItem,
    Opportunity,
    OpportunityAssessment,
    Recommendation,
)
from app.radar.eligibility import evaluate_eligibility
from app.radar.models import (
    IncomeAssessment,
    OpportunityEnrichment,
    Requirement,
    TrackCareerAssessment,
)
from app.radar.profile import effective_tracks
from app.radar.taxonomy import SkillMatchLevel, TaxonomyResolver

_CAPABILITY_KINDS = {"skill", "experience"}
_BARRIER_KINDS = {"license", "education", "experience", "work_authorization"}
_EXPERIENCE_YEARS_RE = re.compile(
    r"\b(?P<years>\d+(?:\.\d+)?)\s*(?:\+|[-–—]\s*\d+(?:\.\d+)?)?\s*(?:years?|años?|anos?)\b",
    re.IGNORECASE,
)
_EXPERIENCE_CONTEXT_STOPWORDS = {
    "a", "al", "and", "anos", "años", "at", "de", "del", "el", "en",
    "experience", "experiencia", "least", "minimum", "minimo", "mínimo",
    "of", "or", "the", "y", "year", "years",
}
_ROLE_TOKEN_ALIASES = {
    "engineering": "engineer",
    "engineers": "engineer",
    "ingenieria": "engineer",
    "ingeniería": "engineer",
    "ingeniero": "engineer",
    "ingeniera": "engineer",
    "developer": "develop",
    "developers": "develop",
    "development": "develop",
    "desarrollador": "develop",
    "desarrolladora": "develop",
    "desarrollo": "develop",
    "management": "manager",
    "gestion": "manager",
    "gestión": "manager",
}
_ROLE_TOKEN_STOPWORDS = {
    "a", "and", "as", "como", "de", "del", "en", "experience", "experiencia",
    "hacia", "in", "jr", "junior", "of", "position", "posición", "posicion",
    "principal", "role", "roles", "rol", "senior", "sr", "staff", "the",
    "transition", "transicion", "transición", "toward", "towards", "y",
}
_ROLE_HEAD_TOKENS = {
    "analyst", "architect", "develop", "engineer", "lead", "manager", "scientist",
}


def assess_career(
    opportunity: Opportunity,
    enrichment: OpportunityEnrichment,
    profile: CandidateProfile,
    track: CandidateTrack,
    resolver: TaxonomyResolver,
    *,
    now: datetime,
) -> OpportunityAssessment:
    """Score one CAREER track while preserving V0.1's public 40/20/20/10/10 shape."""

    assessment_time = _aware_now(now)
    track_profile = _profile_for_track(profile, track)
    mandatory = _career_requirements(enrichment, importance="mandatory")
    preferred = _career_requirements(enrichment, importance="preferred")

    if not mandatory and not preferred:
        return assess_opportunity(opportunity, track_profile, now=assessment_time)

    required_terms, _ = _resolved_terms(
        [requirement for requirement in mandatory if requirement.kind == "skill"],
        track,
        resolver,
    )
    preferred_terms, _ = _resolved_terms(
        [requirement for requirement in preferred if requirement.kind == "skill"],
        track,
        resolver,
    )
    mandatory_resolutions = _resolved_career_requirements(mandatory, track, resolver)
    preferred_resolutions = _resolved_career_requirements(preferred, track, resolver)
    score_opportunity = opportunity.model_copy(
        update={
            "required_skills": required_terms,
            "preferred_skills": preferred_terms,
        }
    )
    base = assess_opportunity(score_opportunity, track_profile, now=assessment_time)
    domain_fit, matched_domains = _career_domain_fit(opportunity, enrichment, track)
    evidence_requirements = _career_evidence_requirements(mandatory, preferred)
    if evidence_requirements:
        evidence_fit, selected_evidence = _career_evidence_fit(
            evidence_requirements,
            track,
            resolver,
            matched_domains,
        )
    else:
        evidence_fit, selected_evidence = base.evidence_fit, base.evidence

    target_requirements = mandatory if mandatory else preferred
    target_resolutions = mandatory_resolutions if mandatory else preferred_resolutions
    mandatory_fit = _weighted_requirement_fit(target_resolutions)

    strengths: list[str] = []
    gaps: list[str] = []
    for requirement, (_, multiplier, experience_status) in zip(
        target_requirements,
        target_resolutions,
    ):
        if requirement.kind == "experience":
            if experience_status == "satisfied":
                strengths.append(requirement.value)
            else:
                gaps.append(requirement.value)
        elif multiplier > 0.0:
            strengths.append(requirement.value)
        else:
            gaps.append(requirement.value)

    if mandatory:
        for requirement, (_, multiplier, _) in zip(preferred, preferred_resolutions):
            if requirement.kind == "skill" and multiplier > 0.0:
                _append_unique(strengths, requirement.value)

    risks = list(base.risks)
    for requirement, (_, _, experience_status) in zip(
        mandatory,
        mandatory_resolutions,
    ):
        if requirement.kind != "experience":
            continue
        if experience_status == "partial":
            _append_unique(risks, "experience_duration_below_posting")
        elif experience_status == "unknown":
            _append_unique(risks, "experience_duration_unverified")

    overall_score = round(
        0.40 * mandatory_fit
        + 0.20 * domain_fit
        + 0.20 * evidence_fit
        + 0.10 * base.location_fit
        + 0.10 * base.freshness_fit,
        1,
    )
    recommendation = _recommend(overall_score, risks)
    explanation = (
        f"mandatory={mandatory_fit:.1f}; domain={domain_fit:.1f}; "
        f"evidence={evidence_fit:.1f}; location={base.location_fit:.1f}; "
        f"freshness={base.freshness_fit:.1f}; matched={strengths}; "
        f"gaps={gaps}; risks={risks}"
    )

    return OpportunityAssessment(
        opportunity_id=opportunity.id,
        overall_score=overall_score,
        mandatory_fit=mandatory_fit,
        domain_fit=domain_fit,
        evidence_fit=evidence_fit,
        location_fit=base.location_fit,
        freshness_fit=base.freshness_fit,
        strengths=strengths,
        gaps=gaps,
        risks=risks,
        evidence=selected_evidence,
        recommendation=recommendation,
        explanation=explanation,
    )


def assess_income(
    opportunity: Opportunity,
    enrichment: OpportunityEnrichment,
    profile: CandidateProfile,
    track: CandidateTrack,
    resolver: TaxonomyResolver,
    *,
    now: datetime,
) -> IncomeAssessment:
    """Score immediate-income viability independently from career fit."""

    assessment_time = _aware_now(now)
    capability_fit, matched_capabilities, capability_gaps = _capability_fit(
        enrichment,
        track,
        resolver,
    )
    logistics_fit = _logistics_fit(opportunity, profile, track)
    schedule_fit = _schedule_fit(enrichment, profile, track)
    entry_friction_fit, unknown_barriers, barrier_gaps = _entry_friction_fit(
        enrichment,
        profile,
        track,
    )
    freshness_fit = _freshness_fit(opportunity, assessment_time)

    income_viability = round(
        0.35 * capability_fit
        + 0.25 * logistics_fit
        + 0.15 * schedule_fit
        + 0.15 * entry_friction_fit
        + 0.10 * freshness_fit,
        1,
    )

    return IncomeAssessment(
        track_id=track.id,
        income_viability=income_viability,
        capability_fit=capability_fit,
        logistics_fit=logistics_fit,
        schedule_fit=schedule_fit,
        entry_friction_fit=entry_friction_fit,
        freshness_fit=freshness_fit,
        matched_capabilities=matched_capabilities,
        gaps=_dedupe([*capability_gaps, *barrier_gaps]),
        unknown_barriers=_dedupe(unknown_barriers),
    )


def best_track_assessments(
    opportunity: Opportunity,
    enrichment: OpportunityEnrichment,
    profile: CandidateProfile,
    resolver: TaxonomyResolver,
    *,
    now: datetime,
) -> tuple[TrackCareerAssessment | None, IncomeAssessment | None]:
    """Choose the best eligible track independently for each search intent."""

    career: list[TrackCareerAssessment] = []
    income: list[IncomeAssessment] = []

    for track in effective_tracks(profile):
        eligibility = evaluate_eligibility(opportunity, enrichment, profile, track)
        if not eligibility.eligible:
            continue

        if "CAREER" in track.intents:
            career.append(
                TrackCareerAssessment(
                    track_id=track.id,
                    assessment=assess_career(
                        opportunity,
                        enrichment,
                        profile,
                        track,
                        resolver,
                        now=now,
                    ),
                )
            )
        if "INCOME_NOW" in track.intents:
            income.append(
                assess_income(
                    opportunity,
                    enrichment,
                    profile,
                    track,
                    resolver,
                    now=now,
                )
            )

    best_career = min(
        career,
        key=lambda item: (-item.assessment.overall_score, item.track_id),
        default=None,
    )
    best_income = min(
        income,
        key=lambda item: (-item.income_viability, item.track_id),
        default=None,
    )
    return best_career, best_income


def _profile_for_track(
    profile: CandidateProfile,
    track: CandidateTrack,
) -> CandidateProfile:
    return profile.model_copy(
        update={
            "roles": list(track.roles),
            "skills": _verified_candidate_skills(track),
            "domains": list(track.domains),
            "evidence": list(track.evidence),
            "tracks": [],
        }
    )


def _career_requirements(
    enrichment: OpportunityEnrichment,
    *,
    importance: str,
) -> list[Requirement]:
    return [
        requirement
        for requirement in enrichment.requirements
        if requirement.importance == importance
        and (
            requirement.kind == "skill"
            or (
                requirement.kind == "experience"
                and _minimum_experience_years(requirement.value) is not None
            )
        )
    ]


def _resolved_terms(
    requirements: list[Requirement],
    track: CandidateTrack,
    resolver: TaxonomyResolver,
) -> tuple[list[str], list[tuple[str | None, float]]]:
    terms: list[str] = []
    resolutions: list[tuple[str | None, float]] = []
    candidate_skills = _verified_candidate_skills(track)
    for requirement in requirements:
        resolved = resolver.resolve_skill(requirement.value, candidate_skills)
        matched_value = resolved.matched_skill
        multiplier = resolved.multiplier
        if (
            requirement.exactness == "exact_product"
            and resolved.level == SkillMatchLevel.TAXONOMY_RELATED
        ):
            multiplier = 0.0
        if multiplier == 0.0 and requirement.exactness != "exact_product":
            role_match = _match_candidate_role(requirement.value, track.roles)
            if role_match is not None:
                matched_value = role_match
                multiplier = 1.0
        resolutions.append((matched_value, multiplier))
        if multiplier > 0.0 and matched_value is not None:
            terms.append(matched_value)
        else:
            terms.append(requirement.value)
    return terms, resolutions


def _resolved_career_requirements(
    requirements: list[Requirement],
    track: CandidateTrack,
    resolver: TaxonomyResolver,
) -> list[tuple[str | None, float, str | None]]:
    skill_resolutions = iter(_resolved_terms(
        [requirement for requirement in requirements if requirement.kind == "skill"],
        track,
        resolver,
    )[1])
    resolutions: list[tuple[str | None, float, str | None]] = []
    for requirement in requirements:
        if requirement.kind == "skill":
            matched_skill, multiplier = next(skill_resolutions)
            resolutions.append((matched_skill, multiplier, None))
            continue
        status, score = _career_experience_support(requirement, track)
        resolutions.append((requirement.value if score > 0.0 else None, score, status))
    return resolutions


def _career_evidence_requirements(
    mandatory: list[Requirement],
    preferred: list[Requirement],
) -> list[Requirement]:
    mandatory_skills = [requirement for requirement in mandatory if requirement.kind == "skill"]
    if mandatory_skills:
        return mandatory_skills
    return [requirement for requirement in preferred if requirement.kind == "skill"]


def _career_domain_fit(
    opportunity: Opportunity,
    enrichment: OpportunityEnrichment,
    track: CandidateTrack,
) -> tuple[float, set[str]]:
    """Treat CAREER domains as compatibility signals, not a candidate-completeness ratio."""

    if not track.domains:
        return 50.0, set()
    corpus = " ".join(
        [
            opportunity.title,
            opportunity.description,
            *(requirement.value for requirement in enrichment.requirements),
        ]
    )
    matched = {
        _normalize(domain)
        for domain in track.domains
        if _contains_phrase(corpus, domain)
    }
    if matched:
        return 100.0, matched
    return 50.0, set()


def _career_evidence_fit(
    requirements: list[Requirement],
    track: CandidateTrack,
    resolver: TaxonomyResolver,
    matched_domains: set[str],
) -> tuple[float, list[EvidenceItem]]:
    """Measure verified evidence coverage for CAREER capabilities, including role-backed ones."""

    if not requirements:
        return 50.0, []

    covered: set[int] = set()
    selected: list[EvidenceItem] = []
    for evidence in track.evidence:
        if not evidence.verified:
            continue
        supported_indexes = {
            index
            for index, requirement in enumerate(requirements)
            if _evidence_supports_career_requirement(
                requirement, evidence, track, resolver, matched_domains
            )
        }
        if not supported_indexes:
            continue
        covered.update(supported_indexes)
        selected.append(evidence)

    return round(len(covered) / len(requirements) * 100.0, 1), selected


def _evidence_supports_career_requirement(
    requirement: Requirement,
    evidence: EvidenceItem,
    track: CandidateTrack,
    resolver: TaxonomyResolver,
    matched_domains: set[str],
) -> bool:
    resolved = resolver.resolve_skill(requirement.value, evidence.skills)
    multiplier = resolved.multiplier
    if (
        requirement.exactness == "exact_product"
        and resolved.level == SkillMatchLevel.TAXONOMY_RELATED
    ):
        multiplier = 0.0
    if multiplier > 0.0:
        return True

    if requirement.exactness == "exact_product":
        return False
    if _match_candidate_role(requirement.value, track.roles) is None:
        return False
    if evidence.type not in {"project", "experience"}:
        return False
    evidence_domains = {_normalize(domain) for domain in evidence.domains}
    return bool(matched_domains and evidence_domains.intersection(matched_domains))


def _match_candidate_role(term: str, candidate_roles: list[str]) -> str | None:
    target_tokens = _role_tokens(term)
    if len(target_tokens) < 2 or not target_tokens.intersection(_ROLE_HEAD_TOKENS):
        return None

    for role in candidate_roles:
        role_tokens = _role_tokens(role)
        if len(role_tokens) < 2 or not role_tokens.intersection(_ROLE_HEAD_TOKENS):
            continue
        overlap = target_tokens.intersection(role_tokens)
        if len(overlap) < 2:
            continue
        if target_tokens == role_tokens:
            return role
        if target_tokens.issubset(role_tokens) or role_tokens.issubset(target_tokens):
            return role
    return None


def _role_tokens(value: str) -> set[str]:
    tokens = {
        _ROLE_TOKEN_ALIASES.get(token, token)
        for token in re.findall(r"[^\W\d_]+", value.casefold(), flags=re.UNICODE)
        if token not in _ROLE_TOKEN_STOPWORDS
    }
    return {token for token in tokens if len(token) >= 2}


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = _normalize(phrase)
    if not normalized_phrase:
        return False
    return re.search(
        rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)",
        _normalize(text),
    ) is not None


def _minimum_experience_years(value: str) -> float | None:
    match = _EXPERIENCE_YEARS_RE.search(value)
    if match is None:
        return None
    return float(match.group("years"))


def _verified_candidate_skills(track: CandidateTrack) -> list[str]:
    skills = list(track.skills)
    seen = {_normalize(value) for value in skills}
    for evidence in track.evidence:
        if not evidence.verified:
            continue
        for skill in evidence.skills:
            key = _normalize(skill)
            if key and key not in seen:
                seen.add(key)
                skills.append(skill)
    return skills


def _weighted_requirement_fit(
    resolutions: list[tuple[str | None, float, str | None]],
) -> float:
    if not resolutions:
        return 50.0
    return round(
        sum(multiplier for _, multiplier, _ in resolutions) / len(resolutions) * 100.0,
        1,
    )


def _capability_fit(
    enrichment: OpportunityEnrichment,
    track: CandidateTrack,
    resolver: TaxonomyResolver,
) -> tuple[float, list[str], list[str]]:
    mandatory = [
        requirement
        for requirement in enrichment.requirements
        if requirement.kind in _CAPABILITY_KINDS
        and requirement.importance == "mandatory"
    ]
    preferred = [
        requirement
        for requirement in enrichment.requirements
        if requirement.kind in _CAPABILITY_KINDS
        and requirement.importance == "preferred"
    ]
    targets = mandatory or preferred
    if not targets:
        return 50.0, [], []

    scores: list[float] = []
    matched: list[str] = []
    gaps: list[str] = []
    for requirement in targets:
        if requirement.kind == "skill":
            resolved = resolver.resolve_skill(
                requirement.value,
                _verified_candidate_skills(track),
            )
            score = resolved.multiplier
            if (
                requirement.exactness == "exact_product"
                and resolved.level == SkillMatchLevel.TAXONOMY_RELATED
            ):
                score = 0.0
        else:
            score = _experience_capability_score(requirement, track)
        scores.append(score)
        if score > 0.0:
            matched.append(requirement.value)
        else:
            gaps.append(requirement.value)

    return round(sum(scores) / len(scores) * 100.0, 1), matched, gaps


def _career_experience_support(
    requirement: Requirement,
    track: CandidateTrack,
) -> tuple[str, float]:
    """Return deterministic CAREER experience support without inventing duration.

    Statuses are internal-only: satisfied=1.0, partial=verified/requested,
    unknown=0.5 when relevant verified capability exists without duration, and
    unsupported=0.0 when no relevant verified evidence exists.
    """

    required_years = _minimum_experience_years(requirement.value)
    required_context = _experience_context_terms(requirement.value)
    relevant: list[EvidenceItem] = []

    for evidence in track.evidence:
        if not evidence.verified or evidence.type not in {"experience", "project"}:
            continue
        corpus = " ".join([evidence.label, *evidence.skills, *evidence.domains])
        evidence_context = _experience_context_terms(corpus)
        if required_context and not required_context.intersection(evidence_context):
            continue
        relevant.append(evidence)

    if not relevant:
        return "unsupported", 0.0
    if required_years is None:
        return "satisfied", 1.0

    explicit_years = [
        years
        for evidence in relevant
        if evidence.type == "experience"
        and (years := _minimum_experience_years(evidence.label)) is not None
    ]
    if not explicit_years:
        return "unknown", 0.5

    evidenced_years = max(explicit_years)
    if evidenced_years >= required_years:
        return "satisfied", 1.0
    if required_years <= 0.0:
        return "satisfied", 1.0
    return "partial", min(evidenced_years / required_years, 1.0)


def _experience_capability_score(
    requirement: Requirement,
    track: CandidateTrack,
) -> float:
    """Preserve strict INCOME_NOW capability semantics for experience barriers."""

    requirement_key = _normalize(requirement.value)
    required_years = _minimum_experience_years(requirement.value)
    required_context = _experience_context_terms(requirement.value)

    for evidence in track.evidence:
        if not evidence.verified or evidence.type != "experience":
            continue
        corpus = " ".join([evidence.label, *evidence.skills, *evidence.domains])
        if required_years is not None:
            evidenced_years = _minimum_experience_years(evidence.label)
            if evidenced_years is None or evidenced_years < required_years:
                continue
            evidence_context = _experience_context_terms(corpus)
            if not required_context or required_context.intersection(evidence_context):
                return 1.0
            continue
        if requirement_key and requirement_key in _normalize(corpus):
            return 1.0
    return 0.0


def _experience_context_terms(value: str) -> set[str]:
    terms = {
        token.casefold()
        for token in re.findall(r"[^\W\d_]+", value, flags=re.UNICODE)
    }
    return {
        term
        for term in terms
        if len(term) >= 3 and term not in _EXPERIENCE_CONTEXT_STOPWORDS
    }


def _logistics_fit(
    opportunity: Opportunity,
    profile: CandidateProfile,
    track: CandidateTrack,
) -> float:
    posting_mode = _canonical_work_mode(opportunity.remote_policy)
    configured_modes = track.accepted_work_modes or profile.remote_preferences
    accepted_modes = {
        canonical
        for value in configured_modes
        if (canonical := _canonical_work_mode(value)) is not None
    }

    if posting_mode is not None and accepted_modes:
        return 100.0 if posting_mode in accepted_modes else 0.0

    if opportunity.location and profile.locations:
        posting_location = _normalize(opportunity.location)
        if any(
            posting_location in _normalize(location)
            or _normalize(location) in posting_location
            for location in profile.locations
        ):
            return 100.0
        if posting_mode == "onsite":
            return 0.0

    return 50.0


def _schedule_fit(
    enrichment: OpportunityEnrichment,
    profile: CandidateProfile,
    track: CandidateTrack,
) -> float:
    schedules: list[str] = []
    if enrichment.work_schedule is not None:
        schedules.append(str(enrichment.work_schedule.value))
    schedules.extend(
        requirement.value
        for requirement in enrichment.requirements
        if requirement.kind == "schedule" and requirement.importance == "mandatory"
    )
    if not schedules:
        return 50.0

    no_go = [*profile.no_go_constraints, *track.no_go_constraints]
    for schedule in schedules:
        schedule_key = _normalize(schedule)
        for constraint in no_go:
            constraint_key = _normalize(constraint)
            if constraint_key and (
                constraint_key in schedule_key or schedule_key in constraint_key
            ):
                return 0.0
    return 100.0


def _entry_friction_fit(
    enrichment: OpportunityEnrichment,
    profile: CandidateProfile,
    track: CandidateTrack,
) -> tuple[float, list[str], list[str]]:
    barriers = [
        requirement
        for requirement in enrichment.requirements
        if requirement.importance == "mandatory"
        and (
            requirement.kind in _BARRIER_KINDS
            or requirement.exactness == "declarative"
        )
    ]
    if not barriers:
        return 100.0, [], []

    scores: list[float] = []
    unknowns: list[str] = []
    gaps: list[str] = []
    for requirement in barriers:
        status = _barrier_status(requirement, profile, track)
        scores.append(status)
        if status == 50.0:
            unknowns.append(requirement.value)
        elif status == 0.0:
            gaps.append(requirement.value)

    return round(sum(scores) / len(scores), 1), unknowns, gaps


def _barrier_status(
    requirement: Requirement,
    profile: CandidateProfile,
    track: CandidateTrack,
) -> float:
    requirement_key = _normalize(requirement.value)

    if requirement.kind == "license":
        if not profile.verified_licenses:
            return 50.0
        return (
            100.0
            if requirement_key
            in {_normalize(value) for value in profile.verified_licenses}
            else 0.0
        )

    if requirement.kind == "work_authorization":
        if not profile.work_authorizations:
            return 50.0
        return (
            100.0
            if requirement_key
            in {_normalize(value) for value in profile.work_authorizations}
            else 0.0
        )

    if requirement.kind in {"education", "experience"}:
        relevant_type = requirement.kind
        verified = [
            evidence
            for evidence in track.evidence
            if evidence.verified and evidence.type == relevant_type
        ]
        if not verified:
            return 50.0
        for evidence in verified:
            corpus = " ".join(
                [evidence.label, *evidence.skills, *evidence.domains]
            ).casefold()
            if requirement_key and requirement_key in corpus:
                return 100.0
        return 50.0

    return 50.0


def _freshness_fit(opportunity: Opportunity, now: datetime) -> float:
    if opportunity.published_at is None:
        return 50.0
    age_days = max(0.0, (now - opportunity.published_at).total_seconds() / 86400.0)
    if age_days <= 7:
        return 100.0
    if age_days <= 30:
        return 75.0
    if age_days <= 90:
        return 25.0
    return 0.0


def _recommend(score: float, risks: list[str]) -> Recommendation:
    if score >= 75.0:
        recommendation: Recommendation = "apply"
    elif score >= 55.0:
        recommendation = "stretch"
    elif score >= 35.0:
        recommendation = "nurture"
    else:
        recommendation = "discard"
    if "location conflict" in risks and recommendation == "apply":
        return "stretch"
    return recommendation


def _canonical_work_mode(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _normalize(value)
    if normalized in {"onsite", "on-site", "on site", "presencial"}:
        return "onsite"
    if normalized in {"hybrid", "híbrido", "hibrido"}:
        return "hybrid"
    if normalized in {"remote", "remoto", "remota"}:
        return "remote"
    return None


def _aware_now(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
