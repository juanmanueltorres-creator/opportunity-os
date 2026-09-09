from __future__ import annotations

import re

from app.cv.models import (
    CVClaim,
    CVDocumentModel,
    EvidenceSelection,
    ValidationResult,
)
from app.cv.strategy.models import (
    STRATEGY_VERSION,
    CoreMessage,
    CVStrategy,
    StrategyTrackConfig,
)
from app.cv.strategy.policy import NarrativePolicy
from app.cv.strategy.scoring import rank_supported_requirements
from app.radar.models import RadarAssessment


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _message_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _normalize(value)).strip("-")
    return f"requirement:{slug or 'supported'}"


def _resolve_positioning_claim(
    document: CVDocumentModel,
    validation: ValidationResult,
    track_config: StrategyTrackConfig | None,
) -> CVClaim:
    validated_ids = set(validation.validated_claim_ids)
    headlines = sorted(
        (
            claim
            for claim in document.claims
            if claim.claim_id in validated_ids
            and claim.section == "headline"
            and claim.kind == "headline"
        ),
        key=lambda claim: claim.claim_id,
    )
    if track_config is not None and track_config.positioning_claim_id is not None:
        for claim in headlines:
            if claim.claim_id == track_config.positioning_claim_id:
                return claim
        raise ValueError("strategy_positioning_claim_invalid")
    if not headlines:
        raise ValueError("strategy_positioning_unavailable")
    return headlines[0]


def _evidence_for_fact_ids(
    document: CVDocumentModel,
    validated_claim_ids: set[str],
    fact_ids: list[str],
) -> list[str]:
    target = set(fact_ids)
    evidence: set[str] = set()
    for claim_id, provenance in document.provenance_map.items():
        if claim_id not in validated_claim_ids:
            continue
        if target & set(provenance.fact_ids):
            evidence.update(provenance.evidence_ids)
    return sorted(evidence)


def _preferred_section_order(
    document: CVDocumentModel,
    policy: NarrativePolicy,
    track_config: StrategyTrackConfig | None,
) -> list[str]:
    base = (
        track_config.preferred_section_order
        if track_config is not None and track_config.preferred_section_order
        else policy.default_section_order
    )
    ordered = list(base)
    for entry in document.entries:
        if entry.section == "headline" or entry.section in ordered:
            continue
        ordered.append(entry.section)
    return ordered


def build_cv_strategy(
    *,
    assessment: RadarAssessment,
    selection: EvidenceSelection,
    document: CVDocumentModel,
    validation: ValidationResult,
    policy: NarrativePolicy,
    track_config: StrategyTrackConfig | None = None,
) -> CVStrategy:
    if not validation.valid:
        raise ValueError("strategy_requires_valid_semantic_document")
    if track_config is not None and track_config.id != selection.application_track_id:
        raise ValueError("strategy_track_config_mismatch")

    validated_claim_ids = set(validation.validated_claim_ids)
    positioning_claim = _resolve_positioning_claim(
        document,
        validation,
        track_config,
    )
    positioning_provenance = document.provenance_map[positioning_claim.claim_id]
    ranked = rank_supported_requirements(
        requirements=assessment.enrichment.requirements,
        selection=selection,
        policy=policy,
        priority_requirements=(
            track_config.priority_requirements if track_config is not None else []
        ),
    )

    core_messages = [
        CoreMessage(
            id="positioning",
            message=positioning_claim.text,
            fact_ids=sorted(positioning_provenance.fact_ids),
            evidence_ids=sorted(positioning_provenance.evidence_ids),
            importance=policy.positioning_message_importance,
            reason="Primary validated evidence-backed positioning claim",
        )
    ]
    for candidate in ranked:
        if len(core_messages) >= policy.max_core_messages:
            break
        core_messages.append(
            CoreMessage(
                id=_message_id(candidate.requirement.value),
                message=candidate.requirement.value,
                fact_ids=sorted(candidate.support.fact_ids),
                evidence_ids=sorted(
                    set(candidate.support.evidence_ids)
                    | set(
                        _evidence_for_fact_ids(
                            document,
                            validated_claim_ids,
                            candidate.support.fact_ids,
                        )
                    )
                ),
                importance=candidate.score,
                reason=candidate.support.explanation,
            )
        )

    unsupported = {_normalize(value) for value in selection.unsupported_requirements}
    must_show = set(positioning_provenance.fact_ids)
    supporting: set[str] = set()
    for requirement in assessment.enrichment.requirements:
        if _normalize(requirement.value) in unsupported:
            continue
        support = selection.requirement_support.get(requirement.value)
        if support is None or support.support_level == "UNKNOWN" or not support.fact_ids:
            continue
        if requirement.importance == "mandatory":
            must_show.update(support.fact_ids)
        else:
            supporting.update(support.fact_ids)

    supporting.difference_update(must_show)
    optional = set(selection.selected_fact_ids) - must_show - supporting

    target_role = (
        assessment.enrichment.normalized_title.value
        if assessment.enrichment.normalized_title is not None
        else assessment.opportunity.title
    )
    company = assessment.opportunity.company

    return CVStrategy(
        strategy_version=STRATEGY_VERSION,
        application_track_id=selection.application_track_id,
        target_role=target_role,
        target_company=company,
        positioning=positioning_claim.text,
        recruiter_question=(
            f"Can this candidate credibly perform {target_role} at {company} "
            "using verified evidence?"
        ),
        core_messages=core_messages,
        must_show_fact_ids=sorted(must_show),
        supporting_fact_ids=sorted(supporting),
        optional_fact_ids=sorted(optional),
        explicit_gaps=sorted(
            selection.unsupported_requirements,
            key=_normalize,
        ),
        preferred_section_order=_preferred_section_order(
            document,
            policy,
            track_config,
        ),
        preferred_layout_profile_id=(
            track_config.preferred_layout_profile_id
            if track_config is not None
            else None
        ),
    )
