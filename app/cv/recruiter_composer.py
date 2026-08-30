from __future__ import annotations

from collections import OrderedDict

from app.cv.models import CVClaim, CVDocumentModel, EvidenceSelection, ValidationResult
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterExperienceEntry,
    RecruiterProjectEntry,
    TechnologyGroup,
)
from app.cv.recruiter_policy import RecruiterPolicy


def compose_recruiter_document(
    *,
    document: CVDocumentModel,
    validation: ValidationResult,
    selection: EvidenceSelection,
    policy: RecruiterPolicy,
) -> RecruiterDocumentModel:
    if not validation.valid:
        raise ValueError("recruiter composition requires a valid semantic document")

    validated_ids = set(validation.validated_claim_ids)
    validated_claims = [
        claim for claim in document.claims if claim.claim_id in validated_ids
    ]
    claim_by_id = {claim.claim_id: claim for claim in validated_claims}
    source_order = {
        claim.claim_id: index for index, claim in enumerate(document.claims)
    }
    supported_ids = _supported_claim_ids(document, selection) & validated_ids

    identity_claim_id = _first_claim_id(
        validated_claims,
        kinds={"identity"},
        supported_ids=supported_ids,
        source_order=source_order,
        required_label="identity",
    )
    headline_claim_id = _first_claim_id(
        validated_claims,
        kinds={"headline"},
        supported_ids=supported_ids,
        source_order=source_order,
        required_label="headline",
    )

    contact_claim_ids = _ordered_claim_ids(
        validated_claims,
        kinds={"contact", "location"},
        supported_ids=supported_ids,
        source_order=source_order,
    )
    profile_claim_ids = _ordered_claim_ids(
        validated_claims,
        kinds={"summary"},
        supported_ids=supported_ids,
        source_order=source_order,
    )[: policy.max_profile_claims]

    technology_groups = _group_skills(
        claims=validated_claims,
        policy=policy,
        supported_ids=supported_ids,
        source_order=source_order,
    )

    selected_project_claim_ids = _ordered_claim_ids(
        validated_claims,
        kinds={"project"},
        supported_ids=supported_ids,
        source_order=source_order,
    )[: policy.max_projects]
    project_entries = _compose_project_entries(
        project_claim_ids=selected_project_claim_ids,
        claims=validated_claims,
        document=document,
        supported_ids=supported_ids,
        source_order=source_order,
    )

    experience_entries = _compose_experience_entries(
        claims=validated_claims,
        document=document,
        supported_ids=supported_ids,
        source_order=source_order,
        max_entries=policy.max_experience_entries,
    )

    education_claim_ids = _ordered_claim_ids(
        validated_claims,
        kinds={"education"},
        supported_ids=supported_ids,
        source_order=source_order,
    )[: policy.max_education_items]
    language_claim_ids = _ordered_claim_ids(
        validated_claims,
        kinds={"language"},
        supported_ids=supported_ids,
        source_order=source_order,
    )
    link_claim_ids = _ordered_claim_ids(
        validated_claims,
        kinds={"link"},
        supported_ids=supported_ids,
        source_order=source_order,
    )

    # Keep only references that resolve in the already validated semantic document.
    assert identity_claim_id in claim_by_id
    assert headline_claim_id in claim_by_id

    return RecruiterDocumentModel(
        source_cv_document_version=document.document_version,
        language=document.language,
        identity_claim_id=identity_claim_id,
        headline_claim_id=headline_claim_id,
        contact_claim_ids=contact_claim_ids,
        profile_claim_ids=profile_claim_ids,
        technology_groups=technology_groups,
        selected_project_claim_ids=selected_project_claim_ids,
        project_entries=project_entries,
        experience_entries=experience_entries,
        education_claim_ids=education_claim_ids,
        language_claim_ids=language_claim_ids,
        link_claim_ids=link_claim_ids,
    )


def reduce_recruiter_document(
    document: RecruiterDocumentModel,
    policy: RecruiterPolicy,
    *,
    step: int,
) -> RecruiterDocumentModel:
    if step < 0:
        raise ValueError("reduction step must be non-negative")

    current = document.model_copy(deep=True)
    action_index = 0

    while True:
        reduced = _reduce_once(current, policy)
        if reduced.model_dump(mode="json") == current.model_dump(mode="json"):
            return current
        current = reduced
        if action_index == step:
            return current
        action_index += 1


