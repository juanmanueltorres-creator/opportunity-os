from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.handoffs.intake_cli import main


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
        "account_id": None,
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

ACTOR_HANDOFF = {
    "contract": "research-opportunity-handoff/v0.1",
    "handoff_id": "roh:water:001",
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
        "actor_refs": [],
        "evidence_refs": [],
        "assumptions": ["A recurring decision exists."],
        "missing_context": ["Decision owner"],
        "research_status": "researching",
    },
}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def build_args(question_file: Path, preview_file: Path, out: Path) -> list[str]:
    return [
        "build-public-candidate",
        "--question-handoff-file",
        str(question_file),
        "--contribution-preview-file",
        str(preview_file),
        "--handoff-id",
        "roh:fixture:github:001",
        "--created-at",
        "2026-09-05T01:10:00-03:00",
        "--out",
        str(out),
    ]


def test_build_public_candidate_writes_contract2_without_local_entry_metadata(tmp_path: Path):
    question_file = tmp_path / "question.json"
    preview_file = tmp_path / "contribution-preview.json"
    out = tmp_path / "out" / "candidate.json"
    write_json(question_file, QUESTION_HANDOFF)
    write_json(preview_file, IMPORTABLE_PREVIEW)

    assert main(build_args(question_file, preview_file, out)) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["candidate"]["kind"] == "PUBLIC_CONTRIBUTION_CANDIDATE"
    assert payload["candidate"]["task_claim_state"] == "AVAILABLE"
    assert "entry_id" not in payload["candidate"]
    assert "account_id" not in payload["candidate"]
    assert "discovered_at" not in payload["candidate"]


def test_build_public_candidate_rejects_non_importable_preview_without_output(tmp_path: Path):
    question_file = tmp_path / "question.json"
    preview_file = tmp_path / "contribution-preview.json"
    out = tmp_path / "missing" / "candidate.json"
    write_json(question_file, QUESTION_HANDOFF)
    blocked = {**IMPORTABLE_PREVIEW, "status": "NO_CHANGE", "proposed_entry": None}
    write_json(preview_file, blocked)

    assert main(build_args(question_file, preview_file, out)) == 2
    assert not out.exists()
    assert not out.parent.exists()


def test_build_public_candidate_rejects_event_only_preview_without_output(tmp_path: Path):
    question_file = tmp_path / "question.json"
    preview_file = tmp_path / "contribution-preview.json"
    out = tmp_path / "missing" / "candidate.json"
    write_json(question_file, QUESTION_HANDOFF)
    event_only = {
        **IMPORTABLE_PREVIEW,
        "proposed_entry": None,
        "candidate_event": {
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
        },
    }
    write_json(preview_file, event_only)

    assert main(build_args(question_file, preview_file, out)) == 2
    assert not out.exists()


def test_preview_actor_handoff_is_reviewable_and_does_not_promote_actor(tmp_path: Path):
    handoff_file = tmp_path / "actor.json"
    out = tmp_path / "preview.json"
    write_json(handoff_file, ACTOR_HANDOFF)

    assert main(["preview", "--handoff-file", str(handoff_file), "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "REVIEWABLE"
    assert payload["allowed_dispositions"] == ["WATCH", "DISCARD"]
    assert payload["blocked_reasons"] == ["actor_ref_required_for_research_actor"]
    assert payload["contribution_entry"] is None


def test_preview_public_candidate_requires_local_metadata_before_offering_import(tmp_path: Path):
    question_file = tmp_path / "question.json"
    contribution_file = tmp_path / "contribution.json"
    contract2 = tmp_path / "candidate.json"
    preview_out = tmp_path / "preview.json"
    write_json(question_file, QUESTION_HANDOFF)
    write_json(contribution_file, IMPORTABLE_PREVIEW)
    assert main(build_args(question_file, contribution_file, contract2)) == 0

    assert main(["preview", "--handoff-file", str(contract2), "--out", str(preview_out)]) == 0
    payload = json.loads(preview_out.read_text(encoding="utf-8"))
    assert payload["allowed_dispositions"] == ["WATCH", "DISCARD"]
    assert payload["blocked_reasons"] == ["local_import_metadata_required"]


def test_preview_public_candidate_with_explicit_metadata_offers_eligibility_only(tmp_path: Path):
    question_file = tmp_path / "question.json"
    contribution_file = tmp_path / "contribution.json"
    contract2 = tmp_path / "candidate.json"
    preview_out = tmp_path / "preview.json"
    write_json(question_file, QUESTION_HANDOFF)
    write_json(contribution_file, IMPORTABLE_PREVIEW)
    assert main(build_args(question_file, contribution_file, contract2)) == 0

    assert main(
        [
            "preview",
            "--handoff-file",
            str(contract2),
            "--out",
            str(preview_out),
            "--contribution-entry-id",
            "entry-example-42",
            "--contribution-discovered-at",
            "2026-09-05T01:30:00+00:00",
        ]
    ) == 0
    payload = json.loads(preview_out.read_text(encoding="utf-8"))
    assert payload["allowed_dispositions"] == [
        "IMPORT_PUBLIC_CONTRIBUTION",
        "WATCH",
        "DISCARD",
    ]
    assert payload["contribution_entry"]["entry_id"] == "entry-example-42"


def test_invalid_handoff_returns_2_and_leaves_output_absent(tmp_path: Path):
    handoff_file = tmp_path / "invalid.json"
    out = tmp_path / "missing" / "preview.json"
    handoff_file.write_text("not-json", encoding="utf-8")

    assert main(["preview", "--handoff-file", str(handoff_file), "--out", str(out)]) == 2
    assert not out.exists()
    assert not out.parent.exists()


def test_commands_do_not_create_sqlite_or_construct_http_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)

    def forbidden_http_client(*args, **kwargs):
        raise AssertionError("HTTP client must not be constructed by handoff CLI")

    monkeypatch.setattr(httpx, "Client", forbidden_http_client)

    question_file = tmp_path / "question.json"
    contribution_file = tmp_path / "contribution.json"
    contract2 = tmp_path / "candidate.json"
    preview_out = tmp_path / "preview.json"
    write_json(question_file, QUESTION_HANDOFF)
    write_json(contribution_file, IMPORTABLE_PREVIEW)

    assert main(build_args(question_file, contribution_file, contract2)) == 0
    assert main(["preview", "--handoff-file", str(contract2), "--out", str(preview_out)]) == 0
    assert not (tmp_path / "state").exists()
    assert list(tmp_path.rglob("*.sqlite3")) == []


def test_identical_explicit_inputs_produce_byte_identical_json(tmp_path: Path):
    question_file = tmp_path / "question.json"
    contribution_file = tmp_path / "contribution.json"
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    write_json(question_file, QUESTION_HANDOFF)
    write_json(contribution_file, IMPORTABLE_PREVIEW)

    assert main(build_args(question_file, contribution_file, out_a)) == 0
    assert main(build_args(question_file, contribution_file, out_b)) == 0
    assert out_a.read_bytes() == out_b.read_bytes()


def test_handoff_cli_has_no_import_subcommand():
    with pytest.raises(SystemExit) as exc:
        main(["import"])
    assert exc.value.code == 2
