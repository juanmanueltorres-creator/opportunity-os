from __future__ import annotations

from app.models.domain import CandidateProfile, CandidateTrack, Opportunity
from app.radar.models import EligibilityResult, OpportunityEnrichment, Requirement

_CLOSED_STATUSES = {"closed", "expired", "filled", "inactive"}


def evaluate_eligibility(
    opportunity: Opportunity,
    enrichment: OpportunityEnrichment,
    profile: CandidateProfile,
    track: CandidateTrack,
) -> EligibilityResult:
    """Evaluate only explicit, factual eligibility constraints.

    Missing candidate facts remain UNKNOWN rather than becoming incompatibilities.
    Semantic/taxonomy relationships are intentionally not accepted as proof for
    declarative requirements such as licenses or work authorization.
    """

    hard_fail_reasons: list[str] = []
    soft_risks: list[str] = []
    unknowns: list[str] = []

    if _normalize(opportunity.status) in _CLOSED_STATUSES:
        _append_unique(hard_fail_reasons, "posting_closed")

    _evaluate_role_family(enrichment, profile, soft_risks)
    _evaluate_work_mode(opportunity, profile, track, hard_fail_reasons)
    _evaluate_work_authorization(
        enrichment.requirements,
        profile,
        hard_fail_reasons,
        unknowns,
    )
    _evaluate_licenses(
        enrichment.requirements,
        profile,
        hard_fail_reasons,
        unknowns,
    )
    _evaluate_schedule(
        enrichment,
        profile,
        track,
        hard_fail_reasons,
    )

    return EligibilityResult(
        eligible=not hard_fail_reasons,
        hard_fail_reasons=hard_fail_reasons,
        soft_risks=soft_risks,
        unknowns=unknowns,
    )


def _evaluate_role_family(
    enrichment: OpportunityEnrichment,
    profile: CandidateProfile,
    soft_risks: list[str],
) -> None:
    if enrichment.role_family is None or not profile.target_role_families:
        return

    role_family = _normalize(enrichment.role_family.value)
    targets = {_normalize(value) for value in profile.target_role_families}
    if role_family not in targets:
        _append_unique(soft_risks, "role_outside_target_family")


def _evaluate_work_mode(
    opportunity: Opportunity,
    profile: CandidateProfile,
    track: CandidateTrack,
    hard_fail_reasons: list[str],
) -> None:
    posting_mode = _canonical_work_mode(opportunity.remote_policy)
    if posting_mode is None:
        return

    configured_modes = track.accepted_work_modes or profile.remote_preferences
    if not configured_modes:
        return

    accepted_modes = {
        canonical
        for value in configured_modes
        if (canonical := _canonical_work_mode(value)) is not None
    }
    if accepted_modes and posting_mode not in accepted_modes:
        _append_unique(hard_fail_reasons, "location_incompatible")


def _evaluate_work_authorization(
    requirements: list[Requirement],
    profile: CandidateProfile,
    hard_fail_reasons: list[str],
    unknowns: list[str],
) -> None:
    mandatory = _mandatory_requirements(requirements, kind="work_authorization")
    if not mandatory:
        return

    if not profile.work_authorizations:
        _append_unique(unknowns, "work_authorization_unverified")
        return

    configured = {_normalize(value) for value in profile.work_authorizations}
    for requirement in mandatory:
        if _normalize(requirement.value) not in configured:
            _append_unique(hard_fail_reasons, "work_authorization_incompatible")
            return


def _evaluate_licenses(
    requirements: list[Requirement],
    profile: CandidateProfile,
    hard_fail_reasons: list[str],
    unknowns: list[str],
) -> None:
    mandatory = _mandatory_requirements(requirements, kind="license")
    if not mandatory:
        return

    if not profile.verified_licenses:
        _append_unique(unknowns, "mandatory_license_unverified")
        return

    verified = {_normalize(value) for value in profile.verified_licenses}
    for requirement in mandatory:
        if _normalize(requirement.value) not in verified:
            _append_unique(hard_fail_reasons, "mandatory_license_missing")
            return


def _evaluate_schedule(
    enrichment: OpportunityEnrichment,
    profile: CandidateProfile,
    track: CandidateTrack,
    hard_fail_reasons: list[str],
) -> None:
    no_go = [*profile.no_go_constraints, *track.no_go_constraints]
    if not no_go:
        return

    schedule_values: list[str] = []
    if enrichment.work_schedule is not None:
        schedule_values.append(str(enrichment.work_schedule.value))
    schedule_values.extend(
        requirement.value
        for requirement in _mandatory_requirements(
            enrichment.requirements,
            kind="schedule",
        )
    )

    for schedule in schedule_values:
        schedule_key = _normalize(schedule)
        for constraint in no_go:
            constraint_key = _normalize(constraint)
            if not constraint_key:
                continue
            if constraint_key in schedule_key or schedule_key in constraint_key:
                _append_unique(hard_fail_reasons, "schedule_no_go")
                return


def _mandatory_requirements(
    requirements: list[Requirement],
    *,
    kind: str,
) -> list[Requirement]:
    return [
        requirement
        for requirement in requirements
        if requirement.kind == kind and requirement.importance == "mandatory"
    ]


def _canonical_work_mode(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _normalize(value)
    if any(token in normalized for token in ("on-site", "onsite", "on site", "presencial")):
        return "onsite"
    if any(token in normalized for token in ("hybrid", "híbrido", "hibrido")):
        return "hybrid"
    if any(token in normalized for token in ("remote", "remoto", "remota")):
        return "remote"
    return None


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
