from __future__ import annotations

from datetime import datetime

from app.operator_bridge.models import (
    ObservationSemanticProvenance,
    OperatorObservation,
)
from app.process_email.models import ProcessClassification, ProcessProjection, ProcessSignal
from app.relationships.models import RelationshipAccount

_PRIORITY = {
    "OFFER_RECEIVED": 5,
    "STAGE_ADVANCED": 4,
    "INTERVIEW_PROPOSED": 3,
    "PROCESS_UPDATED": 2,
    "APPLICATION_ACKNOWLEDGED": 1,
}

_REASON = {
    "INTERVIEW_PROPOSED": "explicit interview invitation observed",
    "STAGE_ADVANCED": "explicit hiring-stage advancement observed",
    "PROCESS_UPDATED": "explicit hiring-process update observed",
    "OFFER_RECEIVED": "explicit employment offer observed",
    "REJECTED": "explicit process rejection observed",
}


class ProcessEventProjector:
    def project(
        self,
        *,
        classification: ProcessClassification,
        account: RelationshipAccount | None,
        account_id: str,
        contact_id: str | None,
        message_id: str,
        observed_at: datetime,
    ) -> ProcessProjection:
        if classification.disposition != "CLASSIFIED":
            return ProcessProjection(warnings=list(classification.warnings))

        eligible = [
            signal
            for signal in classification.signals
            if signal.confidence in {"HIGH", "MEDIUM"}
        ]
        if not eligible:
            warnings = list(classification.warnings)
            if "low_confidence_only" not in warnings:
                warnings.append("low_confidence_only")
            return ProcessProjection(warnings=warnings)

        driving = self._driving_signal(eligible)
        if driving.kind == "APPLICATION_ACKNOWLEDGED":
            return ProcessProjection(warnings=list(classification.warnings))

        if account is None:
            warnings = list(classification.warnings)
            warnings.append("unknown_relationship_account")
            return ProcessProjection(warnings=warnings)

        event_kind, warning = self._event_kind(driving, account)
        if event_kind is None:
            warnings = list(classification.warnings)
            if warning is not None:
                warnings.append(warning)
            return ProcessProjection(warnings=warnings)

        observation = OperatorObservation(
            observation_id=(
                f"gmail-message:{message_id}:process-signal:{driving.kind}"
            ),
            source_type="EMAIL_PROVIDER",
            source_name="gmail",
            source_ref=f"gmail:message:{message_id}",
            kind=event_kind,
            account_id=account_id,
            contact_id=contact_id,
            observed_at=observed_at,
            reason=_REASON[driving.kind],
            semantic_provenance=ObservationSemanticProvenance(
                producer="PROCESS_EMAIL_CLASSIFIER",
                producer_version=classification.classifier_version,
                policy_version=classification.ruleset_version,
                classification=driving.kind,
                reason_code=driving.reason_code,
            ),
        )
        return ProcessProjection(
            proposed_observation=observation,
            warnings=list(classification.warnings),
        )

    @staticmethod
    def _driving_signal(signals: list[ProcessSignal]) -> ProcessSignal:
        rejected = next((signal for signal in signals if signal.kind == "REJECTED"), None)
        if rejected is not None:
            return rejected
        return max(signals, key=lambda signal: _PRIORITY[signal.kind])

    @staticmethod
    def _event_kind(
        signal: ProcessSignal,
        account: RelationshipAccount,
    ) -> tuple[str | None, str | None]:
        if signal.kind in {"INTERVIEW_PROPOSED", "STAGE_ADVANCED", "OFFER_RECEIVED"}:
            if account.open_process:
                return "PROCESS_UPDATED", None
            return "PROCESS_OPENED", None

        if signal.kind == "PROCESS_UPDATED":
            if not account.open_process:
                return None, "no_open_process_to_update"
            return "PROCESS_UPDATED", None

        if signal.kind == "REJECTED":
            if not account.open_process:
                return None, "no_open_process_to_close"
            return "PROCESS_CLOSED", None

        return None, None
