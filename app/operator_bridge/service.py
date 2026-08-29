from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from app.operator_bridge.models import (
    PREVIEW_VERSION,
    STATE_VERSION,
    ObservationImportReceipt,
    ObservationImportRequest,
    ObservationImportResult,
    ObservationPreview,
    OperatorObservation,
    ReceiptStatus,
    canonical_sha256,
    observation_sha256,
)
from app.operator_bridge.normalizer import normalize_observation
from app.relationships.models import CareerContact, RelationshipAccount, RelationshipEvent
from app.relationships.repository import SQLiteRelationshipRepository
from app.relationships.service import RelationshipProjection, RelationshipService


def _aware_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _domain_error_code(exc: ValueError) -> str:
    text = str(exc).lower()
    if "out-of-order" in text:
        return "out_of_order_observation"
    if "contact" in text:
        return "unknown_or_invalid_contact"
    if "account must be registered" in text:
        return "unknown_relationship_account"
    return "invalid_relationship_transition"


def _state_sha256(
    account: RelationshipAccount | None,
    contact: CareerContact | None,
) -> str:
    return canonical_sha256(
        {
            "state_version": STATE_VERSION,
            "account": (
                account.model_dump(mode="json", exclude_none=False)
                if account is not None
                else None
            ),
            "contact": (
                contact.model_dump(mode="json", exclude_none=False)
                if contact is not None
                else None
            ),
        }
    )


def _preview_sha256(
    observation: OperatorObservation,
    event: RelationshipEvent | None,
    state_sha256: str,
) -> str:
    return canonical_sha256(
        {
            "preview_version": PREVIEW_VERSION,
            "observation_sha256": observation_sha256(observation),
            "normalized_event": (
                event.model_dump(mode="json", exclude_none=False)
                if event is not None
                else None
            ),
            "state_sha256": state_sha256,
        }
    )


def _receipt_id(event: RelationshipEvent) -> str:
    digest = hashlib.sha256(event.event_id.encode("utf-8")).hexdigest()
    return f"opreceipt-{digest}"


