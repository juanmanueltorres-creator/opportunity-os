from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import sqlite3

from app.contributions.bridge import ContributionObservationBridge
from app.contributions.models import ContributionEvent, PublicContributionEntry
from app.contributions.observations import (
    ContributionImportReceipt,
    ContributionImportRequest,
    GitHubContributionSelection,
    GitHubIssueSnapshot,
)
from app.contributions.projector import ContributionProjector
from app.contributions.repository import SQLiteContributionRepository

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
ISSUE = "https://github.com/WesleyHanauer/moracarta/issues/25"
REPO = "WesleyHanauer/moracarta"


class FakeProvider:
    def __init__(self, snapshot: GitHubIssueSnapshot) -> None:
        self.snapshot = snapshot
        self.calls = 0
        self.raise_on_fetch = False

    def fetch(self, selection, *, captured_at):
        self.calls += 1
        if self.raise_on_fetch:
            raise AssertionError("provider called during import")
        return self.snapshot.model_copy(update={"captured_at": captured_at})


class SequenceClock:
    def __init__(self, *values: datetime) -> None:
        self.values = list(values)

    def __call__(self) -> datetime:
        if len(self.values) == 1:
            return self.values[0]
        return self.values.pop(0)


def selection() -> GitHubContributionSelection:
    return GitHubContributionSelection(
        resource_kind="ISSUE",
        repository_full_name=REPO,
        number=25,
        source_url=ISSUE,
        operator_github_login="juanmanueltorres-creator",
    )


def snapshot(*, assignees: list[str] | None = None, updated_at: datetime | None = None):
    return GitHubIssueSnapshot(
        repository_full_name=REPO,
        issue_number=25,
        issue_url=ISSUE,
        title="tests: setup command",
        state="OPEN",
        assignee_logins=list(assignees or []),
        author_login="WesleyHanauer",
        created_at=NOW - timedelta(days=2),
        updated_at=updated_at or NOW,
        closed_at=None,
        captured_at=NOW,
    )


def claimed_self_entry() -> PublicContributionEntry:
    return PublicContributionEntry(
        entry_id="contrib-moracarta-25",
        repository_full_name=REPO,
        repository_url=f"https://github.com/{REPO}",
        origin="PUBLIC_ISSUE",
        need_basis="OBSERVED",
        need_statement="tests: setup command",
        evidence_refs=[ISSUE],
        task_ref=ISSUE,
        bounded_task="tests: setup command",
        task_claim_state="CLAIMED_SELF",
        expected_effort="UNKNOWN",
        risk_level="UNKNOWN",
        discovered_at=NOW - timedelta(days=1),
    )


def repo_receipt(*, observation_id: str, entry_id: str, event_id: str | None = None, processed_at: datetime = NOW):
    digest = hashlib.sha256(observation_id.encode("utf-8")).hexdigest()
    return ContributionImportReceipt(
        receipt_id=f"seed-{digest}",
        observation_id=observation_id,
        observation_sha256="a" * 64,
        preview_sha256="b" * 64,
        entry_id=entry_id,
        contribution_event_id=event_id,
        source_ref=ISSUE,
        confirmed_by="seed",
        confirmed_at=processed_at,
        processed_at=processed_at,
        status="IMPORTED",
    )


def seed_entry(repo: SQLiteContributionRepository, entry: PublicContributionEntry) -> None:
    repo.initialize()
    repo.insert_entry_with_receipt(
        entry,
        repo_receipt(observation_id="seed-entry", entry_id=entry.entry_id),
    )


def bridge_for(tmp_path, *, snap, clock=None):
    repo = SQLiteContributionRepository(tmp_path / "state" / "contributions.local.sqlite3")
    provider = FakeProvider(snap)
    bridge = ContributionObservationBridge(
        provider=provider,
        repository=repo,
        projector=ContributionProjector(),
        clock=clock or SequenceClock(NOW),
    )
    return bridge, provider, repo


def test_preview_calls_provider_once_and_does_not_create_missing_db(tmp_path):
    bridge, provider, repo = bridge_for(tmp_path, snap=snapshot())
    preview = bridge.preview(selection())
    assert provider.calls == 1
    assert preview.status == "IMPORTABLE"
    assert not repo.path.exists()
    assert not repo.path.parent.exists()


