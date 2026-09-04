from datetime import datetime, timedelta, timezone

from app.contributions.models import PublicContributionEntry
from app.contributions.normalizer import (
    deterministic_issue_entry_id,
    normalize_embedded_observation,
    normalize_snapshot,
)
from app.contributions.observations import (
    GitHubCheckSnapshot,
    GitHubContributionSelection,
    GitHubIssueSnapshot,
    GitHubPullRequestSnapshot,
    GitHubReviewSnapshot,
)
from app.contributions.projector import ContributionProjector

NOW = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
ISSUE = "https://github.com/owner/repo/issues/1"
PR = "https://github.com/owner/repo/pull/42"


def issue_selection(*, entry_id=None, operator="Juan"):
    return GitHubContributionSelection(
        resource_kind="ISSUE",
        repository_full_name="owner/repo",
        number=1,
        source_url=ISSUE,
        operator_github_login=operator,
        entry_id=entry_id,
    )


def issue_snapshot(
    *,
    state="OPEN",
    assignees=None,
    updated_at=NOW,
    closed_at=None,
    title="  Fix\n  bug\t now  ",
):
    if state == "CLOSED" and closed_at is None:
        closed_at = updated_at
    return GitHubIssueSnapshot(
        repository_full_name="owner/repo",
        issue_number=1,
        issue_url=ISSUE,
        title=title,
        state=state,
        assignee_logins=list(assignees or []),
        author_login="alice",
        created_at=NOW - timedelta(days=1),
        updated_at=updated_at,
        closed_at=closed_at,
        captured_at=NOW + timedelta(minutes=1),
    )


def entry(*, claim="AVAILABLE", task_ref=ISSUE, repo="owner/repo"):
    return PublicContributionEntry(
        entry_id=deterministic_issue_entry_id("owner/repo", 1),
        repository_full_name=repo,
        repository_url=f"https://github.com/{repo}",
        origin="PUBLIC_ISSUE",
        need_basis="OBSERVED",
        need_statement="Fix bug now",
        evidence_refs=[ISSUE],
        task_ref=task_ref,
        bounded_task="Fix bug now",
        task_claim_state=claim,
        discovered_at=NOW,
    )


def pr_selection(*, entry_id=None, repo="owner/repo"):
    if entry_id is None:
        entry_id = deterministic_issue_entry_id("owner/repo", 1)
    return GitHubContributionSelection(
        resource_kind="PULL_REQUEST",
        repository_full_name=repo,
        number=42,
        source_url=f"https://github.com/{repo}/pull/42",
        operator_github_login="juan",
        entry_id=entry_id,
    )


def pr_snapshot(
    *,
    reviews=None,
    checks=None,
    merged=False,
    state="OPEN",
    merged_at=None,
    closed_at=None,
    created_at=NOW,
):
    if merged and merged_at is None:
        merged_at = NOW + timedelta(minutes=20)
    if state == "CLOSED" and closed_at is None:
        closed_at = merged_at or NOW + timedelta(minutes=20)
    return GitHubPullRequestSnapshot(
        repository_full_name="owner/repo",
        pr_number=42,
        pr_url=PR,
        state=state,
        merged=merged,
        draft=False,
        author_login="juan",
        created_at=created_at,
        updated_at=NOW + timedelta(minutes=20),
        closed_at=closed_at,
        merged_at=merged_at,
        head_sha="abc123",
        reviews=list(reviews or []),
        checks=list(checks or []),
        captured_at=NOW + timedelta(minutes=30),
    )


def normalize_issue(snapshot, *, existing=None, events=None, selection=None):
    return normalize_snapshot(
        selection=selection
        or issue_selection(entry_id=existing.entry_id if existing else None),
        snapshot=snapshot,
        entry=existing,
        events=list(events or []),
        projector=ContributionProjector(),
    )


