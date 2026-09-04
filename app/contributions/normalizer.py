from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Literal

from app.contributions.models import ContributionEvent, PublicContributionEntry
from app.contributions.observations import (
    ContributionObservation,
    GitHubCheckSnapshot,
    GitHubContributionSelection,
    GitHubIssueSnapshot,
    GitHubPullRequestSnapshot,
)
from app.contributions.projector import ContributionProjector


@dataclass(frozen=True)
class ContributionNormalization:
    observation: ContributionObservation
    status: Literal["IMPORTABLE", "NO_CHANGE", "BLOCKED"]
    proposed_entry: PublicContributionEntry | None = None
    candidate_event: ContributionEvent | None = None
    errors: tuple[str, ...] = ()


_FACT_KIND_ORDER = {
    "CHANGES_REQUESTED": 0,
    "REVIEW_RECEIVED": 1,
    "EXTERNAL_BLOCKER": 2,
    "BLOCKER_CLEARED": 3,
    "PR_MERGED": 4,
    "PR_CLOSED": 5,
}
_EVENT_KIND_RANK = {
    "TASK_RELEASED": 10,
    "TASK_CLAIMED_SELF": 11,
    "TASK_CLAIMED_OTHER": 12,
    "TASK_CLOSED": 13,
    "PR_OPENED": 20,
    "CHANGES_REQUESTED": 30,
    "REVIEW_RECEIVED": 31,
    "BLOCKED": 32,
    "UNBLOCKED": 33,
    "PR_MERGED": 34,
    "PR_CLOSED": 35,
}
_ISSUE_DESIRED_STATE = {
    "ISSUE_AVAILABLE": "AVAILABLE",
    "ISSUE_CLAIMED_SELF": "CLAIMED_SELF",
    "ISSUE_CLAIMED_OTHER": "CLAIMED_OTHER",
    "ISSUE_CLOSED": "CLOSED",
}
_OBSERVATION_TO_EVENT = {
    "ISSUE_AVAILABLE": "TASK_RELEASED",
    "ISSUE_CLAIMED_SELF": "TASK_CLAIMED_SELF",
    "ISSUE_CLAIMED_OTHER": "TASK_CLAIMED_OTHER",
    "ISSUE_CLOSED": "TASK_CLOSED",
    "PR_OPENED": "PR_OPENED",
    "REVIEW_RECEIVED": "REVIEW_RECEIVED",
    "CHANGES_REQUESTED": "CHANGES_REQUESTED",
    "PR_MERGED": "PR_MERGED",
    "PR_CLOSED": "PR_CLOSED",
    "EXTERNAL_BLOCKER": "BLOCKED",
    "BLOCKER_CLEARED": "UNBLOCKED",
}


def deterministic_issue_entry_id(repository_full_name: str, issue_number: int) -> str:
    identity = f"PUBLIC_GITHUB|{repository_full_name}|ISSUE|{issue_number}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"contrib-{digest}"


def _sanitize_title(value: str) -> str:
    value = "".join(char if char.isprintable() else " " for char in value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:500]


def _observation_id(
    *,
    repository_full_name: str,
    resource_kind: str,
    resource_number: int,
    fact_kind: str,
    source_fact_identity: str,
) -> str:
    identity = "|".join(
        [
            "PUBLIC_GITHUB",
            repository_full_name,
            resource_kind,
            str(resource_number),
            fact_kind,
            source_fact_identity,
        ]
    )
    return "contrib-obs-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _event_id(observation: ContributionObservation, event_kind: str) -> str:
    digest = hashlib.sha256(observation.observation_id.encode("utf-8")).hexdigest()
    rank = _EVENT_KIND_RANK[event_kind]
    return f"contrib-event-{rank:02d}-{digest}"


def _event_for_observation(observation: ContributionObservation) -> ContributionEvent:
    event_kind = _OBSERVATION_TO_EVENT[observation.kind]
    return ContributionEvent(
        event_id=_event_id(observation, event_kind),
        entry_id=observation.entry_id or "missing-entry",
        kind=event_kind,
        source_type="PUBLIC_GITHUB",
        source_ref=observation.source_ref,
        observed_at=observation.fact_at,
        actor_ref=observation.actor_ref,
        task_ref=observation.task_ref if event_kind.startswith("TASK_") else None,
        work_ref=observation.work_ref if event_kind in {
            "PR_OPENED",
            "REVIEW_RECEIVED",
            "CHANGES_REQUESTED",
            "PR_MERGED",
            "PR_CLOSED",
        } else observation.work_ref if event_kind in {"BLOCKED", "UNBLOCKED"} else None,
        reason=observation.reason_code if event_kind == "BLOCKED" else None,
    )


