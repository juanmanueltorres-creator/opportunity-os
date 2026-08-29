from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.relationships.context import SQLiteRelationshipMemory
from app.relationships.models import CareerContact, RelationshipAccount
from app.relationships.repository import SQLiteRelationshipRepository
from app.repositories.opportunities import SQLiteOpportunityRepository

NOW = datetime(2026, 8, 29, 7, 0, tzinfo=timezone.utc)


def _memory(tmp_path: Path) -> SQLiteRelationshipMemory:
    repo = SQLiteRelationshipRepository(tmp_path / "relationships.sqlite3")
    repo.initialize()
    repo.save_contact(
        CareerContact(
            contact_id="contact-1",
            account_id="account-1",
            person="Private Person",
            role="Recruiter",
            contact_type="RECRUITER",
            verification_status="VERIFIED",
            verification_source="private source",
            observed_at=NOW,
            disposition="AVAILABLE",
            channel_kind="email",
            channel_value="private@example.com",
            active=True,
        )
    )
    repo.save_account(
        RelationshipAccount(
            account_id="account-1",
            company="Example Co",
            preferred_next_contact_id="contact-1",
            updated_at=NOW,
        )
    )
    return SQLiteRelationshipMemory(repo)


def test_relationship_context_endpoints_are_redacted_and_read_only(tmp_path: Path) -> None:
    app = create_app(
        repository=SQLiteOpportunityRepository(tmp_path / "opportunities.sqlite3"),
        enable_default_radar=False,
        enable_default_targets=False,
        relationship_memory=_memory(tmp_path),
    )
    with TestClient(app) as client:
        single = client.get("/api/v1/relationships/account-1/context")
        collection = client.get("/api/v1/relationships/context")
        post = client.post("/api/v1/relationships/account-1/context")

    assert single.status_code == 200
    assert collection.status_code == 200
    assert post.status_code == 405
    serialized = f"{single.text}\n{collection.text}".lower()
    assert "private person" not in serialized
    assert "private@example.com" not in serialized
    assert "private source" not in serialized
    assert single.json()["account_id"] == "account-1"
    assert collection.json()["accounts"][0]["account_id"] == "account-1"


def test_missing_default_relationship_db_degrades_to_empty_memory_without_creating_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    relationship_path = tmp_path / "missing" / "relationships.local.sqlite3"
    monkeypatch.setenv("OPPORTUNITY_RELATIONSHIPS_PATH", str(relationship_path))
    app = create_app(
        repository=SQLiteOpportunityRepository(tmp_path / "opportunities.sqlite3"),
        enable_default_radar=False,
        enable_default_targets=False,
    )

    with TestClient(app) as client:
        health = client.get("/health")
        collection = client.get("/api/v1/relationships/context")

    assert health.status_code == 200
    assert collection.status_code == 200
    assert collection.json()["accounts"] == []
    assert relationship_path.exists() is False
