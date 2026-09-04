from __future__ import annotations

import json
from pathlib import Path

from app.contributions.models import ContributionEvent, PublicContributionEntry
from app.contributions.normalizer import normalize_snapshot
from app.contributions.observations import (
    GitHubContributionSelection,
    GitHubIssueSnapshot,
    GitHubPullRequestSnapshot,
)
from app.contributions.projector import ContributionProjector

FIXTURE = Path("tests/fixtures/contributions/github_intake_v1.json")


def load_cases():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


def test_public_fixture_contains_only_sanitized_allowlisted_data():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    serialized = json.dumps(payload).lower()
    for forbidden in [
        "email", "token", "authorization_header", "raw_body", "review_body",
        "check_log", "private_message", "employment_interest",
    ]:
        assert forbidden not in serialized


def test_issue_dogfood_cases_project_expected_claim_state_and_stage():
    projector = ContributionProjector()
    for case in load_cases()[:3]:
        selection = GitHubContributionSelection.model_validate(case["selection"])
        snapshot = GitHubIssueSnapshot.model_validate(case["snapshot"])
        result = normalize_snapshot(
            selection=selection,
            snapshot=snapshot,
            entry=None,
            events=[],
            projector=projector,
        )
        assert result.status == "IMPORTABLE"
        assert result.proposed_entry is not None
        assert result.proposed_entry.task_claim_state == case["expected_claim_state"]
        context = projector.project(entry=result.proposed_entry, events=[])
        assert context.stage == case["expected_stage"]


def test_moracarta_pr_dogfood_enters_review_with_explicit_lineage():
    case = next(item for item in load_cases() if item["case_id"] == "moracarta-pr-open")
    selection = GitHubContributionSelection.model_validate(case["selection"])
    snapshot = GitHubPullRequestSnapshot.model_validate(case["snapshot"])
    entry = PublicContributionEntry.model_validate(case["existing_entry"])
    projector = ContributionProjector()

    result = normalize_snapshot(
        selection=selection,
        snapshot=snapshot,
        entry=entry,
        events=[],
        projector=projector,
    )
    assert result.status == "IMPORTABLE"
    assert result.candidate_event is not None
    assert result.candidate_event.kind == case["expected_event"]
    context = projector.project(entry=entry, events=[result.candidate_event])
    assert context.stage == case["expected_stage"]


def test_sunat_dogfood_preserves_review_stage_while_external_gate_blocks():
    case = next(item for item in load_cases() if item["case_id"] == "sunat-pr-external-blocker")
    selection = GitHubContributionSelection.model_validate(case["selection"])
    snapshot = GitHubPullRequestSnapshot.model_validate(case["snapshot"])
    entry = PublicContributionEntry.model_validate(case["existing_entry"])
    projector = ContributionProjector()

    first = normalize_snapshot(
        selection=selection,
        snapshot=snapshot,
        entry=entry,
        events=[],
        projector=projector,
    )
    assert first.status == "IMPORTABLE"
    assert first.candidate_event is not None
    assert first.candidate_event.kind == case["expected_first_event"]

    events: list[ContributionEvent] = [first.candidate_event]
    second = normalize_snapshot(
        selection=selection,
        snapshot=snapshot,
        entry=entry,
        events=events,
        projector=projector,
    )
    assert second.status == "IMPORTABLE"
    assert second.candidate_event is not None
    assert second.candidate_event.kind == case["expected_second_event"]

    context = projector.project(entry=entry, events=events + [second.candidate_event])
    assert context.stage == case["expected_stage"]
    assert context.blocking_reason == case["expected_blocking_reason"]
