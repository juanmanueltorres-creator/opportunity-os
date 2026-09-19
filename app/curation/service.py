from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from app.availability.refresh_curation_operator import (
    RefreshCurationOperatorRun,
    refresh_curation_run_id,
)
from app.curation.models import (
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
        history = self.history(limit=2)
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
