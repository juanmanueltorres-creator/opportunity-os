from __future__ import annotations

from app.cv.models import (
    CVPolicy,
    EvidenceCatalogSnapshot,
    MasterFactsSnapshot,
)
from app.radar.models import RadarAssessment


class CVPreparationError(ValueError):
    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def resolve_application_track(assessment: RadarAssessment) -> str:
    if assessment.selected_intent == "CAREER":
        if assessment.best_career_track:
            return assessment.best_career_track
        if assessment.best_income_track:
            return assessment.best_income_track
        raise CVPreparationError("track_unavailable")

    if assessment.selected_intent == "INCOME_NOW":
        if assessment.best_income_track:
            return assessment.best_income_track
        if assessment.best_career_track:
            return assessment.best_career_track
        raise CVPreparationError("track_unavailable")

    candidates = {
        track
        for track in (assessment.best_career_track, assessment.best_income_track)
        if track
    }
    if len(candidates) == 1:
        return next(iter(candidates))
    raise CVPreparationError("track_unavailable")


def require_minimum_evidence(
    track_id: str,
    facts: MasterFactsSnapshot,
    catalog: EvidenceCatalogSnapshot,
    policy: CVPolicy,
) -> None:
    eligible_facts = [
        fact
        for fact in facts.facts
        if fact.verified and track_id in fact.track_ids
    ]
    eligible_modules = [
        module
        for module in catalog.modules
        if module.verified and track_id in module.track_ids
    ]

    missing_identity = [
        kind
        for kind in policy.required_identity_kinds
        if not any(fact.kind == kind for fact in eligible_facts)
    ]
    if missing_identity:
        raise CVPreparationError(
            "insufficient_verified_evidence",
            "required verified identity facts are unavailable for selected track",
        )

    has_substantive_fact = any(
        fact.kind in {"employment", "project"} for fact in eligible_facts
    )
    if not has_substantive_fact and not eligible_modules:
        raise CVPreparationError(
            "insufficient_verified_evidence",
            "selected track has no verified experience, project, or evidence module",
        )

    missing_sections = [
        section
        for section in policy.required_sections
        if not _section_has_truthful_content(
            section,
            eligible_facts=eligible_facts,
            eligible_modules=eligible_modules,
        )
    ]
    if missing_sections:
        raise CVPreparationError(
            "insufficient_verified_evidence",
            "required CV section has no verified content for selected track",
        )


def _section_has_truthful_content(
    section: str,
    *,
    eligible_facts: list,
    eligible_modules: list,
) -> bool:
    fact_kinds_by_section = {
        "headline": {"role", "summary_claim"},
        "summary": {"summary_claim", "achievement", "project", "employment"},
        "experience": {"employment"},
        "projects": {"project"},
        "education": {"education"},
        "skills": {"skill"},
        "languages": {"language"},
        "links": {"link"},
    }
    allowed_fact_kinds = fact_kinds_by_section.get(section, set())
    if any(fact.kind in allowed_fact_kinds for fact in eligible_facts):
        return True

    return any(
        any(claim.section == section for claim in module.claims)
        for module in eligible_modules
    )
