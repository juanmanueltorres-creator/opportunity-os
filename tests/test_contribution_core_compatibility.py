from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contributions.models import ContributionEvent, PublicContributionEntry
from app.contributions.projector import ContributionProjector

NOW = datetime(2026, 9, 4, 6, 30, tzinfo=timezone.utc)
TASK = "https://github.com/WesleyHanauer/moracarta/issues/25"
PR = "https://github.com/WesleyHanauer/moracarta/pull/42"


def claimed_self_entry() -> PublicContributionEntry:
    return PublicContributionEntry(
        entry_id="contrib-moracarta-25",
        repository_full_name="WesleyHanauer/moracarta",
        repository_url="https://github.com/WesleyHanauer/moracarta",
        origin="PUBLIC_ISSUE",
        need_basis="OBSERVED",
        need_statement="tests: setup command",
        evidence_refs=[TASK],
        task_ref=TASK,
        bounded_task="tests: setup command",
        task_claim_state="CLAIMED_SELF",
        expected_effort="UNKNOWN",
        risk_level="UNKNOWN",
        discovered_at=NOW,
    )


def task_closed_event(*, observed_at: datetime) -> ContributionEvent:
    return ContributionEvent(
        event_id=f"event-task-close-{observed_at.timestamp()}",
        entry_id="contrib-moracarta-25",
        kind="TASK_CLOSED",
        source_type="PUBLIC_GITHUB",
        source_ref=TASK,
        observed_at=observed_at,
        task_ref=TASK,
    )


def test_claimed_self_entry_initializes_task_ready():
    context = ContributionProjector().project(entry=claimed_self_entry(), events=[])
    assert context.stage == "TASK_READY"
    assert context.task_claim_state == "CLAIMED_SELF"


def test_task_closed_closes_task_ready_entry():
    context = ContributionProjector().project(
        entry=claimed_self_entry(),
        events=[task_closed_event(observed_at=NOW)],
    )
    assert context.stage == "CLOSED"
    assert context.task_claim_state == "CLOSED"


def test_task_closed_does_not_erase_open_pr_review_stage():
    events = [
        ContributionEvent(
            event_id="event-pr-open",
            entry_id="contrib-moracarta-25",
            kind="PR_OPENED",
            source_type="PUBLIC_GITHUB",
            source_ref=PR,
            observed_at=NOW,
            work_ref=PR,
        ),
        task_closed_event(observed_at=NOW.replace(second=1)),
    ]
    context = ContributionProjector().project(entry=claimed_self_entry(), events=events)
    assert context.stage == "IN_REVIEW"
    assert context.task_claim_state == "CLOSED"
    assert context.active_work_ref == PR


def test_task_closed_requires_task_ref():
    with pytest.raises(ValidationError):
        ContributionEvent(
            event_id="event-invalid-close",
            entry_id="contrib-moracarta-25",
            kind="TASK_CLOSED",
            source_type="PUBLIC_GITHUB",
            source_ref=TASK,
            observed_at=NOW,
        )


def test_task_closed_then_released_reopens_task_ready():
    events = [
        task_closed_event(observed_at=NOW),
        ContributionEvent(
            event_id="event-task-released",
            entry_id="contrib-moracarta-25",
            kind="TASK_RELEASED",
            source_type="PUBLIC_GITHUB",
            source_ref=TASK,
            observed_at=NOW.replace(second=1),
            task_ref=TASK,
        ),
    ]
    context = ContributionProjector().project(entry=claimed_self_entry(), events=events)
    assert context.stage == "TASK_READY"
    assert context.task_claim_state == "AVAILABLE"