def normalize_pr(snapshot, *, existing=None, events=None, selection=None):
    return normalize_snapshot(
        selection=selection
        or pr_selection(
            entry_id=(
                existing.entry_id
                if existing
                else deterministic_issue_entry_id("owner/repo", 1)
            )
        ),
        snapshot=snapshot,
        entry=existing,
        events=list(events or []),
        projector=ContributionProjector(),
    )


def test_new_open_unassigned_issue_proposes_available_entry():
    result = normalize_issue(issue_snapshot())
    assert result.status == "IMPORTABLE"
    assert result.candidate_event is None
    assert result.proposed_entry is not None
    assert result.proposed_entry.task_claim_state == "AVAILABLE"
    assert result.proposed_entry.need_statement == "Fix bug now"
    assert result.proposed_entry.entry_id == deterministic_issue_entry_id("owner/repo", 1)
    context = ContributionProjector().project(entry=result.proposed_entry, events=[])
    assert context.stage == "TASK_READY"


def test_new_self_assigned_issue_is_case_insensitive_and_task_ready():
    result = normalize_snapshot(
        selection=issue_selection(operator="juan"),
        snapshot=issue_snapshot(assignees=["JUAN"]),
        entry=None,
        events=[],
        projector=ContributionProjector(),
    )
    assert result.proposed_entry.task_claim_state == "CLAIMED_SELF"
    assert (
        ContributionProjector().project(entry=result.proposed_entry, events=[]).stage
        == "TASK_READY"
    )


def test_new_other_assigned_issue_is_non_actionable():
    result = normalize_issue(issue_snapshot(assignees=["other"]))
    assert result.proposed_entry.task_claim_state == "CLAIMED_OTHER"
    assert (
        ContributionProjector().project(entry=result.proposed_entry, events=[]).stage
        == "DISCOVERED"
    )


def test_closed_issue_without_existing_entry_is_blocked():
    result = normalize_issue(issue_snapshot(state="CLOSED"))
    assert result.status == "BLOCKED"
    assert result.errors == ("closed_issue_requires_existing_entry",)


def test_existing_issue_repository_mismatch_is_blocked():
    result = normalize_issue(issue_snapshot(), existing=entry(repo="other/repo"))
    assert result.status == "BLOCKED"
    assert result.errors == ("repository_mismatch",)


def test_existing_issue_missing_or_wrong_task_ref_is_blocked():
    for task_ref in (None, "https://github.com/owner/repo/issues/99"):
        existing = entry(task_ref=ISSUE)
        object.__setattr__(existing, "task_ref", task_ref)
        result = normalize_issue(issue_snapshot(), existing=existing)
        assert result.status == "BLOCKED"
        assert result.errors == ("task_ref_mismatch",)


def test_unchanged_issue_claim_state_is_no_change_despite_updated_at():
    result = normalize_issue(
        issue_snapshot(updated_at=NOW + timedelta(hours=2)),
        existing=entry(claim="AVAILABLE"),
    )
    assert result.status == "NO_CHANGE"
    assert result.candidate_event is None


def test_claimed_other_to_unassigned_emits_task_released():
    result = normalize_issue(
        issue_snapshot(),
        existing=entry(claim="CLAIMED_OTHER"),
    )
    assert result.status == "IMPORTABLE"
    assert result.candidate_event.kind == "TASK_RELEASED"


def test_issue_close_emits_task_closed_then_reopen_emits_release():
    existing = entry(claim="AVAILABLE")
    closed = normalize_issue(
        issue_snapshot(state="CLOSED", updated_at=NOW + timedelta(minutes=2)),
        existing=existing,
    )
    assert closed.candidate_event.kind == "TASK_CLOSED"
    reopened = normalize_issue(
        issue_snapshot(state="OPEN", updated_at=NOW + timedelta(minutes=3)),
        existing=existing,
        events=[closed.candidate_event],
    )
    assert reopened.candidate_event.kind == "TASK_RELEASED"


