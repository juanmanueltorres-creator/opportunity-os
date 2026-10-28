"""Regression tests for global discovery without weakening short-term eligibility."""
from datetime import datetime, timezone

from app.models.domain import Opportunity
from app.radar.daily_search import rank
from scripts.render_global_radar import render_global_radar

NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)


def job(job_id, *, location, remote_policy):
    return Opportunity(
        id=job_id,
        source="test",
        source_id=job_id,
        source_url=f"https://example.org/jobs/{job_id}",
        company="Company " + job_id,
        title="Python GIS Developer",
        description="Python and GIS developer role.",
        discovered_at=NOW,
        published_at=NOW,
        location=location,
        remote_policy=remote_policy,
    )


def test_global_atlas_preserves_foreign_companies_without_recommending_restricted_jobs():
    jobs = [
        job("us-office", location="New York, United States", remote_policy="onsite"),
        job("europe-only", location="Europe", remote_policy="remote"),
        job("latam", location="Latin America", remote_policy="remote"),
        job("cordoba", location="Córdoba, Argentina", remote_policy="onsite"),
    ]
    local_ids = {m.job.id for m in rank(jobs, now=NOW, limit=100)}
    atlas_ids = {m.job.id for m in rank(
        jobs, now=NOW, limit=100,
        include_worldwide_onsite=True, include_ineligible=True,
    )}
    assert "us-office" not in local_ids
    assert "europe-only" not in local_ids
    assert "latam" in local_ids
    assert "cordoba" in local_ids
    assert {"us-office", "europe-only", "latam", "cordoba"} <= atlas_ids


def test_html_render_has_no_private_data_or_external_scripts():
    payload = {
        "generated_at": NOW.isoformat(),
        "sources": {"remotive": "OK"},
        "atlas": [{
            "company": "Fake </script><script>alert(1)</script>",
            "title": "GIS Developer",
            "source_url": "https://example.org/job",
            "location": "LATAM",
            "track": "gis_geoscience",
            "remote_mode": "REMOTE",
            "argentina_eligible": "YES",
            "work_language": "UNKNOWN",
            "search_lane": "REMOTE_ARGENTINA",
            "score": 77,
        }],
        "persistence": {"status": "NOT_CONFIGURED"},
    }
    html = render_global_radar(payload)
    assert r"\u003c/script\u003e" in html
    assert "</script><script>alert" not in html
    assert "OPPORTUNITY_POSTGRES_WRITE_DSN" not in html
    assert "<script src=" not in html
    assert 'id="radar-data"' in html
    assert "Ver aviso y postular" in html


def test_html_does_not_embed_private_keys_or_contact_lists_from_extra_payload():
    html = render_global_radar({
        "atlas": [],
        "sources": {},
        "private_contact_email": "private-mail@example.invalid",
        "secret_key": "hidden-key-value",
    })
    assert "private-mail@example.invalid" not in html
    assert "hidden-key-value" not in html


def test_rank_still_deduplicates_global_jobs():
    first = job("first", location="Anywhere", remote_policy="remote")
    same = first.model_copy(update={"id": "second", "source": "other", "source_id": "second"})
    results = rank([first, same], now=NOW, include_ineligible=True,
                   include_worldwide_onsite=True)
    assert len(results) == 1
