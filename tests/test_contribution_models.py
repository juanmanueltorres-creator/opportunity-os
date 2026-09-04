from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contributions.models import ContributionEvent, PublicContributionEntry

NOW = datetime(2026, 9, 4, 3, 30, tzinfo=timezone.utc)


def make_entry(**overrides) -> PublicContributionEntry:
    payload = {
        "entry_id": "entry-1",
        "repository_full_name": "example/project",
        "repository_url": "https://github.com/example/project",
        "origin": "PUBLIC_ISSUE",
        "need_basis": "OBSERVED",
        "need_statement": "A reproducible issue exists.",
        "evidence_refs": ["github:issue:example/project#1"],
        "task_ref": "github:issue:example/project#1",
        "task_claim_state": "AVAILABLE",
        "discovered_at": NOW,
    }
    payload.update(overrides)
    return PublicContributionEntry(**payload)


def test_entry_is_strict_and_normalizes_utc() -> None:
    entry = make_entry()
    assert entry.discovered_at.tzinfo is timezone.utc
    with pytest.raises(ValidationError):
        PublicContributionEntry(**entry.model_dump(), invented=True)


def test_entry_rejects_naive_discovered_at() -> None:
    with pytest.raises(ValidationError):
        make_entry(discovered_at=datetime(2026, 9, 4, 3, 30))


def test_observed_need_requires_provenance() -> None:
    with pytest.raises(ValidationError):
        make_entry(evidence_refs=[])


def test_maintainer_stated_need_requires_provenance() -> None:
    with pytest.raises(ValidationError):
        make_entry(need_basis="MAINTAINER_STATED", evidence_refs=[])


def test_hypothesis_can_exist_without_claiming_observed_need() -> None:
    entry = make_entry(
        need_basis="HYPOTHESIZED",
        evidence_refs=[],
        task_ref=None,
        task_claim_state="NONE",
    )
    assert entry.need_basis == "HYPOTHESIZED"
    assert entry.evidence_refs == []


@pytest.mark.parametrize(
    "claim_state",
    ["AVAILABLE", "CLAIMED_SELF", "CLAIMED_OTHER", "CLOSED"],
)
def test_task_claim_states_require_task_ref(claim_state: str) -> None:
    with pytest.raises(ValidationError):
        make_entry(task_ref=None, task_claim_state=claim_state)


def make_event(kind: str, **overrides) -> ContributionEvent:
    payload = {
        "event_id": "event-1",
        "entry_id": "entry-1",
        "kind": kind,
        "source_type": "PUBLIC_GITHUB",
        "source_ref": "github:event:1",
        "observed_at": NOW,
    }
    payload.update(overrides)
    return ContributionEvent(**payload)


def test_event_rejects_naive_observed_at() -> None:
    with pytest.raises(ValidationError):
        make_event("DISCOVERED", observed_at=datetime(2026, 9, 4, 3, 30))


@pytest.mark.parametrize(
    "kind",
    [
        "TASK_SELECTED",
        "TASK_CLAIMED_SELF",
        "TASK_CLAIMED_OTHER",
        "TASK_RELEASED",
    ],
)
def test_task_events_require_task_ref(kind: str) -> None:
    with pytest.raises(ValidationError):
        make_event(kind)


@pytest.mark.parametrize(
    "kind",
    [
        "PR_OPENED",
        "REVIEW_RECEIVED",
        "CHANGES_REQUESTED",
        "PR_MERGED",
        "PR_CLOSED",
    ],
)
def test_pr_events_require_work_ref(kind: str) -> None:
    with pytest.raises(ValidationError):
        make_event(kind)


def test_blocked_event_requires_reason() -> None:
    with pytest.raises(ValidationError):
        make_event("BLOCKED")


def test_valid_blocked_event_keeps_bounded_reason() -> None:
    event = make_event(
        "BLOCKED",
        reason="external deployment authorization required",
    )
    assert event.reason == "external deployment authorization required"