def _issue_kind(snapshot: GitHubIssueSnapshot, operator_login: str) -> tuple[str, str | None]:
    if snapshot.state == "CLOSED":
        return "ISSUE_CLOSED", None
    assignees = sorted({login.casefold(): login for login in snapshot.assignee_logins}.items())
    if not assignees:
        return "ISSUE_AVAILABLE", None
    operator_cf = operator_login.casefold()
    for folded, original in assignees:
        if folded == operator_cf:
            return "ISSUE_CLAIMED_SELF", original
    return "ISSUE_CLAIMED_OTHER", assignees[0][1]


def _issue_observation(
    *,
    selection: GitHubContributionSelection,
    snapshot: GitHubIssueSnapshot,
) -> ContributionObservation:
    kind, actor_ref = _issue_kind(snapshot, selection.operator_github_login)
    title = _sanitize_title(snapshot.title)
    if kind == "ISSUE_CLOSED":
        fact_at = snapshot.closed_at or snapshot.updated_at
        source_fact_identity = f"issue:{snapshot.issue_number}:closed:{fact_at.isoformat()}"
    else:
        assignees = ",".join(sorted(login.casefold() for login in snapshot.assignee_logins))
        fact_at = snapshot.updated_at
        source_fact_identity = (
            f"issue:{snapshot.issue_number}:{snapshot.state.casefold()}:"
            f"{assignees}:{snapshot.updated_at.isoformat()}"
        )
    entry_id = selection.entry_id or deterministic_issue_entry_id(
        snapshot.repository_full_name,
        snapshot.issue_number,
    )
    return ContributionObservation(
        observation_id=_observation_id(
            repository_full_name=snapshot.repository_full_name,
            resource_kind="ISSUE",
            resource_number=snapshot.issue_number,
            fact_kind=kind,
            source_fact_identity=source_fact_identity,
        ),
        source_ref=snapshot.issue_url,
        kind=kind,
        entry_id=entry_id,
        repository_full_name=snapshot.repository_full_name,
        public_title=title,
        fact_at=fact_at,
        captured_at=snapshot.captured_at,
        task_ref=snapshot.issue_url,
        actor_ref=actor_ref,
        source_fact_identity=source_fact_identity,
    )


def _new_issue_entry(observation: ContributionObservation) -> PublicContributionEntry:
    if observation.kind == "ISSUE_CLOSED":
        raise ValueError("closed issue cannot create entry")
    claim_state = _ISSUE_DESIRED_STATE[observation.kind]
    repository_url = f"https://github.com/{observation.repository_full_name}"
    return PublicContributionEntry(
        entry_id=observation.entry_id or "missing-entry",
        repository_full_name=observation.repository_full_name,
        repository_url=repository_url,
        origin="PUBLIC_ISSUE",
        need_basis="OBSERVED",
        need_statement=observation.public_title or "Public issue",
        evidence_refs=[observation.task_ref or observation.source_ref],
        task_ref=observation.task_ref,
        bounded_task=observation.public_title,
        task_claim_state=claim_state,
        expected_effort="UNKNOWN",
        risk_level="UNKNOWN",
        discovered_at=observation.captured_at,
    )


def _blocked(observation: ContributionObservation, error: str) -> ContributionNormalization:
    return ContributionNormalization(
        observation=observation,
        status="BLOCKED",
        errors=(error,),
    )


def _validate_candidate(
    *,
    observation: ContributionObservation,
    entry: PublicContributionEntry,
    events: list[ContributionEvent],
    projector: ContributionProjector,
) -> ContributionNormalization:
    candidate = _event_for_observation(observation)
    existing = next((item for item in events if item.event_id == candidate.event_id), None)
    if existing is not None:
        if existing != candidate:
            return _blocked(observation, "observation_identity_conflict")
        return ContributionNormalization(observation=observation, status="NO_CHANGE")

    ordered = sorted(events, key=lambda item: (item.observed_at, item.event_id))
    if ordered and (candidate.observed_at, candidate.event_id) <= (
        ordered[-1].observed_at,
        ordered[-1].event_id,
    ):
        return _blocked(observation, "invalid_contribution_transition")
    try:
        projector.project(entry=entry, events=events + [candidate])
    except ValueError:
        return _blocked(observation, "invalid_contribution_transition")
    return ContributionNormalization(
        observation=observation,
        status="IMPORTABLE",
        candidate_event=candidate,
    )


