from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib

from pydantic import BaseModel

from app.contributions.github_provider import GitHubContributionProvider
from app.contributions.models import ContributionContext, ContributionEvent, PublicContributionEntry
from app.contributions.normalizer import (
    ContributionNormalization,
    normalize_embedded_observation,
    normalize_snapshot,
)
from app.contributions.observations import (
    PREVIEW_VERSION,
    ContributionImportReceipt,
    ContributionImportRequest,
    ContributionImportResult,
    ContributionObservation,
    ContributionPreview,
    GitHubContributionSelection,
    canonical_sha256,
    observation_sha256,
)
from app.contributions.projector import ContributionProjector
from app.contributions.repository import SQLiteContributionRepository


def _aware_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _dump(value: BaseModel | None):
    if value is None:
        return None
    return value.model_dump(mode="json", exclude_none=False)


def _history_sha256(
    entry: PublicContributionEntry | None,
    events: list[ContributionEvent],
) -> str:
    ordered = sorted(events, key=lambda event: (event.observed_at, event.event_id))
    return canonical_sha256(
        {
            "entry": _dump(entry),
            "events": [_dump(event) for event in ordered],
        }
    )


def _preview_sha256(
    *,
    observation: ContributionObservation,
    entry_for_hash: PublicContributionEntry | None,
    candidate_event: ContributionEvent | None,
    history_sha256: str,
    context_before: ContributionContext | None,
    context_after: ContributionContext | None,
) -> str:
    return canonical_sha256(
        {
            "preview_version": PREVIEW_VERSION,
            "observation_sha256": observation_sha256(observation),
            "entry": _dump(entry_for_hash),
            "candidate_event": _dump(candidate_event),
            "history_sha256": history_sha256,
            "context_before": _dump(context_before),
            "context_after": _dump(context_after),
        }
    )


def _receipt_id(observation_id: str) -> str:
    digest = hashlib.sha256(observation_id.encode("utf-8")).hexdigest()
    return f"contrib-receipt-{digest}"


