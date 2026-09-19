from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from app.availability.models import (
    AvailabilityObservation,
    AvailabilityState,
    OpportunityAvailability,
)
from app.availability.repository import SQLiteAvailabilityRepository
from app.availability.verification_models import (
    VERIFICATION_PREVIEW_VERSION,
    VerificationConfirmRequest,
    VerificationConfirmResult,
    VerificationEvidence,
    VerificationPreview,
    VerificationReceipt,
    canonical_sha256,
    evidence_sha256,
)
from app.repositories.opportunities import SQLiteOpportunityRepository


class AvailabilityVerificationService:
    def __init__(
        self,
        *,
        opportunity_repository: SQLiteOpportunityRepository,
        availability_repository: SQLiteAvailabilityRepository,
    ) -> None:
        self.opportunity_repository = opportunity_repository
        self.availability_repository = availability_repository

    def preview(self, evidence: VerificationEvidence) -> VerificationPreview:
        opportunity = self.opportunity_repository.get(evidence.opportunity_id)
        if opportunity is None:
            return _blocked_preview(evidence, "opportunity_not_found")

        observations = self.availability_repository.list_observations(
            evidence.opportunity_id
        )
        current = self.availability_repository.get(evidence.opportunity_id)
        current_state = (
            current.availability_state
            if current is not None
            else "UNVERIFIED"
        )
        proposed_state = (
            "VERIFIED_OPEN"
            if evidence.decision == "OPEN"
            else "VERIFIED_CLOSED"
        )
        preview_hash = _preview_sha256(
            evidence=evidence,
            opportunity_payload=opportunity.model_dump(
                mode="json",
                exclude_none=False,
            ),
            availability=current,
        )
        status = (
            "ALREADY_VERIFIED"
            if _find_matching_observation(observations, evidence) is not None
            else "READY"
        )
        return VerificationPreview(
            status=status,
            opportunity_id=evidence.opportunity_id,
            evidence_sha256=evidence_sha256(evidence),
            preview_sha256=preview_hash,
            current_state=current_state,
            proposed_state=proposed_state,
            observation_count=(
                current.observation_count if current is not None else 0
            ),
            latest_observation_at=(
                current.latest_observation_at if current is not None else None
            ),
            errors=[],
            external_actions=[],
        )

    def confirm(
        self,
        request: VerificationConfirmRequest,
        *,
        processed_at: datetime,
    ) -> VerificationConfirmResult:
        processed_at = _aware_utc(processed_at, field="processed_at")
        if request.confirmed_at > processed_at:
            return VerificationConfirmResult(
                status="BLOCKED",
                errors=["confirmation_in_future"],
            )
        opportunity = self.opportunity_repository.get(
            request.evidence.opportunity_id
        )
        if opportunity is None:
            return VerificationConfirmResult(
                status="BLOCKED",
                errors=["opportunity_not_found"],
            )

        observations = self.availability_repository.list_observations(
            request.evidence.opportunity_id
        )
        existing = _find_matching_observation(
            observations,
            request.evidence,
        )
        if existing is not None and existing.preview_sha256 is not None:
            return VerificationConfirmResult(
                status="ALREADY_RECORDED",
                receipt=_receipt_from_observation(
                    request.evidence,
                    existing,
                    processed_at=processed_at,
                    resulting_state=_current_availability_state(
                        self.availability_repository,
                        request.evidence.opportunity_id,
                    ),
                ),
            )

        preview = self.preview(request.evidence)
        if preview.preview_sha256 != request.preview_sha256:
            return VerificationConfirmResult(
                status="BLOCKED_STALE_PREVIEW",
                errors=["stale_preview"],
            )
        if preview.status == "BLOCKED":
            return VerificationConfirmResult(
                status="BLOCKED",
                errors=list(preview.errors),
            )
        if preview.status == "ALREADY_VERIFIED":
            return VerificationConfirmResult(
                status="BLOCKED",
                errors=["verification_already_exists_without_workflow_receipt"],
            )

        observation = AvailabilityObservation(
            opportunity_id=request.evidence.opportunity_id,
            observation_type=(
                "VERIFIED_OPEN"
                if request.evidence.decision == "OPEN"
                else "VERIFIED_CLOSED"
            ),
            observed_at=request.evidence.observed_at,
            evidence_source=request.evidence.evidence_source,
            source_url=request.evidence.source_url,
            note=request.evidence.note,
            evidence_kind=request.evidence.evidence_kind,
            confirmed_by=request.confirmed_by,
            confirmed_at=request.confirmed_at,
            preview_sha256=request.preview_sha256,
        )
        recorded = self.availability_repository.record_if_unchanged(
            observation,
            expected_observation_count=preview.observation_count,
            expected_latest_observation_at=preview.latest_observation_at,
        )
        if not recorded:
            observations = self.availability_repository.list_observations(
                request.evidence.opportunity_id
            )
            existing = _find_matching_observation(
                observations,
                request.evidence,
            )
            if existing is not None and existing.preview_sha256 is not None:
                return VerificationConfirmResult(
                    status="ALREADY_RECORDED",
                    receipt=_receipt_from_observation(
                        request.evidence,
                        existing,
                        processed_at=processed_at,
                    ),
                )
            return VerificationConfirmResult(
                status="BLOCKED_STALE_PREVIEW",
                errors=["stale_preview"],
            )

        return VerificationConfirmResult(
            status="RECORDED",
            receipt=_receipt_from_observation(
                request.evidence,
                observation,
                processed_at=processed_at,
                resulting_state=_current_availability_state(
                    self.availability_repository,
                    request.evidence.opportunity_id,
                ),
            ),
        )


