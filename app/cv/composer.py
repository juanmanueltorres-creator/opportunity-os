from __future__ import annotations

from app.cv.models import (
    ClaimProvenance,
    CVClaim,
    CVDocumentModel,
    CVEntry,
    CVPolicy,
    EvidenceCatalogSnapshot,
    EvidenceSelection,
    MasterFact,
    MasterFactsSnapshot,
)

COMPOSER_VERSION = "composer-v1"
CV_DOCUMENT_VERSION = "cvdoc-v1"

_DIRECT_FACT_MAPPING: dict[str, tuple[str, str]] = {
    "identity": ("headline", "identity"),
    "contact": ("headline", "contact"),
    "location": ("headline", "location"),
    "role": ("headline", "headline"),
    "summary_claim": ("summary", "summary"),
    "skill": ("skills", "skill"),
    "employment": ("experience", "organization"),
    "project": ("projects", "project"),
    "education": ("education", "education"),
    "language": ("languages", "language"),
    "link": ("links", "link"),
}
_SECTION_FALLBACK_ORDER = [
    "headline",
    "summary",
    "skills",
    "experience",
    "projects",
    "education",
    "languages",
    "links",
]


def compose_cv(
    *,
    selection: EvidenceSelection,
    master_facts: MasterFactsSnapshot,
    evidence_catalog: EvidenceCatalogSnapshot,
    policy: CVPolicy,
    language: str | None = None,
) -> CVDocumentModel:
    output_language = language or policy.language
    selected_fact_ids = set(selection.selected_fact_ids)
    selected_evidence_ids = set(selection.selected_evidence_ids)
    fact_by_id = {fact.id: fact for fact in master_facts.facts}
    module_by_id = {module.id: module for module in evidence_catalog.modules}

    claims_by_section: dict[str, list[CVClaim]] = {}
    provenance_map: dict[str, ClaimProvenance] = {}

    for fact_id in sorted(selected_fact_ids):
        fact = fact_by_id.get(fact_id)
        if fact is None or not fact.verified:
            continue
        if selection.application_track_id not in fact.track_ids:
            continue
        mapping = _DIRECT_FACT_MAPPING.get(fact.kind)
        if mapping is None:
            continue
        section, kind = mapping
        claim_id = f"fact:{fact.id}"
        claim = CVClaim(
            claim_id=claim_id,
            section=section,
            kind=kind,
            text=_fact_display_text(fact, output_language),
        )
        claims_by_section.setdefault(section, []).append(claim)
        provenance_map[claim_id] = ClaimProvenance(
            fact_ids=[fact.id],
            evidence_ids=_selected_modules_referencing_fact(
                fact.id,
                selected_evidence_ids=selected_evidence_ids,
                module_by_id=module_by_id,
            ),
        )

    for module_id in sorted(selected_evidence_ids):
        module = module_by_id.get(module_id)
        if module is None or not module.verified:
            continue
        if selection.application_track_id not in module.track_ids:
            continue

        for approved in module.claims:
            if not approved.fact_ids:
                continue
            supporting_facts = [fact_by_id.get(fact_id) for fact_id in approved.fact_ids]
            if any(fact is None or not fact.verified for fact in supporting_facts):
                continue
            if any(
                selection.application_track_id not in fact.track_ids
                for fact in supporting_facts
                if fact is not None
            ):
                continue
            if any(fact_id not in selected_fact_ids for fact_id in approved.fact_ids):
                continue

            text = _approved_text(approved.text_by_language, output_language)
            if text is None:
                continue
            claim_id = f"approved:{approved.id}"
            if claim_id in provenance_map:
                continue
            claim = CVClaim(
                claim_id=claim_id,
                section=approved.section,
                kind=approved.kind,
                text=text,
            )
            claims_by_section.setdefault(approved.section, []).append(claim)
            provenance_map[claim_id] = ClaimProvenance(
                fact_ids=list(approved.fact_ids),
                evidence_ids=[module.id],
                approved_claim_id=approved.id,
            )

    ordered_sections = _ordered_sections(policy, set(claims_by_section))
    entries: list[CVEntry] = []
    ordered_claims: list[CVClaim] = []
    for section in ordered_sections:
        section_claims = claims_by_section.get(section, [])
        if not section_claims:
            continue
        ordered_claims.extend(section_claims)
        entries.append(
            CVEntry(
                entry_id=f"section:{section}",
                section=section,
                claim_ids=[claim.claim_id for claim in section_claims],
            )
        )

    return CVDocumentModel(
        document_version=CV_DOCUMENT_VERSION,
        language=output_language,
        claims=ordered_claims,
        entries=entries,
        provenance_map={
            claim.claim_id: provenance_map[claim.claim_id]
            for claim in ordered_claims
        },
    )


def _fact_display_text(fact: MasterFact, language: str) -> str:
    return fact.display_values.get(language, fact.value)


def _approved_text(text_by_language: dict[str, str], language: str) -> str | None:
    requested = text_by_language.get(language)
    if requested:
        return requested
    canonical_english = text_by_language.get("en")
    if canonical_english:
        return canonical_english
    if not text_by_language:
        return None
    first_language = sorted(text_by_language)[0]
    return text_by_language[first_language]


def _selected_modules_referencing_fact(
    fact_id: str,
    *,
    selected_evidence_ids: set[str],
    module_by_id: dict,
) -> list[str]:
    supporting: list[str] = []
    for module_id in sorted(selected_evidence_ids):
        module = module_by_id.get(module_id)
        if module is None:
            continue
        referenced = set(module.fact_ids)
        for approved in module.claims:
            referenced.update(approved.fact_ids)
        if fact_id in referenced:
            supporting.append(module_id)
    return supporting


def _ordered_sections(policy: CVPolicy, available: set[str]) -> list[str]:
    ordered: list[str] = []
    if "headline" in available:
        ordered.append("headline")
    for section in policy.section_order:
        if section in available and section not in ordered:
            ordered.append(section)
    for section in _SECTION_FALLBACK_ORDER:
        if section in available and section not in ordered:
            ordered.append(section)
    for section in sorted(available):
        if section not in ordered:
            ordered.append(section)
    return ordered
