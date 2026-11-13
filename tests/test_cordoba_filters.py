"""Regressions for Córdoba/remote-Argentina daily radar selection."""
from datetime import datetime, timezone

from app.models.domain import Opportunity
from app.radar.daily_search import classify, rank
from scripts.daily_job_radar import select_daily_candidate_pool
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


def test_confirmed_priority_remote_first_with_stable_score_order():
    # The caller can rank Córdoba onsite above remote. Geographic priority
    # must still put evidenced Argentina-remote jobs first, without altering
    # score order within either lane or promoting unknown remote eligibility.
    jobs = [
        offer(location="Córdoba, Argentina", policy="onsite", suffix="local-1"),
        offer(location="Argentina", policy="remote", suffix="remote-1"),
        offer(location="Córdoba, Argentina", policy="hybrid", suffix="local-2"),
        offer(location="Remote LATAM", policy="remote", suffix="remote-2"),
        offer(location="Worldwide", policy="remote", suffix="unknown"),
        offer(location="San Juan, Argentina", policy="onsite", suffix="relocation"),
    ]
    matches = [classify(job) for job in jobs]
    assert all(match is not None for match in matches)
    confirmed, review = partition_cordoba_matches(matches)
    assert [item.job.source_id for item in confirmed] == [
        "remote-1", "remote-2", "local-1", "local-2",
    ]
    assert [item.job.source_id for item in review] == ["unknown"]
    assert all(item.job.source_id != "relocation" for item in confirmed + review)


def test_rank_to_shortlist_preserves_remote_priority_across_score_boundary():
    """Integration boundary: daily_job_radar calls rank() then partition()."""
    jobs = [
        offer(title="Coordinador de operaciones", location="Córdoba, Argentina",
              policy="onsite", suffix="high-score-local"),
        offer(title="Desarrollador Python", location="Argentina",
              policy="remote", suffix="remote-ar"),
        offer(title="Desarrollador Python", location="Worldwide",
              policy="remote", suffix="unknown-remote"),
        offer(title="Coordinador de operaciones", location="San Juan, Argentina",
              policy="onsite", suffix="relocation"),
    ]
    ranked = rank(jobs, now=NOW, limit=100)
    confirmed, review = partition_cordoba_matches(ranked)
    assert [candidate_lane(item) for item in confirmed] == [
        "REMOTE_ARGENTINA", "CORDOBA_LOCAL",
    ]
    assert [item.job.source_id for item in review] == ["unknown-remote"]
    assert "relocation" not in {
        item.job.source_id for item in confirmed + review
    }


def test_prepartition_limit_600_can_hide_lower_scored_remote():
    """R08/P3/UC01: reproduce a truncation blind spot, without changing runtime.

    A higher-scored Córdoba-local cohort can occupy the entire initial
    rank(limit=600) pool before remote-first partitioning takes effect.
    This test records the current defect; it does NOT claim to fix it.
    """
    local_jobs = [
        offer(title="Coordinador de operaciones", location="Córdoba, Argentina",
              policy="onsite", suffix=f"local-{index:03d}")
        for index in range(600)
    ]
    remote = offer(title="Desarrollador Python", location="Argentina",
                   policy="remote", suffix="remote-beyond-limit")
    local_match = classify(local_jobs[0])
    remote_match = classify(remote)
    assert local_match is not None and remote_match is not None
    assert candidate_lane(local_match) == "CORDOBA_LOCAL"
    assert candidate_lane(remote_match) == "REMOTE_ARGENTINA"
    assert local_match.score > remote_match.score

    jobs = local_jobs + [remote]
    truncated = rank(jobs, now=NOW, limit=600)
    confirmed, _review = partition_cordoba_matches(truncated)
    assert len(truncated) == 600
    assert all(item.job.source_id != remote.source_id for item in confirmed)

    # The job is eligible and discoverable if truncation happens later.
    complete = rank(jobs, now=NOW, limit=601)
    complete_confirmed, _ = partition_cordoba_matches(complete)
    assert complete_confirmed[0].job.source_id == remote.source_id


def test_daily_candidate_pool_keeps_remote_beyond_600_local_jobs():
    """R08/P3/UC01: daily selector must not discard remote before partition."""
    local_jobs = [
        offer(title="Coordinador de operaciones", location="Córdoba, Argentina",
              policy="onsite", suffix=f"local-fix-{index:03d}")
        for index in range(600)
    ]
    remote = offer(title="Desarrollador Python", location="Argentina",
                   policy="remote", suffix="remote-after-600")
    # Exercise the same helper used by scripts/daily_job_radar.py.
    pool = select_daily_candidate_pool(local_jobs + [remote], now=NOW)
    confirmed, review = partition_cordoba_matches(pool)
    assert len(pool) == 601
    assert confirmed[0].job.source_id == remote.source_id
    assert len(confirmed[:35]) == 35
    assert not review


def test_daily_candidate_pool_does_not_promote_unknown_or_relocation():
    """R08/P3/UC05: broader pool must not bypass eligibility or relocation."""
    jobs = [
        offer(title="Desarrollador Python", location="Worldwide",
              policy="remote", suffix="review-unknown"),
        offer(title="Coordinador de operaciones", location="San Juan, Argentina",
              policy="onsite", suffix="relocation-other-province"),
        offer(title="Desarrollador Python", location="Argentina",
              policy="remote", suffix="remote-confirmed"),
    ]
    confirmed, review = partition_cordoba_matches(
        select_daily_candidate_pool(jobs, now=NOW)
    )
    assert [item.job.source_id for item in confirmed] == ["remote-confirmed"]
    assert [item.job.source_id for item in review] == ["review-unknown"]
    assert all(item.job.source_id != "relocation-other-province"
               for item in confirmed + review)


def test_synthetic_ranking_benchmark_smoke():
    """R08/P3: benchmark harness must exercise real ranking without external IO."""
    from scripts.benchmark_daily_radar_selection import run_case

    result = run_case(12, repeats=1)
    assert result["size"] == 12
    assert result["legacy_limit_600"]["pool_size"] == 12
    assert result["full_pool"]["pool_size"] == 12
    assert result["full_pool"]["remote_in_top_35"] is True
    assert result["full_pool"]["median_ms"] >= 0
    assert result["full_pool"]["peak_traced_kib_max"] >= 0