def _normalize_issue_observation(
    *,
    observation: ContributionObservation,
    entry: PublicContributionEntry | None,
    events: list[ContributionEvent],
    projector: ContributionProjector,
) -> ContributionNormalization:
    if entry is None:
        if observation.kind == "ISSUE_CLOSED":
            return _blocked(observation, "closed_issue_requires_existing_entry")
        proposed = _new_issue_entry(observation)
        return ContributionNormalization(
            observation=observation,
            status="IMPORTABLE",
            proposed_entry=proposed,
        )
    if entry.repository_full_name != observation.repository_full_name:
        return _blocked(observation, "repository_mismatch")
    if entry.task_ref != observation.task_ref:
        return _blocked(observation, "task_ref_mismatch")
    try:
        context = projector.project(entry=entry, events=events)
    except ValueError:
        return _blocked(observation, "invalid_contribution_transition")
    desired = _ISSUE_DESIRED_STATE[observation.kind]
    if context.task_claim_state == desired:
        return ContributionNormalization(observation=observation, status="NO_CHANGE")
    return _validate_candidate(
        observation=observation,
        entry=entry,
        events=events,
        projector=projector,
    )


def _pr_observation(
    *,
    snapshot: GitHubPullRequestSnapshot,
    entry_id: str | None,
    kind: str,
    fact_at,
    source_ref: str,
    source_fact_identity: str,
    actor_ref: str | None = None,
    reason_code: str | None = None,
) -> ContributionObservation:
    return ContributionObservation(
        observation_id=_observation_id(
            repository_full_name=snapshot.repository_full_name,
            resource_kind="PULL_REQUEST",
            resource_number=snapshot.pr_number,
            fact_kind=kind,
            source_fact_identity=source_fact_identity,
        ),
        source_ref=source_ref,
        kind=kind,
        entry_id=entry_id,
        repository_full_name=snapshot.repository_full_name,
        public_title=None,
        fact_at=fact_at,
        captured_at=snapshot.captured_at,
        work_ref=snapshot.pr_url,
        actor_ref=actor_ref,
        reason_code=reason_code,
        source_fact_identity=source_fact_identity,
    )


def _pr_open_observation(snapshot: GitHubPullRequestSnapshot, entry_id: str | None) -> ContributionObservation:
    identity = f"pr:{snapshot.pr_number}:opened:{snapshot.created_at.isoformat()}"
    return _pr_observation(
        snapshot=snapshot,
        entry_id=entry_id,
        kind="PR_OPENED",
        fact_at=snapshot.created_at,
        source_ref=snapshot.pr_url,
        source_fact_identity=identity,
        actor_ref=snapshot.author_login,
    )


def _active_blocker_source(events: list[ContributionEvent]) -> str | None:
    active: str | None = None
    for event in sorted(events, key=lambda item: (item.observed_at, item.event_id)):
        if event.kind == "BLOCKED":
            active = event.source_ref
        elif event.kind == "UNBLOCKED":
            active = None
    return active


def _pr_fact_observations(
    *,
    snapshot: GitHubPullRequestSnapshot,
    entry_id: str,
    events: list[ContributionEvent],
) -> list[ContributionObservation]:
    observations: list[ContributionObservation] = []
    for review in snapshot.reviews:
        if review.state == "DISMISSED":
            continue
        kind = "CHANGES_REQUESTED" if review.state == "CHANGES_REQUESTED" else "REVIEW_RECEIVED"
        identity = review.review_ref
        observations.append(
            _pr_observation(
                snapshot=snapshot,
                entry_id=entry_id,
                kind=kind,
                fact_at=review.submitted_at,
                source_ref=review.review_ref,
                source_fact_identity=identity,
                actor_ref=review.reviewer_login,
            )
        )

    active_source = _active_blocker_source(events)
    for check in snapshot.checks:
        if check.description_code == "EXTERNAL_AUTHORIZATION_REQUIRED":
            identity = f"check:{check.check_ref}:blocked:{check.fact_at.isoformat()}"
            observations.append(
                _pr_observation(
                    snapshot=snapshot,
                    entry_id=entry_id,
                    kind="EXTERNAL_BLOCKER",
                    fact_at=check.fact_at,
                    source_ref=check.check_ref,
                    source_fact_identity=identity,
                    reason_code="EXTERNAL_AUTHORIZATION_REQUIRED",
                )
            )
        elif (
            active_source == check.check_ref
            and check.state_or_conclusion.casefold() == "success"
        ):
            identity = f"check:{check.check_ref}:cleared:{check.fact_at.isoformat()}"
            observations.append(
                _pr_observation(
                    snapshot=snapshot,
                    entry_id=entry_id,
                    kind="BLOCKER_CLEARED",
                    fact_at=check.fact_at,
                    source_ref=check.check_ref,
                    source_fact_identity=identity,
                )
            )

    if snapshot.merged and snapshot.merged_at is not None:
        identity = f"pr:{snapshot.pr_number}:merged:{snapshot.merged_at.isoformat()}"
        observations.append(
            _pr_observation(
                snapshot=snapshot,
                entry_id=entry_id,
                kind="PR_MERGED",
                fact_at=snapshot.merged_at,
                source_ref=snapshot.pr_url,
                source_fact_identity=identity,
            )
        )
    elif snapshot.state == "CLOSED" and snapshot.closed_at is not None:
        identity = f"pr:{snapshot.pr_number}:closed:{snapshot.closed_at.isoformat()}"
        observations.append(
            _pr_observation(
                snapshot=snapshot,
                entry_id=entry_id,
                kind="PR_CLOSED",
                fact_at=snapshot.closed_at,
                source_ref=snapshot.pr_url,
                source_fact_identity=identity,
            )
        )
    return observations