def test_new_issue_preview_contains_entry_and_projected_context(tmp_path):
    bridge, _, _ = bridge_for(tmp_path, snap=snapshot())
    preview = bridge.preview(selection())
    assert preview.proposed_entry is not None
    assert preview.candidate_event is None
    assert preview.context_before is None
    assert preview.context_after is not None
    assert preview.context_after.stage == "TASK_READY"
    assert preview.external_actions == []


def test_existing_transition_preview_contains_before_and_after(tmp_path):
    bridge, _, repo = bridge_for(tmp_path, snap=snapshot(updated_at=NOW + timedelta(minutes=10)))
    entry = claimed_self_entry()
    seed_entry(repo, entry)
    selected = selection().model_copy(update={"entry_id": entry.entry_id})
    preview = bridge.preview(selected)
    assert preview.status == "IMPORTABLE"
    assert preview.candidate_event is not None
    assert preview.candidate_event.kind == "TASK_RELEASED"
    assert preview.context_before.task_claim_state == "CLAIMED_SELF"
    assert preview.context_after.task_claim_state == "AVAILABLE"


def test_unchanged_existing_state_returns_no_change(tmp_path):
    bridge, _, repo = bridge_for(tmp_path, snap=snapshot(assignees=["juanmanueltorres-creator"]))
    entry = claimed_self_entry()
    seed_entry(repo, entry)
    preview = bridge.preview(selection().model_copy(update={"entry_id": entry.entry_id}))
    assert preview.status == "NO_CHANGE"
    assert preview.proposed_entry is None
    assert preview.candidate_event is None


def test_same_observation_and_state_has_same_preview_hash(tmp_path):
    bridge, _, _ = bridge_for(tmp_path, snap=snapshot())
    first = bridge.preview(selection())
    second = bridge.preview(selection())
    assert first.preview_sha256 == second.preview_sha256
    assert first.observation_sha256 == second.observation_sha256


def test_new_entry_import_is_atomic_and_makes_no_provider_call(tmp_path):
    bridge, provider, repo = bridge_for(
        tmp_path,
        snap=snapshot(),
        clock=SequenceClock(NOW, NOW + timedelta(minutes=2)),
    )
    preview = bridge.preview(selection())
    repo.initialize()
    provider.raise_on_fetch = True
    result = bridge.import_preview(
        ContributionImportRequest(
            preview=preview,
            confirmed_by="juan",
            confirmed_at=NOW + timedelta(minutes=1),
        )
    )
    assert provider.calls == 1
    assert result.status == "IMPORTED"
    assert repo.get_entry(preview.entry_id) == preview.proposed_entry
    assert repo.get_receipt_for_observation(preview.observation.observation_id) is not None


def test_event_import_commits_event_and_receipt_atomically(tmp_path):
    bridge, _, repo = bridge_for(
        tmp_path,
        snap=snapshot(updated_at=NOW + timedelta(minutes=10)),
        clock=SequenceClock(NOW, NOW + timedelta(minutes=12)),
    )
    entry = claimed_self_entry()
    seed_entry(repo, entry)
    preview = bridge.preview(selection().model_copy(update={"entry_id": entry.entry_id}))
    result = bridge.import_preview(
        ContributionImportRequest(
            preview=preview,
            confirmed_by="juan",
            confirmed_at=NOW + timedelta(minutes=11),
        )
    )
    assert result.status == "IMPORTED"
    assert repo.get_event(preview.candidate_event.event_id) == preview.candidate_event
    assert repo.get_receipt_for_observation(preview.observation.observation_id) is not None


def test_exact_repeated_import_returns_already_imported(tmp_path):
    bridge, _, repo = bridge_for(
        tmp_path,
        snap=snapshot(),
        clock=SequenceClock(NOW, NOW + timedelta(minutes=2), NOW + timedelta(minutes=3)),
    )
    preview = bridge.preview(selection())
    repo.initialize()
    request = ContributionImportRequest(
        preview=preview,
        confirmed_by="juan",
        confirmed_at=NOW + timedelta(minutes=1),
    )
    assert bridge.import_preview(request).status == "IMPORTED"
    replay = bridge.import_preview(request)
    assert replay.status == "ALREADY_IMPORTED"
    assert replay.receipt is not None
    assert replay.receipt.status == "ALREADY_IMPORTED"


