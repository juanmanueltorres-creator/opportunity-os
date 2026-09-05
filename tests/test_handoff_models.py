from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.handoffs.models import (
    PUBLIC_CONTRIBUTION_ROUTE,
    QUESTION_RESEARCH_CONTRACT,
    RESEARCH_OPPORTUNITY_CONTRACT,
    SOURCE_FRESHNESS,
    ActorNeedHypothesisCandidate,
    PublicContributionCandidate,
    QuestionResearchHandoff,
    ResearchOpportunityHandoff,
)


DIRECT_QUESTION_HANDOFF = {
    "contract": "question-research-handoff/v0.1",
    "handoff_id": "qrh:fixture:github:001",
    "created_at": "2026-09-04T22:00:00-03:00",
    "source": {
        "system": "question-radar",
        "question_id": "question:fixture:github:001",
        "question_profile_ref": None,
        "decision_id": "decision:fixture:github:001",
        "decision_fingerprint": "sha256:" + "2" * 64,
    },
    "question": {
        "raw": "¿Qué problema público de software geoespacial puedo resolver donde exista una tarea explícita y disponible?",
        "canonical": "¿Qué problema público de software geoespacial puedo resolver donde exista una tarea explícita y disponible?",
    },
    "investigation": {
        "decision": "RESEARCH",
        "rationale": "Investigar una tarea pública explícita sin asumir disponibilidad ni interés laboral.",
        "next_test": "Seleccionar un issue público explícito y observar su estado mediante el contribution preview existente.",
    },
    "routing": {
        "kind": "PUBLIC_CONTRIBUTION_RESEARCH",
        "destination": "opportunity-os",
    },
    "constraints": [
        "PUBLIC_CONTRIBUTION_ENTRY != JOB_OPENING",
        "GOOD_PROBLEM != AVAILABLE_PROBLEM",
    ],
}

ACTOR_NEED_HANDOFF = {
    "contract": "research-opportunity-handoff/v0.1",
    "handoff_id": "roh:fixture:water:001",
    "created_at": "2026-09-05T01:15:00-03:00",
    "source": {
        "system": "andes-context-os",
        "source_question_ref": "question:fixture:water-san-juan:001",
        "research_intent_ref": "intent:water-san-juan:001",
        "hypothesis_ref": "hypothesis:water-san-juan:001",
    },
    "candidate": {
        "kind": "ACTOR_NEED_HYPOTHESIS",
        "need_category": "water_decision_support",
        "statement": "A recurring water-management decision may benefit from consolidated territorial evidence.",
        "actor_refs": [],
        "evidence_refs": [],
        "assumptions": ["A recurring decision exists."],
        "missing_context": ["Decision owner"],
        "research_status": "researching",
    },
}

PUBLIC_CANDIDATE_HANDOFF = {
    "contract": "research-opportunity-handoff/v0.1",
    "handoff_id": "roh:fixture:github:001",
    "created_at": "2026-09-05T01:20:00-03:00",
    "source": {
        "system": "question-radar",
        "source_question_ref": "question:fixture:github:001",
        "research_intent_ref": None,
        "hypothesis_ref": None,
    },
    "candidate": {
        "kind": "PUBLIC_CONTRIBUTION_CANDIDATE",
        "repository_full_name": "example/project",
        "repository_url": "https://github.com/example/project",
        "origin": "PUBLIC_ISSUE",
        "need_basis": "MAINTAINER_STATED",
        "need_statement": "Add support for the documented geospatial format.",
        "evidence_refs": ["github:example/project/issues/42"],
        "task_ref": "github:example/project/issues/42",
        "bounded_task": "Implement the explicitly requested format support.",
        "task_claim_state": "AVAILABLE",
        "expected_effort": "S",
        "risk_level": "LOW",
    },
}


def test_parses_direct_public_contribution_question_handoff():
    handoff = QuestionResearchHandoff.model_validate(deepcopy(DIRECT_QUESTION_HANDOFF))
    assert handoff.contract == QUESTION_RESEARCH_CONTRACT
    assert handoff.routing.kind == PUBLIC_CONTRIBUTION_ROUTE
    assert handoff.routing.destination == "opportunity-os"
    assert handoff.source_freshness == SOURCE_FRESHNESS
    assert handoff.model_dump(mode="json") == DIRECT_QUESTION_HANDOFF


