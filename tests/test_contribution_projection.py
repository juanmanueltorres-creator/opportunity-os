from datetime import datetime, timedelta, timezone

import pytest

from app.contributions.models import ContributionEvent, PublicContributionEntry
from app.contributions.projector import ContributionProjectionError, ContributionProjector

NOW = datetime(2026, 9, 4, 3, 30, tzinfo=timezone.utc)


def make_entry(*, claim: str = "NONE") -> PublicContributionEntry:
    return PublicContributionEntry(
        entry_id="entry-1",
        repository_full_name="example/project",
        repository_url="https://github.com/example/project",
        origin="REPOSITORY_RESEARCH",
        need_basis="HYPOTHESIZED",
        need_statement="A bounded contribution may be useful.",
        evidence_refs=[],
        task_ref="github:issue:example/project#25" if claim != "NONE" else None,
        task_claim_state=claim,
        discovered_at=NOW,
    )


def make_event(kind: str, minute: int, **overrides) -> ContributionEvent:
    payload = {
        "event_id": f"event-{minute:02d}-{kind.lower()}",
        "entry_id": "entry-1",
        "kind": kind,
        "source_type": "PUBLIC_GITHUB",
        "source_ref": f"github:event:{minute}",
        "observed_at": NOW + timedelta(minutes=minute),
    }
    payload.update(overrides)
    return ContributionEvent(**payload)


def test_available_entry_starts_task_ready() -> None:
    context = ContributionProjector().project(
        entry=make_entry(claim="AVAILABLE"),
        events=[],
    )
    assert context.stage == "TASK_READY"
    assert context.task_claim_state == "AVAILABLE"
    assert context.event_count == 0


def test_claimed_other_entry_stays_discovered() -> None:
    context = ContributionProjector().project(
        entry=make_entry(claim="CLAIMED_OTHER"),
        events=[],
    )
    assert context.stage == "DISCOVERED"
    assert context.task_claim_state == "CLAIMED_OTHER"


def test_outreach_without_reply_is_contacted_not_engaged() -> None:
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[make_event("OUTREACH_SENT", 1)],
    )
    assert context.stage == "CONTACTED"


def test_maintainer_reply_is_engaged_without_fabricating_task() -> None:
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[
            make_event("OUTREACH_SENT", 1),
            make_event("MAINTAINER_REPLIED", 2),
        ],
    )
    assert context.stage == "ENGAGED"
    assert context.task_claim_state == "NONE"


def test_self_claim_and_work_start_progress_to_in_progress() -> None:
    task_ref = "github:issue:example/project#25"
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[
            make_event("TASK_SELECTED", 1, task_ref=task_ref),
            make_event("TASK_CLAIMED_SELF", 2, task_ref=task_ref),
            make_event("WORK_STARTED", 3),
        ],
    )
    assert context.stage == "IN_PROGRESS"
    assert context.task_claim_state == "CLAIMED_SELF"


def test_claim_by_other_never_fabricates_task_ready() -> None:
    task_ref = "github:issue:example/project#25"
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[make_event("TASK_CLAIMED_OTHER", 1, task_ref=task_ref)],
    )
    assert context.stage == "DISCOVERED"
    assert context.task_claim_state == "CLAIMED_OTHER"


def test_open_pr_projects_in_review() -> None:
    work_ref = "github:pr:example/project#42"
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[make_event("PR_OPENED", 1, work_ref=work_ref)],
    )
    assert context.stage == "IN_REVIEW"
    assert context.active_work_ref == work_ref


def test_merged_pr_projects_completed() -> None:
    work_ref = "github:pr:example/project#42"
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[
            make_event("PR_OPENED", 1, work_ref=work_ref),
            make_event("PR_MERGED", 2, work_ref=work_ref),
        ],
    )
    assert context.stage == "COMPLETED"
    assert context.active_work_ref == work_ref


def test_closed_unmerged_pr_projects_closed() -> None:
    work_ref = "github:pr:example/project#42"
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[
            make_event("PR_OPENED", 1, work_ref=work_ref),
            make_event("PR_CLOSED", 2, work_ref=work_ref),
        ],
    )
    assert context.stage == "CLOSED"
    assert context.active_work_ref == work_ref