class OperatorBridgeService:
    def __init__(
        self,
        repository: SQLiteRelationshipRepository,
        relationships: RelationshipService,
    ) -> None:
        self.repository = repository
        self.relationships = relationships

    def _contact_for(
        self,
        observation: OperatorObservation,
    ) -> CareerContact | None:
        if observation.contact_id is None:
            return None
        contact = self.repository.get_contact(observation.contact_id)
        if contact is None or contact.account_id != observation.account_id:
            return None
        return contact

    def _preview_result(
        self,
        *,
        observation: OperatorObservation,
        event: RelationshipEvent | None,
        account: RelationshipAccount | None,
        contact: CareerContact | None,
        status: str,
        projection: RelationshipProjection | None = None,
        errors: list[str] | None = None,
    ) -> ObservationPreview:
        state_hash = _state_sha256(account, contact)
        preview_hash = _preview_sha256(observation, event, state_hash)
        return ObservationPreview(
            preview_version=PREVIEW_VERSION,
            status=status,
            observation_id=observation.observation_id,
            observation_sha256=observation_sha256(observation),
            preview_sha256=preview_hash,
            account_id=observation.account_id,
            contact_id=observation.contact_id,
            event_kind=event.kind if event is not None else None,
            state_before=account.relationship_state if account is not None else None,
            state_after=(
                projection.account.relationship_state
                if projection is not None
                else account.relationship_state if status == "ALREADY_IMPORTED" and account is not None else None
            ),
            open_process_before=account.open_process if account is not None else None,
            open_process_after=(
                projection.account.open_process
                if projection is not None
                else account.open_process if status == "ALREADY_IMPORTED" and account is not None else None
            ),
            source_type=observation.source_type,
            source_name=observation.source_name,
            source_ref=observation.source_ref,
            reason=observation.reason,
            errors=list(errors or []),
            external_actions=[],
        )

    def preview(self, observation: OperatorObservation) -> ObservationPreview:
        account = self.repository.get_account(observation.account_id)
        contact = self._contact_for(observation)

        try:
            event = normalize_observation(observation)
        except ValueError as exc:
            return self._preview_result(
                observation=observation,
                event=None,
                account=account,
                contact=contact,
                status="BLOCKED",
                errors=[_domain_error_code(exc)],
            )

        existing = self.repository.get_event(event.event_id)
        if existing is not None:
            if existing != event:
                return self._preview_result(
                    observation=observation,
                    event=event,
                    account=account,
                    contact=contact,
                    status="BLOCKED",
                    errors=["observation_identity_conflict"],
                )
            return self._preview_result(
                observation=observation,
                event=event,
                account=account,
                contact=contact,
                status="ALREADY_IMPORTED",
            )

        if account is None:
            return self._preview_result(
                observation=observation,
                event=event,
                account=None,
                contact=None,
                status="BLOCKED",
                errors=["unknown_relationship_account"],
            )

        if observation.contact_id is not None and contact is None:
            return self._preview_result(
                observation=observation,
                event=event,
                account=account,
                contact=None,
                status="BLOCKED",
                errors=["unknown_or_invalid_contact"],
            )

        try:
            projection = self.relationships.preview(event)
        except ValueError as exc:
            return self._preview_result(
                observation=observation,
                event=event,
                account=account,
                contact=contact,
                status="BLOCKED",
                errors=[_domain_error_code(exc)],
            )

        return self._preview_result(
            observation=observation,
            event=event,
            account=account,
            contact=contact,
            status="IMPORTABLE",
            projection=projection,
        )

    def _build_receipt(
        self,
        *,
        request: ObservationImportRequest,
        event: RelationshipEvent,
        processed_at: datetime,
        status: ReceiptStatus,
    ) -> ObservationImportReceipt:
        return ObservationImportReceipt(
            receipt_id=_receipt_id(event),
            observation_id=request.observation.observation_id,
            observation_sha256=observation_sha256(request.observation),
            preview_sha256=request.preview_sha256,
            relationship_event_id=event.event_id,
            account_id=event.account_id,
            contact_id=event.contact_id,
            source_type=request.observation.source_type,
            source_name=request.observation.source_name,
            source_ref=request.observation.source_ref,
            confirmed_by=request.confirmed_by,
            confirmed_at=request.confirmed_at,
            processed_at=processed_at,
            status=status,
        )

    def import_observation(
        self,
        request: ObservationImportRequest,
        *,
        processed_at: datetime,
    ) -> ObservationImportResult:
        processed_at = _aware_utc(processed_at, field="processed_at")
        try:
            event = normalize_observation(request.observation)
        except ValueError as exc:
            return ObservationImportResult(
                status="BLOCKED_DOMAIN",
                errors=[_domain_error_code(exc)],
            )

        existing = self.repository.get_event(event.event_id)
        if existing is not None:
            if existing != event:
                return ObservationImportResult(
                    status="CONFLICT",
                    errors=["observation_identity_conflict"],
                )
            return ObservationImportResult(
                status="ALREADY_IMPORTED",
                receipt=self._build_receipt(
                    request=request,
                    event=event,
                    processed_at=processed_at,
                    status="ALREADY_IMPORTED",
                ),
            )

        preview = self.preview(request.observation)
        if preview.preview_sha256 != request.preview_sha256:
            return ObservationImportResult(
                status="BLOCKED_STALE_PREVIEW",
                errors=["stale_preview"],
            )
        if preview.status == "BLOCKED":
            return ObservationImportResult(
                status="BLOCKED_DOMAIN",
                errors=list(preview.errors),
            )

        try:
            self.relationships.record(event)
        except ValueError as exc:
            return ObservationImportResult(
                status="BLOCKED_DOMAIN",
                errors=[_domain_error_code(exc)],
            )

        return ObservationImportResult(
            status="IMPORTED",
            receipt=self._build_receipt(
                request=request,
                event=event,
                processed_at=processed_at,
                status="IMPORTED",
            ),
        )
