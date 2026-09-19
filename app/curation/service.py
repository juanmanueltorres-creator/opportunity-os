from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from app.availability.refresh_curation_operator import (
    RefreshCurationOperatorRun,
)
from app.curation.models import (
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
        return CurationRunRecordResult(
            status=disposition,
            record=record,
            errors=[],
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
            self.repository.list_published_opportunity_ids(
                evidence.opportunity_ids
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
    ) -> PublicationConfirmResult:
        preview = request.preview
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

        already_published = self.repository.list_published_opportunity_ids(
            preview.evidence.opportunity_ids
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
