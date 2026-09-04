from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contributions.models import PublicContributionEntry
from app.contributions.observations import (
    PREVIEW_VERSION,
    ContributionImportRequest,
    ContributionImportResult,
    ContributionObservation,
    ContributionPreview,
    GitHubCheckSnapshot,
    GitHubContributionSelection,
    GitHubIssueSnapshot,
    GitHubPullRequestSnapshot,
    GitHubReviewSnapshot,
    observation_sha256,
)

NOW = datetime(2026, 9, 4, 6, 45, tzinfo=timezone.utc)
ISSUE = "https://github.com/trixocom/odoo-argentina-trx-ce/issues/1"
PR = "https://github.com/WesleyHanauer/moracarta/pull/42"


def issue_observation(**overrides):
    payload = dict(
        observation_id="obs-issue-1",
        source_type="PUBLIC_GITHUB",
        source_name="github",
        source_ref=ISSUE,
        kind="ISSUE_AVAILABLE",
        entry_id=None,
        repository_full_name="trixocom/odoo-argentina-trx-ce",
        public_title="Invalid language code: es_419 en l10n_ar_edi_base",
        fact_at=NOW,
        captured_at=NOW,
        task_ref=ISSUE,
        work_ref=None,
        actor_ref=None,
        reason_code=None,
        source_fact_identity="issue:1:open:unassigned:2026-09-04T06:45:00Z",
    )
    payload.update(overrides)
    return ContributionObservation(**payload)


def test_selection_rejects_unknown_field():
    with pytest.raises(ValidationError):
        GitHubContributionSelection(
            resource_kind="ISSUE",
            repository_full_name="owner/repo",
            number=1,
            source_url="https://github.com/owner/repo/issues/1",
            operator_github_login="juan",
            unexpected="forbidden",
        )


def test_selection_rejects_url_identity_mismatch():
    with pytest.raises(ValidationError):
        GitHubContributionSelection(
            resource_kind="ISSUE",
            repository_full_name="owner/repo",
            number=2,
            source_url="https://github.com/owner/repo/issues/1",
            operator_github_login="juan",
        )


def test_pull_request_selection_requires_entry_id():
    with pytest.raises(ValidationError):
        GitHubContributionSelection(
            resource_kind="PULL_REQUEST",
            repository_full_name="WesleyHanauer/moracarta",
            number=42,
            source_url=PR,
            operator_github_login="juanmanueltorres-creator",
        )


def test_issue_snapshot_requires_aware_timestamps():
    naive = datetime(2026, 9, 4, 6, 45)
    with pytest.raises(ValidationError):
        GitHubIssueSnapshot(
            repository_full_name="owner/repo",
            issue_number=1,
            issue_url="https://github.com/owner/repo/issues/1",
            title="Bug",
            state="OPEN",
            assignee_logins=[],
            author_login="alice",
            created_at=naive,
            updated_at=NOW,
            closed_at=None,
            captured_at=NOW,
        )


def test_pull_snapshot_normalizes_nested_times_and_forbids_raw_text():
    review = GitHubReviewSnapshot(
        review_ref="review-1",
        reviewer_login="bob",
        state="APPROVED",
        submitted_at=NOW,
    )
    check = GitHubCheckSnapshot(
        check_ref="check-1",
        name="Vercel",
        state_or_conclusion="ACTION_REQUIRED",
        description_code="EXTERNAL_AUTHORIZATION_REQUIRED",
        fact_at=NOW,
    )
    snapshot = GitHubPullRequestSnapshot(
        repository_full_name="WesleyHanauer/moracarta",
        pr_number=42,
        pr_url=PR,
        state="OPEN",
        merged=False,
        draft=False,
        author_login="juanmanueltorres-creator",
        created_at=NOW,
        updated_at=NOW,
        closed_at=None,
        merged_at=None,
        head_sha="abc123",
        reviews=[review],
        checks=[check],
        captured_at=NOW,
    )
    assert snapshot.reviews[0].submitted_at.tzinfo is not None
    with pytest.raises(ValidationError):
        GitHubCheckSnapshot(
            check_ref="check-2",
            name="CI",
            state_or_conclusion="failure",
            description_code=None,
            fact_at=NOW,
            check_log="secret",
        )


def test_issue_observation_requires_task_ref_and_title():
    with pytest.raises(ValidationError):
        issue_observation(task_ref=None)
    with pytest.raises(ValidationError):
        issue_observation(public_title=None)


def test_pr_observation_requires_work_ref():
    with pytest.raises(ValidationError):
        issue_observation(
            kind="PR_OPENED",
            source_ref=PR,
            task_ref=None,
            public_title=None,
            entry_id="contrib-1",
            repository_full_name="WesleyHanauer/moracarta",
            work_ref=None,
            source_fact_identity="pr:42:open",
        )


