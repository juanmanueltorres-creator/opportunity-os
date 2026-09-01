from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.process_email.models import ProcessEmailPreview, ProcessEmailSelection
from app.repositories.opportunities import SQLiteOpportunityRepository

NOW = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)


class FakeProcessEmailService:
    def __init__(self) -> None:
        self.selections: list[ProcessEmailSelection] = []

    async def preview(self, selection: ProcessEmailSelection) -> ProcessEmailPreview:
        self.selections.append(selection)
        return ProcessEmailPreview(
            status="NOT_PROCESS",
            source_ref=f"gmail:message:{selection.message_id}",
            observed_at=NOW,
            signals=[],
            warnings=[],
            external_actions=[],
        )


def _app(tmp_path: Path, **kwargs):
    return create_app(
        repository=SQLiteOpportunityRepository(tmp_path / "opportunities.sqlite3"),
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
        enable_operator_import=False,
        enable_gmail_read=False,
        **kwargs,
    )


def test_process_email_route_is_absent_by_default(tmp_path: Path) -> None:
    app = _app(tmp_path)

    assert "/api/v1/process-email/preview" not in app.openapi()["paths"]
    assert "/api/v1/process-email/import" not in app.openapi()["paths"]


def test_enabled_without_injected_service_returns_safe_503(tmp_path: Path) -> None:
    app = _app(tmp_path, enable_process_email=True)

    assert "/api/v1/process-email/preview" in app.openapi()["paths"]
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/process-email/preview",
            json={
                "account_id": "example-co",
                "message_id": "m1",
                "selected_by": "operator",
            },
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "process_email_unavailable"}


def test_enabled_route_passes_exact_typed_selection_to_injected_service(tmp_path: Path) -> None:
    service = FakeProcessEmailService()
    app = _app(
        tmp_path,
        process_email_service=service,
        enable_process_email=True,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/process-email/preview",
            json={
                "account_id": "example-co",
                "contact_id": "contact-1",
                "message_id": "m1",
                "selected_by": "operator",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "NOT_PROCESS"
    assert response.json()["external_actions"] == []
    assert service.selections == [
        ProcessEmailSelection(
            account_id="example-co",
            contact_id="contact-1",
            message_id="m1",
            selected_by="operator",
        )
    ]
    assert "/api/v1/process-email/import" not in app.openapi()["paths"]


def test_process_email_env_flag_enables_only_when_true(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPPORTUNITY_PROCESS_EMAIL_ENABLED", "yes")
    app = _app(tmp_path, process_email_service=FakeProcessEmailService())

    assert "/api/v1/process-email/preview" in app.openapi()["paths"]


def test_process_email_env_flag_rejects_invalid_boolean(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPPORTUNITY_PROCESS_EMAIL_ENABLED", "maybe")

    with pytest.raises(ValueError, match="OPPORTUNITY_PROCESS_EMAIL_ENABLED must be boolean"):
        _app(tmp_path)
