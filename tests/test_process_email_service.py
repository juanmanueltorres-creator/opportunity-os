from __future__ import annotations

from datetime import datetime, timezone
import logging

import pytest

from app.adapters.gmail_content.models import GmailContentEnvelope
from app.adapters.gmail_content.provider import GmailProviderError
from app.adapters.gmail_read.models import GmailMessageEnvelope
from app.operator_bridge.models import ObservationPreview, observation_sha256
from app.process_email.models import (
    EvidenceSpan,
    ProcessClassification,
    ProcessEmailSelection,
    ProcessSignal,
)
from app.process_email.projector import ProcessEventProjector
from app.process_email.service import ProcessEmailService
from app.relationships.models import RelationshipAccount

NOW = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)

_REASON_CODE = {
    "APPLICATION_ACKNOWLEDGED": "APPLICATION_RECEIPT_EXPLICIT",
    "INTERVIEW_PROPOSED": "INTERVIEW_INVITATION_EXPLICIT",
    "PROCESS_UPDATED": "PROCESS_RESCHEDULE_EXPLICIT",
    "REJECTED": "REJECTION_EXPLICIT",
}


class FakeContentProvider:
    def __init__(self, envelope: GmailContentEnvelope | None = None, error: str | None = None):
        self.envelope = envelope
        self.error = error
        self.calls: list[str] = []

    async def get_message_content(self, message_id: str) -> GmailContentEnvelope:
        self.calls.append(message_id)
        if self.error is not None:
            raise GmailProviderError(self.error)
        assert self.envelope is not None
        return self.envelope


class CountingClassifier:
    def __init__(self, result: ProcessClassification):
        self.result = result
        self.calls: list[str] = []

    def classify(self, text: str) -> ProcessClassification:
        self.calls.append(text)
        return self.result


class FakeRelationshipRepository:
    def __init__(self, account: RelationshipAccount | None):
        self.account = account
        self.get_account_calls: list[str] = []
        self.write_calls: list[str] = []

    def get_account(self, account_id: str) -> RelationshipAccount | None:
        self.get_account_calls.append(account_id)
        return self.account

    def save_account(self, *args, **kwargs):  # pragma: no cover - safety bomb
        self.write_calls.append("save_account")
        raise AssertionError("preview must not write relationship state")

    def append_event(self, *args, **kwargs):  # pragma: no cover - safety bomb
        self.write_calls.append("append_event")
        raise AssertionError("preview must not append relationship events")

    def apply_event_transaction(self, *args, **kwargs):  # pragma: no cover - safety bomb
        self.write_calls.append("apply_event_transaction")
        raise AssertionError("preview must not apply relationship events")


class FakeOperatorBridge:
    def __init__(self, *, blocked: bool = False):
        self.blocked = blocked
        self.preview_calls = []
        self.import_calls = 0

    def preview(self, observation):
        self.preview_calls.append(observation)
        return ObservationPreview(
            preview_version="operator-preview-v1",
            status="BLOCKED" if self.blocked else "IMPORTABLE",
            observation_id=observation.observation_id,
            observation_sha256=observation_sha256(observation),
            preview_sha256="b" * 64,
            account_id=observation.account_id,
            contact_id=observation.contact_id,
            event_kind=observation.kind,
            source_type=observation.source_type,
            source_name=observation.source_name,
            source_ref=observation.source_ref,
            reason=observation.reason,
            errors=["invalid_relationship_transition"] if self.blocked else [],
            external_actions=[],
        )

    def import_observation(self, *args, **kwargs):  # pragma: no cover - safety bomb
        self.import_calls += 1
        raise AssertionError("process email preview must never import")


def _message(*, inbound: bool = True, body: str = "body") -> GmailContentEnvelope:
    if inbound:
        message = GmailMessageEnvelope(
            message_id="m1",
            thread_id="t1",
            internal_date=NOW,
            label_ids=("INBOX",),
            from_address="recruiter@example.com",
            to_addresses=("owner@example.com",),
            subject="SUBJECT_PRIVATE_SENTINEL",
        )
    else:
        message = GmailMessageEnvelope(
            message_id="m1",
            thread_id="t1",
            internal_date=NOW,
            label_ids=("SENT",),
            from_address="owner@example.com",
            to_addresses=("recruiter@example.com",),
            subject="SUBJECT_PRIVATE_SENTINEL",
        )
    return GmailContentEnvelope(message=message, current_message_text=body)


def _signal(kind: str, *, confidence: str = "HIGH", evidence: str | None = None) -> ProcessSignal:
    text = evidence or kind.lower().replace("_", " ")
    return ProcessSignal(
        kind=kind,
        confidence=confidence,
        reason_code=_REASON_CODE[kind],
        evidence_spans=[EvidenceSpan(start=0, end=len(text), text=text)],
    )


def _classified(*signals: ProcessSignal, warnings: list[str] | None = None) -> ProcessClassification:
    return ProcessClassification(
        disposition="CLASSIFIED",
        signals=list(signals),
        warnings=list(warnings or []),
    )