def _find_matching_observation(
    observations: list[AvailabilityObservation],
    evidence: VerificationEvidence,
) -> AvailabilityObservation | None:
    expected_type = (
        "VERIFIED_OPEN"
        if evidence.decision == "OPEN"
        else "VERIFIED_CLOSED"
    )
    for observation in observations:
        if (
            observation.observation_type == expected_type
            and observation.observed_at == evidence.observed_at
            and observation.evidence_source == evidence.evidence_source
            and observation.source_url == evidence.source_url
            and observation.note == evidence.note
            and observation.evidence_kind == evidence.evidence_kind
        ):
            return observation
    return None


def _preview_sha256(
    *,
    evidence: VerificationEvidence,
    opportunity_payload: dict[str, object],
    availability: OpportunityAvailability | None,
) -> str:
    return canonical_sha256(
        {
            "preview_version": VERIFICATION_PREVIEW_VERSION,
            "evidence_sha256": evidence_sha256(evidence),
            "opportunity": opportunity_payload,
            "availability": (
                availability.model_dump(mode="json", exclude_none=False)
                if availability is not None
                else None
            ),
        }
    )


def _blocked_preview(
    evidence: VerificationEvidence,
    error: str,
) -> VerificationPreview:
    blocked_hash = canonical_sha256(
        {
            "preview_version": VERIFICATION_PREVIEW_VERSION,
            "evidence_sha256": evidence_sha256(evidence),
            "blocked": error,
        }
    )
    return VerificationPreview(
        status="BLOCKED",
        opportunity_id=evidence.opportunity_id,
        evidence_sha256=evidence_sha256(evidence),
        preview_sha256=blocked_hash,
        current_state="UNVERIFIED",
        proposed_state=(
            "VERIFIED_OPEN"
            if evidence.decision == "OPEN"
            else "VERIFIED_CLOSED"
        ),
        observation_count=0,
        latest_observation_at=None,
        errors=[error],
        external_actions=[],
    )



def _current_availability_state(
    repository: SQLiteAvailabilityRepository,
    opportunity_id: str,
) -> AvailabilityState:
    current = repository.get(opportunity_id)
    return (
        current.availability_state
        if current is not None
        else "UNVERIFIED"
    )

def _receipt_from_observation(
    evidence: VerificationEvidence,
    observation: AvailabilityObservation,
    *,
    processed_at: datetime,
    resulting_state: AvailabilityState,
) -> VerificationReceipt:
    if (
        observation.confirmed_by is None
        or observation.confirmed_at is None
        or observation.preview_sha256 is None
    ):
        raise ValueError("workflow verification observation missing confirmation provenance")
    digest = hashlib.sha256(
        evidence_sha256(evidence).encode("utf-8")
    ).hexdigest()
    return VerificationReceipt(
        receipt_id=f"availability-verification-{digest[:20]}",
        opportunity_id=evidence.opportunity_id,
        decision=evidence.decision,
        evidence_sha256=evidence_sha256(evidence),
        preview_sha256=observation.preview_sha256,
        confirmed_by=observation.confirmed_by,
        confirmed_at=observation.confirmed_at,
        processed_at=processed_at,
        resulting_state=resulting_state,
    )


def _aware_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)
