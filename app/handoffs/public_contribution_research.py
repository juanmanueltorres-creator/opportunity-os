from __future__ import annotations

from datetime import datetime
import json

from app.contributions.observations import ContributionPreview
from app.handoffs.models import (
    QuestionResearchHandoff,
    ResearchOpportunityHandoff,
)


def _require_aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


def build_public_contribution_candidate_handoff(
    question_handoff: QuestionResearchHandoff,
    contribution_preview: ContributionPreview,
    *,
    handoff_id: str,
    created_at: datetime,
) -> ResearchOpportunityHandoff:
    if not isinstance(question_handoff, QuestionResearchHandoff):
        raise TypeError("question_handoff must be a QuestionResearchHandoff")
    if not isinstance(contribution_preview, ContributionPreview):
        raise TypeError("contribution_preview must be a ContributionPreview")
    if contribution_preview.status != "IMPORTABLE":
        raise ValueError("contribution_preview must be IMPORTABLE")
    if contribution_preview.proposed_entry is None:
        raise ValueError("contribution_preview must contain proposed_entry")
    if contribution_preview.candidate_event is not None:
        raise ValueError("contribution_preview candidate_event must be null")

    _require_aware(created_at, "created_at")
    entry = contribution_preview.proposed_entry

    return ResearchOpportunityHandoff.model_validate(
        {
            "contract": "research-opportunity-handoff/v0.1",
            "handoff_id": handoff_id,
            "created_at": created_at,
            "source": {
                "system": "question-radar",
                "source_question_ref": question_handoff.source.question_id,
                "research_intent_ref": None,
                "hypothesis_ref": None,
            },
            "candidate": {
                "kind": "PUBLIC_CONTRIBUTION_CANDIDATE",
                "repository_full_name": entry.repository_full_name,
                "repository_url": entry.repository_url,
                "origin": entry.origin,
                "need_basis": entry.need_basis,
                "need_statement": entry.need_statement,
                "evidence_refs": list(entry.evidence_refs),
                "task_ref": entry.task_ref,
                "bounded_task": entry.bounded_task,
                "task_claim_state": entry.task_claim_state,
                "expected_effort": entry.expected_effort,
                "risk_level": entry.risk_level,
            },
        }
    )


def render_research_opportunity_handoff_json(
    handoff: ResearchOpportunityHandoff,
) -> str:
    if not isinstance(handoff, ResearchOpportunityHandoff):
        raise TypeError("handoff must be a ResearchOpportunityHandoff")
    return (
        json.dumps(
            handoff.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
