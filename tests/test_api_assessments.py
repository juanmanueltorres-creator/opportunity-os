from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.domain import CandidateProfile, EvidenceItem, Opportunity
from app.repositories.opportunities import SQLiteOpportunityRepository

NOW = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)


def test_assessment_endpoint_returns_explainable_components(tmp_path) -> None:
    repository = SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()
    opportunity, _ = repository.upsert(
        Opportunity(
            id="job-1",
            source="example",
            source_id="1",
            source_url="https://example.com/jobs/1",
            company="Example Co",
            title="Python GIS Developer",
            description="Build GIS services",
            discovered_at=NOW,
            required_skills=["python", "postgis"],
            remote_policy="remote",
        )
    )
    profile = CandidateProfile(
        name="Example Candidate",
        roles=["GIS Developer"],
        skills=["python"],
        domains=["gis"],
        remote_preferences=["remote"],
        evidence=[
            EvidenceItem(
                label="Python GIS project",
                type="project",
                skills=["python"],
                domains=["gis"],
                verified=True,
            )
        ],
    )
    client = TestClient(create_app(repository=repository, profile=profile))

    response = client.post(f"/api/v1/assessments/{opportunity.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["opportunity_id"] == opportunity.id
    assert body["mandatory_fit"] == 50.0
    assert set(["mandatory_fit", "domain_fit", "evidence_fit", "location_fit", "freshness_fit"]).issubset(body)
    assert body["strengths"] == ["python"]
    assert body["gaps"] == ["postgis"]
    assert body["evidence"][0]["label"] == "Python GIS project"
    assert body["recommendation"] in {"apply", "stretch", "nurture", "discard"}
    assert body["explanation"]


def test_assessment_missing_opportunity_returns_404(tmp_path) -> None:
    repository = SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()
    profile = CandidateProfile(name="Example", skills=["python"])
    client = TestClient(create_app(repository=repository, profile=profile))

    response = client.post("/api/v1/assessments/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Opportunity not found"}
