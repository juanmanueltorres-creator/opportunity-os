from datetime import datetime, timezone

import pytest

from app.adapters.gmail_content.models import GmailContentEnvelope
from app.adapters.gmail_read.models import GmailMessageEnvelope
from app.process_email.models import ProcessClassification, ProcessEmailSelection
from app.process_email.projector import ProcessEventProjector
from app.process_email.service import ProcessEmailService

NOW = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)


class Provider:
    async def get_message_content(self, message_id: str) -> GmailContentEnvelope:
        assert message_id == "m1"
        return GmailContentEnvelope(
            message=GmailMessageEnvelope(
                message_id="m1",
                thread_id="t1",
                internal_date=NOW,
                label_ids=("INBOX",),
                from_address="recruiter@example.com",
                to_addresses=("owner@example.com",),
            ),
            current_message_text="Automatic reply: I am out of the office until Monday.",
        )


class Classifier:
    def classify(self, text: str) -> ProcessClassification:
        assert text == "Automatic reply: I am out of the office until Monday."
        return ProcessClassification(disposition="NOT_PROCESS", signals=[])


class RepositoryBomb:
    def get_account(self, account_id: str):  # pragma: no cover - safety bomb
        raise AssertionError("NOT_PROCESS must not read relationship state")


class BridgeBomb:
    def preview(self, observation):  # pragma: no cover - safety bomb
        raise AssertionError("NOT_PROCESS must not reach operator bridge")


@pytest.mark.asyncio
async def test_not_process_returns_transient_preview_without_relationship_access() -> None:
    service = ProcessEmailService(
        Provider(),
        Classifier(),
        ProcessEventProjector(),
        owned_addresses={"owner@example.com"},
        relationship_repository=RepositoryBomb(),
        operator_bridge=BridgeBomb(),
    )

    result = await service.preview(
        ProcessEmailSelection(
            account_id="example-co",
            message_id="m1",
            selected_by="operator",
        )
    )

    assert result.status == "NOT_PROCESS"
    assert result.source_ref == "gmail:message:m1"
    assert result.observed_at == NOW
    assert result.signals == []
    assert result.proposed_observation is None
    assert result.operator_preview is None
    assert result.external_actions == []