def test_pr_without_entry_id_is_blocked_defense_in_depth():
    selection = GitHubContributionSelection.model_construct(
        resource_kind="PULL_REQUEST",
        repository_full_name="owner/repo",
        number=42,
        source_url=PR,
        operator_github_login="juan",
        entry_id=None,
    )
    result = normalize_pr(pr_snapshot(), existing=entry(), selection=selection)
    assert result.status == "BLOCKED"
    assert result.errors == ("pr_requires_entry_id",)


def test_pr_repository_mismatch_is_blocked():
    selection = pr_selection(repo="other/repo")
    snapshot = pr_snapshot().model_copy(
        update={
            "repository_full_name": "other/repo",
            "pr_url": "https://github.com/other/repo/pull/42",
        }
    )
    result = normalize_pr(snapshot, existing=entry(), selection=selection)
    assert result.status == "BLOCKED"
    assert result.errors == ("repository_mismatch",)


def test_pr_open_is_always_first_even_if_reviews_and_merge_exist():
    review = GitHubReviewSnapshot(
        review_ref="review:1",
        reviewer_login="maintainer",
        state="APPROVED",
        submitted_at=NOW + timedelta(minutes=5),
    )
    result = normalize_pr(
        pr_snapshot(
            reviews=[review],
            merged=True,
            state="CLOSED",
            merged_at=NOW + timedelta(minutes=10),
        ),
        existing=entry(),
    )
    assert result.status == "IMPORTABLE"
    assert result.candidate_event.kind == "PR_OPENED"
    assert result.candidate_event.observed_at == NOW


def test_older_review_is_selected_before_later_merge():
    opened = normalize_pr(pr_snapshot(), existing=entry()).candidate_event
    review = GitHubReviewSnapshot(
        review_ref="review:1",
        reviewer_login="maintainer",
        state="APPROVED",
        submitted_at=NOW + timedelta(minutes=5),
    )
    result = normalize_pr(
        pr_snapshot(
            reviews=[review],
            merged=True,
            state="CLOSED",
            merged_at=NOW + timedelta(minutes=10),
        ),
        existing=entry(),
        events=[opened],
    )
    assert result.candidate_event.kind == "REVIEW_RECEIVED"


def test_equal_timestamp_tie_order_is_changes_then_review_then_blocker_then_merge():
    opened = normalize_pr(pr_snapshot(), existing=entry()).candidate_event
    t = NOW + timedelta(minutes=5)
    reviews = [
        GitHubReviewSnapshot(
            review_ref="review:approved",
            reviewer_login="a",
            state="APPROVED",
            submitted_at=t,
        ),
        GitHubReviewSnapshot(
            review_ref="review:changes",
            reviewer_login="b",
            state="CHANGES_REQUESTED",
            submitted_at=t,
        ),
    ]
    check = GitHubCheckSnapshot(
        check_ref="check-run:7",
        name="Deploy",
        state_or_conclusion="ACTION_REQUIRED",
        description_code="EXTERNAL_AUTHORIZATION_REQUIRED",
        fact_at=t,
    )
    snap = pr_snapshot(
        reviews=reviews,
        checks=[check],
        merged=True,
        state="CLOSED",
        merged_at=t,
        closed_at=t,
    )
    first = normalize_pr(snap, existing=entry(), events=[opened])
    assert first.candidate_event.kind == "CHANGES_REQUESTED"
    second = normalize_pr(
        snap,
        existing=entry(),
        events=[opened, first.candidate_event],
    )
    assert second.candidate_event.kind == "REVIEW_RECEIVED"
    third = normalize_pr(
        snap,
        existing=entry(),
        events=[opened, first.candidate_event, second.candidate_event],
    )
    assert third.candidate_event.kind == "BLOCKED"
    fourth = normalize_pr(
        snap,
        existing=entry(),
        events=[
            opened,
            first.candidate_event,
            second.candidate_event,
            third.candidate_event,
        ],
    )
    assert fourth.candidate_event.kind == "PR_MERGED"
    ids = [
        first.candidate_event.event_id,
        second.candidate_event.event_id,
        third.candidate_event.event_id,
        fourth.candidate_event.event_id,
    ]
    assert ids == sorted(ids)