def test_external_blocker_requires_allowlisted_reason_code():
    with pytest.raises(ValidationError):
        issue_observation(
            kind="EXTERNAL_BLOCKER",
            source_ref=PR,
            task_ref=None,
            public_title=None,
            entry_id="contrib-1",
            repository_full_name="WesleyHanauer/moracarta",
            work_ref=PR,
            reason_code=None,
            source_fact_identity="check:1",
        )
    blocker = issue_observation(
        kind="EXTERNAL_BLOCKER",
        source_ref=PR,
        task_ref=None,
        public_title=None,
        entry_id="contrib-1",
        repository_full_name="WesleyHanauer/moracarta",
        work_ref=PR,
        reason_code="EXTERNAL_AUTHORIZATION_REQUIRED",
        source_fact_identity="check:1",
    )
    assert blocker.reason_code == "EXTERNAL_AUTHORIZATION_REQUIRED"


def test_preview_privacy_and_empty_external_actions():
    observation = issue_observation()
    preview = ContributionPreview(
        preview_version=PREVIEW_VERSION,
        status="NO_CHANGE",
        observation=observation,
        observation_sha256=observation_sha256(observation),
        preview_sha256="a" * 64,
        entry_id="contrib-example",
        source_ref=ISSUE,
        proposed_entry=None,
        candidate_event=None,
        context_before=None,
        context_after=None,
        errors=[],
        external_actions=[],
    )
    payload = preview.model_dump_json().lower()
    for forbidden in [
        "bearer ",
        "github_token",
        "authorization_header",
        "raw_body",
        "review_text",
        "check_log",
        "salary",
        "employment_interest",
    ]:
        assert forbidden not in payload
    with pytest.raises(ValidationError):
        ContributionPreview.model_validate(
            {**preview.model_dump(mode="json"), "external_actions": ["comment"]}
        )


def test_importable_preview_requires_exactly_one_proposal():
    observation = issue_observation(entry_id="contrib-example")
    entry = PublicContributionEntry(
        entry_id="contrib-example",
        repository_full_name="trixocom/odoo-argentina-trx-ce",
        repository_url="https://github.com/trixocom/odoo-argentina-trx-ce",
        origin="PUBLIC_ISSUE",
        need_basis="OBSERVED",
        need_statement="Bug",
        evidence_refs=[ISSUE],
        task_ref=ISSUE,
        bounded_task="Bug",
        task_claim_state="AVAILABLE",
        discovered_at=NOW,
    )
    valid = dict(
        preview_version=PREVIEW_VERSION,
        status="IMPORTABLE",
        observation=observation,
        observation_sha256=observation_sha256(observation),
        preview_sha256="b" * 64,
        entry_id="contrib-example",
        source_ref=ISSUE,
        proposed_entry=entry,
        candidate_event=None,
        context_before=None,
        context_after=None,
        errors=[],
        external_actions=[],
    )
    assert ContributionPreview(**valid).proposed_entry is not None
    with pytest.raises(ValidationError):
        ContributionPreview(**{**valid, "proposed_entry": None})


def test_blocked_preview_requires_error_and_no_proposal():
    observation = issue_observation(entry_id="contrib-example")
    with pytest.raises(ValidationError):
        ContributionPreview(
            preview_version=PREVIEW_VERSION,
            status="BLOCKED",
            observation=observation,
            observation_sha256=observation_sha256(observation),
            preview_sha256="c" * 64,
            entry_id="contrib-example",
            source_ref=ISSUE,
            proposed_entry=None,
            candidate_event=None,
            context_before=None,
            context_after=None,
            errors=[],
            external_actions=[],
        )


def test_import_request_requires_importable_preview_and_confirmation_after_capture():
    observation = issue_observation()
    no_change = ContributionPreview(
        preview_version=PREVIEW_VERSION,
        status="NO_CHANGE",
        observation=observation,
        observation_sha256=observation_sha256(observation),
        preview_sha256="d" * 64,
        entry_id="contrib-example",
        source_ref=ISSUE,
        proposed_entry=None,
        candidate_event=None,
        context_before=None,
        context_after=None,
        errors=[],
        external_actions=[],
    )
    with pytest.raises(ValidationError):
        ContributionImportRequest(
            preview=no_change,
            confirmed_by="juan",
            confirmed_at=NOW,
        )


def test_import_result_shape_requires_receipt_for_success():
    with pytest.raises(ValidationError):
        ContributionImportResult(status="IMPORTED", receipt=None, errors=[])
