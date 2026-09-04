from __future__ import annotations

from app.contributions.models import (
    ContributionContext,
    ContributionEvent,
    PublicContributionEntry,
)


class ContributionProjectionError(ValueError):
    pass


class ContributionProjector:
    def project(
        self,
        *,
        entry: PublicContributionEntry,
        events: list[ContributionEvent],
    ) -> ContributionContext:
        ordered = sorted(events, key=lambda event: (event.observed_at, event.event_id))

        stage = "TASK_READY" if entry.task_claim_state == "AVAILABLE" else "DISCOVERED"
        task_claim_state = entry.task_claim_state
        blocking_reason = None
        active_work_ref = None
        last_event_kind = None
        last_observed_at = None
        pause_restore_stage = None
        known_pr_ref = None

        for event in ordered:
            if event.entry_id != entry.entry_id:
                raise ContributionProjectionError(
                    "event entry_id does not match contribution entry"
                )

            kind = event.kind

            if kind == "DISCOVERED":
                pass
            elif kind == "OUTREACH_SENT":
                stage = "CONTACTED"
            elif kind in {
                "MAINTAINER_REPLIED",
                "COLLABORATION_WELCOMED",
                "WORK_PROPOSED",
            }:
                stage = "ENGAGED"
            elif kind == "TASK_SELECTED":
                stage = "TASK_READY"
            elif kind == "TASK_CLAIMED_SELF":
                stage = "TASK_READY"
                task_claim_state = "CLAIMED_SELF"
            elif kind == "TASK_CLAIMED_OTHER":
                task_claim_state = "CLAIMED_OTHER"
            elif kind == "TASK_RELEASED":
                stage = "TASK_READY"
                task_claim_state = "AVAILABLE"
            elif kind == "WORK_STARTED":
                stage = "IN_PROGRESS"
            elif kind == "PR_OPENED":
                known_pr_ref = event.work_ref
                active_work_ref = event.work_ref
                stage = "IN_REVIEW"
            elif kind in {"REVIEW_RECEIVED", "CHANGES_REQUESTED"}:
                self._require_known_pr(event, known_pr_ref)
                stage = "IN_REVIEW"
            elif kind == "PR_MERGED":
                self._require_known_pr(event, known_pr_ref)
                stage = "COMPLETED"
            elif kind == "PR_CLOSED":
                self._require_known_pr(event, known_pr_ref)
                stage = "CLOSED"
            elif kind == "BLOCKED":
                if blocking_reason is not None:
                    raise ContributionProjectionError(
                        "cannot add a second blocker before UNBLOCKED"
                    )
                blocking_reason = event.reason
            elif kind == "UNBLOCKED":
                if blocking_reason is None:
                    raise ContributionProjectionError(
                        "cannot UNBLOCK without an active blocker"
                    )
                blocking_reason = None
            elif kind == "PAUSED":
                if stage != "PAUSED":
                    pause_restore_stage = stage
                stage = "PAUSED"
            elif kind == "RESUMED":
                if stage != "PAUSED" or pause_restore_stage is None:
                    raise ContributionProjectionError(
                        "cannot RESUME without an active pause"
                    )
                stage = pause_restore_stage
                pause_restore_stage = None
            elif kind == "DISCARDED":
                stage = "DISCARDED"

            last_event_kind = kind
            last_observed_at = event.observed_at

        return ContributionContext(
            entry_id=entry.entry_id,
            stage=stage,
            blocking_reason=blocking_reason,
            last_event_kind=last_event_kind,
            last_observed_at=last_observed_at,
            task_claim_state=task_claim_state,
            active_work_ref=active_work_ref,
            event_count=len(ordered),
        )

    @staticmethod
    def _require_known_pr(
        event: ContributionEvent,
        known_pr_ref: str | None,
    ) -> None:
        if known_pr_ref is None:
            raise ContributionProjectionError(
                f"{event.kind} requires a prior PR_OPENED event"
            )
        if event.work_ref != known_pr_ref:
            raise ContributionProjectionError(
                f"{event.kind} work_ref does not match the open PR"
            )