@pytest.mark.parametrize(
    "kind",
    ["REVIEW_RECEIVED", "CHANGES_REQUESTED", "PR_MERGED", "PR_CLOSED"],
)
def test_pr_followup_without_open_pr_fails_closed(kind: str) -> None:
    with pytest.raises(ContributionProjectionError):
        ContributionProjector().project(
            entry=make_entry(),
            events=[
                make_event(
                    kind,
                    1,
                    work_ref="github:pr:example/project#42",
                )
            ],
        )


def test_unblock_without_active_blocker_fails_closed() -> None:
    with pytest.raises(ContributionProjectionError):
        ContributionProjector().project(
            entry=make_entry(),
            events=[make_event("UNBLOCKED", 1)],
        )


def test_double_block_fails_closed() -> None:
    with pytest.raises(ContributionProjectionError):
        ContributionProjector().project(
            entry=make_entry(),
            events=[
                make_event("BLOCKED", 1, reason="first blocker"),
                make_event("BLOCKED", 2, reason="second blocker"),
            ],
        )


def test_event_for_another_entry_fails_closed() -> None:
    foreign = make_event("OUTREACH_SENT", 1).model_copy(
        update={"entry_id": "entry-other"}
    )
    with pytest.raises(ContributionProjectionError):
        ContributionProjector().project(entry=make_entry(), events=[foreign])


def test_review_work_ref_must_match_open_pr() -> None:
    with pytest.raises(ContributionProjectionError):
        ContributionProjector().project(
            entry=make_entry(),
            events=[
                make_event(
                    "PR_OPENED",
                    1,
                    work_ref="github:pr:example/project#42",
                ),
                make_event(
                    "REVIEW_RECEIVED",
                    2,
                    work_ref="github:pr:example/project#99",
                ),
            ],
        )


def test_blocker_preserves_in_review_stage() -> None:
    work_ref = "github:pr:example/project#115"
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[
            make_event("PR_OPENED", 1, work_ref=work_ref),
            make_event(
                "BLOCKED",
                2,
                reason="external deployment authorization required",
            ),
        ],
    )
    assert context.stage == "IN_REVIEW"
    assert context.blocking_reason == "external deployment authorization required"
    assert context.active_work_ref == work_ref


def test_unblock_clears_only_blocker() -> None:
    work_ref = "github:pr:example/project#115"
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[
            make_event("PR_OPENED", 1, work_ref=work_ref),
            make_event(
                "BLOCKED",
                2,
                reason="external deployment authorization required",
            ),
            make_event("UNBLOCKED", 3),
        ],
    )
    assert context.stage == "IN_REVIEW"
    assert context.blocking_reason is None
    assert context.active_work_ref == work_ref


def test_pause_and_resume_restore_previous_stage() -> None:
    context = ContributionProjector().project(
        entry=make_entry(),
        events=[
            make_event("OUTREACH_SENT", 1),
            make_event("MAINTAINER_REPLIED", 2),
            make_event("PAUSED", 3),
            make_event("RESUMED", 4),
        ],
    )
    assert context.stage == "ENGAGED"


def test_projection_is_deterministic_for_equal_timestamps() -> None:
    timestamp = NOW + timedelta(minutes=1)
    event_a = ContributionEvent(
        event_id="event-a",
        entry_id="entry-1",
        kind="OUTREACH_SENT",
        source_type="PUBLIC_GITHUB",
        source_ref="github:event:a",
        observed_at=timestamp,
    )
    event_b = ContributionEvent(
        event_id="event-b",
        entry_id="entry-1",
        kind="MAINTAINER_REPLIED",
        source_type="PUBLIC_GITHUB",
        source_ref="github:event:b",
        observed_at=timestamp,
    )
    projector = ContributionProjector()
    first = projector.project(entry=make_entry(), events=[event_b, event_a])
    second = projector.project(entry=make_entry(), events=[event_a, event_b])
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.stage == "ENGAGED"