def test_dismissed_review_and_generic_failure_are_ignored():
    opened = normalize_pr(pr_snapshot(), existing=entry()).candidate_event
    review = GitHubReviewSnapshot(
        review_ref="review:1",
        reviewer_login="maintainer",
        state="DISMISSED",
        submitted_at=NOW + timedelta(minutes=5),
    )
    check = GitHubCheckSnapshot(
        check_ref="check-run:1",
        name="CI",
        state_or_conclusion="failure",
        description_code=None,
        fact_at=NOW + timedelta(minutes=6),
    )
    result = normalize_pr(
        pr_snapshot(reviews=[review], checks=[check]),
        existing=entry(),
        events=[opened],
    )
    assert result.status == "NO_CHANGE"
    assert result.candidate_event is None


def test_explicit_authorization_gate_emits_blocked_with_bounded_reason():
    opened = normalize_pr(pr_snapshot(), existing=entry()).candidate_event
    check = GitHubCheckSnapshot(
        check_ref="check-run:7",
        name="Deploy",
        state_or_conclusion="ACTION_REQUIRED",
        description_code="EXTERNAL_AUTHORIZATION_REQUIRED",
        fact_at=NOW + timedelta(minutes=5),
    )
    result = normalize_pr(
        pr_snapshot(checks=[check]),
        existing=entry(),
        events=[opened],
    )
    assert result.candidate_event.kind == "BLOCKED"
    assert result.candidate_event.reason == "EXTERNAL_AUTHORIZATION_REQUIRED"
    assert result.candidate_event.source_ref == "check-run:7"


def test_success_for_same_check_clears_only_active_blocker():
    opened = normalize_pr(pr_snapshot(), existing=entry()).candidate_event
    blocked_check = GitHubCheckSnapshot(
        check_ref="check-run:7",
        name="Deploy",
        state_or_conclusion="ACTION_REQUIRED",
        description_code="EXTERNAL_AUTHORIZATION_REQUIRED",
        fact_at=NOW + timedelta(minutes=5),
    )
    blocked = normalize_pr(
        pr_snapshot(checks=[blocked_check]),
        existing=entry(),
        events=[opened],
    ).candidate_event
    clear_check = GitHubCheckSnapshot(
        check_ref="check-run:7",
        name="Deploy",
        state_or_conclusion="success",
        description_code=None,
        fact_at=NOW + timedelta(minutes=6),
    )
    cleared = normalize_pr(
        pr_snapshot(checks=[clear_check]),
        existing=entry(),
        events=[opened, blocked],
    )
    assert cleared.candidate_event.kind == "UNBLOCKED"
    no_active = normalize_pr(
        pr_snapshot(checks=[clear_check]),
        existing=entry(),
        events=[opened],
    )
    assert no_active.status == "NO_CHANGE"


def test_event_ids_are_deterministic_and_one_candidate_max():
    opened1 = normalize_pr(pr_snapshot(), existing=entry()).candidate_event
    opened2 = normalize_pr(pr_snapshot(), existing=entry()).candidate_event
    assert opened1.event_id == opened2.event_id
    assert opened1.event_id.startswith("contrib-event-")


def test_embedded_observation_recreates_same_existing_issue_transition_without_network():
    existing = entry(claim="CLAIMED_OTHER")
    snapshot_result = normalize_issue(issue_snapshot(), existing=existing)
    embedded = normalize_embedded_observation(
        observation=snapshot_result.observation,
        entry=existing,
        events=[],
        projector=ContributionProjector(),
    )
    assert embedded.status == snapshot_result.status
    assert embedded.candidate_event == snapshot_result.candidate_event


def test_embedded_new_issue_recreates_same_proposed_entry():
    snapshot_result = normalize_issue(issue_snapshot())
    embedded = normalize_embedded_observation(
        observation=snapshot_result.observation,
        entry=None,
        events=[],
        projector=ContributionProjector(),
    )
    assert embedded.proposed_entry == snapshot_result.proposed_entry
