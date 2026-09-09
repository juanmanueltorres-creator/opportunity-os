from __future__ import annotations

from dataclasses import dataclass

from app.cv.models import (
    CVClaim,
    CVDocumentModel,
    ClaimProvenance,
    EvidenceSelection,
    ValidationResult,
)
from app.cv.strategy.models import CVStrategy


@dataclass(frozen=True)
class NarrativeClaimRank:
    claim_id: str
    bucket_rank: int
    core_message_hits: int
    requirement_supported: bool
    source_order: int

    @property
    def sort_key(self) -> tuple[int, int, int, int, str]:
        return (
            self.bucket_rank,
            -self.core_message_hits,
            0 if self.requirement_supported else 1,
            self.source_order,
            self.claim_id,
        )


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

    result: set[str] = set()
    for claim_id, provenance in document.provenance_map.items():
        if set(provenance.fact_ids) & supported_facts:
            result.add(claim_id)
            continue
        if set(provenance.evidence_ids) & supported_evidence:
            result.add(claim_id)
    return result


def _bucket_rank(
    provenance: ClaimProvenance | None,
    strategy: CVStrategy,
) -> int:
    if provenance is None:
        return 3

    fact_ids = set(provenance.fact_ids)
    if fact_ids & set(strategy.must_show_fact_ids):
        return 0
    if fact_ids & set(strategy.supporting_fact_ids):
        return 1
    if fact_ids & set(strategy.optional_fact_ids):
        return 2
    return 3


def _core_message_hits(
    provenance: ClaimProvenance | None,
    strategy: CVStrategy,
) -> int:
    if provenance is None:
        return 0

    fact_ids = set(provenance.fact_ids)
    evidence_ids = set(provenance.evidence_ids)
    return sum(
        1
        for message in strategy.core_messages
        if fact_ids & set(message.fact_ids)
        or evidence_ids & set(message.evidence_ids)
    )


def rank_validated_claims(
    *,
    claims: list[CVClaim],
    document: CVDocumentModel,
    validation: ValidationResult,
    selection: EvidenceSelection,
    strategy: CVStrategy,
) -> list[CVClaim]:
    validated_ids = set(validation.validated_claim_ids)
    source_order = {
        claim.claim_id: index for index, claim in enumerate(document.claims)
    }
    supported_ids = _supported_claim_ids(document, selection)

    ranked: list[tuple[NarrativeClaimRank, CVClaim]] = []
    for claim in claims:
        if claim.claim_id not in validated_ids:
            continue
        provenance = document.provenance_map.get(claim.claim_id)
        rank = NarrativeClaimRank(
            claim_id=claim.claim_id,
            bucket_rank=_bucket_rank(provenance, strategy),
            core_message_hits=_core_message_hits(provenance, strategy),
            requirement_supported=claim.claim_id in supported_ids,
            source_order=source_order.get(claim.claim_id, 10**9),
        )
        ranked.append((rank, claim))

    ranked.sort(key=lambda item: item[0].sort_key)
    return [claim for _, claim in ranked]
