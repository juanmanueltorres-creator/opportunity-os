from __future__ import annotations

from collections import OrderedDict

from app.cv.models import CVClaim, CVDocumentModel, EvidenceSelection, ValidationResult
from app.cv.narrative.ranking import rank_validated_claims
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterExperienceEntry,
    RecruiterProjectEntry,
    TechnologyGroup,
)
from app.cv.recruiter_policy import RecruiterPolicy
from app.cv.strategy.models import CVStrategy


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _validated_claims(
    document: CVDocumentModel,
    validation: ValidationResult,
) -> list[CVClaim]:
    validated_ids = set(validation.validated_claim_ids)
    return [claim for claim in document.claims if claim.claim_id in validated_ids]


def _resolve_positioning_claim(
    *,
    claims: list[CVClaim],
    document: CVDocumentModel,
    strategy: CVStrategy,
) -> CVClaim:
    positioning_messages = [
        message
        for message in strategy.core_messages
        if message.id == "positioning"
        or _normalize(message.message) == _normalize(strategy.positioning)
    ]
    message_fact_ids = {
        fact_id for message in positioning_messages for fact_id in message.fact_ids
    }
    message_evidence_ids = {
        evidence_id
        for message in positioning_messages
        for evidence_id in message.evidence_ids
    }

    for claim in claims:
        if claim.section != "headline" or claim.kind != "headline":
            continue
        if _normalize(claim.text) != _normalize(strategy.positioning):
            continue
        provenance = document.provenance_map.get(claim.claim_id)
        if provenance is None:
            continue
        if set(provenance.fact_ids) & message_fact_ids:
            return claim
        if set(provenance.evidence_ids) & message_evidence_ids:
            return claim
    raise ValueError("narrative_positioning_claim_unresolved")


def _rank(
    *,
    claims: list[CVClaim],
    document: CVDocumentModel,
    validation: ValidationResult,
    selection: EvidenceSelection,
    strategy: CVStrategy,
) -> list[CVClaim]:
    return rank_validated_claims(
        claims=claims,
        document=document,
        validation=validation,
        selection=selection,
        strategy=strategy,
    )


def _first_structural_claim(
    claims: list[CVClaim],
    *,
    kinds: set[str],
    label: str,
) -> CVClaim:
    for claim in claims:
        if claim.kind in kinds:
            return claim
    raise ValueError(f"narrative_missing_{label}_claim")


def _group_skills(
    *,
    ranked_claims: list[CVClaim],
    policy: RecruiterPolicy,
) -> list[TechnologyGroup]:
    member_to_group: dict[str, str] = {}
    for group_id, group in policy.skill_groups.items():
        if group_id == "additional":
            continue
        for member in group.members:
            member_to_group.setdefault(_normalize(member), group_id)

    grouped: OrderedDict[str, list[str]] = OrderedDict()
    seen_texts: set[str] = set()
    for claim in ranked_claims:
        if claim.kind != "skill":
            continue
        normalized = _normalize(claim.text)
        if normalized in seen_texts:
            continue
        seen_texts.add(normalized)
        group_id = member_to_group.get(normalized)
        if group_id is None and "additional" in policy.skill_groups:
            group_id = "additional"
        if group_id is None:
            continue
        grouped.setdefault(group_id, []).append(claim.claim_id)

    result: list[TechnologyGroup] = []
    remaining_tokens = policy.max_skill_tokens
    for group_id, claim_ids in grouped.items():
        if len(result) >= policy.max_skill_groups or remaining_tokens <= 0:
            break
        selected = claim_ids[:remaining_tokens]
        if selected:
            result.append(
                TechnologyGroup(label_id=group_id, skill_claim_ids=selected)
            )
            remaining_tokens -= len(selected)
    return result


def _overlapping_bullet_ids(
    *,
    primary_claim_id: str,
    ranked_bullets: list[CVClaim],
    document: CVDocumentModel,
    used_bullets: set[str],
) -> list[str]:
    primary = document.provenance_map.get(primary_claim_id)
    if primary is None:
        return []
    primary_facts = set(primary.fact_ids)
    for bullet in ranked_bullets:
        if bullet.claim_id in used_bullets:
            continue
        provenance = document.provenance_map.get(bullet.claim_id)
        if provenance is None:
            continue
        if primary_facts & set(provenance.fact_ids):
            used_bullets.add(bullet.claim_id)
            return [bullet.claim_id]
    return []


