from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.domain import CandidateProfile
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.service import RadarService
from app.radar.taxonomy import AliasRegistry, TaxonomyResolver
from app.repositories.enrichments import SQLiteEnrichmentRepository
from app.repositories.opportunities import SQLiteOpportunityRepository

NOW = datetime(2026, 8, 28, 21, 45, tzinfo=timezone.utc)


def _profile() -> CandidateProfile:
    return CandidateProfile(
        name="Example Candidate",
        roles=["Support Analyst"],
        skills=["Python"],
    )


def _service(tmp_path):
    repository = SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()
    enrichments = SQLiteEnrichmentRepository(tmp_path / "opportunities.db")
    enrichments.initialize()
    aliases = tmp_path / "aliases.yaml"
    aliases.write_text("version: '1'\nentries: []\n", encoding="utf-8")
    resolver = TaxonomyResolver(alias_registry=AliasRegistry.load(aliases))
    service = RadarService(
        opportunity_repository=repository,
        enrichment_repository=enrichments,
        connectors=[],
        extractor=RuleBasedRequirementExtractor(),
        resolver=resolver,
    )
    return repository, service


def test_manual_import_persists_normalized_opportunity(tmp_path) -> None:
    repository, service = _service(tmp_path)
    app = create_app(
        repository=repository,
        profile=_profile(),
        radar_service=service,
    )

    payload = {
        "source": "community-board",
        "source_url": "https://example.com/jobs/manual-1",
        "title": "Support Analyst",
        "company": "Example Cooperative",
        "raw_description": "Must have Python.",
        "location": "Remote, Argentina",
        "remote_policy": "remote",
        "published_at": "2026-08-27T18:00:00Z",
        "application_deadline": "2026-09-05T23:59:00Z",
    }

    with TestClient(app) as client:
        response = client.post("/api/v1/opportunities/manual", json=payload)

    assert response.status_code == 200
    opportunity = response.json()
    assert opportunity["source"] == "community-board"
    assert opportunity["company"] == "Example Cooperative"
    assert opportunity["title"] == "Support Analyst"
    assert opportunity["id"].startswith("community-board:manual-")
    assert repository.get(opportunity["id"]) is not None
    assert "Application deadline: 2026-09-05" in opportunity["description"]


def test_duplicate_manual_import_returns_same_identity_without_second_row(tmp_path) -> None:
    repository, service = _service(tmp_path)
    app = create_app(
        repository=repository,
        profile=_profile(),
        radar_service=service,
    )
    payload = {
        "source": "manual",
        "source_url": "https://example.com/jobs/stable",
        "title": "Support Analyst",
        "company": "Example Co",
        "raw_description": "Must have Python.",
    }

    with TestClient(app) as client:
        first = client.post("/api/v1/opportunities/manual", json=payload)
        second = client.post("/api/v1/opportunities/manual", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert len(repository.list()) == 1


def test_manual_import_requires_radar_service(tmp_path) -> None:
    repository = SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()
    app = create_app(
        repository=repository,
        profile=_profile(),
        radar_service=None,
        enable_default_radar=False,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/opportunities/manual",
            json={
                "source": "manual",
                "source_url": "https://example.com/jobs/1",
                "title": "Role",
                "company": "Example Co",
                "raw_description": "Description",
            },
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Radar service unavailable"}