def _normalize_pr_snapshot(
    *,
    selection: GitHubContributionSelection,
    snapshot: GitHubPullRequestSnapshot,
    entry: PublicContributionEntry | None,
    events: list[ContributionEvent],
    projector: ContributionProjector,
) -> ContributionNormalization:
    open_observation = _pr_open_observation(snapshot, selection.entry_id)
    if selection.entry_id is None:
        return _blocked(open_observation, "pr_requires_entry_id")
    if entry is None or entry.entry_id != selection.entry_id:
        return _blocked(open_observation, "unknown_contribution_entry")
    if entry.repository_full_name != snapshot.repository_full_name:
        return _blocked(open_observation, "repository_mismatch")

    has_open = any(
        event.kind == "PR_OPENED" and event.work_ref == snapshot.pr_url
        for event in events
    )
    if not has_open:
        return _validate_candidate(
            observation=open_observation,
            entry=entry,
            events=events,
            projector=projector,
        )

    fact_observations = _pr_fact_observations(
        snapshot=snapshot,
        entry_id=selection.entry_id,
        events=events,
    )
    fact_observations.sort(
        key=lambda obs: (
            obs.fact_at,
            _FACT_KIND_ORDER[obs.kind],
            obs.source_fact_identity,
        )
    )
    event_ids = {event.event_id for event in events}
    invalid: ContributionNormalization | None = None
    for observation in fact_observations:
        candidate = _event_for_observation(observation)
        if candidate.event_id in event_ids:
            continue
        result = _validate_candidate(
            observation=observation,
            entry=entry,
            events=events,
            projector=projector,
        )
        if result.status == "IMPORTABLE":
            return result
        if result.status == "BLOCKED" and invalid is None:
            invalid = result
    if invalid is not None:
        return invalid
    latest = max(
        [open_observation, *fact_observations],
        key=lambda obs: (
            obs.fact_at,
            _FACT_KIND_ORDER.get(obs.kind, -1),
            obs.source_fact_identity,
        ),
    )
    return ContributionNormalization(observation=latest, status="NO_CHANGE")


def normalize_embedded_observation(
    *,
    observation: ContributionObservation,
    entry: PublicContributionEntry | None,
    events: list[ContributionEvent],
    projector: ContributionProjector,
) -> ContributionNormalization:
    if observation.kind.startswith("ISSUE_"):
        return _normalize_issue_observation(
            observation=observation,
            entry=entry,
            events=events,
            projector=projector,
        )
    if observation.entry_id is None:
        return _blocked(observation, "pr_requires_entry_id")
    if entry is None or entry.entry_id != observation.entry_id:
        return _blocked(observation, "unknown_contribution_entry")
    if entry.repository_full_name != observation.repository_full_name:
        return _blocked(observation, "repository_mismatch")
    return _validate_candidate(
        observation=observation,
        entry=entry,
        events=events,
        projector=projector,
    )


def normalize_snapshot(
    *,
    selection: GitHubContributionSelection,
    snapshot: GitHubIssueSnapshot | GitHubPullRequestSnapshot,
    entry: PublicContributionEntry | None,
    events: list[ContributionEvent],
    projector: ContributionProjector,
) -> ContributionNormalization:
    if isinstance(snapshot, GitHubIssueSnapshot):
        observation = _issue_observation(selection=selection, snapshot=snapshot)
        return _normalize_issue_observation(
            observation=observation,
            entry=entry,
            events=events,
            projector=projector,
        )
    if isinstance(snapshot, GitHubPullRequestSnapshot):
        return _normalize_pr_snapshot(
            selection=selection,
            snapshot=snapshot,
            entry=entry,
            events=events,
            projector=projector,
        )
    raise TypeError("unsupported GitHub contribution snapshot")