def _project_entries(
    *,
    projects: list[CVClaim],
    bullets: list[CVClaim],
    document: CVDocumentModel,
) -> list[RecruiterProjectEntry]:
    used: set[str] = set()
    return [
        RecruiterProjectEntry(
            primary_claim_id=project.claim_id,
            bullet_claim_ids=_overlapping_bullet_ids(
                primary_claim_id=project.claim_id,
                ranked_bullets=bullets,
                document=document,
                used_bullets=used,
            ),
        )
        for project in projects
    ]


def _experience_entries(
    *,
    primary_claims: list[CVClaim],
    bullets: list[CVClaim],
    document: CVDocumentModel,
) -> list[RecruiterExperienceEntry]:
    used: set[str] = set()
    return [
        RecruiterExperienceEntry(
            primary_claim_id=primary.claim_id,
            bullet_claim_ids=_overlapping_bullet_ids(
                primary_claim_id=primary.claim_id,
                ranked_bullets=bullets,
                document=document,
                used_bullets=used,
            ),
        )
        for primary in primary_claims
    ]


def compose_strategy_recruiter_document(
    *,
    document: CVDocumentModel,
    validation: ValidationResult,
    selection: EvidenceSelection,
    strategy: CVStrategy,
    policy: RecruiterPolicy,
) -> RecruiterDocumentModel:
    claims = _validated_claims(document, validation)
    claim_by_id = {claim.claim_id: claim for claim in claims}

    identity = _first_structural_claim(claims, kinds={"identity"}, label="identity")
    headline = _resolve_positioning_claim(
        claims=claims,
        document=document,
        strategy=strategy,
    )

    ranked = _rank(
        claims=claims,
        document=document,
        validation=validation,
        selection=selection,
        strategy=strategy,
    )

    contact_claim_ids = [
        claim.claim_id for claim in claims if claim.kind in {"contact", "location"}
    ]
    profile_claim_ids = [
        claim.claim_id for claim in ranked if claim.kind == "summary"
    ][: policy.max_profile_claims]

    technology_groups = _group_skills(ranked_claims=ranked, policy=policy)

    projects = [claim for claim in ranked if claim.kind == "project"][
        : policy.max_projects
    ]
    project_bullets = [
        claim
        for claim in ranked
        if claim.section == "projects" and claim.kind == "bullet"
    ]
    project_entries = _project_entries(
        projects=projects,
        bullets=project_bullets,
        document=document,
    )

    experience_primary = [
        claim
        for claim in ranked
        if claim.section == "experience" and claim.kind != "bullet"
    ][: policy.max_experience_entries]
    experience_bullets = [
        claim
        for claim in ranked
        if claim.section == "experience" and claim.kind == "bullet"
    ]
    experience_entries = _experience_entries(
        primary_claims=experience_primary,
        bullets=experience_bullets,
        document=document,
    )

    education_claim_ids = [
        claim.claim_id for claim in claims if claim.kind == "education"
    ][: policy.max_education_items]
    language_claim_ids = [
        claim.claim_id for claim in claims if claim.kind == "language"
    ]
    link_claim_ids = [claim.claim_id for claim in claims if claim.kind == "link"]

    assert identity.claim_id in claim_by_id
    assert headline.claim_id in claim_by_id

    return RecruiterDocumentModel(
        source_cv_document_version=document.document_version,
        language=document.language,
        identity_claim_id=identity.claim_id,
        headline_claim_id=headline.claim_id,
        contact_claim_ids=contact_claim_ids,
        profile_claim_ids=profile_claim_ids,
        technology_groups=technology_groups,
        selected_project_claim_ids=[project.claim_id for project in projects],
        project_entries=project_entries,
        experience_entries=experience_entries,
        education_claim_ids=education_claim_ids,
        language_claim_ids=language_claim_ids,
        link_claim_ids=link_claim_ids,
    )