def test_direct_question_handoff_rejects_territorial_route():
    payload = deepcopy(DIRECT_QUESTION_HANDOFF)
    payload["routing"] = {
        "kind": "TERRITORIAL_RESEARCH",
        "destination": "andes-context-os",
    }
    with pytest.raises(ValidationError, match="PUBLIC_CONTRIBUTION_RESEARCH"):
        QuestionResearchHandoff.model_validate(payload)


def test_parses_actor_need_candidate():
    handoff = ResearchOpportunityHandoff.model_validate(deepcopy(ACTOR_NEED_HANDOFF))
    assert handoff.contract == RESEARCH_OPPORTUNITY_CONTRACT
    assert isinstance(handoff.candidate, ActorNeedHypothesisCandidate)
    assert handoff.candidate.actor_refs == []
    assert handoff.candidate.research_status == "researching"
    assert handoff.source_freshness == SOURCE_FRESHNESS


def test_parses_public_contribution_candidate():
    handoff = ResearchOpportunityHandoff.model_validate(deepcopy(PUBLIC_CANDIDATE_HANDOFF))
    assert isinstance(handoff.candidate, PublicContributionCandidate)
    assert handoff.candidate.repository_full_name == "example/project"
    assert handoff.candidate.task_claim_state == "AVAILABLE"


def test_rejects_unknown_contract_version():
    payload = {**PUBLIC_CANDIDATE_HANDOFF, "contract": "research-opportunity-handoff/v0.2"}
    with pytest.raises(ValidationError, match="research-opportunity-handoff/v0.1"):
        ResearchOpportunityHandoff.model_validate(payload)


def test_rejects_unknown_candidate_kind():
    payload = deepcopy(PUBLIC_CANDIDATE_HANDOFF)
    payload["candidate"]["kind"] = "JOB_OPENING"
    with pytest.raises(ValidationError):
        ResearchOpportunityHandoff.model_validate(payload)


def test_rejects_unknown_fields():
    payload = deepcopy(ACTOR_NEED_HANDOFF)
    payload["candidate"]["buyer"] = "someone"
    with pytest.raises(ValidationError, match="buyer"):
        ResearchOpportunityHandoff.model_validate(payload)


def test_actor_need_requires_assumptions_and_missing_context_fields():
    payload = deepcopy(ACTOR_NEED_HANDOFF)
    del payload["candidate"]["assumptions"]
    del payload["candidate"]["missing_context"]
    with pytest.raises(ValidationError):
        ResearchOpportunityHandoff.model_validate(payload)


def test_public_candidate_preserves_existing_contribution_vocabularies():
    handoff = ResearchOpportunityHandoff.model_validate(deepcopy(PUBLIC_CANDIDATE_HANDOFF))
    candidate = handoff.candidate
    assert isinstance(candidate, PublicContributionCandidate)
    assert candidate.origin == "PUBLIC_ISSUE"
    assert candidate.need_basis == "MAINTAINER_STATED"
    assert candidate.task_claim_state == "AVAILABLE"
    assert candidate.expected_effort == "S"
    assert candidate.risk_level == "LOW"


def test_contract2_source_semantics_follow_candidate_kind():
    actor_payload = deepcopy(ACTOR_NEED_HANDOFF)
    actor_payload["source"]["system"] = "question-radar"
    with pytest.raises(ValidationError, match="andes-context-os"):
        ResearchOpportunityHandoff.model_validate(actor_payload)

    public_payload = deepcopy(PUBLIC_CANDIDATE_HANDOFF)
    public_payload["source"]["research_intent_ref"] = "intent:not-allowed"
    with pytest.raises(ValidationError, match="research_intent_ref"):
        ResearchOpportunityHandoff.model_validate(public_payload)


def test_contract_timestamps_must_be_timezone_aware():
    direct = {**DIRECT_QUESTION_HANDOFF, "created_at": "2026-09-04T22:00:00"}
    with pytest.raises(ValidationError, match="timezone-aware"):
        QuestionResearchHandoff.model_validate(direct)

    opportunity = {**PUBLIC_CANDIDATE_HANDOFF, "created_at": "2026-09-05T01:20:00"}
    with pytest.raises(ValidationError, match="timezone-aware"):
        ResearchOpportunityHandoff.model_validate(opportunity)
