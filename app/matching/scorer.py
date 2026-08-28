from __future__ import annotations

from datetime import datetime, timezone
import re

from app.models.domain import CandidateProfile, EvidenceItem, Opportunity, OpportunityAssessment, Recommendation


def _normalize(value: str) -> str:
    return value.strip().casefold()


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = _normalize(phrase)
    if not normalized_phrase:
        return False
    return re.search(rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)", text.casefold()) is not None


def _ratio(matched: int, total: int, *, neutral: float = 50.0) -> float:
    if total == 0:
        return neutral
    return round((matched / total) * 100.0, 1)


def _skill_fit(opportunity: Opportunity, profile: CandidateProfile) -> tuple[float, list[str], list[str], list[str]]:
    profile_skills = {_normalize(skill) for skill in profile.skills}
    if opportunity.required_skills:
        targets = opportunity.required_skills
    elif opportunity.preferred_skills:
        targets = opportunity.preferred_skills
    else:
        return 50.0, [], [], []
    matched = [skill for skill in targets if _normalize(skill) in profile_skills]
    gaps = [skill for skill in targets if _normalize(skill) not in profile_skills]
    return _ratio(len(matched), len(targets)), matched, gaps, targets


def _domain_fit(opportunity: Opportunity, profile: CandidateProfile) -> tuple[float, set[str]]:
    if not profile.domains:
        return 50.0, set()
    corpus = " ".join(part for part in [opportunity.title, opportunity.description, *opportunity.required_skills, *opportunity.preferred_skills] if part)
    matched_domains = {_normalize(domain) for domain in profile.domains if _contains_phrase(corpus, domain)}
    return _ratio(len(matched_domains), len(profile.domains)), matched_domains


def _select_evidence(profile: CandidateProfile, target_skills: list[str], matched_domains: set[str]) -> tuple[float, list[EvidenceItem]]:
    target_norms = {_normalize(skill) for skill in target_skills}
    selected: list[EvidenceItem] = []
    for item in profile.evidence:
        if not item.verified:
            continue
        item_skills = {_normalize(skill) for skill in item.skills}
        item_domains = {_normalize(domain) for domain in item.domains}
        if (target_norms and item_skills & target_norms) or (matched_domains and item_domains & matched_domains):
            selected.append(item)
    if not target_norms:
        return (100.0 if selected else 50.0), selected
    covered: set[str] = set()
    for item in selected:
        covered.update({_normalize(skill) for skill in item.skills} & target_norms)
    return _ratio(len(covered), len(target_norms), neutral=0.0), selected


def _location_fit(opportunity: Opportunity, profile: CandidateProfile) -> tuple[float, list[str]]:
    risks: list[str] = []
    remote_policy = _normalize(opportunity.remote_policy or "")
    candidate_remote = any(_contains_phrase(preference, "remote") for preference in profile.remote_preferences)
    if "remote" in remote_policy and candidate_remote:
        return 100.0, risks
    if not opportunity.location:
        return 50.0, risks
    location_match = any(_contains_phrase(opportunity.location, candidate_location) or _contains_phrase(candidate_location, opportunity.location) for candidate_location in profile.locations)
    if location_match:
        return 100.0, risks
    if profile.locations:
        risks.append("location conflict")
        return 0.0, risks
    if remote_policy in {"on-site", "onsite", "on site"} and candidate_remote:
        risks.append("location conflict")
        return 0.0, risks
    return 50.0, risks


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


def assess_opportunity(opportunity: Opportunity, profile: CandidateProfile, now: datetime | None = None) -> OpportunityAssessment:
    assessment_time = now or datetime.now(timezone.utc)
    if assessment_time.tzinfo is None or assessment_time.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    assessment_time = assessment_time.astimezone(timezone.utc)
    mandatory_fit, strengths, gaps, target_skills = _skill_fit(opportunity, profile)
    domain_fit, matched_domains = _domain_fit(opportunity, profile)
    evidence_fit, evidence = _select_evidence(profile, target_skills, matched_domains)
    location_fit, risks = _location_fit(opportunity, profile)
    freshness_fit = _freshness_fit(opportunity, assessment_time)
    overall_score = round(0.40 * mandatory_fit + 0.20 * domain_fit + 0.20 * evidence_fit + 0.10 * location_fit + 0.10 * freshness_fit, 1)
    recommendation = _recommend(overall_score, risks)
    explanation = f"mandatory={mandatory_fit:.1f}; domain={domain_fit:.1f}; evidence={evidence_fit:.1f}; location={location_fit:.1f}; freshness={freshness_fit:.1f}; matched={strengths}; gaps={gaps}; risks={risks}"
    return OpportunityAssessment(opportunity_id=opportunity.id, overall_score=overall_score, mandatory_fit=mandatory_fit, domain_fit=domain_fit, evidence_fit=evidence_fit, location_fit=location_fit, freshness_fit=freshness_fit, strengths=strengths, gaps=gaps, risks=risks, evidence=evidence, recommendation=recommendation, explanation=explanation)