def _ambiguous() -> ProcessClassification:
    return ProcessClassification(
        disposition="AMBIGUOUS",
        signals=[_signal("INTERVIEW_PROPOSED"), _signal("REJECTED")],
        warnings=["conflicting_process_signals"],
    )


def _account(*, open_process: bool) -> RelationshipAccount:
    return RelationshipAccount(
        account_id="example-co",
        company="Example Co",
        relationship_state="PROCESS_OPEN" if open_process else "PROCESS_CLOSED",
        open_process=open_process,
        updated_at=NOW,
    )


def _selection() -> ProcessEmailSelection:
    return ProcessEmailSelection(
        account_id="example-co",
        contact_id="contact-1",
        message_id="m1",
        selected_by="operator",
    )


def _service(
    *,
    envelope: GmailContentEnvelope | None = None,
    provider_error: str | None = None,
    classification: ProcessClassification,
    account: RelationshipAccount | None = None,
    operator_bridge: FakeOperatorBridge | None = None,
):
    provider = FakeContentProvider(envelope=envelope, error=provider_error)
    classifier = CountingClassifier(classification)
    repository = FakeRelationshipRepository(account)
    service = ProcessEmailService(
        provider,
        classifier,
        ProcessEventProjector(),
        owned_addresses={"OWNER@example.com"},
        relationship_repository=repository,
        operator_bridge=operator_bridge,
    )
    return service, provider, classifier, repository


@pytest.mark.asyncio
async def test_inbound_interview_reads_exact_message_and_returns_existing_operator_preview() -> None:
    body = "We would like to invite you to an interview."
    bridge = FakeOperatorBridge()
    service, provider, classifier, repository = _service(
        envelope=_message(body=body),
        classification=_classified(_signal("INTERVIEW_PROPOSED", evidence=body)),
        account=_account(open_process=False),
        operator_bridge=bridge,
    )

    result = await service.preview(_selection())

    assert provider.calls == ["m1"]
    assert classifier.calls == [body]
    assert repository.get_account_calls == ["example-co"]
    assert result.status == "CLASSIFIED"
    assert result.source_ref == "gmail:message:m1"
    assert result.observed_at == NOW
    assert [signal.kind for signal in result.signals] == ["INTERVIEW_PROPOSED"]
    assert result.proposed_observation is not None
    assert result.proposed_observation.kind == "PROCESS_OPENED"
    assert result.operator_preview is not None
    assert result.operator_preview.status == "IMPORTABLE"
    assert bridge.preview_calls == [result.proposed_observation]
    assert bridge.import_calls == 0
    assert result.external_actions == []


@pytest.mark.asyncio
async def test_outbound_message_is_invalid_before_classifier_or_relationship_lookup() -> None:
    classification = _classified(_signal("INTERVIEW_PROPOSED"))
    service, provider, classifier, repository = _service(
        envelope=_message(inbound=False),
        classification=classification,
        account=_account(open_process=False),
        operator_bridge=FakeOperatorBridge(),
    )

    result = await service.preview(_selection())

    assert provider.calls == ["m1"]
    assert classifier.calls == []
    assert repository.get_account_calls == []
    assert result.status == "INVALID_SELECTION"
    assert result.warnings == ["message_not_inbound"]
    assert result.proposed_observation is None
    assert result.operator_preview is None


@pytest.mark.asyncio
async def test_ack_only_is_classified_but_non_mutating_and_does_not_read_relationship_state() -> None:
    body = "We received your application."
    service, _, classifier, repository = _service(
        envelope=_message(body=body),
        classification=_classified(_signal("APPLICATION_ACKNOWLEDGED", evidence=body)),
        operator_bridge=FakeOperatorBridge(),
    )

    result = await service.preview(_selection())

    assert classifier.calls == [body]
    assert repository.get_account_calls == []
    assert result.status == "CLASSIFIED"
    assert result.proposed_observation is None
    assert result.operator_preview is None


@pytest.mark.asyncio
async def test_low_only_is_non_mutating_without_relationship_lookup() -> None:
    classification = _classified(
        _signal("PROCESS_UPDATED", confidence="LOW"),
        warnings=["low_confidence_only"],
    )
    service, _, _, repository = _service(
        envelope=_message(),
        classification=classification,
        operator_bridge=FakeOperatorBridge(),
    )

    result = await service.preview(_selection())

    assert repository.get_account_calls == []
    assert result.status == "CLASSIFIED"
    assert result.warnings == ["low_confidence_only"]
    assert result.proposed_observation is None


