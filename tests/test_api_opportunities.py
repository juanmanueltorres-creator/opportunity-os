from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.domain import Opportunity
from app.repositories.opportunities import SQLiteOpportunityRepository

NOW = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)


def _repository(tmp_path) -> SQLiteOpportunityRepository:
    repository = SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()
    return repository


def _opportunity() -> Opportunity:
    return Opportunity(
        id="job-1",
        source="example",
        source_id="1",
        source_url="https://example.com/jobs/1",
        company="Example Mapping Co",
        title="GIS Developer",
        description="Build GIS tools",
        discovered_at=NOW,
        required_skills=["python"],
    )


def test_list_and_detail_use_stable_opportunity_contracts(tmp_path) -> None:
    repository = _repository(tmp_path)
    stored, _ = repository.upsert(_opportunity())
    client = TestClient(create_app(repository=repository))

    list_response = client.get("/api/v1/opportunities")
    detail_response = client.get(f"/api/v1/opportunities/{stored.id}")

    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == stored.id
    assert list_response.json()[0]["required_skills"] == ["python"]
    assert detail_response.status_code == 200
    assert detail_response.json()["company"] == "Example Mapping Co"


def test_missing_opportunity_returns_stable_404(tmp_path) -> None:
    repository = _repository(tmp_path)
    client = TestClient(create_app(repository=repository))

    response = client.get("/api/v1/opportunities/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Opportunity not found"}
