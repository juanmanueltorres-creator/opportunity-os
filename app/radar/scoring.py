from __future__ import annotations

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
    mandatory = _skill_requirements(enrichment, importance="mandatory")
    preferred = _skill_requirements(enrichment, importance="preferred")

    if not mandatory and not preferred:
        return assess_opportunity(opportunity, track_profile, now=assessment_time)

    required_terms, mandatory_resolutions = _resolved_terms(
        mandatory,
        track,
        resolver,
    )
    preferred_terms, preferred_resolutions = _resolved_terms(
        preferred,
        track,
        resolver,
    )
    score_opportunity = opportunity.model_copy(
        update={
            "required_skills": required_terms,
            "preferred_skills": preferred_terms,
        }
    )
    base = assess_opportunity(score_opportunity, track_profile, now=assessment_time)

    target_requirements = mandatory if mandatory else preferred
    target_resolutions = mandatory_resolutions if mandatory else preferred_resolutions
    mandatory_fit = _weighted_requirement_fit(target_resolutions)
    strengths = [
        requirement.value
        for requirement, (_, multiplier) in zip(target_requirements, target_resolutions)
        if multiplier > 0.0
    ]
    gaps = [
        requirement.value
        for requirement, (_, multiplier) in zip(target_requirements, target_resolutions)
        if multiplier == 0.0
    ]

    overall_score = round(
        0.40 * mandatory_fit
        + 0.20 * base.domain_fit
        + 0.20 * base.evidence_fit
        + 0.10 * base.location_fit
        + 0.10 * base.freshness_fit,
        1,
    )
    recommendation = _recommend(overall_score, base.risks)
    explanation = (
        f"mandatory={mandatory_fit:.1f}; domain={base.domain_fit:.1f}; "
        f"evidence={base.evidence_fit:.1f}; location={base.location_fit:.1f}; "
        f"freshness={base.freshness_fit:.1f}; matched={strengths}; "
        f"gaps={gaps}; risks={base.risks}"
    )

    return OpportunityAssessment(
        opportunity_id=opportunity.id,
        overall_score=overall_score,
        mandatory_fit=mandatory_fit,
        domain_fit=base.domain_fit,
        evidence_fit=base.evidence_fit,
        location_fit=base.location_fit,
        freshness_fit=base.freshness_fit,
        strengths=strengths,
        gaps=gaps,
        risks=base.risks,
        evidence=base.evidence,
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
            "skills": list(track.skills),
            "domains": list(track.domains),
            "evidence": list(track.evidence),
            "tracks": [],
        }
    )


def _skill_requirements(
    enrichment: OpportunityEnrichment,
    *,
    importance: str,
) -> list[Requirement]:
    return [
        requirement
        for requirement in enrichment.requirements
        if requirement.kind == "skill" and requirement.importance == importance
    ]


def _resolved_terms(
    requirements: list[Requirement],
    track: CandidateTrack,
    resolver: TaxonomyResolver,
) -> tuple[list[str], list[tuple[str | None, float]]]:
    terms: list[str] = []
    resolutions: list[tuple[str | None, float]] = []
    for requirement in requirements:
        resolved = resolver.resolve_skill(requirement.value, track.skills)
        multiplier = resolved.multiplier
        if (
            requirement.exactness == "exact_product"
            and resolved.level == SkillMatchLevel.TAXONOMY_RELATED
        ):
            multiplier = 0.0
        resolutions.append((resolved.matched_skill, multiplier))
        if multiplier > 0.0 and resolved.matched_skill is not None:
            terms.append(resolved.matched_skill)
        else:
            terms.append(requirement.value)
    return terms, resolutions


def _weighted_requirement_fit(
    resolutions: list[tuple[str | None, float]],
) -> float:
    if not resolutions:
        return 50.0
    return round(
        sum(multiplier for _, multiplier in resolutions) / len(resolutions) * 100.0,
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
            resolved = resolver.resolve_skill(requirement.value, track.skills)
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


def _experience_capability_score(
    requirement: Requirement,
    track: CandidateTrack,
) -> float:
    requirement_key = _normalize(requirement.value)
    for evidence in track.evidence:
        if not evidence.verified or evidence.type != "experience":
            continue
        corpus = " ".join(
            [evidence.label, *evidence.skills, *evidence.domains]
        ).casefold()
        if requirement_key and requirement_key in corpus:
            return 1.0
    return 0.0


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
