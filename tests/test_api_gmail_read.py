from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.adapters.gmail_read.models import GmailObservationResult, GmailReadSelection
from app.main import create_app
from app.operator_bridge.models import OperatorObservation
from app.relationships.repository import SQLiteRelationshipRepository
from app.repositories.opportunities import SQLiteOpportunityRepository

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


class FakeGmailReadService:
    def __init__(self) -> None:
        self.selections: list[GmailReadSelection] = []

    async def observe(self, selection: GmailReadSelection) -> GmailObservationResult:
        self.selections.append(selection)
        observation = OperatorObservation(
            observation_id="gmail-message:m1:message-sent",
            source_type="EMAIL_PROVIDER",
            source_name="gmail",
            source_ref="gmail:message:m1",
            kind="MESSAGE_SENT",
            account_id=selection.account_id,
            contact_id=selection.contact_id,
            observed_at=NOW,
            reason="selected Gmail message is confirmed in Sent",
        )
        return GmailObservationResult(
            status="OBSERVATION_READY",
            observation=observation,
            source_ref="gmail:message:m1",
        )


def _app(tmp_path: Path, **kwargs):
    return create_app(
        repository=SQLiteOpportunityRepository(tmp_path / "opportunities.sqlite3"),
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
        **kwargs,
    )


def test_gmail_read_route_is_absent_by_default(tmp_path: Path) -> None:
    app = _app(tmp_path)
    assert "/api/v1/adapters/gmail/observe" not in app.openapi()["paths"]


def test_enabled_without_injected_service_returns_safe_503(tmp_path: Path) -> None:
    app = _app(tmp_path, enable_gmail_read=True)
    assert "/api/v1/adapters/gmail/observe" in app.openapi()["paths"]

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/adapters/gmail/observe",
            json={
                "account_id": "example-co",
                "message_id": "m1",
                "selected_by": "operator",
            },
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "gmail_read_unavailable"}


def test_enabled_route_returns_observation_from_injected_service(tmp_path: Path) -> None:
    service = FakeGmailReadService()
    app = _app(
        tmp_path,
        gmail_read_service=service,
        enable_gmail_read=True,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/adapters/gmail/observe",
            json={
                "account_id": "example-co",
                "contact_id": "contact-1",
                "message_id": "m1",
                "selected_by": "operator",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "OBSERVATION_READY"
    assert payload["observation"]["kind"] == "MESSAGE_SENT"
    assert payload["observation"]["account_id"] == "example-co"
    assert payload["external_actions"] == []
    rendered = str(payload).lower()
    for forbidden in ("raw_payload", "message_body", "access_token"):
        assert forbidden not in rendered
    assert len(service.selections) == 1
    assert service.selections[0].message_id == "m1"


def test_observe_does_not_mutate_relationship_memory(tmp_path: Path) -> None:
    relationship_repo = SQLiteRelationshipRepository(tmp_path / "relationships.sqlite3")
    relationship_repo.initialize()
    before = relationship_repo.list_events("example-co")

    service = FakeGmailReadService()
    app = _app(
        tmp_path,
        gmail_read_service=service,
        enable_gmail_read=True,
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/adapters/gmail/observe",
            json={
                "account_id": "example-co",
                "message_id": "m1",
                "selected_by": "operator",
            },
        )

    assert response.status_code == 200
    assert relationship_repo.list_events("example-co") == before == []
