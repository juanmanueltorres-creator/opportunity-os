import json
from copy import deepcopy
from datetime import datetime

import pytest

from app.contributions.observations import ContributionPreview
from app.handoffs.models import QuestionResearchHandoff
from app.handoffs.public_contribution_research import (
    build_public_contribution_candidate_handoff,
    render_research_opportunity_handoff_json,
)


QUESTION_HANDOFF = {
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
    "constraints": ["GOOD_PROBLEM != AVAILABLE_PROBLEM"],
}

IMPORTABLE_PREVIEW = {
    "preview_version": "contribution-preview-v1",
    "status": "IMPORTABLE",
    "observation": {
        "observation_id": "obs:example:42:available",
        "source_type": "PUBLIC_GITHUB",
        "source_name": "github",
        "source_ref": "github:example/project/issues/42",
        "kind": "ISSUE_AVAILABLE",
        "entry_id": "entry-example-42",
        "repository_full_name": "example/project",
        "public_title": "Add support for the documented geospatial format",
        "fact_at": "2026-09-05T01:00:00Z",
        "captured_at": "2026-09-05T01:01:00Z",
        "task_ref": "github:example/project/issues/42",
        "work_ref": None,
        "actor_ref": None,
        "reason_code": None,
        "source_fact_identity": "issue:example/project:42:open:unassigned",
    },
    "observation_sha256": "a" * 64,
    "preview_sha256": "b" * 64,
    "entry_id": "entry-example-42",
    "source_ref": "github:example/project/issues/42",
    "proposed_entry": {
        "entry_id": "entry-example-42",
        "repository_full_name": "example/project",
        "repository_url": "https://github.com/example/project",
        "account_id": "account-local-only",
        "origin": "PUBLIC_ISSUE",
        "need_basis": "MAINTAINER_STATED",
        "need_statement": "Add support for the documented geospatial format.",
        "evidence_refs": ["github:example/project/issues/42"],
        "task_ref": "github:example/project/issues/42",
        "bounded_task": "Implement the explicitly requested format support.",
        "task_claim_state": "AVAILABLE",
        "expected_effort": "S",
        "risk_level": "LOW",
        "discovered_at": "2026-09-05T01:01:00Z",
    },
    "candidate_event": None,
    "context_before": None,
    "context_after": None,
    "errors": [],
    "external_actions": [],
}


def question_handoff() -> QuestionResearchHandoff:
    return QuestionResearchHandoff.model_validate(deepcopy(QUESTION_HANDOFF))


def preview(payload: dict | None = None) -> ContributionPreview:
    return ContributionPreview.model_validate(deepcopy(payload or IMPORTABLE_PREVIEW))


def test_builds_public_candidate_from_existing_importable_preview_only():
    handoff = build_public_contribution_candidate_handoff(
        question_handoff(),
        preview(),
        handoff_id="roh:fixture:github:001",
        created_at=datetime.fromisoformat("2026-09-05T01:10:00-03:00"),
    )
    payload = handoff.model_dump(mode="json")

    assert payload["source"] == {
        "system": "question-radar",
        "source_question_ref": "question:fixture:github:001",
        "research_intent_ref": None,
        "hypothesis_ref": None,
    }
    assert payload["candidate"] == {
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
    }


def test_adapter_does_not_copy_local_entry_metadata_into_contract2():
    payload = build_public_contribution_candidate_handoff(
        question_handoff(),
        preview(),
        handoff_id="roh:fixture:github:001",
        created_at=datetime.fromisoformat("2026-09-05T01:10:00-03:00"),
    ).model_dump(mode="json")

    candidate = payload["candidate"]
    assert "entry_id" not in candidate
    assert "account_id" not in candidate
    assert "discovered_at" not in candidate


def test_rejects_non_importable_preview():
    payload = deepcopy(IMPORTABLE_PREVIEW)
    payload["status"] = "NO_CHANGE"
    payload["proposed_entry"] = None
    with pytest.raises(ValueError, match="IMPORTABLE"):
        build_public_contribution_candidate_handoff(
            question_handoff(),
            preview(payload),
            handoff_id="roh:fixture:github:no-change",
            created_at=datetime.fromisoformat("2026-09-05T01:10:00-03:00"),
        )


def test_rejects_importable_preview_without_proposed_entry():
    payload = deepcopy(IMPORTABLE_PREVIEW)
    payload["proposed_entry"] = None
    payload["candidate_event"] = {
        "event_id": "event:entry-example-42:task-selected",
        "entry_id": "entry-example-42",
        "kind": "TASK_SELECTED",
        "source_type": "PUBLIC_GITHUB",
        "source_ref": "github:example/project/issues/42",
        "observed_at": "2026-09-05T01:01:00Z",
        "actor_ref": None,
        "work_ref": None,
        "task_ref": "github:example/project/issues/42",
        "reason": None,
    }
    with pytest.raises(ValueError, match="proposed_entry"):
        build_public_contribution_candidate_handoff(
            question_handoff(),
            preview(payload),
            handoff_id="roh:fixture:github:event-only",
            created_at=datetime.fromisoformat("2026-09-05T01:10:00-03:00"),
        )


def test_rejects_naive_created_at():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_public_contribution_candidate_handoff(
            question_handoff(),
            preview(),
            handoff_id="roh:fixture:github:naive",
            created_at=datetime(2026, 9, 5, 1, 10),
        )


def test_renderer_is_byte_deterministic_and_has_no_preview_local_metadata():
    handoff = build_public_contribution_candidate_handoff(
        question_handoff(),
        preview(),
        handoff_id="roh:fixture:github:001",
        created_at=datetime.fromisoformat("2026-09-05T01:10:00-03:00"),
    )
    first = render_research_opportunity_handoff_json(handoff)
    second = render_research_opportunity_handoff_json(handoff)
    assert first == second
    assert first.endswith("\n")
    assert json.loads(first) == handoff.model_dump(mode="json")
    assert "account-local-only" not in first
    assert "entry-example-42" not in json.dumps(json.loads(first)["candidate"])
