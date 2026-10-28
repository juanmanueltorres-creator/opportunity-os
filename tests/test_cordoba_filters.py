"""Regressions for Córdoba/remote-Argentina daily radar selection."""
from datetime import datetime, timezone

from app.models.domain import Opportunity
from app.radar.daily_search import classify, rank
from app.radar.cordoba_filters import (
    candidate_lane, is_cordoba_location, partition_cordoba_matches,
)

NOW = datetime(2026, 10, 26, 15, tzinfo=timezone.utc)


def offer(title="Coordinador de operaciones", location="Córdoba, Argentina",
          policy="onsite", description="Gestión de operaciones", suffix="0"):
    return Opportunity(
        id="test:" + suffix, source="remotive", source_id=suffix,
        source_url="https://example.com/jobs/" + suffix,
        company="Empresa demo " + suffix, title=title,
        description=description, location=location, remote_policy=policy,
        discovered_at=NOW, published_at=NOW,
    )


def test_local_hybrid_and_onsite_cordoba_confirmed():
    for policy in ("onsite", "hybrid", "híbrido", "presencial"):
        m = classify(offer(policy=policy))
        assert m is not None
        assert candidate_lane(m) == "CORDOBA_LOCAL"
        if policy in {"hybrid", "híbrido"}:
            assert m.remote_mode == "HYBRID"
    assert is_cordoba_location("Córdoba Capital, AR")
    assert not is_cordoba_location("Córdoba, España")


def test_buenos_aires_san_juan_and_other_cities_not_local():
    for city in ("Buenos Aires, Argentina", "San Juan, Argentina",
                 "Rosario, Argentina", "Mendoza, Argentina"):
        item = classify(offer(location=city, policy="onsite"))
        assert item is not None
        assert candidate_lane(item) == "EXCLUDED"


def test_explicit_remote_argentina_or_latam_confirmed():
    for location in ("Argentina", "Remote LATAM", "Latin America"):
        item = classify(offer(title="Desarrollador Python", location=location,
                              policy="remote"))
        assert item is not None
        assert candidate_lane(item) == "REMOTE_ARGENTINA"


def test_unknown_remote_countries_are_review_not_eligible():
    for location in ("Worldwide", "México", "Anywhere", "Remote"):
        item = classify(offer(title="Python Developer", location=location,
                              policy="remote"))
        assert item is not None
        assert candidate_lane(item) == "REVIEW"


def test_foreign_only_and_mandatory_english_excluded():
    foreign = classify(offer(title="Python Developer", location="US only",
                             policy="remote"))
    assert foreign and candidate_lane(foreign) == "EXCLUDED"
    english = classify(offer(
        title="Python Developer", location="LATAM", policy="remote",
        description="Fluent English required for daily meetings",
    ))
    assert english and candidate_lane(english) == "EXCLUDED"


def test_local_without_modality_review_only():
    unknown = classify(offer(policy="", location="Córdoba, Argentina"))
    assert unknown is not None and candidate_lane(unknown) == "REVIEW"


def test_partition_keeps_review_separate_and_score_order():
    candidate_jobs = [
        offer(title="Desarrollador Python", location="LATAM", policy="remote", suffix="1"),
        offer(title="Desarrollador Python", location="Worldwide", policy="remote", suffix="2"),
        offer(location="Buenos Aires, Argentina", policy="onsite", suffix="3"),
        offer(location="Córdoba, Argentina", policy="hybrid", suffix="4"),
    ]
    shortlisted = rank(candidate_jobs, now=NOW, limit=100)
    confirmed, review = partition_cordoba_matches(shortlisted)
    assert {item.job.source_id for item in confirmed} == {"1", "4"}
    assert {item.job.source_id for item in review} == {"2"}
    assert all(candidate_lane(item) != "EXCLUDED" for item in confirmed + review)


def test_explicit_latam_title_can_confirm_remote_but_not_restricted_country():
    accepted = classify(offer(
        title="Desarrollador Full-Stack para LATAM",
        location="Remote",
        policy="remote",
    ))
    assert accepted is not None
    assert accepted.argentina_eligible == "YES"
    assert candidate_lane(accepted) == "REMOTE_ARGENTINA"
    assert "título" in (accepted.eligibility_evidence or "")
    restricted = classify(offer(
        title="Python Developer LATAM",
        location="US only",
        policy="remote",
    ))
    assert restricted is not None
    assert restricted.argentina_eligible == "NO"
    assert candidate_lane(restricted) == "EXCLUDED"