def _supported_claim_ids(
    document: CVDocumentModel,
    selection: EvidenceSelection,
) -> set[str]:
    supported_facts: set[str] = set()
    supported_evidence: set[str] = set()

    for support in selection.requirement_support.values():
        if support.support_level == "UNKNOWN":
            continue
        supported_facts.update(support.fact_ids)
        supported_evidence.update(support.evidence_ids)

    supported_claims: set[str] = set()
    for claim_id, provenance in document.provenance_map.items():
        if set(provenance.fact_ids) & supported_facts:
            supported_claims.add(claim_id)
            continue
        if set(provenance.evidence_ids) & supported_evidence:
            supported_claims.add(claim_id)

    return supported_claims


def _first_claim_id(
    claims: list[CVClaim],
    *,
    kinds: set[str],
    supported_ids: set[str],
    source_order: dict[str, int],
    required_label: str,
) -> str:
    ordered = _ordered_claim_ids(
        claims,
        kinds=kinds,
        supported_ids=supported_ids,
        source_order=source_order,
    )
    if not ordered:
        raise ValueError(f"validated semantic document has no {required_label} claim")
    return ordered[0]


def _ordered_claim_ids(
    claims: list[CVClaim],
    *,
    kinds: set[str],
    supported_ids: set[str],
    source_order: dict[str, int],
) -> list[str]:
    matching = [claim for claim in claims if claim.kind in kinds]
    matching.sort(
        key=lambda claim: (
            0 if claim.claim_id in supported_ids else 1,
            source_order.get(claim.claim_id, 10**9),
            claim.claim_id,
        )
    )
    return [claim.claim_id for claim in matching]


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _group_skills(
    *,
    claims: list[CVClaim],
    policy: RecruiterPolicy,
    supported_ids: set[str],
    source_order: dict[str, int],
) -> list[TechnologyGroup]:
    skills = [claim for claim in claims if claim.kind == "skill"]
    skills.sort(
        key=lambda claim: (
            0 if claim.claim_id in supported_ids else 1,
            source_order.get(claim.claim_id, 10**9),
            claim.claim_id,
        )
    )

    member_to_group: dict[str, str] = {}
    policy_group_order = list(policy.skill_groups)
    for group_id, group in policy.skill_groups.items():
        if group_id == "additional":
            continue
        for member in group.members:
            member_to_group.setdefault(_normalize(member), group_id)

    grouped: OrderedDict[str, list[str]] = OrderedDict()
    for claim in skills:
        group_id = member_to_group.get(_normalize(claim.text))
        if group_id is None and "additional" in policy.skill_groups:
            group_id = "additional"
        if group_id is None:
            continue
        grouped.setdefault(group_id, []).append(claim.claim_id)

    group_rank: dict[str, tuple[int, int, int]] = {}
    claim_position = {
        claim.claim_id: index for index, claim in enumerate(skills)
    }
    for group_id, claim_ids in grouped.items():
        group_rank[group_id] = (
            0 if any(claim_id in supported_ids for claim_id in claim_ids) else 1,
            min(claim_position[claim_id] for claim_id in claim_ids),
            policy_group_order.index(group_id),
        )

    ordered_group_ids = sorted(grouped, key=lambda group_id: group_rank[group_id])
    result: list[TechnologyGroup] = []
    remaining_tokens = policy.max_skill_tokens

    for group_id in ordered_group_ids:
        if len(result) >= policy.max_skill_groups or remaining_tokens <= 0:
            break
        claim_ids = grouped[group_id][:remaining_tokens]
        if not claim_ids:
            continue
        result.append(
            TechnologyGroup(label_id=group_id, skill_claim_ids=claim_ids)
        )
        remaining_tokens -= len(claim_ids)

    return result


def _compose_project_entries(
    *,
    project_claim_ids: list[str],
    claims: list[CVClaim],
    document: CVDocumentModel,
    supported_ids: set[str],
    source_order: dict[str, int],
) -> list[RecruiterProjectEntry]:
    bullets = [
        claim
        for claim in claims
        if claim.section == "projects" and claim.kind == "bullet"
    ]
    bullets.sort(
        key=lambda claim: (
            0 if claim.claim_id in supported_ids else 1,
            source_order.get(claim.claim_id, 10**9),
            claim.claim_id,
        )
    )

    used_bullets: set[str] = set()
    result: list[RecruiterProjectEntry] = []

    for project_claim_id in project_claim_ids:
        primary_provenance = document.provenance_map.get(project_claim_id)
        primary_fact_ids = (
            set(primary_provenance.fact_ids) if primary_provenance is not None else set()
        )
        selected_bullet_ids: list[str] = []

        for bullet in bullets:
            if bullet.claim_id in used_bullets:
                continue
            bullet_provenance = document.provenance_map.get(bullet.claim_id)
            if bullet_provenance is None:
                continue
            if primary_fact_ids & set(bullet_provenance.fact_ids):
                selected_bullet_ids = [bullet.claim_id]
                used_bullets.add(bullet.claim_id)
                break

        result.append(
            RecruiterProjectEntry(
                primary_claim_id=project_claim_id,
                bullet_claim_ids=selected_bullet_ids,
            )
        )

    return result


