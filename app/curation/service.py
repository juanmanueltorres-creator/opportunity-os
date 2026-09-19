from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from app.availability.refresh_curation_operator import (
    RefreshCurationOperatorRun,
    refresh_curation_run_id,
)
from app.curation.models import (
    CurationChangeBrief,
    CurationChangeBriefFormat,
    CurationOperatorOverview,
    CurationPublicationCoverage,
    CurationRunDelta,
    CurationRunDeltaMetrics,
    CurationRunHistory,
    CurationRunHistoryItem,
    CurationRunMetricChange,
    CurationRunRecord,
    CurationRunRecordResult,
    PublicationCheckpoint,
    PublicationCheckpointConfirmRequest,
    PublicationCheckpointEvidence,
    PublicationCheckpointPreview,
    PublicationConfirmResult,
)
from app.curation.repository import SQLiteCurationLedgerRepository


class CurationLedgerService:
    def __init__(
        self,
        *,
        repository: SQLiteCurationLedgerRepository,
    ) -> None:
        self.repository = repository

    def record_run(
        self,
        run: RefreshCurationOperatorRun,
        *,
        recorded_at: datetime,
    ) -> CurationRunRecordResult:
        normalized_recorded_at = _aware_utc(recorded_at)
        expected_run_id = refresh_curation_run_id(
            source_refresh=run.source_refresh,
            operator_view=run.operator_view,
        )
        if expected_run_id != run.run_id:
            return CurationRunRecordResult(
                status="BLOCKED",
                errors=["run_id_snapshot_mismatch"],
            )
        if (
            run.generated_at != run.source_refresh.generated_at
            or run.generated_at != run.operator_view.generated_at
        ):
            return CurationRunRecordResult(
                status="BLOCKED",
                errors=["run_timestamp_snapshot_mismatch"],
            )
        if run.partial_source_failure != (
            run.source_refresh.error_count > 0
        ):
            return CurationRunRecordResult(
                status="BLOCKED",
                errors=["run_partial_failure_snapshot_mismatch"],
            )
        if run.external_reads != run.source_refresh.external_reads:
            return CurationRunRecordResult(
                status="BLOCKED",
                errors=["run_external_reads_snapshot_mismatch"],
            )
        if normalized_recorded_at < run.generated_at:
            return CurationRunRecordResult(
                status="BLOCKED",
                errors=["recorded_at_before_run"],
            )
        payload_sha256 = _run_payload_sha256(run)
        record = CurationRunRecord(
            run_id=run.run_id,
            generated_at=run.generated_at,
            recorded_at=normalized_recorded_at,
            payload_sha256=payload_sha256,
            digest_id=run.operator_view.publishable.digest_id,
            publishable_opportunity_ids=list(
                run.operator_view.publishable.opportunity_ids
            ),
            review_opportunity_ids=[
                item.opportunity_id
                for item in run.operator_view.review_items
            ],
            held_displayed_opportunity_ids=list(
                run.operator_view.held.displayed_ids
            ),
        )
        payload_json = json.dumps(
            {
                "record": record.model_dump(
                    mode="json",
                    exclude_none=False,
                ),
                "run": run.model_dump(
                    mode="json",
                    exclude_none=False,
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        disposition = self.repository.record_run(
            record,
            payload_json=payload_json,
        )
        if disposition == "CONFLICT":
            return CurationRunRecordResult(
                status="CONFLICT",
                errors=["run_id_payload_conflict"],
            )
        if disposition == "IDENTICAL":
            persisted = self.repository.get_run_record(run.run_id)
            if persisted is None:
                raise RuntimeError("identical curation run disappeared")
            record = persisted
        return CurationRunRecordResult(
            status=disposition,
            record=record,
            errors=[],
        )

    def history(self, *, limit: int = 20) -> CurationRunHistory:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be within 1..100")

        items: list[CurationRunHistoryItem] = []
        for payload_json in self.repository.list_run_payload_json(limit=limit):
            payload = json.loads(payload_json)
            record = CurationRunRecord.model_validate(payload["record"])
            run = RefreshCurationOperatorRun.model_validate(payload["run"])
            if record.run_id != run.run_id:
                raise RuntimeError("curation run history snapshot mismatch")

            checkpoints = self.repository.list_publication_checkpoints_for_run(
                run.run_id
            )
            published_opportunity_ids: list[str] = []
            seen_opportunity_ids: set[str] = set()
            publication_channels = []
            latest_published_at = None
            for checkpoint in checkpoints:
                if checkpoint.run_id != run.run_id:
                    raise RuntimeError(
                        "publication checkpoint history snapshot mismatch"
                    )
                for opportunity_id in checkpoint.opportunity_ids:
                    if opportunity_id not in seen_opportunity_ids:
                        seen_opportunity_ids.add(opportunity_id)
                        published_opportunity_ids.append(opportunity_id)
                if checkpoint.channel not in publication_channels:
                    publication_channels.append(checkpoint.channel)
                if (
                    latest_published_at is None
                    or checkpoint.confirmed_at > latest_published_at
                ):
                    latest_published_at = checkpoint.confirmed_at

            failed_sources = [
                diagnostic.source
                for diagnostic in run.source_refresh.diagnostics
                if diagnostic.status == "error"
            ]
            items.append(
                CurationRunHistoryItem(
                    run_id=run.run_id,
                    generated_at=run.generated_at,
                    recorded_at=record.recorded_at,
                    source_count=run.source_refresh.source_count,
                    source_ok_count=run.source_refresh.ok_count,
                    source_error_count=run.source_refresh.error_count,
                    failed_sources=failed_sources,
                    fetched_opportunity_count=run.source_refresh.fetched_count,
                    new_opportunity_count=run.source_refresh.created_count,
                    existing_opportunity_count=(
                        run.source_refresh.existing_count
                    ),
                    review_count=run.operator_view.review_count,
                    publishable_count=run.operator_view.publishable_count,
                    held_count=run.operator_view.held_count,
                    review_opportunity_ids=list(
                        record.review_opportunity_ids
                    ),
                    publishable_opportunity_ids=list(
                        record.publishable_opportunity_ids
                    ),
                    held_displayed_opportunity_ids=list(
                        record.held_displayed_opportunity_ids
                    ),
                    publication_checkpoint_count=len(checkpoints),
                    published_opportunity_ids=published_opportunity_ids,
                    publication_channels=publication_channels,
                    latest_published_at=latest_published_at,
                    partial_source_failure=run.partial_source_failure,
                )
            )

        return CurationRunHistory(
            limit=limit,
            count=len(items),
            items=items,
            external_actions=[],
        )

    def latest_delta(self) -> CurationRunDelta:
        return _delta_from_history(self.history(limit=2))

    def latest_change_brief(
        self,
        *,
        format: CurationChangeBriefFormat = "markdown",
    ) -> CurationChangeBrief:
        return _change_brief_from_delta(
            self.latest_delta(),
            format=format,
        )

    def latest_publication_coverage(
        self,
    ) -> CurationPublicationCoverage:
        return _publication_coverage_from_history(self.history(limit=1))

    def operator_overview(
        self,
        *,
        format: CurationChangeBriefFormat = "markdown",
    ) -> CurationOperatorOverview:
        history = self.history(limit=2)
        delta = _delta_from_history(history)
        brief = _change_brief_from_delta(delta, format=format)
        coverage = _publication_coverage_from_history(history)

        current = delta.current_run
        if current is None:
            return CurationOperatorOverview(
                status="EMPTY",
                delta=delta,
                change_brief=brief,
                publication_coverage=coverage,
                external_actions=[],
            )

        return CurationOperatorOverview(
            status=delta.status,
            current_run=current,
            delta=delta,
            change_brief=brief,
            publication_coverage=coverage,
            review_opportunity_ids=list(current.review_opportunity_ids),
            publishable_opportunity_ids=list(current.publishable_opportunity_ids),
            held_displayed_opportunity_ids=list(
                current.held_displayed_opportunity_ids
            ),
            uncheckpointed_publishable_ids=list(
                coverage.uncheckpointed_publishable_ids
            ),
            external_actions=[],
        )

    def preview_publication(
        self,
        evidence: PublicationCheckpointEvidence,
    ) -> PublicationCheckpointPreview:
        run = self.repository.get_run_record(evidence.run_id)
        publication_count = self.repository.publication_count()
        if run is None:
            return _blocked_preview(
                evidence,
                publication_count=publication_count,
                errors=["curation_run_not_recorded"],
            )
        if run.digest_id != evidence.digest_id:
            return _blocked_preview(
                evidence,
                publication_count=publication_count,
                errors=["digest_id_mismatch"],
                run_payload_sha256=run.payload_sha256,
            )

        publishable_ids = set(run.publishable_opportunity_ids)
        requested_ids = set(evidence.opportunity_ids)
        if not requested_ids.issubset(publishable_ids):
            return _blocked_preview(
                evidence,
                publication_count=publication_count,
                errors=["opportunity_not_in_recorded_publishable_digest"],
                run_payload_sha256=run.payload_sha256,
            )

        already_published = sorted(
            self.repository.list_published_opportunity_ids_for_run(
                run_id=evidence.run_id,
                opportunity_ids=evidence.opportunity_ids,
            )
        )
        if already_published:
            return PublicationCheckpointPreview(
                status="BLOCKED",
                preview_sha256=_preview_sha256(
                    evidence=evidence,
                    run_payload_sha256=run.payload_sha256,
                    publication_count_before=publication_count,
                ),
                evidence=evidence,
                run_payload_sha256=run.payload_sha256,
                eligible_opportunity_ids=[],
                already_published_opportunity_ids=already_published,
                errors=["opportunity_already_published"],
                publication_count_before=publication_count,
            )

        return PublicationCheckpointPreview(
            status="READY",
            preview_sha256=_preview_sha256(
                evidence=evidence,
                run_payload_sha256=run.payload_sha256,
                publication_count_before=publication_count,
            ),
            evidence=evidence,
            run_payload_sha256=run.payload_sha256,
            eligible_opportunity_ids=list(evidence.opportunity_ids),
            already_published_opportunity_ids=[],
            errors=[],
            publication_count_before=publication_count,
        )

    def confirm_publication(
        self,
        request: PublicationCheckpointConfirmRequest,
        *,
        processed_at: datetime,
    ) -> PublicationConfirmResult:
        processed = _aware_utc(processed_at)
        preview = request.preview
        existing_receipt = self.repository.get_publication_by_preview_sha256(
            preview.preview_sha256
        )
        if existing_receipt is not None:
            return PublicationConfirmResult(
                status="ALREADY_RECORDED",
                checkpoint=existing_receipt,
                errors=[],
            )
        if preview.status != "READY":
            return PublicationConfirmResult(
                status="BLOCKED",
                errors=["publication_preview_not_ready"],
            )

        run = self.repository.get_run_record(preview.evidence.run_id)
        if run is None:
            return PublicationConfirmResult(
                status="BLOCKED",
                errors=["curation_run_not_recorded"],
            )
        if run.payload_sha256 != preview.run_payload_sha256:
            return PublicationConfirmResult(
                status="BLOCKED",
                errors=["curation_run_changed"],
            )
        if run.digest_id != preview.evidence.digest_id:
            return PublicationConfirmResult(
                status="BLOCKED",
                errors=["digest_id_mismatch"],
            )
        if not set(preview.evidence.opportunity_ids).issubset(
            set(run.publishable_opportunity_ids)
        ):
            return PublicationConfirmResult(
                status="BLOCKED",
                errors=["opportunity_not_in_recorded_publishable_digest"],
            )
        expected_hash = _preview_sha256(
            evidence=preview.evidence,
            run_payload_sha256=run.payload_sha256,
            publication_count_before=preview.publication_count_before,
        )
        if expected_hash != preview.preview_sha256:
            return PublicationConfirmResult(
                status="BLOCKED",
                errors=["publication_preview_hash_mismatch"],
            )
        if request.confirmed_at < run.generated_at:
            return PublicationConfirmResult(
                status="BLOCKED",
                errors=["confirmation_before_curation_run"],
            )
        if request.confirmed_at > processed:
            return PublicationConfirmResult(
                status="BLOCKED",
                errors=["confirmation_in_future"],
            )

        already_published = (
            self.repository.list_published_opportunity_ids_for_run(
                run_id=preview.evidence.run_id,
                opportunity_ids=preview.evidence.opportunity_ids,
            )
        )
        if already_published:
            return PublicationConfirmResult(
                status="BLOCKED",
                errors=["opportunity_already_published"],
            )

        checkpoint = PublicationCheckpoint(
            checkpoint_id=_checkpoint_id(request),
            run_id=preview.evidence.run_id,
            digest_id=preview.evidence.digest_id,
            opportunity_ids=list(preview.evidence.opportunity_ids),
            channel=preview.evidence.channel,
            confirmed_by=request.confirmed_by,
            confirmed_at=request.confirmed_at,
            note=request.note,
            preview_sha256=preview.preview_sha256,
        )
        recorded = self.repository.record_publication_if_count_unchanged(
            checkpoint,
            expected_publication_count=preview.publication_count_before,
        )
        if not recorded:
            existing_receipt = (
                self.repository.get_publication_by_preview_sha256(
                    preview.preview_sha256
                )
            )
            if existing_receipt is not None:
                return PublicationConfirmResult(
                    status="ALREADY_RECORDED",
                    checkpoint=existing_receipt,
                    errors=[],
                )
            return PublicationConfirmResult(
                status="BLOCKED",
                errors=["publication_ledger_changed"],
            )
        return PublicationConfirmResult(
            status="RECORDED",
            checkpoint=checkpoint,
            errors=[],
        )


def _blocked_preview(
    evidence: PublicationCheckpointEvidence,
    *,
    publication_count: int,
    errors: list[str],
    run_payload_sha256: str | None = None,
) -> PublicationCheckpointPreview:
    return PublicationCheckpointPreview(
        status="BLOCKED",
        preview_sha256=_preview_sha256(
            evidence=evidence,
            run_payload_sha256=run_payload_sha256,
            publication_count_before=publication_count,
        ),
        evidence=evidence,
        run_payload_sha256=run_payload_sha256,
        eligible_opportunity_ids=[],
        already_published_opportunity_ids=[],
        errors=errors,
        publication_count_before=publication_count,
    )


def _run_payload_sha256(run: RefreshCurationOperatorRun) -> str:
    canonical = json.dumps(
        run.model_dump(mode="json", exclude_none=False),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _preview_sha256(
    *,
    evidence: PublicationCheckpointEvidence,
    run_payload_sha256: str | None,
    publication_count_before: int,
) -> str:
    payload = {
        "evidence": evidence.model_dump(
            mode="json",
            exclude_none=False,
        ),
        "run_payload_sha256": run_payload_sha256,
        "publication_count_before": publication_count_before,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _checkpoint_id(
    request: PublicationCheckpointConfirmRequest,
) -> str:
    payload = {
        "preview_sha256": request.preview.preview_sha256,
        "confirmed_by": request.confirmed_by,
        "confirmed_at": request.confirmed_at.isoformat(),
        "note": request.note,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"publication-{digest[:20]}"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("recorded_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _metric_change(previous: int, current: int) -> CurationRunMetricChange:
    return CurationRunMetricChange(
        previous=previous,
        current=current,
        change=current - previous,
    )


def _entered(current: list[str], previous: list[str]) -> list[str]:
    return sorted(set(current) - set(previous))


def _signed(value: int) -> str:
    return f"+{value}" if value > 0 else str(value)


def _ids_text(items: list[str]) -> str:
    return ", ".join(items) if items else "none"


def _change_brief_highlights(delta: CurationRunDelta) -> list[str]:
    if delta.status != "READY" or delta.metrics is None:
        raise ValueError("ready delta required for change brief highlights")

    metrics = delta.metrics
    highlights = [
        (
            "Current run created opportunity count: "
            f"{metrics.new_opportunity_count.current} "
            f"(change {_signed(metrics.new_opportunity_count.change)} "
            "vs previous recorded run)."
        ),
        (
            "Source error count: "
            f"{metrics.source_error_count.current} "
            f"(change {_signed(metrics.source_error_count.change)})."
        ),
        (
            "Review set membership: "
            f"+{len(delta.entered_review_ids)} / "
            f"-{len(delta.exited_review_ids)} exact recorded IDs."
        ),
        (
            "Publishable set membership: "
            f"+{len(delta.entered_publishable_ids)} / "
            f"-{len(delta.exited_publishable_ids)} exact recorded IDs."
        ),
        (
            "Displayed-held subset membership: "
            f"+{len(delta.entered_displayed_held_ids)} / "
            f"-{len(delta.exited_displayed_held_ids)} exact recorded IDs."
        ),
        (
            "Publication checkpoints attached to current run: "
            f"{metrics.publication_checkpoint_count.current}; "
            "published IDs only on current run: "
            f"{len(delta.published_only_in_current_run_ids)}."
        ),
    ]

    if delta.started_failing_sources:
        highlights.append(
            "Sources newly failing in current snapshot: "
            f"{_ids_text(delta.started_failing_sources)}."
        )
    if delta.recovered_sources:
        highlights.append(
            "Sources no longer failing in current snapshot: "
            f"{_ids_text(delta.recovered_sources)}."
        )
    if delta.entered_publishable_ids:
        highlights.append(
            "Entered publishable set: "
            f"{_ids_text(delta.entered_publishable_ids)}."
        )
    if delta.exited_publishable_ids:
        highlights.append(
            "Exited publishable set: "
            f"{_ids_text(delta.exited_publishable_ids)}."
        )
    if delta.published_only_in_current_run_ids:
        highlights.append(
            "Checkpointed only against current run: "
            f"{_ids_text(delta.published_only_in_current_run_ids)}."
        )
    return highlights


def _render_change_brief(
    *,
    status: str,
    format: CurationChangeBriefFormat,
    headline: str,
    current_run_id: str | None,
    previous_run_id: str | None,
    highlights: list[str],
) -> str:
    if format == "markdown":
        lines = [
            "# Opportunity OS — Change Brief",
            "",
            f"**Status:** {status}",
            f"**Summary:** {headline}",
        ]
        if current_run_id is not None:
            lines.append(f"**Current run:** {current_run_id}")
        if previous_run_id is not None:
            lines.append(f"**Previous run:** {previous_run_id}")
        lines.extend(["", "## Recorded changes", ""])
        lines.extend(f"- {item}" for item in highlights)
        lines.extend(
            [
                "",
                "---",
                (
                    "Read-only snapshot comparison: membership change does not "
                    "imply cause or verified state transition."
                ),
            ]
        )
        return "\n".join(lines)

    lines = [
        "Opportunity OS — Change Brief",
        f"Status: {status}",
        f"Summary: {headline}",
    ]
    if current_run_id is not None:
        lines.append(f"Current run: {current_run_id}")
    if previous_run_id is not None:
        lines.append(f"Previous run: {previous_run_id}")
    lines.append("")
    lines.extend(f"- {item}" for item in highlights)
    lines.extend(
        [
            "",
            (
                "Read-only snapshot comparison: membership change does not "
                "imply cause or verified state transition."
            ),
        ]
    )
    return "\n".join(lines)


def _delta_from_history(history: CurationRunHistory) -> CurationRunDelta:
    if history.count == 0:
        return CurationRunDelta(
            status="EMPTY",
            external_actions=[],
        )

    current = history.items[0]
    if history.count == 1:
        return CurationRunDelta(
            status="BASELINE_ONLY",
            current_run=current,
            external_actions=[],
        )

    previous = history.items[1]
    metrics = CurationRunDeltaMetrics(
        source_error_count=_metric_change(
            previous.source_error_count,
            current.source_error_count,
        ),
        fetched_opportunity_count=_metric_change(
            previous.fetched_opportunity_count,
            current.fetched_opportunity_count,
        ),
        new_opportunity_count=_metric_change(
            previous.new_opportunity_count,
            current.new_opportunity_count,
        ),
        existing_opportunity_count=_metric_change(
            previous.existing_opportunity_count,
            current.existing_opportunity_count,
        ),
        review_count=_metric_change(
            previous.review_count,
            current.review_count,
        ),
        publishable_count=_metric_change(
            previous.publishable_count,
            current.publishable_count,
        ),
        held_count=_metric_change(
            previous.held_count,
            current.held_count,
        ),
        publication_checkpoint_count=_metric_change(
            previous.publication_checkpoint_count,
            current.publication_checkpoint_count,
        ),
        published_opportunity_count=_metric_change(
            len(previous.published_opportunity_ids),
            len(current.published_opportunity_ids),
        ),
    )
    return CurationRunDelta(
        status="READY",
        current_run=current,
        previous_run=previous,
        metrics=metrics,
        started_failing_sources=_entered(
            current.failed_sources,
            previous.failed_sources,
        ),
        recovered_sources=_entered(
            previous.failed_sources,
            current.failed_sources,
        ),
        entered_review_ids=_entered(
            current.review_opportunity_ids,
            previous.review_opportunity_ids,
        ),
        exited_review_ids=_entered(
            previous.review_opportunity_ids,
            current.review_opportunity_ids,
        ),
        entered_publishable_ids=_entered(
            current.publishable_opportunity_ids,
            previous.publishable_opportunity_ids,
        ),
        exited_publishable_ids=_entered(
            previous.publishable_opportunity_ids,
            current.publishable_opportunity_ids,
        ),
        entered_displayed_held_ids=_entered(
            current.held_displayed_opportunity_ids,
            previous.held_displayed_opportunity_ids,
        ),
        exited_displayed_held_ids=_entered(
            previous.held_displayed_opportunity_ids,
            current.held_displayed_opportunity_ids,
        ),
        published_only_in_current_run_ids=_entered(
            current.published_opportunity_ids,
            previous.published_opportunity_ids,
        ),
        published_only_in_previous_run_ids=_entered(
            previous.published_opportunity_ids,
            current.published_opportunity_ids,
        ),
        external_actions=[],
    )


def _change_brief_from_delta(
    delta: CurationRunDelta,
    *,
    format: CurationChangeBriefFormat,
) -> CurationChangeBrief:
    if format not in {"markdown", "plain"}:
        raise ValueError("unsupported change brief format")

    if delta.status == "EMPTY":
        headline = "No recorded curation runs yet"
        highlights = [
            "Record a curation run before comparing operational changes."
        ]
        return CurationChangeBrief(
            status="EMPTY",
            format=format,
            headline=headline,
            highlights=highlights,
            rendered_text=_render_change_brief(
                status="EMPTY",
                format=format,
                headline=headline,
                current_run_id=None,
                previous_run_id=None,
                highlights=highlights,
            ),
            external_actions=[],
        )

    if delta.current_run is None:
        raise RuntimeError("change brief missing current run")

    current_run_id = delta.current_run.run_id
    if delta.status == "BASELINE_ONLY":
        headline = "Baseline recorded; one more run is required"
        highlights = [
            (
                "Current recorded run: "
                f"{current_run_id}. No run-to-run transition is claimed."
            )
        ]
        return CurationChangeBrief(
            status="BASELINE_ONLY",
            format=format,
            current_run_id=current_run_id,
            headline=headline,
            highlights=highlights,
            rendered_text=_render_change_brief(
                status="BASELINE_ONLY",
                format=format,
                headline=headline,
                current_run_id=current_run_id,
                previous_run_id=None,
                highlights=highlights,
            ),
            external_actions=[],
        )

    if delta.previous_run is None or delta.metrics is None:
        raise RuntimeError("ready change brief requires complete delta")

    previous_run_id = delta.previous_run.run_id
    highlights = _change_brief_highlights(delta)
    headline = "Recorded curation changes since the previous run"
    return CurationChangeBrief(
        status="READY",
        format=format,
        current_run_id=current_run_id,
        previous_run_id=previous_run_id,
        headline=headline,
        highlights=highlights,
        rendered_text=_render_change_brief(
            status="READY",
            format=format,
            headline=headline,
            current_run_id=current_run_id,
            previous_run_id=previous_run_id,
            highlights=highlights,
        ),
        external_actions=[],
    )


def _publication_coverage_from_history(
    history: CurationRunHistory,
) -> CurationPublicationCoverage:
    if history.count == 0:
        return CurationPublicationCoverage(
            status="EMPTY",
            publishable_count=0,
            checkpointed_count=0,
            uncheckpointed_count=0,
            external_actions=[],
        )

    current = history.items[0]
    publishable_ids = sorted(set(current.publishable_opportunity_ids))
    checkpointed_ids = sorted(set(current.published_opportunity_ids))
    publishable_set = set(publishable_ids)
    checkpointed_set = set(checkpointed_ids)

    unexpected = checkpointed_set - publishable_set
    if unexpected:
        raise RuntimeError(
            "publication checkpoint references non-publishable run item"
        )

    uncheckpointed_ids = sorted(publishable_set - checkpointed_set)
    if not publishable_ids:
        status = "NO_PUBLISHABLE"
    elif not checkpointed_ids:
        status = "NONE_CHECKPOINTED"
    elif uncheckpointed_ids:
        status = "PARTIAL"
    else:
        status = "COMPLETE"

    return CurationPublicationCoverage(
        status=status,
        run_id=current.run_id,
        generated_at=current.generated_at,
        publishable_count=len(publishable_ids),
        publishable_opportunity_ids=publishable_ids,
        checkpointed_count=len(checkpointed_ids),
        checkpointed_opportunity_ids=checkpointed_ids,
        uncheckpointed_count=len(uncheckpointed_ids),
        uncheckpointed_publishable_ids=uncheckpointed_ids,
        latest_checkpointed_at=current.latest_published_at,
        external_actions=[],
    )