@pytest.mark.asyncio
async def test_ambiguous_conflict_returns_transient_signals_without_relationship_lookup() -> None:
    service, _, _, repository = _service(
        envelope=_message(),
        classification=_ambiguous(),
        operator_bridge=FakeOperatorBridge(),
    )

    result = await service.preview(_selection())

    assert repository.get_account_calls == []
    assert result.status == "AMBIGUOUS"
    assert [signal.kind for signal in result.signals] == ["INTERVIEW_PROPOSED", "REJECTED"]
    assert result.warnings == ["conflicting_process_signals"]
    assert result.proposed_observation is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "warning"),
    [
        ("PROCESS_UPDATED", "no_open_process_to_update"),
        ("REJECTED", "no_open_process_to_close"),
    ],
)
async def test_closed_process_blocks_update_or_rejection_candidate(kind: str, warning: str) -> None:
    service, _, _, repository = _service(
        envelope=_message(),
        classification=_classified(_signal(kind)),
        account=_account(open_process=False),
        operator_bridge=FakeOperatorBridge(),
    )

    result = await service.preview(_selection())

    assert repository.get_account_calls == ["example-co"]
    assert result.status == "CLASSIFIED"
    assert result.warnings == [warning]
    assert result.proposed_observation is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        "gmail_unauthorized",
        "gmail_forbidden",
        "gmail_not_found",
        "gmail_rate_limited",
        "gmail_provider_error",
        "gmail_timeout",
    ],
)
async def test_provider_failures_map_to_provider_error_without_classifier_call(code: str) -> None:
    service, provider, classifier, repository = _service(
        provider_error=code,
        classification=_classified(_signal("INTERVIEW_PROPOSED")),
    )

    result = await service.preview(_selection())

    assert provider.calls == ["m1"]
    assert classifier.calls == []
    assert repository.get_account_calls == []
    assert result.status == "PROVIDER_ERROR"
    assert result.warnings == [code]
    assert result.proposed_observation is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        "unsupported_mime",
        "missing_usable_body",
        "content_too_large",
        "quoted_content_ambiguous",
        "gmail_payload_invalid",
    ],
)
async def test_content_failures_map_to_content_unavailable(code: str) -> None:
    service, _, classifier, repository = _service(
        provider_error=code,
        classification=_classified(_signal("INTERVIEW_PROPOSED")),
    )

    result = await service.preview(_selection())

    assert classifier.calls == []
    assert repository.get_account_calls == []
    assert result.status == "CONTENT_UNAVAILABLE"
    assert result.warnings == [code]
    assert result.proposed_observation is None


@pytest.mark.asyncio
async def test_missing_relationship_account_blocks_mutation_candidate() -> None:
    service, _, _, repository = _service(
        envelope=_message(),
        classification=_classified(_signal("INTERVIEW_PROPOSED")),
        account=None,
        operator_bridge=FakeOperatorBridge(),
    )

    result = await service.preview(_selection())

    assert repository.get_account_calls == ["example-co"]
    assert result.status == "BLOCKED"
    assert result.warnings == ["unknown_relationship_account"]
    assert result.proposed_observation is None


@pytest.mark.asyncio
async def test_missing_operator_bridge_blocks_only_when_mutation_candidate_exists() -> None:
    service, _, _, repository = _service(
        envelope=_message(),
        classification=_classified(_signal("INTERVIEW_PROPOSED")),
        account=_account(open_process=False),
        operator_bridge=None,
    )

    result = await service.preview(_selection())

    assert repository.get_account_calls == ["example-co"]
    assert result.status == "BLOCKED"
    assert result.warnings == ["operator_bridge_unavailable"]
    assert result.proposed_observation is None
    assert result.operator_preview is None


@pytest.mark.asyncio
async def test_operator_bridge_block_is_propagated_without_import() -> None:
    bridge = FakeOperatorBridge(blocked=True)
    service, _, _, repository = _service(
        envelope=_message(),
        classification=_classified(_signal("INTERVIEW_PROPOSED")),
        account=_account(open_process=False),
        operator_bridge=bridge,
    )

    result = await service.preview(_selection())

    assert repository.get_account_calls == ["example-co"]
    assert result.status == "BLOCKED"
    assert result.warnings == ["invalid_relationship_transition"]
    assert result.proposed_observation is None
    assert result.operator_preview is None
    assert bridge.import_calls == 0


@pytest.mark.asyncio
async def test_preview_never_writes_or_exposes_import_method() -> None:
    bridge = FakeOperatorBridge()
    service, _, _, repository = _service(
        envelope=_message(),
        classification=_classified(_signal("INTERVIEW_PROPOSED")),
        account=_account(open_process=False),
        operator_bridge=bridge,
    )

    await service.preview(_selection())

    assert repository.write_calls == []
    assert bridge.import_calls == 0
    assert not hasattr(service, "import_observation")
    assert not hasattr(service, "import_process_email")


@pytest.mark.asyncio
async def test_logs_never_contain_subject_body_or_evidence_text(caplog) -> None:
    body = "BODY_PRIVATE_SENTINEL"
    evidence = "EVIDENCE_PRIVATE_SENTINEL"
    bridge = FakeOperatorBridge()
    service, _, _, _ = _service(
        envelope=_message(body=body),
        classification=_classified(_signal("INTERVIEW_PROPOSED", evidence=evidence)),
        account=_account(open_process=False),
        operator_bridge=bridge,
    )

    with caplog.at_level(logging.DEBUG):
        result = await service.preview(_selection())

    assert result.status == "CLASSIFIED"
    assert "SUBJECT_PRIVATE_SENTINEL" not in caplog.text
    assert body not in caplog.text
    assert evidence not in caplog.text
