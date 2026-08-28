from __future__ import annotations

from app.cv.models import (
    CVPolicy,
    EvidenceCatalogSnapshot,
    EvidenceSelection,
    MasterFact,
    MasterFactsSnapshot,
    RequirementSupport,
)
from app.radar.models import OpportunityEnrichment, Requirement
from app.radar.taxonomy import SkillMatchLevel, TaxonomyResolver


_STRUCTURAL_FACT_KINDS = {
    "identity",
    "contact",
    "location",
    "link",
    "summary_claim",
    "role",
    "education",
    "language",
}


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def select_evidence(
    *,
    enrichment: OpportunityEnrichment,
    application_track_id: str,
    master_facts: MasterFactsSnapshot,
    evidence_catalog: EvidenceCatalogSnapshot,
    policy: CVPolicy,
    resolver: TaxonomyResolver | None = None,
) -> EvidenceSelection:
    eligible_facts = sorted(
        (
            fact
            for fact in master_facts.facts
            if fact.verified and application_track_id in fact.track_ids
        ),
        key=lambda fact: fact.id,
    )
    eligible_modules = sorted(
        (
            module
            for module in evidence_catalog.modules
            if module.verified and application_track_id in module.track_ids
        ),
        key=lambda module: module.id,
    )
    fact_by_id = {fact.id: fact for fact in eligible_facts}
    skill_facts = [fact for fact in eligible_facts if fact.kind == "skill"]

    selected_fact_ids = {
        fact.id for fact in eligible_facts if fact.kind in _STRUCTURAL_FACT_KINDS
    }
    supported_fact_ids: set[str] = set()
    requirement_support: dict[str, RequirementSupport] = {}
    unsupported_requirements: list[str] = []
    explanations: list[str] = []

    for requirement in enrichment.requirements:
        support = _support_requirement(
            requirement,
            eligible_facts=eligible_facts,
            skill_facts=skill_facts,
            resolver=resolver,
        )
        requirement_support[requirement.value] = support
        supported_fact_ids.update(support.fact_ids)
        selected_fact_ids.update(support.fact_ids)
        explanations.append(support.explanation)

        cannot_claim_exact_product = (
            requirement.exactness == "exact_product"
            and support.support_level == "TAXONOMY_RELATED"
        )
        if requirement.importance == "mandatory" and (
            support.support_level == "UNKNOWN" or cannot_claim_exact_product
        ):
            if requirement.value not in unsupported_requirements:
                unsupported_requirements.append(requirement.value)

    selected_module_ids: list[str] = []
    requirement_terms = {_normalize(req.value) for req in enrichment.requirements}
    title_text = (
        _normalize(enrichment.normalized_title.value)
        if enrichment.normalized_title is not None
        else ""
    )

    for module in eligible_modules:
        if _module_is_relevant(
            module=module,
            supported_fact_ids=supported_fact_ids,
            requirement_terms=requirement_terms,
            title_text=title_text,
            required_sections=set(policy.required_sections),
        ):
            selected_module_ids.append(module.id)
            for fact_id in module.fact_ids:
                if fact_id in fact_by_id:
                    selected_fact_ids.add(fact_id)
            for claim in module.claims:
                for fact_id in claim.fact_ids:
                    if fact_id in fact_by_id:
                        selected_fact_ids.add(fact_id)
            explanations.append(f"Selected evidence module {module.id}")

    return EvidenceSelection(
        application_track_id=application_track_id,
        selected_fact_ids=sorted(selected_fact_ids),
        selected_evidence_ids=selected_module_ids,
        requirement_support=requirement_support,
        unsupported_requirements=unsupported_requirements,
        selection_explanations=explanations,
    )


def _support_requirement(
    requirement: Requirement,
    *,
    eligible_facts: list[MasterFact],
    skill_facts: list[MasterFact],
    resolver: TaxonomyResolver | None,
) -> RequirementSupport:
    if requirement.kind == "skill":
        if resolver is not None:
            resolved = resolver.resolve_skill(
                requirement.value,
                [fact.value for fact in skill_facts],
            )
            if resolved.level != SkillMatchLevel.UNKNOWN and resolved.matched_skill:
                matched = _find_fact_by_value(skill_facts, resolved.matched_skill)
                if matched is not None:
                    return RequirementSupport(
                        requirement=requirement.value,
                        support_level=resolved.level.value,
                        fact_ids=[matched.id],
                        evidence_ids=[],
                        explanation=(
                            f"{requirement.value} supported by {matched.id} via "
                            f"{resolved.level.value}"
                        ),
                    )
        else:
            matched = _find_fact_by_value(skill_facts, requirement.value)
            if matched is not None:
                return RequirementSupport(
                    requirement=requirement.value,
                    support_level="EXACT_VERIFIED",
                    fact_ids=[matched.id],
                    evidence_ids=[],
                    explanation=f"{requirement.value} exactly supported by {matched.id}",
                )
    else:
        matched = _find_fact_by_value(eligible_facts, requirement.value)
        if matched is not None:
            return RequirementSupport(
                requirement=requirement.value,
                support_level="EXACT_VERIFIED",
                fact_ids=[matched.id],
                evidence_ids=[],
                explanation=f"{requirement.value} exactly supported by {matched.id}",
            )

    return RequirementSupport(
        requirement=requirement.value,
        support_level="UNKNOWN",
        fact_ids=[],
        evidence_ids=[],
        explanation=f"No verified support for {requirement.value}",
    )


def _find_fact_by_value(
    facts: list[MasterFact],
    value: str,
) -> MasterFact | None:
    target = _normalize(value)
    for fact in facts:
        if _normalize(fact.value) == target:
            return fact
    return None


def _module_is_relevant(
    *,
    module,
    supported_fact_ids: set[str],
    requirement_terms: set[str],
    title_text: str,
    required_sections: set[str],
) -> bool:
    referenced_ids = set(module.fact_ids)
    for claim in module.claims:
        referenced_ids.update(claim.fact_ids)

    if referenced_ids & supported_fact_ids:
        return True

    normalized_keywords = {_normalize(keyword) for keyword in module.keywords}
    if normalized_keywords & requirement_terms:
        return True
    if title_text and any(keyword in title_text for keyword in normalized_keywords):
        return True
    if any(claim.section in required_sections for claim in module.claims):
        return True
    return False
