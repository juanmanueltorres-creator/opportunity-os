from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.connectors.base import ConnectorError
from app.main import create_app
from app.models.domain import Opportunity
from app.repositories.opportunities import SQLiteOpportunityRepository

NOW = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)


def _repository(tmp_path) -> SQLiteOpportunityRepository:
    repository = SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()
    return repository


def _job() -> Opportunity:
    return Opportunity(
        id="remotive:1",
        source="remotive",
        source_id="1",
        source_url="https://remotive.com/jobs/1",
        company="Example Co",
        title="Geospatial Developer",
        description="Build GIS tools",
        discovered_at=NOW,
        remote_policy="remote",
    )


def test_remotive_ingestion_endpoint_returns_created_and_existing_counts(tmp_path) -> None:
    repository = _repository(tmp_path)

    class FakeConnector:
        async def fetch(self) -> list[Opportunity]:
            return [_job()]

    client = TestClient(create_app(repository=repository, remotive_connector=FakeConnector()))

    first = client.post("/api/v1/ingest/remotive")
    second = client.post("/api/v1/ingest/remotive")

    assert first.status_code == 200
    assert first.json() == {"created": 1, "existing": 0}
    assert second.status_code == 200
    assert second.json() == {"created": 0, "existing": 1}


def test_connector_error_maps_to_public_safe_502(tmp_path) -> None:
    repository = _repository(tmp_path)
    raw_message = "internal upstream detail that must not leak"

    class FailingConnector:
        async def fetch(self) -> list[Opportunity]:
            raise ConnectorError(raw_message)

    client = TestClient(create_app(repository=repository, remotive_connector=FailingConnector()))

    response = client.post("/api/v1/ingest/remotive")

    assert response.status_code == 502
    assert response.json() == {"detail": "Upstream job source unavailable"}
    assert raw_message not in response.text
