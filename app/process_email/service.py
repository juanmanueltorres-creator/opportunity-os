from __future__ import annotations

from app.adapters.gmail_content.provider import GmailContentProvider, GmailProviderError
from app.adapters.gmail_read.direction import is_inbound, normalize_owned_addresses
from app.operator_bridge.service import OperatorBridgeService
from app.process_email.classifier import ProcessClassifier
from app.process_email.models import (
    ProcessClassification,
    ProcessEmailPreview,
    ProcessEmailSelection,
)
from app.process_email.projector import ProcessEventProjector
from app.relationships.repository import SQLiteRelationshipRepository

_PROVIDER_ERRORS = {
    "gmail_unauthorized",
    "gmail_forbidden",
    "gmail_not_found",
    "gmail_rate_limited",
    "gmail_provider_error",
    "gmail_timeout",
}
_CONTENT_ERRORS = {
    "unsupported_mime",
    "missing_usable_body",
    "content_too_large",
    "quoted_content_ambiguous",
    "gmail_payload_invalid",
}
_MUTATION_SIGNAL_KINDS = {
    "INTERVIEW_PROPOSED",
    "STAGE_ADVANCED",
    "PROCESS_UPDATED",
    "OFFER_RECEIVED",
    "REJECTED",
}


def _merge_warnings(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for warning in group:
            if warning not in merged:
                merged.append(warning)
    return merged


def _needs_relationship_state(classification: ProcessClassification) -> bool:
    if classification.disposition != "CLASSIFIED":
        return False
    return any(
        signal.confidence in {"HIGH", "MEDIUM"}
        and signal.kind in _MUTATION_SIGNAL_KINDS
        for signal in classification.signals
    )


class ProcessEmailService:
    def __init__(
        self,
        content_provider: GmailContentProvider,
        classifier: ProcessClassifier,
        projector: ProcessEventProjector,
        *,
        owned_addresses: set[str] | frozenset[str],
        relationship_repository: SQLiteRelationshipRepository | None,
        operator_bridge: OperatorBridgeService | None,
    ) -> None:
        self.content_provider = content_provider
        self.classifier = classifier
        self.projector = projector
        self.owned_addresses = normalize_owned_addresses(owned_addresses)
        self.relationship_repository = relationship_repository
        self.operator_bridge = operator_bridge

    @staticmethod
    def _source_ref(message_id: str) -> str:
        return f"gmail:message:{message_id}"

    async def preview(self, selection: ProcessEmailSelection) -> ProcessEmailPreview:
        source_ref = self._source_ref(selection.message_id)
        try:
            content = await self.content_provider.get_message_content(selection.message_id)
        except GmailProviderError as exc:
            status = "CONTENT_UNAVAILABLE" if exc.code in _CONTENT_ERRORS else "PROVIDER_ERROR"
            if exc.code not in _CONTENT_ERRORS and exc.code not in _PROVIDER_ERRORS:
                status = "PROVIDER_ERROR"
            return ProcessEmailPreview(
                status=status,
                source_ref=source_ref,
                warnings=[exc.code],
                external_actions=[],
            )

        message = content.message
        observed_at = message.internal_date
        source_ref = self._source_ref(message.message_id)

        if not is_inbound(message, self.owned_addresses):
            return ProcessEmailPreview(
                status="INVALID_SELECTION",
                source_ref=source_ref,
                observed_at=observed_at,
                warnings=["message_not_inbound"],
                external_actions=[],
            )

        classification = self.classifier.classify(content.current_message_text)

        if classification.disposition == "NOT_PROCESS":
            return ProcessEmailPreview(
                status="NOT_PROCESS",
                classifier_version=classification.classifier_version,
                ruleset_version=classification.ruleset_version,
                source_ref=source_ref,
                observed_at=observed_at,
                signals=list(classification.signals),
                warnings=list(classification.warnings),
                external_actions=[],
            )

        if classification.disposition == "AMBIGUOUS":
            return ProcessEmailPreview(
                status="AMBIGUOUS",
                classifier_version=classification.classifier_version,
                ruleset_version=classification.ruleset_version,
                source_ref=source_ref,
                observed_at=observed_at,
                signals=list(classification.signals),
                warnings=list(classification.warnings),
                external_actions=[],
            )

        account = None
        if _needs_relationship_state(classification):
            if self.relationship_repository is not None:
                account = self.relationship_repository.get_account(selection.account_id)

        projection = self.projector.project(
            classification=classification,
            account=account,
            account_id=selection.account_id,
            contact_id=selection.contact_id,
            message_id=message.message_id,
            observed_at=observed_at,
        )

        if projection.proposed_observation is None:
            warnings = _merge_warnings(
                list(classification.warnings),
                list(projection.warnings),
            )
            status = (
                "BLOCKED"
                if "unknown_relationship_account" in warnings
                else "CLASSIFIED"
            )
            return ProcessEmailPreview(
                status=status,
                classifier_version=classification.classifier_version,
                ruleset_version=classification.ruleset_version,
                source_ref=source_ref,
                observed_at=observed_at,
                signals=list(classification.signals),
                warnings=warnings,
                external_actions=[],
            )

        if self.operator_bridge is None:
            return ProcessEmailPreview(
                status="BLOCKED",
                classifier_version=classification.classifier_version,
                ruleset_version=classification.ruleset_version,
                source_ref=source_ref,
                observed_at=observed_at,
                signals=list(classification.signals),
                warnings=_merge_warnings(
                    list(classification.warnings),
                    list(projection.warnings),
                    ["operator_bridge_unavailable"],
                ),
                external_actions=[],
            )

        operator_preview = self.operator_bridge.preview(projection.proposed_observation)
        if operator_preview.status == "BLOCKED":
            return ProcessEmailPreview(
                status="BLOCKED",
                classifier_version=classification.classifier_version,
                ruleset_version=classification.ruleset_version,
                source_ref=source_ref,
                observed_at=observed_at,
                signals=list(classification.signals),
                warnings=_merge_warnings(
                    list(classification.warnings),
                    list(projection.warnings),
                    list(operator_preview.errors),
                ),
                external_actions=[],
            )

        return ProcessEmailPreview(
            status="CLASSIFIED",
            classifier_version=classification.classifier_version,
            ruleset_version=classification.ruleset_version,
            source_ref=source_ref,
            observed_at=observed_at,
            signals=list(classification.signals),
            warnings=_merge_warnings(
                list(classification.warnings),
                list(projection.warnings),
            ),
            proposed_observation=projection.proposed_observation,
            operator_preview=operator_preview,
            external_actions=[],
        )
