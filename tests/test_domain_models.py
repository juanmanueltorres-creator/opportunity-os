from datetime import datetime
from importlib import import_module

import pytest
from pydantic import ValidationError


def _domain():
    return import_module("app.models.domain")


def test_profile_requires_a_name_and_skills() -> None:
    domain = _domain()

    with pytest.raises(ValidationError):
        domain.CandidateProfile(
            name="",
            roles=[],
            skills=[],
            domains=[],
            locations=[],
            remote_preferences=[],
            evidence=[],
        )


def test_evidence_is_explicitly_verified_or_not() -> None:
    domain = _domain()

    item = domain.EvidenceItem(
        label="Example",
        type="project",
        skills=["python"],
        domains=["gis"],
        verified=True,
    )

    assert item.verified is True


def test_opportunity_rejects_naive_discovered_at() -> None:
    domain = _domain()

    with pytest.raises(ValidationError):
        domain.Opportunity(
            id="job-1",
            source="example",
            source_id="1",
            source_url="https://example.com/jobs/1",
            company="Example Co",
            title="GIS Developer",
            description="Build GIS software",
            discovered_at=datetime(2026, 8, 28, 12, 0, 0),
        )
