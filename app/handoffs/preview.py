from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from app.contributions.models import PublicContributionEntry
from app.handoffs.models import (
    SOURCE_FRESHNESS,
    ActorNeedHypothesisCandidate,
    PublicContributionCandidate,
    ResearchOpportunityHandoff,
)


PreviewStatus = Literal["REVIEWABLE", "BLOCKED"]
Disposition = Literal[
    "RESEARCH_ACTOR",
    "IMPORT_PUBLIC_CONTRIBUTION",
    "WATCH",
    "DISCARD",
]


class OpportunityHandoffPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PreviewStatus
    handoff_id: str
    candidate_kind: Literal[
        "ACTOR_NEED_HYPOTHESIS",
        "PUBLIC_CONTRIBUTION_CANDIDATE",
    ]
    source_freshness: Literal["AS_OF_EXPORT"]
    statement: str
    research_status: str | None
    actor_refs: list[str]
    evidence_refs: list[str]
    assumptions: list[str]
    missing_context: list[str]
    allowed_dispositions: list[Disposition]
    blocked_reasons: list[str]
    contribution_entry: PublicContributionEntry | None


def _actor_preview(
    handoff: ResearchOpportunityHandoff,
    candidate: ActorNeedHypothesisCandidate,
) -> OpportunityHandoffPreview:
    if candidate.research_status in {"contradicted", "discarded"}:
        dispositions: list[Disposition] = ["WATCH", "DISCARD"]
        blocked_reasons: list[str] = ["research_status_not_researchable"]
    elif candidate.actor_refs:
        dispositions = ["RESEARCH_ACTOR", "WATCH", "DISCARD"]
        blocked_reasons = []
    else:
        dispositions = ["WATCH", "DISCARD"]
        blocked_reasons = ["actor_ref_required_for_research_actor"]

    return OpportunityHandoffPreview(
        status="REVIEWABLE",
        handoff_id=handoff.handoff_id,
        candidate_kind=candidate.kind,
        source_freshness=SOURCE_FRESHNESS,
        statement=candidate.statement,
        research_status=candidate.research_status,
        actor_refs=list(candidate.actor_refs),
        evidence_refs=list(candidate.evidence_refs),
        assumptions=list(candidate.assumptions),
        missing_context=list(candidate.missing_context),
        allowed_dispositions=dispositions,
        blocked_reasons=blocked_reasons,
        contribution_entry=None,
    )


def _public_preview_without_import_metadata(
    handoff: ResearchOpportunityHandoff,
    candidate: PublicContributionCandidate,
) -> OpportunityHandoffPreview:
    return OpportunityHandoffPreview(
        status="REVIEWABLE",
        handoff_id=handoff.handoff_id,
        candidate_kind=candidate.kind,
        source_freshness=SOURCE_FRESHNESS,
        statement=candidate.need_statement,
        research_status=None,
        actor_refs=[],
        evidence_refs=list(candidate.evidence_refs),
        assumptions=[],
        missing_context=[],
        allowed_dispositions=["WATCH", "DISCARD"],
        blocked_reasons=["local_import_metadata_required"],
        contribution_entry=None,
    )


def _blocked_public_preview(
    handoff: ResearchOpportunityHandoff,
    candidate: PublicContributionCandidate,
    reason: str,
) -> OpportunityHandoffPreview:
    return OpportunityHandoffPreview(
        status="BLOCKED",
        handoff_id=handoff.handoff_id,
        candidate_kind=candidate.kind,
        source_freshness=SOURCE_FRESHNESS,
        statement=candidate.need_statement,
        research_status=None,
        actor_refs=[],
        evidence_refs=list(candidate.evidence_refs),
        assumptions=[],
        missing_context=[],
        allowed_dispositions=["WATCH", "DISCARD"],
        blocked_reasons=[reason],
        contribution_entry=None,
    )


def preview_research_opportunity_handoff(
    handoff: ResearchOpportunityHandoff,
    *,
    contribution_entry_id: str | None = None,
    contribution_discovered_at: datetime | None = None,
) -> OpportunityHandoffPreview:
    if not isinstance(handoff, ResearchOpportunityHandoff):
        raise TypeError("handoff must be a ResearchOpportunityHandoff")

    candidate = handoff.candidate
    if isinstance(candidate, ActorNeedHypothesisCandidate):
        return _actor_preview(handoff, candidate)

    if not isinstance(candidate, PublicContributionCandidate):
        raise TypeError("unsupported handoff candidate")

    if contribution_entry_id is None and contribution_discovered_at is None:
        return _public_preview_without_import_metadata(handoff, candidate)

    if contribution_entry_id is None or contribution_discovered_at is None:
        return _blocked_public_preview(
            handoff,
            candidate,
            "local_import_metadata_incomplete",
        )

    try:
        entry = PublicContributionEntry.model_validate(
            {
                "entry_id": contribution_entry_id,
                "repository_full_name": candidate.repository_full_name,
                "repository_url": candidate.repository_url,
                "account_id": None,
                "origin": candidate.origin,
                "need_basis": candidate.need_basis,
                "need_statement": candidate.need_statement,
                "evidence_refs": list(candidate.evidence_refs),
                "task_ref": candidate.task_ref,
                "bounded_task": candidate.bounded_task,
                "task_claim_state": candidate.task_claim_state,
                "expected_effort": candidate.expected_effort,
                "risk_level": candidate.risk_level,
                "discovered_at": contribution_discovered_at,
            }
        )
    except ValidationError:
        return _blocked_public_preview(
            handoff,
            candidate,
            "contribution_entry_domain_validation_failed",
        )

    return OpportunityHandoffPreview(
        status="REVIEWABLE",
        handoff_id=handoff.handoff_id,
        candidate_kind=candidate.kind,
        source_freshness=SOURCE_FRESHNESS,
        statement=candidate.need_statement,
        research_status=None,
        actor_refs=[],
        evidence_refs=list(candidate.evidence_refs),
        assumptions=[],
        missing_context=[],
        allowed_dispositions=["IMPORT_PUBLIC_CONTRIBUTION", "WATCH", "DISCARD"],
        blocked_reasons=[],
        contribution_entry=entry,
    )
