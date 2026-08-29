from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.domain import CandidateProfile
from app.repositories.opportunities import SQLiteOpportunityRepository
from app.targets.models import TargetAccountBatch, TargetAccountPolicy


class FakeTargetService:
    def run(self, profile: CandidateProfile, *, now: datetime) -> TargetAccountBatch:
        return TargetAccountBatch(
            policy=TargetAccountPolicy(),
            profile_fingerprint="profile",
            generated_at=now,
            items=[],
        )


def test_target_radar_requires_profile(tmp_path) -> None:
    app = create_app(
        repository=SQLiteOpportunityRepository(tmp_path / "db.sqlite3"),
        profile=None,
        enable_default_radar=False,
        target_service=FakeTargetService(),
    )
    with TestClient(app) as client:
        response = client.post("/api/v1/targets/radar/run")
    assert response.status_code == 503
    assert response.json()["detail"] == "Candidate profile unavailable"


def test_target_radar_requires_target_service(tmp_path) -> None:
    app = create_app(
        repository=SQLiteOpportunityRepository(tmp_path / "db.sqlite3"),
        profile=CandidateProfile(name="Candidate", skills=["python"]),
        enable_default_radar=False,
        target_service=None,
    )
    with TestClient(app) as client:
        response = client.post("/api/v1/targets/radar/run")
    assert response.status_code == 503
    assert response.json()["detail"] == "Target account registry unavailable"


def test_target_radar_returns_strict_batch_without_outreach_side_effect(tmp_path) -> None:
    app = create_app(
        repository=SQLiteOpportunityRepository(tmp_path / "db.sqlite3"),
        profile=CandidateProfile(name="Candidate", skills=["python"]),
        enable_default_radar=False,
        target_service=FakeTargetService(),
    )
    with TestClient(app) as client:
        response = client.post("/api/v1/targets/radar/run")
    assert response.status_code == 200
    assert response.json()["profile_fingerprint"] == "profile"
    assert response.json()["items"] == []
