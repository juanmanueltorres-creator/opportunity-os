from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.operator_bridge.service import OperatorBridgeService
from app.relationships.models import RelationshipAccount
from app.relationships.repository import SQLiteRelationshipRepository
from app.relationships.service import RelationshipService
from app.repositories.opportunities import SQLiteOpportunityRepository

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def _operator_service(tmp_path: Path) -> tuple[OperatorBridgeService, SQLiteRelationshipRepository]:
    relationships_repo = SQLiteRelationshipRepository(tmp_path / "relationships.sqlite3")
    relationships_repo.initialize()
    relationships = RelationshipService(relationships_repo)
    relationships.register_account(
        RelationshipAccount(
            account_id="example-co",
            company="Example Co",
            updated_at=NOW - timedelta(days=1),
        )
    )
    return OperatorBridgeService(relationships_repo, relationships), relationships_repo


def _observation_payload() -> dict[str, object]:
    return {
        "observation_id": "provider-message-1",
        "source_type": "EMAIL_PROVIDER",
        "source_name": "gmail",
        "source_ref": "message:provider-message-1",
        "kind": "MESSAGE_SENT",
        "account_id": "example-co",
        "observed_at": NOW.isoformat(),
        "reason": "authorized normalized fact",
    }


def test_operator_routes_are_absent_by_default(tmp_path: Path) -> None:
    app = create_app(
        repository=SQLiteOpportunityRepository(tmp_path / "opportunities.sqlite3"),
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )

    assert not any(
        path.startswith("/api/v1/operator/")
        for path in app.openapi()["paths"]
    )


def test_relationship_routes_remain_get_only(tmp_path: Path) -> None:
    app = create_app(
        repository=SQLiteOpportunityRepository(tmp_path / "opportunities.sqlite3"),
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )
    relationship_paths = {
        path: operations
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/v1/relationships")
    }

    assert set(relationship_paths) == {
        "/api/v1/relationships/context",
        "/api/v1/relationships/{account_id}/context",
    }
    for operations in relationship_paths.values():
        assert set(operations).isdisjoint({"post", "put", "patch", "delete"})


def test_enabled_preview_and_import_are_redacted_and_local_only(tmp_path: Path) -> None:
    bridge, relationship_repo = _operator_service(tmp_path)
    app = create_app(
        repository=SQLiteOpportunityRepository(tmp_path / "opportunities.sqlite3"),
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
        operator_bridge_service=bridge,
        enable_operator_import=True,
    )

    with TestClient(app) as client:
        preview_response = client.post(
            "/api/v1/operator/observations/preview",
            json=_observation_payload(),
        )
        assert preview_response.status_code == 200
        preview = preview_response.json()
        assert preview["status"] == "IMPORTABLE"
        assert relationship_repo.list_events("example-co") == []

        import_response = client.post(
            "/api/v1/operator/observations/import",
            json={
                "observation": _observation_payload(),
                "preview_sha256": preview["preview_sha256"],
                "confirmed_by": "operator",
                "confirmed_at": NOW.isoformat(),
            },
        )
        assert import_response.status_code == 200
        assert import_response.json()["status"] == "IMPORTED"
        assert len(relationship_repo.list_events("example-co")) == 1

        retry_response = client.post(
            "/api/v1/operator/observations/import",
            json={
                "observation": _observation_payload(),
                "preview_sha256": preview["preview_sha256"],
                "confirmed_by": "operator",
                "confirmed_at": NOW.isoformat(),
            },
        )
        assert retry_response.status_code == 200
        assert retry_response.json()["status"] == "ALREADY_IMPORTED"
        assert len(relationship_repo.list_events("example-co")) == 1

    rendered = str(preview_response.json()).lower() + str(import_response.json()).lower()
    for forbidden in ("person", "channel_value", "body", "raw_payload"):
        assert forbidden not in rendered


def test_enabled_without_existing_relationship_storage_returns_safe_503_and_creates_nothing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    missing = tmp_path / "missing-relationships.sqlite3"
    monkeypatch.setenv("OPPORTUNITY_RELATIONSHIPS_PATH", str(missing))
    app = create_app(
        repository=SQLiteOpportunityRepository(tmp_path / "opportunities.sqlite3"),
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
        enable_operator_import=True,
    )

    with TestClient(app) as client:
        preview = client.post(
            "/api/v1/operator/observations/preview",
            json=_observation_payload(),
        )
        imported = client.post(
            "/api/v1/operator/observations/import",
            json={
                "observation": _observation_payload(),
                "preview_sha256": "a" * 64,
                "confirmed_by": "operator",
                "confirmed_at": NOW.isoformat(),
            },
        )

    assert preview.status_code == 503
    assert preview.json()["detail"] == "relationship_storage_unavailable"
    assert imported.status_code == 503
    assert imported.json()["detail"] == "relationship_storage_unavailable"
    assert not missing.exists()