def test_changed_local_history_after_preview_blocks_as_stale(tmp_path):
    bridge, _, repo = bridge_for(
        tmp_path,
        snap=snapshot(updated_at=NOW + timedelta(minutes=10)),
        clock=SequenceClock(NOW, NOW + timedelta(minutes=12)),
    )
    entry = claimed_self_entry()
    seed_entry(repo, entry)
    selected = selection().model_copy(update={"entry_id": entry.entry_id})
    preview = bridge.preview(selected)
    local_event = ContributionEvent(
        event_id="local-work-proposed",
        entry_id=entry.entry_id,
        kind="WORK_PROPOSED",
        source_type="MANUAL",
        source_ref="manual:work-proposed",
        observed_at=NOW + timedelta(minutes=5),
    )
    repo.append_event_with_receipt(
        local_event,
        repo_receipt(
            observation_id="seed-local-history",
            entry_id=entry.entry_id,
            event_id=local_event.event_id,
            processed_at=NOW + timedelta(minutes=5),
        ),
        ContributionProjector(),
    )
    result = bridge.import_preview(
        ContributionImportRequest(
            preview=preview,
            confirmed_by="juan",
            confirmed_at=NOW + timedelta(minutes=11),
        )
    )
    assert result.status == "BLOCKED_STALE_PREVIEW"
    assert result.errors == ["stale_preview"]


def test_same_observation_id_with_different_hash_is_conflict(tmp_path):
    bridge, _, repo = bridge_for(
        tmp_path,
        snap=snapshot(),
        clock=SequenceClock(NOW, NOW + timedelta(minutes=2)),
    )
    preview = bridge.preview(selection())
    repo.initialize()
    conflicting = repo_receipt(observation_id=preview.observation.observation_id, entry_id=preview.entry_id)
    conflicting = conflicting.model_copy(update={"observation_sha256": "f" * 64})
    with sqlite3.connect(repo.path) as conn:
        conn.execute(
            "INSERT INTO contribution_import_receipts (receipt_id, observation_id, entry_id, payload_json, processed_at) VALUES (?, ?, ?, ?, ?)",
            (
                conflicting.receipt_id,
                conflicting.observation_id,
                conflicting.entry_id,
                conflicting.model_dump_json(),
                conflicting.processed_at.isoformat(),
            ),
        )
    result = bridge.import_preview(
        ContributionImportRequest(
            preview=preview,
            confirmed_by="juan",
            confirmed_at=NOW + timedelta(minutes=1),
        )
    )
    assert result.status == "CONFLICT"
    assert result.errors == ["observation_identity_conflict"]


def test_embedded_domain_revalidation_failure_is_blocked_domain(tmp_path):
    bridge, _, repo = bridge_for(
        tmp_path,
        snap=snapshot(updated_at=NOW + timedelta(minutes=10)),
        clock=SequenceClock(NOW, NOW + timedelta(minutes=22)),
    )
    entry = claimed_self_entry()
    seed_entry(repo, entry)
    preview = bridge.preview(selection().model_copy(update={"entry_id": entry.entry_id}))
    late_event = ContributionEvent(
        event_id="late-work-proposed",
        entry_id=entry.entry_id,
        kind="WORK_PROPOSED",
        source_type="MANUAL",
        source_ref="manual:late",
        observed_at=NOW + timedelta(minutes=20),
    )
    repo.append_event_with_receipt(
        late_event,
        repo_receipt(
            observation_id="seed-late-history",
            entry_id=entry.entry_id,
            event_id=late_event.event_id,
            processed_at=NOW + timedelta(minutes=20),
        ),
        ContributionProjector(),
    )
    result = bridge.import_preview(
        ContributionImportRequest(
            preview=preview,
            confirmed_by="juan",
            confirmed_at=NOW + timedelta(minutes=21),
        )
    )
    assert result.status == "BLOCKED_DOMAIN"
    assert result.errors == ["invalid_contribution_transition"]


def test_receipt_uses_injected_processed_at_and_deterministic_id(tmp_path):
    processed = NOW + timedelta(minutes=2)
    bridge, _, repo = bridge_for(tmp_path, snap=snapshot(), clock=SequenceClock(NOW, processed))
    preview = bridge.preview(selection())
    repo.initialize()
    result = bridge.import_preview(
        ContributionImportRequest(
            preview=preview,
            confirmed_by="juan",
            confirmed_at=NOW + timedelta(minutes=1),
        )
    )
    assert result.receipt is not None
    assert result.receipt.processed_at == processed
    digest = hashlib.sha256(preview.observation.observation_id.encode("utf-8")).hexdigest()
    assert result.receipt.receipt_id == f"contrib-receipt-{digest}"
