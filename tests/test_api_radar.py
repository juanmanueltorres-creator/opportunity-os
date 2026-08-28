from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.domain import CandidateProfile
from app.radar.models import DailyRadarBatch, SourceDiagnostic
from app.radar.service import RadarSourceError
from app.repositories.opportunities import SQLiteOpportunityRepository

NOW = datetime(2026, 8, 28, 21, 30, tzinfo=timezone.utc)


class FakeRadarService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.run_calls = 0

    async def run(self, profile: CandidateProfile, *, now: datetime) -> DailyRadarBatch:
        self.run_calls += 1
        if self.error is not None:
            raise self.error
        return DailyRadarBatch(
            batch_id="batch:test",
            generated_at=now,
            policy={"max_items": 20, "selection_mode": "income_first"},
            profile_fingerprint="sha256:test",
            scoring_version="v0.2a1",
            extractor_version="rules-v1",
            alias_registry_version="1",
            taxonomy_versions={},
            items=[],
            count=0,
            high_count=0,
            medium_count=0,
            intent_counts={},
            tier_counts={},
            source_diagnostics=[
                SourceDiagnostic(
                    source="lever:example",
                    status="error",
                    code="source_unavailable",
                    message="Source unavailable",
                )
            ],
        )


def _repository(tmp_path) -> SQLiteOpportunityRepository:
    repository = SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()
    return repository


def _profile() -> CandidateProfile:
    return CandidateProfile(
        name="Example Candidate",
        roles=["Support Analyst"],
        skills=["Python"],
    )


def test_radar_run_requires_candidate_profile(tmp_path) -> None:
    service = FakeRadarService()
    app = create_app(
        repository=_repository(tmp_path),
        profile=None,
        radar_service=service,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/radar/run")

    assert response.status_code == 503
    assert response.json() == {"detail": "Candidate profile unavailable"}
    assert service.run_calls == 0


def test_radar_run_returns_typed_batch_with_sanitized_source_diagnostic(tmp_path) -> None:
    service = FakeRadarService()
    app = create_app(
        repository=_repository(tmp_path),
        profile=_profile(),
        radar_service=service,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/radar/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 0
    assert payload["policy"]["max_items"] == 20
    assert payload["source_diagnostics"] == [
        {
            "source": "lever:example",
            "status": "error",
            "code": "source_unavailable",
            "message": "Source unavailable",
        }
    ]
    assert service.run_calls == 1


def test_radar_source_failure_maps_to_public_safe_502(tmp_path) -> None:
    error = RadarSourceError(
        "No radar candidates available",
        diagnostics=[
            SourceDiagnostic(
                source="broken",
                status="error",
                code="source_unavailable",
                message="Source unavailable",
            )
        ],
    )
    service = FakeRadarService(error=error)
    app = create_app(
        repository=_repository(tmp_path),
        profile=_profile(),
        radar_service=service,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/radar/run")

    assert response.status_code == 502
    assert response.json() == {"detail": "Radar sources unavailable"}
    assert "No radar candidates available" not in response.text


def test_existing_v01_health_route_remains_unchanged_with_radar_injected(tmp_path) -> None:
    app = create_app(
        repository=_repository(tmp_path),
        profile=_profile(),
        radar_service=FakeRadarService(),
    )

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "opportunity-os"}