def _compose_experience_entries(
    *,
    claims: list[CVClaim],
    document: CVDocumentModel,
    supported_ids: set[str],
    source_order: dict[str, int],
    max_entries: int,
) -> list[RecruiterExperienceEntry]:
    primary_claims = [
        claim
        for claim in claims
        if claim.section == "experience" and claim.kind != "bullet"
    ]
    primary_claims.sort(
        key=lambda claim: (
            0 if claim.claim_id in supported_ids else 1,
            source_order.get(claim.claim_id, 10**9),
            claim.claim_id,
        )
    )

    bullets = [
        claim
        for claim in claims
        if claim.section == "experience" and claim.kind == "bullet"
    ]
    bullets.sort(
        key=lambda claim: (
            0 if claim.claim_id in supported_ids else 1,
            source_order.get(claim.claim_id, 10**9),
            claim.claim_id,
        )
    )

    used_bullets: set[str] = set()
    result: list[RecruiterExperienceEntry] = []

    for primary in primary_claims[:max_entries]:
        primary_provenance = document.provenance_map.get(primary.claim_id)
        primary_fact_ids = (
            set(primary_provenance.fact_ids) if primary_provenance is not None else set()
        )
        selected_bullet_ids: list[str] = []

        for bullet in bullets:
            if bullet.claim_id in used_bullets:
                continue
            bullet_provenance = document.provenance_map.get(bullet.claim_id)
            if bullet_provenance is None:
                continue
            if primary_fact_ids & set(bullet_provenance.fact_ids):
                selected_bullet_ids = [bullet.claim_id]
                used_bullets.add(bullet.claim_id)
                break

        result.append(
            RecruiterExperienceEntry(
                primary_claim_id=primary.claim_id,
                bullet_claim_ids=selected_bullet_ids,
            )
        )

    return result


def _reduce_once(
    document: RecruiterDocumentModel,
    policy: RecruiterPolicy,
) -> RecruiterDocumentModel:
    # 1. Optional duplicate links: preserve the first canonical link.
    if len(document.link_claim_ids) > 1:
        return document.model_copy(
            update={"link_claim_ids": document.link_claim_ids[:-1]}
        )

    # 2. Lower-relevance skills: preserve one skill token as minimum
    # recruiter context, then continue to later reduction categories.
    skill_token_count = sum(
        len(group.skill_claim_ids) for group in document.technology_groups
    )
    if skill_token_count > 1:
        groups = [group.model_copy(deep=True) for group in document.technology_groups]
        last = groups[-1]
        if len(last.skill_claim_ids) > 1:
            groups[-1] = last.model_copy(
                update={"skill_claim_ids": last.skill_claim_ids[:-1]}
            )
        else:
            groups.pop()
        return document.model_copy(update={"technology_groups": groups})

    # 3. Project #4 then #3, while keeping two when at least two exist.
    if document.project_entries and len(document.project_entries) > 2:
        remaining_entries = document.project_entries[:-1]
        return document.model_copy(
            update={
                "project_entries": remaining_entries,
                "selected_project_claim_ids": [
                    entry.primary_claim_id for entry in remaining_entries
                ],
            }
        )
    if not document.project_entries and len(document.selected_project_claim_ids) > 2:
        return document.model_copy(
            update={
                "selected_project_claim_ids": document.selected_project_claim_ids[:-1]
            }
        )

    # 4. Lower-relevance optional experience entries; preserve one context row.
    if len(document.experience_entries) > 1:
        return document.model_copy(
            update={"experience_entries": document.experience_entries[:-1]}
        )

    # 5. Optional training/education entries; preserve one education row.
    if len(document.education_claim_ids) > 1:
        return document.model_copy(
            update={"education_claim_ids": document.education_claim_ids[:-1]}
        )

    return document
