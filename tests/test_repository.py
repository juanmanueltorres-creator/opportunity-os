from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest

from app.models.domain import Opportunity

NOW = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)


def _repository_module():
    return import_module("app.repositories.opportunities")


def _opportunity(
    *,
    job_id: str = "job-1",
    source: str = "source-a",
    source_id: str = "1",
    company: str = "Example Co",
    title: str = "GIS Developer",
    location: str | None = "Argentina",
    discovered_at: datetime = NOW,
    published_at: datetime | None = None,
) -> Opportunity:
    return Opportunity(
        id=job_id,
        source=source,
        source_id=source_id,
        source_url=f"https://example.com/{source}/{source_id}",
        company=company,
        title=title,
        description="Build GIS software",
        discovered_at=discovered_at,
        location=location,
        published_at=published_at,
        required_skills=["python", "postgis"],
        preferred_skills=["fastapi"],
    )


def test_repository_persists_across_instances(tmp_path) -> None:
    module = _repository_module()
    db_path = tmp_path / "opportunities.db"
    first = module.SQLiteOpportunityRepository(db_path)
    first.initialize()
    stored, created = first.upsert(_opportunity())
    second = module.SQLiteOpportunityRepository(db_path)
    second.initialize()
    loaded = second.get(stored.id)
    assert created is True
    assert loaded == stored
    assert loaded.required_skills == ["python", "postgis"]


def test_duplicate_source_identity_does_not_create_second_row(tmp_path) -> None:
    module = _repository_module()
    repository = module.SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()
    first, first_created = repository.upsert(_opportunity())
    second, second_created = repository.upsert(_opportunity(title="Changed upstream title"))
    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert len(repository.list()) == 1


def test_normalized_dedupe_key_collapses_same_job_from_another_source(tmp_path) -> None:
    module = _repository_module()
    repository = module.SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()
    first, _ = repository.upsert(_opportunity())
    duplicate, created = repository.upsert(
        _opportunity(
            job_id="job-2",
            source="source-b",
            source_id="99",
            company=" example co ",
            title="gis developer",
            location="ARGENTINA",
        )
    )
    assert created is False
    assert duplicate.id == first.id
    assert len(repository.list()) == 1


def test_failed_write_does_not_damage_previously_committed_rows(tmp_path) -> None:
    module = _repository_module()
    repository = module.SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()
    stored, _ = repository.upsert(_opportunity())
    malformed = Opportunity.model_construct(
        id="broken",
        source="broken",
        source_id="broken",
        source_url="https://example.com/broken",
        company="Broken Co",
        title="Broken",
        description="Broken payload",
        discovered_at="not-a-datetime",
        status="found",
        location=None,
        remote_policy=None,
        published_at=None,
        required_skills=[],
        preferred_skills=[],
        compensation=None,
    )
    with pytest.raises((AttributeError, TypeError, ValueError)):
        repository.upsert(malformed)
    assert repository.get(stored.id) == stored
    assert len(repository.list()) == 1


def test_radar_candidate_query_is_not_truncated_by_regular_list_limit(tmp_path) -> None:
    module = _repository_module()
    repository = module.SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()

    for index in range(125):
        repository.upsert(
            _opportunity(
                job_id=f"recent-{index:03d}",
                source_id=f"recent-{index:03d}",
                title=f"Recent Role {index:03d}",
                discovered_at=NOW - timedelta(days=index % 20),
            )
        )

    assert len(repository.list()) == 100
    candidates = repository.list_radar_candidates(now=NOW, lookback_days=30)
    assert len(candidates) == 125
    assert candidates[0].discovered_at >= candidates[-1].discovered_at


def test_radar_candidate_age_prefers_published_at_then_falls_back_to_discovered_at(tmp_path) -> None:
    module = _repository_module()
    repository = module.SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    repository.initialize()

    repository.upsert(
        _opportunity(
            job_id="published-old",
            source_id="published-old",
            title="Published Old",
            discovered_at=NOW - timedelta(days=1),
            published_at=NOW - timedelta(days=31),
        )
    )
    repository.upsert(
        _opportunity(
            job_id="published-recent",
            source_id="published-recent",
            title="Published Recent",
            discovered_at=NOW - timedelta(days=90),
            published_at=NOW - timedelta(days=5),
        )
    )
    repository.upsert(
        _opportunity(
            job_id="discovered-recent",
            source_id="discovered-recent",
            title="Discovered Recent",
            discovered_at=NOW - timedelta(days=10),
        )
    )
    repository.upsert(
        _opportunity(
            job_id="discovered-old",
            source_id="discovered-old",
            title="Discovered Old",
            discovered_at=NOW - timedelta(days=40),
        )
    )

    candidates = repository.list_radar_candidates(now=NOW, lookback_days=30)
    ids = [item.id for item in candidates]

    assert ids == ["published-recent", "discovered-recent"]