class ContributionObservationBridge:
    def __init__(
        self,
        *,
        provider: GitHubContributionProvider,
        repository: SQLiteContributionRepository,
        projector: ContributionProjector,
        clock: Callable[[], datetime],
    ) -> None:
        self.provider = provider
        self.repository = repository
        self.projector = projector
        self.clock = clock

    def _current_state(
        self,
        entry_id: str,
    ) -> tuple[PublicContributionEntry | None, list[ContributionEvent]]:
        entry = self.repository.get_entry(entry_id)
        events = self.repository.list_events(entry_id) if entry is not None else []
        return entry, events

    def _context(
        self,
        entry: PublicContributionEntry | None,
        events: list[ContributionEvent],
    ) -> ContributionContext | None:
        if entry is None:
            return None
        try:
            return self.projector.project(entry=entry, events=events)
        except ValueError:
            return None

    def _render_preview(
        self,
        *,
        normalization: ContributionNormalization,
        current_entry: PublicContributionEntry | None,
        current_events: list[ContributionEvent],
        status_override: str | None = None,
        errors_override: list[str] | None = None,
        strip_proposal: bool = False,
    ) -> ContributionPreview:
        proposed_entry = None if strip_proposal else normalization.proposed_entry
        candidate_event = None if strip_proposal else normalization.candidate_event
        context_before = self._context(current_entry, current_events)

        if proposed_entry is not None:
            context_after = self._context(proposed_entry, [])
            entry_for_hash = proposed_entry
        elif candidate_event is not None and current_entry is not None:
            context_after = self._context(
                current_entry,
                current_events + [candidate_event],
            )
            entry_for_hash = current_entry
        else:
            context_after = context_before
            entry_for_hash = current_entry

        obs_hash = observation_sha256(normalization.observation)
        history_hash = _history_sha256(current_entry, current_events)
        preview_hash = _preview_sha256(
            observation=normalization.observation,
            entry_for_hash=entry_for_hash,
            candidate_event=candidate_event,
            history_sha256=history_hash,
            context_before=context_before,
            context_after=context_after,
        )
        return ContributionPreview(
            preview_version=PREVIEW_VERSION,
            status=status_override or normalization.status,
            observation=normalization.observation,
            observation_sha256=obs_hash,
            preview_sha256=preview_hash,
            entry_id=normalization.observation.entry_id or "missing-entry",
            source_ref=normalization.observation.source_ref,
            proposed_entry=proposed_entry,
            candidate_event=candidate_event,
            context_before=context_before,
            context_after=context_after,
            errors=(errors_override if errors_override is not None else list(normalization.errors)),
            external_actions=[],
        )

    def preview(self, selection: GitHubContributionSelection) -> ContributionPreview:
        captured_at = _aware_utc(self.clock(), field="captured_at")
        snapshot = self.provider.fetch(selection, captured_at=captured_at)

        provisional_entry_id = selection.entry_id
        if provisional_entry_id is None and selection.resource_kind == "ISSUE":
            from app.contributions.normalizer import deterministic_issue_entry_id

            provisional_entry_id = deterministic_issue_entry_id(
                selection.repository_full_name,
                selection.number,
            )
        entry, events = self._current_state(provisional_entry_id or "missing-entry")
        normalization = normalize_snapshot(
            selection=selection,
            snapshot=snapshot,
            entry=entry,
            events=events,
            projector=self.projector,
        )

        current_receipt = self.repository.get_receipt_for_observation(
            normalization.observation.observation_id
        )
        current_obs_hash = observation_sha256(normalization.observation)
        if current_receipt is not None:
            if current_receipt.observation_sha256 != current_obs_hash:
                return self._render_preview(
                    normalization=normalization,
                    current_entry=entry,
                    current_events=events,
                    status_override="BLOCKED",
                    errors_override=["observation_identity_conflict"],
                    strip_proposal=True,
                )
            return self._render_preview(
                normalization=normalization,
                current_entry=entry,
                current_events=events,
                status_override="ALREADY_IMPORTED",
                errors_override=[],
                strip_proposal=True,
            )

        return self._render_preview(
            normalization=normalization,
            current_entry=entry,
            current_events=events,
        )

    def _already_receipt(
        self,
        *,
        stored: ContributionImportReceipt,
        processed_at: datetime,
    ) -> ContributionImportReceipt:
        return stored.model_copy(
            update={
                "processed_at": processed_at,
                "status": "ALREADY_IMPORTED",
            }
        )

    def _build_receipt(
        self,
        *,
        request: ContributionImportRequest,
        processed_at: datetime,
    ) -> ContributionImportReceipt:
        preview = request.preview
        return ContributionImportReceipt(
            receipt_id=_receipt_id(preview.observation.observation_id),
            observation_id=preview.observation.observation_id,
            observation_sha256=preview.observation_sha256,
            preview_sha256=preview.preview_sha256,
            entry_id=preview.entry_id,
            contribution_event_id=(
                preview.candidate_event.event_id
                if preview.candidate_event is not None
                else None
            ),
            source_ref=preview.source_ref,
            confirmed_by=request.confirmed_by,
            confirmed_at=request.confirmed_at,
            processed_at=processed_at,
            status="IMPORTED",
        )

    def import_preview(
        self,
        request: ContributionImportRequest,
    ) -> ContributionImportResult:
        processed_at = _aware_utc(self.clock(), field="processed_at")
        preview = request.preview
        actual_obs_hash = observation_sha256(preview.observation)
        if actual_obs_hash != preview.observation_sha256:
            return ContributionImportResult(
                status="CONFLICT",
                errors=["observation_identity_conflict"],
            )

        stored_receipt = self.repository.get_receipt_for_observation(
            preview.observation.observation_id
        )
        if stored_receipt is not None:
            if stored_receipt.observation_sha256 != actual_obs_hash:
                return ContributionImportResult(
                    status="CONFLICT",
                    errors=["observation_identity_conflict"],
                )
            return ContributionImportResult(
                status="ALREADY_IMPORTED",
                receipt=self._already_receipt(
                    stored=stored_receipt,
                    processed_at=processed_at,
                ),
                errors=[],
            )

        entry, events = self._current_state(preview.entry_id)
        normalization = normalize_embedded_observation(
            observation=preview.observation,
            entry=entry,
            events=events,
            projector=self.projector,
        )
        if normalization.status == "BLOCKED":
            return ContributionImportResult(
                status="BLOCKED_DOMAIN",
                errors=list(normalization.errors),
            )

        rebuilt = self._render_preview(
            normalization=normalization,
            current_entry=entry,
            current_events=events,
        )
        if rebuilt.preview_sha256 != preview.preview_sha256:
            return ContributionImportResult(
                status="BLOCKED_STALE_PREVIEW",
                errors=["stale_preview"],
            )
        if normalization.status != "IMPORTABLE":
            return ContributionImportResult(
                status="BLOCKED_STALE_PREVIEW",
                errors=["stale_preview"],
            )

        receipt = self._build_receipt(request=request, processed_at=processed_at)
        try:
            if normalization.proposed_entry is not None:
                self.repository.insert_entry_with_receipt(
                    normalization.proposed_entry,
                    receipt,
                )
            elif normalization.candidate_event is not None:
                self.repository.append_event_with_receipt(
                    normalization.candidate_event,
                    receipt,
                    self.projector,
                )
            else:
                return ContributionImportResult(
                    status="BLOCKED_DOMAIN",
                    errors=["invalid_contribution_transition"],
                )
        except ValueError as exc:
            text = str(exc).casefold()
            if "conflict" in text:
                return ContributionImportResult(
                    status="CONFLICT",
                    errors=["observation_identity_conflict"],
                )
            return ContributionImportResult(
                status="BLOCKED_DOMAIN",
                errors=["invalid_contribution_transition"],
            )

        return ContributionImportResult(
            status="IMPORTED",
            receipt=receipt,
            errors=[],
        )
