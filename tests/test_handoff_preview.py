from copy import deepcopy
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.handoffs.models import ResearchOpportunityHandoff
from app.handoffs.preview import preview_research_opportunity_handoff


ACTOR_WITH_REFS = {
    "contract": "research-opportunity-handoff/v0.1",
    "handoff_id": "roh:actor:001",
    "created_at": "2026-09-05T01:15:00-03:00",
    "source": {
        "system": "andes-context-os",
        "source_question_ref": "question:water:001",
        "research_intent_ref": "intent:water:001",
        "hypothesis_ref": "hypothesis:water:001",
    },
    "candidate": {
        "kind": "ACTOR_NEED_HYPOTHESIS",
        "need_category": "water_decision_support",
        "statement": "A recurring water decision may benefit from consolidated territorial evidence.",
        "actor_refs": ["actor:public:001"],
        "evidence_refs": ["evidence:public:001"],
        "assumptions": ["The referenced actor materially participates in the decision."],
        "missing_context": ["Procurement or collaboration path"],
        "research_status": "researching",
    },
}

PUBLIC_CANDIDATE = {
    "contract": "research-opportunity-handoff/v0.1",
    "handoff_id": "roh:github:001",
    "created_at": "2026-09-05T01:20:00-03:00",
    "source": {
        "system": "question-radar",
        "source_question_ref": "question:github:001",
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


def handoff(payload: dict) -> ResearchOpportunityHandoff:
    return ResearchOpportunityHandoff.model_validate(deepcopy(payload))


@pytest.mark.parametrize("research_status", ["proposed", "researching", "supported"])
def test_active_actor_statuses_offer_research_watch_discard(research_status: str):
    payload = deepcopy(ACTOR_WITH_REFS)
    payload["candidate"]["research_status"] = research_status
    preview = preview_research_opportunity_handoff(handoff(payload))
    assert preview.status == "REVIEWABLE"
    assert preview.candidate_kind == "ACTOR_NEED_HYPOTHESIS"
    assert preview.source_freshness == "AS_OF_EXPORT"
    assert preview.allowed_dispositions == ["RESEARCH_ACTOR", "WATCH", "DISCARD"]
    assert preview.contribution_entry is None


@pytest.mark.parametrize("research_status", ["contradicted", "discarded"])
def test_terminal_actor_statuses_do_not_offer_research_actor(research_status: str):
    payload = deepcopy(ACTOR_WITH_REFS)
    payload["candidate"]["research_status"] = research_status
    preview = preview_research_opportunity_handoff(handoff(payload))
    assert preview.allowed_dispositions == ["WATCH", "DISCARD"]
    assert preview.blocked_reasons == ["research_status_not_researchable"]


@pytest.mark.parametrize("research_status", ["supported", "contradicted"])
def test_evidence_backed_statuses_reject_empty_evidence_refs(research_status: str):
    payload = deepcopy(ACTOR_WITH_REFS)
    payload["candidate"]["research_status"] = research_status
    payload["candidate"]["evidence_refs"] = []

    with pytest.raises(ValidationError, match="evidence_refs"):
        handoff(payload)


def test_actor_refs_empty_offer_watch_discard_only():
    payload = deepcopy(ACTOR_WITH_REFS)
    payload["candidate"]["actor_refs"] = []
    preview = preview_research_opportunity_handoff(handoff(payload))
    assert preview.allowed_dispositions == ["WATCH", "DISCARD"]
    assert preview.blocked_reasons == ["actor_ref_required_for_research_actor"]


def test_actor_preview_preserves_evidence_assumptions_missing_context_and_status():
    preview = preview_research_opportunity_handoff(handoff(ACTOR_WITH_REFS))
    assert preview.statement == ACTOR_WITH_REFS["candidate"]["statement"]
    assert preview.research_status == "researching"
    assert preview.actor_refs == ["actor:public:001"]
    assert preview.evidence_refs == ["evidence:public:001"]
    assert preview.assumptions == ["The referenced actor materially participates in the decision."]
    assert preview.missing_context == ["Procurement or collaboration path"]


def test_actor_preview_has_no_target_or_action_object():
    preview = preview_research_opportunity_handoff(handoff(ACTOR_WITH_REFS))
    assert not hasattr(preview, "target_account")
    assert not hasattr(preview, "relationship")
    assert not hasattr(preview, "outreach")
    assert not hasattr(preview, "draft")


def test_public_candidate_without_local_identity_is_reviewable_but_not_import_eligible():
    preview = preview_research_opportunity_handoff(handoff(PUBLIC_CANDIDATE))
    assert preview.status == "REVIEWABLE"
    assert preview.statement == PUBLIC_CANDIDATE["candidate"]["need_statement"]
    assert preview.research_status is None
    assert preview.actor_refs == []
    assert preview.assumptions == []
    assert preview.missing_context == []
    assert preview.allowed_dispositions == ["WATCH", "DISCARD"]
    assert preview.blocked_reasons == ["local_import_metadata_required"]
    assert preview.contribution_entry is None


def test_public_candidate_with_explicit_identity_builds_ephemeral_entry_and_offers_import():
    preview = preview_research_opportunity_handoff(
        handoff(PUBLIC_CANDIDATE),
        contribution_entry_id="entry-example-42",
        contribution_discovered_at=datetime.fromisoformat("2026-09-05T01:30:00+00:00"),
    )
    assert preview.status == "REVIEWABLE"
    assert preview.allowed_dispositions == ["IMPORT_PUBLIC_CONTRIBUTION", "WATCH", "DISCARD"]
    assert preview.blocked_reasons == []
    assert preview.contribution_entry is not None
    assert preview.contribution_entry.entry_id == "entry-example-42"
    assert preview.contribution_entry.account_id is None
    assert preview.contribution_entry.task_claim_state == "AVAILABLE"


def test_maintainer_stated_need_without_evidence_fails_closed_when_checking_import_compatibility():
    payload = deepcopy(PUBLIC_CANDIDATE)
    payload["candidate"]["evidence_refs"] = []
    preview = preview_research_opportunity_handoff(
        handoff(payload),
        contribution_entry_id="entry-example-42",
        contribution_discovered_at=datetime.fromisoformat("2026-09-05T01:30:00+00:00"),
    )
    assert preview.status == "BLOCKED"
    assert preview.allowed_dispositions == ["WATCH", "DISCARD"]
    assert preview.contribution_entry is None
    assert preview.blocked_reasons == ["contribution_entry_domain_validation_failed"]


def test_available_task_without_task_ref_fails_closed_when_checking_import_compatibility():
    payload = deepcopy(PUBLIC_CANDIDATE)
    payload["candidate"]["task_ref"] = None
    preview = preview_research_opportunity_handoff(
        handoff(payload),
        contribution_entry_id="entry-example-42",
        contribution_discovered_at=datetime.fromisoformat("2026-09-05T01:30:00+00:00"),
    )
    assert preview.status == "BLOCKED"
    assert preview.contribution_entry is None
    assert preview.blocked_reasons == ["contribution_entry_domain_validation_failed"]


def test_claimed_other_remains_claimed_other_in_ephemeral_entry():
    payload = deepcopy(PUBLIC_CANDIDATE)
    payload["candidate"]["task_claim_state"] = "CLAIMED_OTHER"
    preview = preview_research_opportunity_handoff(
        handoff(payload),
        contribution_entry_id="entry-example-42",
        contribution_discovered_at=datetime.fromisoformat("2026-09-05T01:30:00+00:00"),
    )
    assert preview.contribution_entry is not None
    assert preview.contribution_entry.task_claim_state == "CLAIMED_OTHER"


def test_partial_local_import_metadata_is_blocked_without_guessing_missing_value():
    preview = preview_research_opportunity_handoff(
        handoff(PUBLIC_CANDIDATE),
        contribution_entry_id="entry-example-42",
    )
    assert preview.status == "BLOCKED"
    assert preview.allowed_dispositions == ["WATCH", "DISCARD"]
    assert preview.blocked_reasons == ["local_import_metadata_incomplete"]
    assert preview.contribution_entry is None


def test_naive_local_discovered_at_fails_closed():
    preview = preview_research_opportunity_handoff(
        handoff(PUBLIC_CANDIDATE),
        contribution_entry_id="entry-example-42",
        contribution_discovered_at=datetime(2026, 9, 5, 1, 30),
    )
    assert preview.status == "BLOCKED"
    assert preview.blocked_reasons == ["contribution_entry_domain_validation_failed"]
    assert preview.contribution_entry is None
